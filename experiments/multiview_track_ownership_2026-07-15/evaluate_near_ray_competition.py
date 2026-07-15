#!/usr/bin/env python3
"""Diagnose persistent near-ray multi-depth ownership across all surfaces.

Unlike the exact-site metric, this also catches distinct point2D identities
that land within a small image-space radius in multiple views.  A pair counts
only when its metric depth separation is layer-sized (default 12--100 mm) and
the same two 3D point identities compete in at least two images.  The tool is
read-only and never filters or rewrites a reconstruction.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree


def umeyama_scale(source: np.ndarray, target: np.ndarray) -> float:
    source0 = source - source.mean(axis=0)
    target0 = target - target.mean(axis=0)
    covariance = target0.T @ source0 / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    correction = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        correction[-1] = -1
    variance = np.mean(np.sum(source0 * source0, axis=1))
    return float(np.sum(singular * correction) / variance)


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


def frame_id(image: pycolmap.Image) -> int:
    return int(Path(image.name).stem.split("_")[-1])


def score(
    model_dir: Path,
    ledger: list[dict],
    radius_px: float,
    min_gap_m: float,
    max_gap_m: float,
    min_images: int,
) -> dict:
    reconstruction = pycolmap.Reconstruction(model_dir)
    rec_centers = []
    arkit_centers = []
    for image in reconstruction.images.values():
        rec_centers.append(image.projection_center())
        arkit_centers.append(ledger[frame_id(image)]["arkitCameraCenterWorld"])
    scale = umeyama_scale(
        np.asarray(rec_centers, dtype=np.float64),
        np.asarray(arkit_centers, dtype=np.float64),
    )

    # One-to-many correspondence graphs may contain more than one observation
    # of the same 3D identity in a single image.  Persistence is a multi-view
    # property, so repeated observations in one image count exactly once.
    pair_images: dict[tuple[int, int], set[int]] = defaultdict(set)
    pair_pixel_distances: dict[tuple[int, int], list[float]] = defaultdict(list)
    pair_depth_gaps_mm: dict[tuple[int, int], list[float]] = defaultdict(list)
    n_observations = 0
    n_near_pairs = 0
    n_layer_pairs = 0

    for image in reconstruction.images.values():
        rows: list[tuple[float, float, int, float]] = []
        cam_from_world = image.cam_from_world()
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point_id = int(point2d.point3D_id)
            depth = float((cam_from_world * reconstruction.points3D[point_id].xyz)[2])
            if depth <= 0.0:
                continue
            rows.append((float(point2d.xy[0]), float(point2d.xy[1]), point_id, depth))
        n_observations += len(rows)
        if len(rows) < 2:
            continue
        xy = np.asarray([(row[0], row[1]) for row in rows], dtype=np.float64)
        for first, second in cKDTree(xy).query_pairs(radius_px, output_type="set"):
            n_near_pairs += 1
            point1 = rows[first][2]
            point2 = rows[second][2]
            if point1 == point2:
                continue
            gap_m = abs(rows[first][3] - rows[second][3]) * scale
            if gap_m < min_gap_m or gap_m > max_gap_m:
                continue
            n_layer_pairs += 1
            pair = (min(point1, point2), max(point1, point2))
            pair_images[pair].add(int(image.image_id))
            pair_pixel_distances[pair].append(float(np.linalg.norm(xy[first] - xy[second])))
            pair_depth_gaps_mm[pair].append(gap_m * 1000.0)

    persistent = [
        pair for pair, image_ids in pair_images.items() if len(image_ids) >= min_images
    ]
    persistent_point_ids = set(itertools.chain.from_iterable(persistent))
    image_counts = [float(len(pair_images[pair])) for pair in persistent]
    pixel_distances = [
        value for pair in persistent for value in pair_pixel_distances[pair]
    ]
    depth_gaps = [value for pair in persistent for value in pair_depth_gaps_mm[pair]]
    denom = max(1, n_observations)
    return {
        "registered_frames": len(reconstruction.images),
        "sparse_points": len(reconstruction.points3D),
        "metric_alignment_scale": scale,
        "triangulated_observations": n_observations,
        "near_observation_pairs": n_near_pairs,
        "layer_gap_observation_pairs": n_layer_pairs,
        "candidate_point_pairs": len(pair_images),
        "persistent_point_pairs": len(persistent),
        "persistent_pairs_per_1000_observations": 1000.0 * len(persistent) / denom,
        "persistent_point_ids": len(persistent_point_ids),
        "persistent_pair_image_count": summary(image_counts),
        "persistent_pixel_distance_px": summary(pixel_distances),
        "persistent_depth_gap_mm": summary(depth_gaps),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--radius-px", type=float, default=2.0)
    parser.add_argument("--min-gap-mm", type=float, default=12.0)
    parser.add_argument("--max-gap-mm", type=float, default=100.0)
    parser.add_argument("--min-images", type=int, default=2)
    args = parser.parse_args()
    ledger = [json.loads(line) for line in args.ledger.read_text().splitlines() if line]
    arms: dict[str, Path] = {}
    for value in args.arm:
        name, separator, model = value.partition("=")
        if not separator:
            raise ValueError(f"invalid --arm {value!r}")
        arms[name] = Path(model)
    result = {
        "schema": "pocketworld_near_ray_competition_v2",
        "pycolmap_version": pycolmap.__version__,
        "diagnostic_only": True,
        "radius_px": args.radius_px,
        "min_gap_mm": args.min_gap_mm,
        "max_gap_mm": args.max_gap_mm,
        "min_images": args.min_images,
        "persistence_unit": "distinct_registered_images",
        "arms": {
            name: score(
                model,
                ledger,
                args.radius_px,
                args.min_gap_mm / 1000.0,
                args.max_gap_mm / 1000.0,
                args.min_images,
            )
            for name, model in arms.items()
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
