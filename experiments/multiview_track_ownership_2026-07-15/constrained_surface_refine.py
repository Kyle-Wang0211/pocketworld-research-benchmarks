#!/usr/bin/env python3
"""Refine a published sparse cloud with bounded-reprojection surface priors.

This experiment never removes a frame, observation, track, or 3D point.  It
keeps camera parameters fixed and moves only the point identities present in
the production PLY.  A robust local point-to-plane term proposes the movement;
a global line search enforces an explicit bound on the original reprojection
sum of squares before any candidate is written.

The implementation is a lightweight proxy for adding the same residual to the
native Ceres bundle adjustment.  It is intentionally not a production cloud
post-filter: its output is used only to decide whether the joint objective is
worth porting into the reconstruction solve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pycolmap
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching
from scipy.spatial import cKDTree


PLY_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("r", "u1"),
        ("g", "u1"),
        ("b", "u1"),
    ]
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile_summary(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def read_ply(path: Path) -> tuple[bytes, np.ndarray, np.ndarray]:
    payload = path.read_bytes()
    marker = b"end_header\n"
    end = payload.find(marker)
    if end < 0:
        raise RuntimeError(f"{path}: missing PLY end_header")
    header = payload[: end + len(marker)]
    header_text = header.decode("ascii")
    if "format binary_little_endian 1.0" not in header_text:
        raise RuntimeError(f"{path}: expected binary little-endian PLY")
    count = next(
        int(line.split()[2])
        for line in header_text.splitlines()
        if line.startswith("element vertex ")
    )
    rows = np.frombuffer(
        payload, dtype=PLY_DTYPE, count=count, offset=len(header)
    ).copy()
    xyz = np.column_stack((rows["x"], rows["y"], rows["z"])).astype(
        np.float64
    )
    return header, rows, xyz


def published_point_order(
    reconstruction: pycolmap.Reconstruction, published_xyz: np.ndarray
) -> tuple[np.ndarray, dict[str, float | int | str]]:
    point_ids = np.asarray(list(reconstruction.points3D), dtype=np.int64)
    model_xyz = np.asarray(
        [reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    tree = cKDTree(model_xyz)
    distances, indices = tree.query(published_xyz, k=1)
    strategy = "unique_nearest"
    if len(set(map(int, indices))) != len(indices):
        # PLY coordinates are float32 while the COLMAP model retains float64.
        # Very close points can therefore choose the same nearest neighbour
        # after quantization.  Resolve only that identity ambiguity with a
        # minimum-cost one-to-one assignment; neither geometry nor membership
        # is changed by this mapping step.
        strategy = "float32_bipartite"
        match = None
        for requested_k in (8, 16, 32, 64):
            k = min(requested_k, len(model_xyz))
            candidate_distances, candidate_indices = tree.query(
                published_xyz, k=k
            )
            if k == 1:
                candidate_distances = candidate_distances[:, None]
                candidate_indices = candidate_indices[:, None]
            rows = np.repeat(np.arange(len(published_xyz)), k)
            cols = candidate_indices.reshape(-1)
            costs = candidate_distances.reshape(-1)
            valid = costs <= 1e-5
            graph = csr_matrix(
                (costs[valid] + 1e-12, (rows[valid], cols[valid])),
                shape=(len(published_xyz), len(model_xyz)),
            )
            try:
                matched_rows, matched_cols = min_weight_full_bipartite_matching(
                    graph
                )
            except ValueError:
                if k == min(64, len(model_xyz)):
                    raise RuntimeError(
                        "published PLY has no one-to-one float32 identity map"
                    )
                continue
            if len(matched_rows) == len(published_xyz):
                match = np.empty(len(published_xyz), dtype=np.int64)
                match[matched_rows] = matched_cols
                break
        if match is None:
            raise RuntimeError("published PLY identity assignment is incomplete")
        indices = match
        distances = np.linalg.norm(published_xyz - model_xyz[indices], axis=1)
    if len(distances) and float(np.max(distances)) > 1e-5:
        raise RuntimeError(
            f"published PLY mapping error {float(np.max(distances))} exceeds 1e-5"
        )
    return point_ids[indices], {
        "count": int(len(indices)),
        "mapping_error_max": float(np.max(distances)) if len(distances) else 0.0,
        "mapping_error_p90": (
            float(np.percentile(distances, 90)) if len(distances) else 0.0
        ),
        "mapping_strategy": strategy,
    }


def frame_id(image: pycolmap.Image) -> int:
    return int(Path(image.name).stem.split("_")[-1])


def umeyama_scale(source: np.ndarray, target: np.ndarray) -> float:
    source0 = source - source.mean(axis=0)
    target0 = target - target.mean(axis=0)
    covariance = target0.T @ source0 / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    diagonal = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        diagonal[-1] = -1
    variance = np.mean(np.sum(source0 * source0, axis=1))
    return float(np.sum(singular * diagonal) / variance)


def camera_projection_and_jacobian(
    camera: pycolmap.Camera,
    image: pycolmap.Image,
    xyz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if camera.model.name != "SIMPLE_PINHOLE":
        raise RuntimeError(f"unsupported camera model {camera.model.name}")
    pose = image.cam_from_world()
    rotation = np.asarray(pose.rotation.matrix(), dtype=np.float64)
    point_cam = rotation @ xyz + np.asarray(pose.translation, dtype=np.float64)
    x, y, z = map(float, point_cam)
    if z <= 1e-9:
        raise RuntimeError(f"point projects behind image {image.image_id}")
    focal, cx, cy = map(float, camera.params[:3])
    projection = np.asarray([focal * x / z + cx, focal * y / z + cy])
    jacobian_cam = np.asarray(
        [
            [focal / z, 0.0, -focal * x / (z * z)],
            [0.0, focal / z, -focal * y / (z * z)],
        ]
    )
    return projection, jacobian_cam @ rotation


def observation_map(
    reconstruction: pycolmap.Reconstruction, point_ids: np.ndarray
) -> dict[int, list[tuple[int, np.ndarray]]]:
    result: dict[int, list[tuple[int, np.ndarray]]] = defaultdict(list)
    for point_id in point_ids:
        point = reconstruction.points3D[int(point_id)]
        for element in point.track.elements:
            image = reconstruction.images[element.image_id]
            xy = np.asarray(image.points2D[element.point2D_idx].xy, dtype=np.float64)
            result[int(point_id)].append((int(element.image_id), xy))
    return result


def reprojection_errors(
    reconstruction: pycolmap.Reconstruction,
    point_ids: np.ndarray,
    xyz: np.ndarray,
    observations: dict[int, list[tuple[int, np.ndarray]]],
) -> np.ndarray:
    errors = []
    for index, point_id in enumerate(point_ids):
        for image_id, observed in observations[int(point_id)]:
            image = reconstruction.images[image_id]
            camera = reconstruction.cameras[image.camera_id]
            projected, _ = camera_projection_and_jacobian(camera, image, xyz[index])
            errors.append(float(np.linalg.norm(projected - observed)))
    return np.asarray(errors, dtype=np.float64)


def local_normals(xyz: np.ndarray, neighbors: np.ndarray) -> np.ndarray:
    normals = np.empty_like(xyz)
    for index, row in enumerate(neighbors):
        local = xyz[row]
        centered = local - local.mean(axis=0)
        covariance = centered.T @ centered / max(1, len(local))
        _, vectors = np.linalg.eigh(covariance)
        normals[index] = vectors[:, 0]
    return normals


def propose_step(
    reconstruction: pycolmap.Reconstruction,
    point_ids: np.ndarray,
    xyz: np.ndarray,
    observations: dict[int, list[tuple[int, np.ndarray]]],
    metric_scale: float,
    num_neighbors: int,
    min_shared_images: int,
    normal_sigma_deg: float,
    robust_scale_mm: float,
    smooth_weight: float,
    max_step_mm: float,
) -> tuple[np.ndarray, dict[str, float | int]]:
    query_k = min(len(xyz), num_neighbors + 1)
    distances, neighbor_rows = cKDTree(xyz).query(xyz, k=query_k)
    if query_k == 1:
        neighbor_rows = neighbor_rows[:, None]
        distances = distances[:, None]
    neighbor_rows = neighbor_rows[:, 1:]
    distances = distances[:, 1:]
    normals = local_normals(xyz, neighbor_rows)
    image_sets = {
        int(point_id): {image_id for image_id, _ in observations[int(point_id)]}
        for point_id in point_ids
    }
    point_index = {int(point_id): index for index, point_id in enumerate(point_ids)}
    del point_index

    delta_all = np.zeros_like(xyz)
    accepted_edges = 0
    skipped_shared = 0
    skipped_normal = 0
    normal_sigma = np.deg2rad(normal_sigma_deg)
    metric_to_mm = metric_scale * 1000.0

    for index, point_id in enumerate(point_ids):
        hessian = np.eye(3, dtype=np.float64) * 1e-9
        gradient = np.zeros(3, dtype=np.float64)
        for image_id, observed in observations[int(point_id)]:
            image = reconstruction.images[image_id]
            camera = reconstruction.cameras[image.camera_id]
            projected, jacobian = camera_projection_and_jacobian(
                camera, image, xyz[index]
            )
            residual = projected - observed
            hessian += jacobian.T @ jacobian
            gradient += jacobian.T @ residual

        local_radius = max(float(distances[index, -1]), 1e-9)
        for distance, neighbor in zip(
            distances[index], neighbor_rows[index], strict=True
        ):
            neighbor = int(neighbor)
            neighbor_id = int(point_ids[neighbor])
            shared = image_sets[int(point_id)] & image_sets[neighbor_id]
            if len(shared) < min_shared_images:
                skipped_shared += 1
                continue
            normal1 = normals[index]
            normal2 = normals[neighbor]
            dot = float(np.clip(abs(normal1 @ normal2), 0.0, 1.0))
            angle = float(np.arccos(dot))
            if angle > 3.0 * normal_sigma:
                skipped_normal += 1
                continue
            if normal1 @ normal2 < 0.0:
                normal2 = -normal2
            normal = normal1 + normal2
            norm = float(np.linalg.norm(normal))
            if norm <= 1e-9:
                skipped_normal += 1
                continue
            normal /= norm
            plane_distance_mm = float(normal @ (xyz[index] - xyz[neighbor])) * metric_to_mm
            spatial_weight = np.exp(-0.5 * (float(distance) / local_radius) ** 2)
            normal_weight = np.exp(-0.5 * (angle / normal_sigma) ** 2)
            robust_weight = 1.0 / np.sqrt(
                1.0 + (plane_distance_mm / robust_scale_mm) ** 2
            )
            weight = smooth_weight * spatial_weight * normal_weight * robust_weight
            row = normal * metric_to_mm
            residual = plane_distance_mm
            hessian += weight * np.outer(row, row)
            gradient += weight * row * residual
            accepted_edges += 1

        delta = -np.linalg.solve(hessian, gradient)
        step_mm = float(np.linalg.norm(delta)) * metric_to_mm
        if step_mm > max_step_mm:
            delta *= max_step_mm / step_mm
        delta_all[index] = delta

    return delta_all, {
        "directed_surface_edges": int(accepted_edges),
        "skipped_min_shared_images": int(skipped_shared),
        "skipped_normal_disagreement": int(skipped_normal),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--ply", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--output-ply", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--neighbors", type=int, default=10)
    parser.add_argument("--min-shared-images", type=int, default=1)
    parser.add_argument("--normal-sigma-deg", type=float, default=20.0)
    parser.add_argument("--robust-scale-mm", type=float, default=10.0)
    parser.add_argument("--smooth-weight", type=float, required=True)
    parser.add_argument("--max-step-mm", type=float, default=3.0)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--reprojection-relaxation", type=float, default=1.01)
    args = parser.parse_args()

    for output in (args.output_model, args.output_ply, args.stats):
        if output.exists():
            raise FileExistsError(f"refusing to overwrite {output}")
    args.output_model.mkdir(parents=True)
    args.output_ply.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)

    reconstruction = pycolmap.Reconstruction(args.model)
    header, ply_rows, published_xyz = read_ply(args.ply)
    point_ids, mapping = published_point_order(reconstruction, published_xyz)
    xyz0 = np.asarray(
        [reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    xyz = xyz0.copy()
    observations = observation_map(reconstruction, point_ids)

    ledger = {
        int(row["frameId"]): row
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    source_centers = []
    target_centers = []
    for image in reconstruction.images.values():
        source_centers.append(image.projection_center())
        target_centers.append(ledger[frame_id(image)]["arkitCameraCenterWorld"])
    metric_scale = umeyama_scale(
        np.asarray(source_centers, dtype=np.float64),
        np.asarray(target_centers, dtype=np.float64),
    )

    baseline_errors = reprojection_errors(
        reconstruction, point_ids, xyz0, observations
    )
    baseline_sse = float(np.sum(baseline_errors**2))
    iteration_rows = []
    for iteration in range(args.iterations):
        delta, step_stats = propose_step(
            reconstruction,
            point_ids,
            xyz,
            observations,
            metric_scale,
            args.neighbors,
            args.min_shared_images,
            args.normal_sigma_deg,
            args.robust_scale_mm,
            args.smooth_weight,
            args.max_step_mm,
        )
        alpha = 1.0
        accepted_xyz = xyz
        accepted_errors = reprojection_errors(
            reconstruction, point_ids, xyz, observations
        )
        while alpha >= 1.0 / 1024.0:
            candidate_xyz = xyz + alpha * delta
            candidate_errors = reprojection_errors(
                reconstruction, point_ids, candidate_xyz, observations
            )
            if float(np.sum(candidate_errors**2)) <= (
                args.reprojection_relaxation * baseline_sse
            ):
                accepted_xyz = candidate_xyz
                accepted_errors = candidate_errors
                break
            alpha *= 0.5
        xyz = accepted_xyz
        iteration_rows.append(
            {
                "iteration": iteration + 1,
                "line_search_alpha": alpha,
                "reprojection_sse_ratio": float(
                    np.sum(accepted_errors**2) / baseline_sse
                ),
                **step_stats,
            }
        )

    for point_id, position in zip(point_ids, xyz, strict=True):
        reconstruction.points3D[int(point_id)].xyz = position
    reconstruction.write(str(args.output_model))

    ply_rows["x"] = xyz[:, 0].astype(np.float32)
    ply_rows["y"] = xyz[:, 1].astype(np.float32)
    ply_rows["z"] = xyz[:, 2].astype(np.float32)
    args.output_ply.write_bytes(header + ply_rows.tobytes())

    final_errors = reprojection_errors(reconstruction, point_ids, xyz, observations)
    displacement_mm = np.linalg.norm(xyz - xyz0, axis=1) * metric_scale * 1000.0
    payload = {
        "schema": "pocketworld_bounded_reprojection_surface_refine_v1",
        "diagnostic_only": True,
        "identity_policy": "no frame observation track or point is removed",
        "model": str(args.model),
        "ply": str(args.ply),
        "output_model": str(args.output_model),
        "output_ply": str(args.output_ply),
        "model_points_before": len(pycolmap.Reconstruction(args.model).points3D),
        "model_points_after": len(reconstruction.points3D),
        "registered_frames": len(reconstruction.images),
        "published_mapping": mapping,
        "metric_scale": metric_scale,
        "config": {
            "neighbors": args.neighbors,
            "min_shared_images": args.min_shared_images,
            "normal_sigma_deg": args.normal_sigma_deg,
            "robust_scale_mm": args.robust_scale_mm,
            "smooth_weight": args.smooth_weight,
            "max_step_mm": args.max_step_mm,
            "iterations": args.iterations,
            "reprojection_relaxation": args.reprojection_relaxation,
        },
        "reprojection_px_before": percentile_summary(baseline_errors),
        "reprojection_px_after": percentile_summary(final_errors),
        "reprojection_sse_ratio": float(
            np.sum(final_errors**2) / max(baseline_sse, 1e-30)
        ),
        "displacement_mm": percentile_summary(displacement_mm),
        "iterations": iteration_rows,
        "input_hashes": {
            "cameras_bin": sha256(args.model / "cameras.bin"),
            "images_bin": sha256(args.model / "images.bin"),
            "points3D_bin": sha256(args.model / "points3D.bin"),
            "ply": sha256(args.ply),
            "ledger": sha256(args.ledger),
        },
        "output_hashes": {
            "cameras_bin": sha256(args.output_model / "cameras.bin"),
            "images_bin": sha256(args.output_model / "images.bin"),
            "points3D_bin": sha256(args.output_model / "points3D.bin"),
            "ply": sha256(args.output_ply),
        },
    }
    args.stats.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
