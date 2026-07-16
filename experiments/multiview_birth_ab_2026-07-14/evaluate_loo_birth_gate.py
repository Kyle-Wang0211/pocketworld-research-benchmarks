#!/usr/bin/env python3
"""Evaluate a non-destructive multi-view point birth certificate.

Two-view landmarks remain in the SfM reconstruction as optimizer hypotheses.
This evaluator asks a stricter product question: can every view of a track be
predicted from the other views?  A point is eligible for a public point slot
only after track length, parallax, reprojection, and leave-one-view-out (LOO)
triangulation agree.  No point is deleted from the reconstruction.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def load_arkit_centers(path: Path) -> dict[int, np.ndarray]:
    centers: dict[int, np.ndarray] = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            centers[int(row["frameId"])] = np.asarray(
                row["arkitCameraCenterWorld"], dtype=np.float64
            )
    return centers


def umeyama(source: np.ndarray, target: np.ndarray):
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_zero = source - source_mean
    target_zero = target - target_mean
    covariance = target_zero.T @ source_zero / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    diagonal = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        diagonal[-1] = -1
    rotation = u @ np.diag(diagonal) @ vt
    variance = np.mean(np.sum(source_zero * source_zero, axis=1))
    scale = float(np.sum(singular * diagonal) / variance)
    translation = target_mean - scale * (rotation @ source_mean)
    return scale, rotation, translation


def frame_id_for_image(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match:
        return int(match.group(1))
    return int(image.image_id) - 1


def align_to_arkit(reconstruction: pycolmap.Reconstruction, ledger: Path):
    arkit = load_arkit_centers(ledger)
    source = []
    target = []
    for image in reconstruction.images.values():
        if not image.has_pose:
            continue
        frame_id = frame_id_for_image(image)
        if frame_id not in arkit:
            continue
        source.append(np.asarray(image.cam_from_world().tgt_origin_in_src()))
        target.append(arkit[frame_id])
    if len(source) < 3:
        raise RuntimeError("fewer than three camera centers overlap the ledger")
    source_array = np.asarray(source)
    target_array = np.asarray(target)
    scale, rotation, translation = umeyama(source_array, target_array)
    aligned = scale * (rotation @ source_array.T).T + translation
    camera_error = np.linalg.norm(aligned - target_array, axis=1)
    return scale, rotation, translation, camera_error


def triangulate_dlt(projections: list[np.ndarray], rays: list[np.ndarray]):
    rows = []
    for projection, ray in zip(projections, rays, strict=True):
        rows.append(ray[0] * projection[2] - projection[0])
        rows.append(ray[1] * projection[2] - projection[1])
    _, _, vt = np.linalg.svd(np.asarray(rows), full_matrices=False)
    homogeneous = vt[-1]
    if abs(homogeneous[3]) < 1e-12:
        return None
    point = homogeneous[:3] / homogeneous[3]
    return point if np.all(np.isfinite(point)) else None


def verified_match_edges(database_path: Path) -> set[tuple[int, int, int, int]]:
    database = pycolmap.Database.open(str(database_path))
    pair_ids, geometries = database.read_two_view_geometries()
    edges: set[tuple[int, int, int, int]] = set()
    for pair_id, geometry in zip(pair_ids, geometries, strict=True):
        image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
        for index1, index2 in np.asarray(geometry.inlier_matches):
            edges.add((int(image1), int(index1), int(image2), int(index2)))
    return edges


def point_certificate(
    reconstruction: pycolmap.Reconstruction,
    point,
    verified_edges: set[tuple[int, int, int, int]],
):
    observations = []
    observed_cells = []
    observation_ids = []
    for element in point.track.elements:
        image = reconstruction.images[element.image_id]
        if not image.has_pose or element.point2D_idx >= len(image.points2D):
            continue
        camera = reconstruction.cameras[image.camera_id]
        pixel = np.asarray(image.points2D[element.point2D_idx].xy)
        ray = camera.cam_from_img(pixel)
        if ray is None:
            continue
        pose = image.cam_from_world()
        observations.append(
            (
                np.asarray(pose.matrix()),
                np.asarray(ray),
                pixel,
                camera,
                np.asarray(pose.tgt_origin_in_src()),
                frame_id_for_image(image),
            )
        )
        observed_cells.append(
            (
                frame_id_for_image(image),
                min(31, max(0, int(pixel[0] * 32 / max(1, camera.width)))),
                min(17, max(0, int(pixel[1] * 18 / max(1, camera.height)))),
            )
        )
        observation_ids.append((int(image.image_id), int(element.point2D_idx)))

    count = len(observations)
    if count < 2:
        return None
    xyz = np.asarray(point.xyz)
    reprojection = []
    for projection, _, pixel, camera, _, _ in observations:
        point_cam = projection @ np.r_[xyz, 1.0]
        if point_cam[2] <= 0:
            return None
        projected = camera.img_from_cam(point_cam)
        if projected is None:
            return None
        reprojection.append(float(np.linalg.norm(np.asarray(projected) - pixel)))

    max_angle = 0.0
    for index, first in enumerate(observations):
        first_ray = xyz - first[4]
        first_ray /= np.linalg.norm(first_ray)
        for second in observations[index + 1 :]:
            second_ray = xyz - second[4]
            second_ray /= np.linalg.norm(second_ray)
            cosine = float(np.clip(first_ray @ second_ray, -1.0, 1.0))
            max_angle = max(max_angle, float(np.degrees(np.arccos(cosine))))

    loo_error = []
    loo_relative_shift = []
    if count >= 3:
        reference_depth = float(
            np.median([np.linalg.norm(xyz - observation[4]) for observation in observations])
        )
        for held_out in range(count):
            kept = [obs for index, obs in enumerate(observations) if index != held_out]
            estimate = triangulate_dlt(
                [obs[0] for obs in kept], [obs[1] for obs in kept]
            )
            if estimate is None:
                loo_error.append(float("inf"))
                loo_relative_shift.append(float("inf"))
                continue
            projection, _, pixel, camera, _, _ = observations[held_out]
            point_cam = projection @ np.r_[estimate, 1.0]
            projected = camera.img_from_cam(point_cam) if point_cam[2] > 0 else None
            if projected is None:
                loo_error.append(float("inf"))
            else:
                loo_error.append(
                    float(np.linalg.norm(np.asarray(projected) - pixel))
                )
            loo_relative_shift.append(
                float(np.linalg.norm(estimate - xyz) / max(reference_depth, 1e-12))
            )

    frame_ids = [observation[5] for observation in observations]
    direct_edges: set[tuple[int, int]] = set()
    degrees = [0] * count
    for first in range(count):
        image1, index1 = observation_ids[first]
        for second in range(first + 1, count):
            image2, index2 = observation_ids[second]
            if image1 < image2:
                key = (image1, index1, image2, index2)
            else:
                key = (image2, index2, image1, index1)
            if key in verified_edges:
                direct_edges.add((first, second))
                degrees[first] += 1
                degrees[second] += 1
    has_direct_triangle = any(
        (first, second) in direct_edges
        and (first, third) in direct_edges
        and (second, third) in direct_edges
        for first in range(count)
        for second in range(first + 1, count)
        for third in range(second + 1, count)
    )
    return {
        "track_length": count,
        "mean_reprojection_px": float(np.mean(reprojection)),
        "max_reprojection_px": float(np.max(reprojection)),
        "max_angle_deg": max_angle,
        "frame_span": max(frame_ids) - min(frame_ids),
        "loo_max_error_px": float(np.max(loo_error)) if loo_error else float("inf"),
        "loo_median_error_px": (
            float(np.median(loo_error)) if loo_error else float("inf")
        ),
        "loo_max_relative_shift": (
            float(np.max(loo_relative_shift))
            if loo_relative_shift
            else float("inf")
        ),
        "direct_edge_count": len(direct_edges),
        "min_direct_degree": min(degrees),
        "has_direct_triangle": has_direct_triangle,
        "_observed_cells": observed_cells,
    }


def floor_score(points: np.ndarray) -> dict:
    y = points[:, 1]
    low, high = np.percentile(y, [2, 15])
    band = points[(y >= low) & (y <= high)]
    design = np.column_stack((band[:, 0], band[:, 2], np.ones(len(band))))
    coefficients, *_ = np.linalg.lstsq(design, band[:, 1], rcond=None)
    residual = band[:, 1] - design @ coefficients
    return {
        "points": int(len(points)),
        "floor_band_points": int(len(band)),
        "floor_thickness_16_84_mm": float(
            (np.percentile(residual, 84) - np.percentile(residual, 16)) * 1000
        ),
        "floor_ghost_below_minus15mm": int(np.sum(residual < -0.015)),
    }


def local_surface_score(points: np.ndarray) -> dict:
    keys = np.floor(points / 0.010).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    counts = np.bincount(inverse)
    centroids = np.column_stack(
        [np.bincount(inverse, weights=points[:, axis]) / counts for axis in range(3)]
    )
    tree = cKDTree(centroids)
    normal_rms = []
    for neighbors in tree.query_ball_point(centroids, r=0.080):
        if len(neighbors) < 12:
            continue
        patch = centroids[neighbors]
        centered = patch - patch.mean(axis=0)
        eigenvalues = np.linalg.eigvalsh(centered.T @ centered / len(patch))
        if eigenvalues[2] <= 0 or eigenvalues[1] / eigenvalues[2] < 0.20:
            continue
        normal_rms.append(np.sqrt(max(0.0, eigenvalues[0])) * 1000)
    values = np.asarray(normal_rms)
    return {
        "voxel_centroids": int(len(centroids)),
        "planar_neighborhoods": int(len(values)),
        "normal_scatter_median_mm": float(np.median(values)),
        "normal_scatter_p90_mm": float(np.percentile(values, 90)),
    }


def image_coverage_score(
    point_cells: list[list[tuple[int, int, int]]], mask: np.ndarray, frame_ids: list[int]
) -> dict:
    occupied = {frame_id: set() for frame_id in frame_ids}
    for selected, cells in zip(mask, point_cells, strict=True):
        if not selected:
            continue
        for frame_id, x, y in cells:
            if frame_id in occupied:
                occupied[frame_id].add((x, y))
    counts = np.asarray([len(occupied[frame_id]) for frame_id in frame_ids])
    return {
        "grid": "32x18",
        "occupied_cells_median": float(np.median(counts)),
        "occupied_cells_p10": float(np.percentile(counts, 10)),
        "occupied_cells_min": int(np.min(counts)),
        "occupied_pct_median": float(100.0 * np.median(counts) / (32 * 18)),
    }


def adaptive_coverage_birth_mask(
    strict_mask: np.ndarray,
    reserve_mask: np.ndarray,
    point_cells: list[list[tuple[int, int, int]]],
    fields: dict[str, np.ndarray],
    target_cells_per_frame: int,
) -> tuple[np.ndarray, dict]:
    """Issue reserve births only while an observed frame is under-covered.

    This models a birth allocator, not a point-cloud cleanup pass: strict LOO
    certificates receive public identities first.  A looser LOO reserve may
    receive an identity only when it fills a previously empty 32x18 cell in a
    frame that has not reached the requested coverage floor.  Candidates are
    processed deterministically from strongest to weakest multi-view evidence.
    """

    selected = strict_mask.copy()
    occupied: dict[int, set[tuple[int, int]]] = {}
    for point_index in np.flatnonzero(selected):
        for frame_id, x, y in point_cells[point_index]:
            occupied.setdefault(frame_id, set()).add((x, y))

    candidates = np.flatnonzero(reserve_mask & ~strict_mask)
    ranked = sorted(
        (int(index) for index in candidates),
        key=lambda index: (
            not bool(fields["has_direct_triangle"][index]),
            float(fields["loo_max_error_px"][index]),
            float(fields["loo_max_relative_shift"][index]),
            float(fields["max_reprojection_px"][index]),
            -int(fields["direct_edge_count"][index]),
            -int(fields["track_length"][index]),
            -float(fields["max_angle_deg"][index]),
            index,
        ),
    )

    promoted = 0
    promoted_with_triangle = 0
    for point_index in ranked:
        cells = set(point_cells[point_index])
        fills_undercovered_frame = any(
            len(occupied.get(frame_id, set())) < target_cells_per_frame
            and (x, y) not in occupied.get(frame_id, set())
            for frame_id, x, y in cells
        )
        if not fills_undercovered_frame:
            continue
        selected[point_index] = True
        promoted += 1
        promoted_with_triangle += int(fields["has_direct_triangle"][point_index])
        for frame_id, x, y in cells:
            occupied.setdefault(frame_id, set()).add((x, y))

    return selected, {
        "strict_births": int(strict_mask.sum()),
        "reserve_candidates": int((reserve_mask & ~strict_mask).sum()),
        "promoted_births": promoted,
        "promoted_with_direct_triangle": promoted_with_triangle,
        "target_cells_per_frame": target_cells_per_frame,
    }


def persistent_near_ray_conflicts(
    reconstruction: pycolmap.Reconstruction,
    point_index_by_id: dict[int, int],
    candidate_mask: np.ndarray,
    metric_scale: float,
    radius_px: float,
    min_gap_m: float = 0.012,
    max_gap_m: float = 0.100,
    min_images: int = 2,
) -> list[tuple[int, int]]:
    """Find candidate births that repeatedly claim nearly the same sightline."""

    pair_images: dict[tuple[int, int], set[int]] = collections.defaultdict(set)
    for image in reconstruction.images.values():
        cam_from_world = image.cam_from_world()
        rows = []
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point_id = int(point2d.point3D_id)
            point_index = point_index_by_id.get(point_id)
            if point_index is None or not candidate_mask[point_index]:
                continue
            depth = float((cam_from_world * reconstruction.points3D[point_id].xyz)[2])
            if depth <= 0.0:
                continue
            rows.append((np.asarray(point2d.xy), point_index, depth))
        if len(rows) < 2:
            continue
        xy = np.asarray([row[0] for row in rows], dtype=np.float64)
        for first, second in cKDTree(xy).query_pairs(radius_px, output_type="set"):
            point1 = rows[first][1]
            point2 = rows[second][1]
            if point1 == point2:
                continue
            gap_m = abs(rows[first][2] - rows[second][2]) * metric_scale
            if gap_m < min_gap_m or gap_m > max_gap_m:
                continue
            pair = (min(point1, point2), max(point1, point2))
            pair_images[pair].add(int(image.image_id))
    return sorted(pair for pair, images in pair_images.items() if len(images) >= min_images)


def exclusive_ray_owner_birth_mask(
    candidate_mask: np.ndarray,
    fields: dict[str, np.ndarray],
    conflict_edges: list[tuple[int, int]],
) -> tuple[np.ndarray, dict]:
    """Grant one public identity per persistent near-ray competition graph.

    All candidates remain internal SfM hypotheses.  Public identities are
    issued once, in descending certificate quality; a losing hypothesis never
    becomes public, so this does not rely on deleting an already-created layer.
    """

    neighbors: dict[int, set[int]] = collections.defaultdict(set)
    for first, second in conflict_edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    ranked = sorted(
        (int(index) for index in np.flatnonzero(candidate_mask)),
        key=lambda index: (
            not bool(fields["has_direct_triangle"][index]),
            float(fields["loo_max_error_px"][index]),
            float(fields["loo_max_relative_shift"][index]),
            float(fields["max_reprojection_px"][index]),
            -int(fields["direct_edge_count"][index]),
            -int(fields["track_length"][index]),
            -float(fields["max_angle_deg"][index]),
            index,
        ),
    )
    selected = np.zeros_like(candidate_mask)
    blocked: set[int] = set()
    for point_index in ranked:
        if point_index in blocked:
            continue
        selected[point_index] = True
        blocked.update(neighbors.get(point_index, ()))
    return selected, {
        "candidate_births": int(candidate_mask.sum()),
        "persistent_competition_edges": len(conflict_edges),
        "withheld_competing_births": int(candidate_mask.sum() - selected.sum()),
    }


def score(model: Path, ledger: Path, database: Path) -> dict:
    reconstruction = pycolmap.Reconstruction(str(model))
    verified_edges = verified_match_edges(database)
    scale, rotation, translation, camera_error = align_to_arkit(
        reconstruction, ledger
    )
    points = []
    point_ids = []
    certificates = []
    point_cells = []
    for point_id, point in reconstruction.points3D.items():
        certificate = point_certificate(reconstruction, point, verified_edges)
        if certificate is None:
            continue
        points.append(np.asarray(point.xyz))
        point_ids.append(int(point_id))
        point_cells.append(certificate.pop("_observed_cells"))
        certificates.append(certificate)
    points_array = np.asarray(points)
    metric_points = scale * (rotation @ points_array.T).T + translation

    fields = {
        key: np.asarray([certificate[key] for certificate in certificates])
        for key in certificates[0]
    }
    base = (
        (fields["track_length"] >= 3)
        & (fields["mean_reprojection_px"] <= 2.0)
        & (fields["max_angle_deg"] >= 5.0)
    )
    gates = {
        "current_birth_gate": base,
        "current_plus_max_reproj_3": base & (fields["max_reprojection_px"] <= 3.0),
    }
    # Byte-for-byte criterion used by IsPointPublishable in the current C++
    # source.  It intentionally has no relative-position-shift gate.
    publish_cpp_exact = (
        base
        & (fields["max_reprojection_px"] <= 3.0)
        & (fields["loo_max_error_px"] <= 4.0)
    )
    gates["publish_cpp_exact"] = publish_cpp_exact
    for loo_px in (2.0, 3.0, 4.0, 6.0):
        for relative_shift in (0.02, 0.05, 0.10):
            gates[f"loo_{loo_px:g}px_shift_{relative_shift:g}"] = (
                base
                & (fields["max_reprojection_px"] <= 3.0)
                & (fields["loo_max_error_px"] <= loo_px)
                & (fields["loo_max_relative_shift"] <= relative_shift)
            )
    for loo_px in (4.0, 6.0):
        gates[f"loo_{loo_px:g}px_direct_triangle"] = (
            base
            & (fields["max_reprojection_px"] <= 3.0)
            & (fields["loo_max_error_px"] <= loo_px)
            & fields["has_direct_triangle"]
        )

    strict_birth = (
        base
        & (fields["max_reprojection_px"] <= 3.0)
        & (fields["loo_max_error_px"] <= 4.0)
        & (fields["loo_max_relative_shift"] <= 0.02)
    )
    reserve_birth = (
        base
        & (fields["max_reprojection_px"] <= 3.0)
        & (fields["loo_max_error_px"] <= 6.0)
        & (fields["loo_max_relative_shift"] <= 0.02)
    )
    adaptive_details = {}
    for target_cells in (8, 12, 16, 24):
        name = f"adaptive_loo4_plus_loo6_to_{target_cells}_cells"
        gates[name], adaptive_details[name] = adaptive_coverage_birth_mask(
            strict_birth,
            reserve_birth,
            point_cells,
            fields,
            target_cells,
        )

    point_index_by_id = {
        point_id: point_index for point_index, point_id in enumerate(point_ids)
    }
    ownership_details = {}
    for min_images in (2, 3):
        for radius_px in (2.0, 4.0, 6.0, 8.0):
            name = f"loo4_ray_owner_{radius_px:g}px_{min_images}views"
            conflicts = persistent_near_ray_conflicts(
                reconstruction,
                point_index_by_id,
                strict_birth,
                scale,
                radius_px,
                min_images=min_images,
            )
            gates[name], ownership_details[name] = exclusive_ray_owner_birth_mask(
                strict_birth,
                fields,
                conflicts,
            )
            ownership_details[name].update(
                {
                    "radius_px": radius_px,
                    "min_images": min_images,
                    "metric_depth_gap_mm": [12.0, 100.0],
                }
            )
            exact_name = (
                f"publish_cpp_ray_owner_{radius_px:g}px_{min_images}views"
            )
            exact_conflicts = persistent_near_ray_conflicts(
                reconstruction,
                point_index_by_id,
                publish_cpp_exact,
                scale,
                radius_px,
                min_images=min_images,
            )
            gates[exact_name], ownership_details[exact_name] = (
                exclusive_ray_owner_birth_mask(
                    publish_cpp_exact,
                    fields,
                    exact_conflicts,
                )
            )
            ownership_details[exact_name].update(
                {
                    "radius_px": radius_px,
                    "min_images": min_images,
                    "metric_depth_gap_mm": [12.0, 100.0],
                    "candidate_gate": "publish_cpp_exact",
                }
            )

    result = {
        "model": str(model),
        "registered": int(len(camera_error)),
        "internal_points": int(len(points_array)),
        "camera_center_median_mm": float(np.median(camera_error) * 1000),
        "camera_center_p90_mm": float(np.percentile(camera_error, 90) * 1000),
        "gates": {},
    }
    frame_ids = sorted(
        frame_id_for_image(image)
        for image in reconstruction.images.values()
        if image.has_pose
    )
    for name, mask in gates.items():
        if int(mask.sum()) < 100:
            continue
        selected = metric_points[mask]
        result["gates"][name] = {
            **floor_score(selected),
            "retained_pct_of_current": float(100.0 * mask.sum() / base.sum()),
            "local_surface": local_surface_score(selected),
            "image_coverage": image_coverage_score(point_cells, mask, frame_ids),
            **({"birth_allocator": adaptive_details[name]} if name in adaptive_details else {}),
            **({"ray_ownership": ownership_details[name]} if name in ownership_details else {}),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, action="append", required=True)
    parser.add_argument("--ledger", type=Path, action="append", required=True)
    parser.add_argument("--database", type=Path, action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (
        len(args.model)
        == len(args.ledger)
        == len(args.database)
        == len(args.label)
    ):
        parser.error("--model, --ledger, --database, and --label counts must match")
    payload = {
        "schema": "pocketworld_loo_birth_gate_v1",
        "runs": {
            label: score(model, ledger, database)
            for label, model, ledger, database in zip(
                args.label, args.model, args.ledger, args.database, strict=True
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
