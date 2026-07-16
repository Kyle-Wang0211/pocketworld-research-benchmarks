#!/usr/bin/env python3
"""All-space point-birth diagnostics for cap51 reconstructions.

Unlike the historical floor-only bimodal-cell score, this diagnostic asks an
upstream SfM question: did one exact image feature site acquire more than one
3D owner?  Two opaque scene points cannot both own the same camera ray at the
same pixel.  DSP-SIFT can emit multiple descriptors at identical coordinates;
if those descriptor rows form separate tracks, the normal one-observation / one-
point invariant is bypassed and multiple depths can be born.

This file is evaluation-only.  It never filters, moves, hides, or rewrites a
reconstruction.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pycolmap


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src0 = src - src_mean
    dst0 = dst - dst_mean
    covariance = dst0.T @ src0 / len(src)
    u, singular, vt = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        correction[-1, -1] = -1
    rotation = u @ correction @ vt
    variance = np.mean(np.sum(src0 * src0, axis=1))
    scale = float(np.sum(singular * np.diag(correction)) / variance)
    translation = dst_mean - scale * (rotation @ src_mean)
    return scale, rotation, translation


def summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"median": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def score(model_dir: Path, ledger: list[dict], layer_gap_m: float) -> dict:
    reconstruction = pycolmap.Reconstruction(model_dir)
    centers_rec = np.empty((len(ledger), 3), dtype=np.float64)
    centers_arkit = np.asarray(
        [row["arkitCameraCenterWorld"] for row in ledger], dtype=np.float64
    )
    for image in reconstruction.images.values():
        frame_id = int(Path(image.name).stem.split("_")[-1])
        centers_rec[frame_id] = image.projection_center()

    scale, rotation, translation = umeyama(centers_rec, centers_arkit)
    aligned = scale * (rotation @ centers_rec.T).T + translation
    aligned_error_mm = np.linalg.norm(aligned - centers_arkit, axis=1) * 1000.0
    direct_error_mm = np.linalg.norm(centers_rec - centers_arkit, axis=1) * 1000.0

    n_triangulated_observations = 0
    n_observed_sites = 0
    competition_groups = 0
    competition_observations = 0
    layer_groups = 0
    layer_observations = 0
    depth_spreads_mm: list[float] = []
    layer_depth_spreads_mm: list[float] = []
    competing_point_ids: set[int] = set()
    layer_point_ids: set[int] = set()
    point_pair_images: Counter[tuple[int, int]] = Counter()

    for image in reconstruction.images.values():
        sites: dict[tuple[float, float], list[tuple[int, float]]] = defaultdict(list)
        cam_from_world = image.cam_from_world()
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            n_triangulated_observations += 1
            point3d_id = int(point2d.point3D_id)
            xyz = reconstruction.points3D[point3d_id].xyz
            depth = float((cam_from_world * xyz)[2])
            if depth <= 0.0:
                continue
            # Keypoint coordinates originate as float32 and are promoted to
            # float64 by pycolmap. Exact equality therefore identifies the
            # extractor's true duplicate site without a tunable pixel radius.
            key = (float(point2d.xy[0]), float(point2d.xy[1]))
            sites[key].append((point3d_id, depth))

        n_observed_sites += len(sites)
        for owners in sites.values():
            owner_depth = {}
            for point3d_id, depth in owners:
                owner_depth.setdefault(point3d_id, depth)
            if len(owner_depth) < 2:
                continue
            ordered_ids = sorted(owner_depth)
            depths = np.asarray([owner_depth[point_id] for point_id in ordered_ids])
            spread_m = float((np.max(depths) - np.min(depths)) * scale)
            spread_mm = spread_m * 1000.0
            competition_groups += 1
            competition_observations += len(owners)
            depth_spreads_mm.append(spread_mm)
            competing_point_ids.update(ordered_ids)
            for pair in itertools.combinations(ordered_ids, 2):
                point_pair_images[pair] += 1
            if spread_m >= layer_gap_m:
                layer_groups += 1
                layer_observations += len(owners)
                layer_depth_spreads_mm.append(spread_mm)
                layer_point_ids.update(ordered_ids)

    persistent_pairs = [count for count in point_pair_images.values() if count >= 2]
    track_lengths = [
        len(reconstruction.points3D[point_id].track.elements)
        for point_id in competing_point_ids
    ]
    layer_track_lengths = [
        len(reconstruction.points3D[point_id].track.elements)
        for point_id in layer_point_ids
    ]
    denom = max(1, n_triangulated_observations)
    return {
        "registered_frames": len(reconstruction.images),
        "sparse_points": len(reconstruction.points3D),
        "metric_alignment_scale": scale,
        "camera_direct_error_mm": summary(direct_error_mm.tolist()),
        "camera_sim3_aligned_error_mm": summary(aligned_error_mm.tolist()),
        "triangulated_observations": n_triangulated_observations,
        "observed_exact_sites": n_observed_sites,
        "exact_site_competition_groups": competition_groups,
        "exact_site_competition_observations": competition_observations,
        "exact_site_competition_groups_per_1000_observations": (
            1000.0 * competition_groups / denom
        ),
        "competing_point_ids": len(competing_point_ids),
        "competition_depth_spread_mm": summary(depth_spreads_mm),
        "layer_gap_threshold_mm": layer_gap_m * 1000.0,
        "multi_depth_layer_groups": layer_groups,
        "multi_depth_layer_observations": layer_observations,
        "multi_depth_layer_groups_per_1000_observations": (
            1000.0 * layer_groups / denom
        ),
        "multi_depth_point_ids": len(layer_point_ids),
        "multi_depth_spread_mm": summary(layer_depth_spreads_mm),
        "persistent_competing_point_pairs_2plus_images": len(persistent_pairs),
        "persistent_pair_image_count": summary([float(v) for v in persistent_pairs]),
        "competing_point_track_length": summary([float(v) for v in track_lengths]),
        "multi_depth_point_track_length": summary(
            [float(v) for v in layer_track_lengths]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--arm",
        action="append",
        required=True,
        help="name=/absolute/or/relative/model_dir (repeatable)",
    )
    parser.add_argument("--layer-gap-mm", type=float, default=12.0)
    args = parser.parse_args()

    ledger = [
        json.loads(line) for line in args.ledger.read_text().splitlines() if line
    ]
    arms: dict[str, Path] = {}
    for value in args.arm:
        name, separator, model_dir = value.partition("=")
        if not separator or not name or not model_dir:
            raise ValueError(f"invalid --arm {value!r}; expected name=path")
        arms[name] = Path(model_dir)

    result = {
        "metric": "all_space_exact_feature_site_ray_ownership",
        "pycolmap_version": pycolmap.__version__,
        "diagnostic_only": True,
        "arms": {
            name: score(model_dir, ledger, args.layer_gap_mm / 1000.0)
            for name, model_dir in arms.items()
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"WROTE {args.output}")


if __name__ == "__main__":
    main()
