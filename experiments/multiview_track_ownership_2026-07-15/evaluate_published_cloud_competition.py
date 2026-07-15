#!/usr/bin/env python3
"""Score near-ray conflicts on the exact C++-published PLY point set.

The binary PLY contains float32 copies of points selected by the production
birth certificate.  We map those coordinates back to immutable COLMAP point
identities, then evaluate only observations belonging to that exact set.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pycolmap
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching
from scipy.spatial import cKDTree


def read_binary_xyz(path: Path) -> np.ndarray:
    payload = path.read_bytes()
    marker = b"end_header\n"
    end = payload.find(marker)
    if end < 0:
        raise RuntimeError(f"{path}: missing PLY end_header")
    header = payload[: end + len(marker)].decode("ascii")
    lines = header.splitlines()
    if "format binary_little_endian 1.0" not in lines:
        raise RuntimeError(f"{path}: expected binary little-endian PLY")
    count = next(
        int(line.split()[2]) for line in lines if line.startswith("element vertex ")
    )
    dtype = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("r", "u1"),
            ("g", "u1"),
            ("b", "u1"),
        ]
    )
    rows = np.frombuffer(payload, dtype=dtype, count=count, offset=end + len(marker))
    return np.column_stack((rows["x"], rows["y"], rows["z"])).astype(np.float64)


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


def frame_id(image: pycolmap.Image) -> int:
    return int(Path(image.name).stem.split("_")[-1])


def map_published_ids(reconstruction: pycolmap.Reconstruction, ply: Path):
    point_ids = np.asarray(list(reconstruction.points3D), dtype=np.int64)
    xyz = np.asarray(
        [reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    published_xyz = read_binary_xyz(ply)
    tree = cKDTree(xyz)
    distances, indices = tree.query(published_xyz, k=1)
    strategy = "unique_nearest"
    if len(set(map(int, indices))) != len(indices):
        # The PLY stores float32 coordinates while the model stores float64.
        # In a large reconstruction, two very close model points can therefore
        # choose the same nearest neighbour after quantization even though a
        # one-to-one identity assignment exists.  Resolve only that identity
        # ambiguity with a minimum-cost bipartite assignment.  This does not
        # alter either cloud or participate in any quality decision.
        strategy = "float32_bipartite"
        match = None
        for k in (8, 16, 32, 64):
            k = min(k, len(xyz))
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
                shape=(len(published_xyz), len(xyz)),
            )
            try:
                matched_rows, matched_cols = min_weight_full_bipartite_matching(
                    graph
                )
            except ValueError:
                if k == min(64, len(xyz)):
                    raise RuntimeError(
                        f"{ply}: no one-to-one float32 identity assignment"
                    )
                continue
            if len(matched_rows) == len(published_xyz):
                match = np.empty(len(published_xyz), dtype=np.int64)
                match[matched_rows] = matched_cols
                break
        if match is None:
            raise RuntimeError(f"{ply}: incomplete one-to-one identity assignment")
        indices = match
        distances = np.linalg.norm(published_xyz - xyz[indices], axis=1)
    if len(distances) and float(np.max(distances)) > 1e-5:
        raise RuntimeError(
            f"{ply}: coordinate-to-model mapping max error {float(np.max(distances))}"
        )
    return {int(point_ids[index]) for index in indices}, {
        "published_ply_points": int(len(published_xyz)),
        "mapped_unique_point_ids": int(len(indices)),
        "mapping_error_max": float(np.max(distances)) if len(distances) else 0.0,
        "mapping_error_p90": float(np.percentile(distances, 90)) if len(distances) else 0.0,
        "mapping_strategy": strategy,
    }


def estimate_local_normals(
    reconstruction: pycolmap.Reconstruction,
    published_ids: set[int],
    num_neighbors: int = 10,
) -> dict[int, np.ndarray]:
    """Estimate unoriented PCA normals on the exact published point set."""
    point_ids = np.asarray(sorted(published_ids), dtype=np.int64)
    xyz = np.asarray(
        [reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    query_k = min(len(xyz), num_neighbors + 1)
    _, neighbor_rows = cKDTree(xyz).query(xyz, k=query_k)
    if query_k == 1:
        neighbor_rows = neighbor_rows[:, None]
    normals = {}
    for index, point_id in enumerate(point_ids):
        rows = np.atleast_1d(neighbor_rows[index])[1:]
        if len(rows) < 3:
            normals[int(point_id)] = np.asarray([0.0, 0.0, 1.0])
            continue
        local = xyz[rows]
        centered = local - local.mean(axis=0)
        covariance = centered.T @ centered / len(local)
        _, vectors = np.linalg.eigh(covariance)
        normals[int(point_id)] = vectors[:, 0]
    return normals


def normal_layer_geometry(
    reconstruction: pycolmap.Reconstruction,
    point1: int,
    point2: int,
    normals: dict[int, np.ndarray],
    metric_scale: float,
) -> dict[str, float]:
    """Separate a nearby pair into surface-normal and tangent displacement."""
    normal1 = normals[point1].copy()
    normal2 = normals[point2].copy()
    dot = float(np.clip(abs(normal1 @ normal2), 0.0, 1.0))
    if normal1 @ normal2 < 0.0:
        normal2 = -normal2
    normal = normal1 + normal2
    normal /= max(float(np.linalg.norm(normal)), 1e-12)
    delta = (
        np.asarray(reconstruction.points3D[point1].xyz)
        - np.asarray(reconstruction.points3D[point2].xyz)
    ) * metric_scale * 1000.0
    normal_separation = abs(float(normal @ delta))
    total = float(np.linalg.norm(delta))
    tangent = float(np.sqrt(max(0.0, total * total - normal_separation**2)))
    return {
        "normal_angle_deg": float(np.degrees(np.arccos(dot))),
        "normal_separation_mm": normal_separation,
        "tangent_separation_mm": tangent,
        "point_distance_mm": total,
    }


def distribution(values: list[float]) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=np.float64)
    if len(array) == 0:
        return {"count": 0, "median": None, "p90": None, "p95": None, "max": None}
    return {
        "count": int(len(array)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def local_surface_quality(
    reconstruction: pycolmap.Reconstruction,
    published_ids: set[int],
    metric_scale: float,
    num_neighbors: int = 10,
) -> dict:
    """Measure point-to-neighbour-plane roughness without removing edge points."""
    point_ids = np.asarray(sorted(published_ids), dtype=np.int64)
    xyz = np.asarray(
        [reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    query_k = min(len(xyz), num_neighbors + 1)
    _, neighbor_rows = cKDTree(xyz).query(xyz, k=query_k)
    if query_k == 1:
        neighbor_rows = neighbor_rows[:, None]
    residual_mm = []
    planar_residual_mm = []
    curvature_ratio = []
    for index in range(len(xyz)):
        rows = np.atleast_1d(neighbor_rows[index])[1:]
        if len(rows) < 3:
            continue
        local = xyz[rows]
        center = local.mean(axis=0)
        centered = local - center
        values, vectors = np.linalg.eigh(centered.T @ centered / len(local))
        ratio = float(values[0] / max(float(np.sum(values)), 1e-30))
        residual = (
            abs(float(vectors[:, 0] @ (xyz[index] - center)))
            * metric_scale
            * 1000.0
        )
        curvature_ratio.append(ratio)
        residual_mm.append(residual)
        if ratio <= 0.05:
            planar_residual_mm.append(residual)
    return {
        "neighbors": num_neighbors,
        "point_to_neighbor_plane_mm": distribution(residual_mm),
        "planar_neighborhood_point_to_plane_mm": distribution(planar_residual_mm),
        "neighborhood_curvature_ratio": distribution(curvature_ratio),
        "planar_neighborhood_threshold": 0.05,
    }


def score(model: Path, ply: Path, ledger: list[dict]) -> dict:
    reconstruction = pycolmap.Reconstruction(model)
    published_ids, mapping = map_published_ids(reconstruction, ply)
    source = []
    target = []
    for image in reconstruction.images.values():
        source.append(image.projection_center())
        target.append(ledger[frame_id(image)]["arkitCameraCenterWorld"])
    scale, rotation, translation = umeyama(
        np.asarray(source, dtype=np.float64), np.asarray(target, dtype=np.float64)
    )
    local_normals = estimate_local_normals(reconstruction, published_ids)
    surface_quality = local_surface_quality(
        reconstruction, published_ids, scale
    )

    metric_points = np.asarray(
        [
            scale * (rotation @ reconstruction.points3D[point_id].xyz) + translation
            for point_id in published_ids
        ]
    )
    y = metric_points[:, 1]
    low, high = np.percentile(y, [2, 15])
    floor = metric_points[(y >= low) & (y <= high)]
    design = np.column_stack((floor[:, 0], floor[:, 2], np.ones(len(floor))))
    coefficients, *_ = np.linalg.lstsq(design, floor[:, 1], rcond=None)
    residual = floor[:, 1] - design @ coefficients

    coverage = defaultdict(set)
    for image in reconstruction.images.values():
        camera = reconstruction.cameras[image.camera_id]
        index = frame_id(image)
        for point2d in image.points2D:
            if not point2d.has_point3D() or int(point2d.point3D_id) not in published_ids:
                continue
            x = min(31, max(0, int(float(point2d.xy[0]) * 32 / camera.width)))
            y_cell = min(17, max(0, int(float(point2d.xy[1]) * 18 / camera.height)))
            coverage[index].add((x, y_cell))
    coverage_counts = np.asarray([len(coverage[index]) for index in sorted(coverage)])

    conflicts = {}
    normal_layer_conflicts = {}
    for radius_px in (2.0, 4.0, 6.0, 8.0):
        near_pair_images = defaultdict(set)
        pair_images = defaultdict(set)
        pair_observations = defaultdict(int)
        for image in reconstruction.images.values():
            rows = []
            cam_from_world = image.cam_from_world()
            for point2d in image.points2D:
                if not point2d.has_point3D():
                    continue
                point_id = int(point2d.point3D_id)
                if point_id not in published_ids:
                    continue
                depth = float((cam_from_world * reconstruction.points3D[point_id].xyz)[2])
                if depth <= 0.0:
                    continue
                rows.append((np.asarray(point2d.xy), point_id, depth))
            if len(rows) < 2:
                continue
            xy = np.asarray([row[0] for row in rows], dtype=np.float64)
            for first, second in cKDTree(xy).query_pairs(radius_px, output_type="set"):
                point1, point2 = rows[first][1], rows[second][1]
                if point1 == point2:
                    continue
                pair = (min(point1, point2), max(point1, point2))
                near_pair_images[pair].add(int(image.image_id))
                gap_mm = abs(rows[first][2] - rows[second][2]) * scale * 1000.0
                if gap_mm < 12.0 or gap_mm > 100.0:
                    continue
                pair_images[pair].add(int(image.image_id))
                pair_observations[pair] += 1
        conflicts[f"{radius_px:g}px"] = {}
        for min_images in (2, 3):
            persistent = {
                pair for pair, image_ids in pair_images.items() if len(image_ids) >= min_images
            }
            conflicts[f"{radius_px:g}px"][f"{min_images}views"] = {
                "persistent_point_pairs": len(persistent),
                "persistent_point_ids": len(set(itertools.chain.from_iterable(persistent))),
                "persistent_observations": int(
                    sum(pair_observations[pair] for pair in persistent)
                ),
                "pair_details": [
                    {
                        "point_ids": list(pair),
                        "distinct_image_ids": sorted(pair_images[pair]),
                        "observation_count": pair_observations[pair],
                    }
                    for pair in sorted(persistent)
                ],
            }
        normal_layer_conflicts[f"{radius_px:g}px"] = {}
        pair_geometry = {
            pair: normal_layer_geometry(
                reconstruction,
                pair[0],
                pair[1],
                local_normals,
                scale,
            )
            for pair in near_pair_images
        }
        for max_normal_angle_deg in (20.0, 30.0, 45.0):
            angle_key = f"{max_normal_angle_deg:g}deg"
            normal_layer_conflicts[f"{radius_px:g}px"][angle_key] = {}
            for min_images in (2, 3):
                persistent = {
                    pair
                    for pair, image_ids in near_pair_images.items()
                    if len(image_ids) >= min_images
                    and pair_geometry[pair]["normal_angle_deg"]
                    <= max_normal_angle_deg
                    and 12.0
                    <= pair_geometry[pair]["normal_separation_mm"]
                    <= 100.0
                    and pair_geometry[pair]["tangent_separation_mm"]
                    <= pair_geometry[pair]["normal_separation_mm"]
                }
                normal_layer_conflicts[f"{radius_px:g}px"][angle_key][
                    f"{min_images}views"
                ] = {
                    "persistent_point_pairs": len(persistent),
                    "persistent_point_ids": len(
                        set(itertools.chain.from_iterable(persistent))
                    ),
                    "pair_details": [
                        {
                            "point_ids": list(pair),
                            "distinct_image_ids": sorted(near_pair_images[pair]),
                            **pair_geometry[pair],
                        }
                        for pair in sorted(persistent)
                    ],
                }

    return {
        "model": str(model),
        "ply": str(ply),
        "internal_points": len(reconstruction.points3D),
        **mapping,
        "floor_thickness_16_84_mm": float(
            (np.percentile(residual, 84) - np.percentile(residual, 16)) * 1000.0
        ),
        "coverage_32x18_median": float(np.median(coverage_counts)),
        "coverage_32x18_p10": float(np.percentile(coverage_counts, 10)),
        "coverage_32x18_min": int(np.min(coverage_counts)),
        "near_ray_competition": conflicts,
        "normal_layer_competition": normal_layer_conflicts,
        "local_surface_quality": surface_quality,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm", action="append", required=True)
    args = parser.parse_args()
    ledger = [json.loads(line) for line in args.ledger.read_text().splitlines() if line]
    arms = {}
    for value in args.arm:
        name, separator, paths = value.partition("=")
        model, separator2, ply = paths.partition("|")
        if not separator or not separator2:
            raise ValueError(f"invalid --arm {value!r}; expected name=model|ply")
        arms[name] = score(Path(model), Path(ply), ledger)
    result = {
        "schema": "pocketworld_published_cloud_competition_v1",
        "diagnostic_only": True,
        "persistence_unit": "distinct_registered_images",
        "depth_gap_mm": [12.0, 100.0],
        "arms": arms,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
