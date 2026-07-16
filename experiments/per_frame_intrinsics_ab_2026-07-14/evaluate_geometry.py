#!/usr/bin/env python3
"""Align both sparse models to ARKit and compare metric floor geometry."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def load_arkit_centers(path: Path) -> dict[int, np.ndarray]:
    result = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            result[int(row["frameId"])] = np.asarray(
                row["arkitCameraCenterWorld"], dtype=np.float64
            )
    return result


def quaternion_rotation(q: np.ndarray) -> np.ndarray:
    q = q / np.linalg.norm(q)
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def load_sfm_centers(path: Path) -> dict[int, np.ndarray]:
    result = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if int(row["registered"]) != 1:
                continue
            q = np.array([row[k] for k in ("qw", "qx", "qy", "qz")], dtype=float)
            t = np.array([row[k] for k in ("tx", "ty", "tz")], dtype=float)
            result[int(row["frame_id"])] = -(quaternion_rotation(q).T @ t)
    return result


def load_binary_ply(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        count = None
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("truncated PLY header")
            text = line.decode("ascii").strip()
            if text.startswith("element vertex "):
                count = int(text.split()[-1])
            if text == "end_header":
                break
        if count is None:
            raise RuntimeError("missing PLY vertex count")
        record = struct.Struct("<fffBBB")
        xyz = np.empty((count, 3), dtype=np.float64)
        for index in range(count):
            values = record.unpack(stream.read(record.size))
            xyz[index] = values[:3]
    return xyz


def load_track_quality(path: Path) -> dict[str, np.ndarray]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {
        "track_length": np.asarray(
            [int(row["track_length"]) for row in rows], dtype=np.int32
        ),
        "max_reprojection_error_px": np.asarray(
            [float(row.get("max_reprojection_error_px", "inf")) for row in rows]
        ),
        "mean_reprojection_error_px": np.asarray(
            [float(row.get("mean_reprojection_error_px", "inf")) for row in rows]
        ),
        "max_triangulation_angle_deg": np.asarray(
            [float(row.get("max_triangulation_angle_deg", "0")) for row in rows]
        ),
        "frame_span": np.asarray(
            [int(row.get("frame_span", "0")) for row in rows], dtype=np.int32
        ),
    }


def floor_score(points: np.ndarray) -> dict:
    y = points[:, 1]
    low, high = np.percentile(y, [2, 15])
    band = points[(y >= low) & (y <= high)]
    design = np.column_stack((band[:, 0], band[:, 2], np.ones(len(band))))
    coefficients, *_ = np.linalg.lstsq(design, band[:, 1], rcond=None)
    residual = band[:, 1] - design @ coefficients
    return {
        "points": len(points),
        "floor_band_points": len(band),
        "floor_thickness_16_84_mm": float(
            (np.percentile(residual, 84) - np.percentile(residual, 16)) * 1000
        ),
        "floor_residual_minus50_to_minus15mm": int(
            np.sum((residual >= -0.050) & (residual < -0.015))
        ),
        "floor_residual_below_minus15mm": int(np.sum(residual < -0.015)),
    }


def local_surface_score(points: np.ndarray) -> dict:
    voxel_m = 0.010
    keys = np.floor(points / voxel_m).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    counts = np.bincount(inverse)
    centroids = np.column_stack(
        [np.bincount(inverse, weights=points[:, axis]) / counts for axis in range(3)]
    )
    tree = cKDTree(centroids)
    normal_rms = []
    surface_variation = []
    for index, neighbors in enumerate(tree.query_ball_point(centroids, r=0.080)):
        if len(neighbors) < 12:
            continue
        patch = centroids[neighbors]
        centered = patch - patch.mean(axis=0)
        eigenvalues = np.linalg.eigvalsh(centered.T @ centered / len(patch))
        if eigenvalues[2] <= 0 or eigenvalues[1] / eigenvalues[2] < 0.20:
            continue
        normal_rms.append(np.sqrt(max(0.0, eigenvalues[0])) * 1000)
        surface_variation.append(eigenvalues[0] / max(1e-15, eigenvalues.sum()))
    normal_rms = np.asarray(normal_rms)
    surface_variation = np.asarray(surface_variation)
    return {
        "voxel_centroids": len(centroids),
        "planar_neighborhoods": len(normal_rms),
        "normal_scatter_median_mm": float(np.median(normal_rms)),
        "normal_scatter_p90_mm": float(np.percentile(normal_rms, 90)),
        "normal_scatter_p95_mm": float(np.percentile(normal_rms, 95)),
        "surface_variation_median": float(np.median(surface_variation)),
        "surface_variation_p90": float(np.percentile(surface_variation, 90)),
    }


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


def score(run_dir: Path, arkit: dict[int, np.ndarray], *, sweep_gates=False) -> dict:
    sfm = load_sfm_centers(run_dir / "poses.csv")
    ids = sorted(set(sfm) & set(arkit))
    source = np.stack([sfm[index] for index in ids])
    target = np.stack([arkit[index] for index in ids])
    scale, rotation, translation = umeyama(source, target)
    aligned_cameras = scale * (rotation @ source.T).T + translation
    camera_error = np.linalg.norm(aligned_cameras - target, axis=1)

    points = load_binary_ply(run_dir / "cloud.ply")
    track_quality = load_track_quality(run_dir / "track_lengths.csv")
    track_lengths = track_quality["track_length"]
    if len(track_lengths) != len(points):
        raise RuntimeError("point/track length mismatch")
    metric_points = scale * (rotation @ points.T).T + translation
    floors = {
        f"track_ge_{minimum}": {
            **floor_score(metric_points[track_lengths >= minimum]),
            "local_surface": local_surface_score(
                metric_points[track_lengths >= minimum]
            ),
        }
        for minimum in (2, 3, 4, 5)
        if np.sum(track_lengths >= minimum) >= 100
    }
    all_floor = floors["track_ge_2"]
    result = {
        "registered": len(ids),
        "points": len(points),
        "sim3_scale": scale,
        "camera_center_median_mm": float(np.median(camera_error) * 1000),
        "camera_center_p90_mm": float(np.percentile(camera_error, 90) * 1000),
        "floor_band_points": all_floor["floor_band_points"],
        "floor_thickness_16_84_mm": all_floor["floor_thickness_16_84_mm"],
        "floor_residual_minus50_to_minus15mm": all_floor[
            "floor_residual_minus50_to_minus15mm"
        ],
        "floor_residual_below_minus15mm": all_floor[
            "floor_residual_below_minus15mm"
        ],
        "track_length_median": float(np.median(track_lengths)),
        "track_stratified_floor": floors,
    }
    if sweep_gates:
        gates = {}
        # Pre-registered grid: a two-view proposal may be published only when
        # its baseline, final reprojection residual, and temporal separation all
        # pass. Three-view tracks are always mature. Tune on cap56, validate the
        # selected rule unchanged on cap51.
        for angle_deg in (3.0, 5.0, 8.0, 12.0):
            for max_reprojection_px in (1.0, 2.0, 3.0):
                for min_frame_span in (1, 2, 4):
                    mature = track_lengths >= 3
                    strong_two_view = (
                        (track_lengths == 2)
                        & (
                            track_quality["max_triangulation_angle_deg"]
                            >= angle_deg
                        )
                        & (
                            track_quality["max_reprojection_error_px"]
                            <= max_reprojection_px
                        )
                        & (track_quality["frame_span"] >= min_frame_span)
                    )
                    mask = mature | strong_two_view
                    if np.sum(mask) < 100:
                        continue
                    name = (
                        f"angle_ge_{angle_deg:g}_reproj_le_"
                        f"{max_reprojection_px:g}_span_ge_{min_frame_span}"
                    )
                    gates[name] = {
                        **floor_score(metric_points[mask]),
                        "two_view_published": int(np.sum(strong_two_view)),
                        "local_surface": local_surface_score(metric_points[mask]),
                    }
        result["publish_gate_sweep"] = gates
        mature_gates = {}
        # COLMAP's viewer defaults to track length >=3 and max point error 2px.
        # Evaluate stricter native birth predicates using the exact per-point
        # residuals because this on-device path does not populate Point3D.error.
        for max_mean_reprojection_px in (1.0, 1.5, 2.0, 3.0):
            for min_angle_deg in (1.5, 2.0, 3.0, 5.0):
                mask = (
                    (track_lengths >= 3)
                    & (
                        track_quality["mean_reprojection_error_px"]
                        <= max_mean_reprojection_px
                    )
                    & (
                        track_quality["max_triangulation_angle_deg"]
                        >= min_angle_deg
                    )
                )
                if np.sum(mask) < 100:
                    continue
                name = (
                    f"track_ge_3_mean_reproj_le_{max_mean_reprojection_px:g}_"
                    f"angle_ge_{min_angle_deg:g}"
                )
                mature_gates[name] = {
                    **floor_score(metric_points[mask]),
                    "local_surface": local_surface_score(metric_points[mask]),
                }
        result["mature_gate_sweep"] = mature_gates
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--single", type=Path)
    parser.add_argument("--shared", type=Path)
    parser.add_argument("--per-frame", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sweep-publish-gates", action="store_true")
    args = parser.parse_args()
    arkit = load_arkit_centers(args.ledger)
    if args.single is not None:
        if args.shared is not None or args.per_frame is not None:
            parser.error("--single cannot be combined with --shared/--per-frame")
        result = {
            "schema": "pocketworld_sparse_geometry_single_v1",
            "run": score(
                args.single, arkit, sweep_gates=args.sweep_publish_gates
            ),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    if args.shared is None or args.per_frame is None:
        parser.error("provide --single or both --shared and --per-frame")
    result = {
        "schema": "pocketworld_per_frame_intrinsics_geometry_ab_v1",
        "shared": score(
            args.shared, arkit, sweep_gates=args.sweep_publish_gates
        ),
        "per_frame": score(
            args.per_frame, arkit, sweep_gates=args.sweep_publish_gates
        ),
    }
    shared = result["shared"]
    per_frame = result["per_frame"]
    result["delta"] = {
        "point_count_pct": 100 * (per_frame["points"] / shared["points"] - 1),
        "camera_center_median_pct": 100 * (
            per_frame["camera_center_median_mm"] / shared["camera_center_median_mm"] - 1
        ),
        "floor_thickness_pct": 100 * (
            per_frame["floor_thickness_16_84_mm"] / shared["floor_thickness_16_84_mm"] - 1
        ),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
