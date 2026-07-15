#!/usr/bin/env python3
"""Deterministically re-estimate COLMAP TVG rows from stored match hypotheses.

The site-aware Metal matcher can recover physical-site pairs that were absent
from the descriptor-level matcher.  Intersecting its output with the old TVG
rows measures only removals and prevents recovered pairs from ever becoming
inliers.  This tool makes a new database snapshot and runs COLMAP's official
two-view geometry estimator for every non-empty match row.  The input database
is never modified.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pycolmap


def sqlite_snapshot(source_path: Path, output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    output = sqlite3.connect(output_path)
    try:
        source.backup(output)
    finally:
        output.close()
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--max-error-px", type=float, default=4.0)
    parser.add_argument("--min-inliers", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ransac-min-trials", type=int, default=100)
    parser.add_argument("--ransac-max-trials", type=int, default=10000)
    parser.add_argument("--ransac-confidence", type=float, default=0.999)
    parser.add_argument("--ransac-dyn-multiplier", type=float, default=3.0)
    parser.add_argument(
        "--mark-prior-focal",
        action="store_true",
        help=(
            "mark the stored measured focal length as a prior before geometry "
            "estimation, so calibrated cameras use essential geometry"
        ),
    )
    args = parser.parse_args()

    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")
    sqlite_snapshot(args.input, args.output)

    database = pycolmap.Database.open(str(args.output))
    cameras = {int(camera.camera_id): camera for camera in database.read_all_cameras()}
    if args.mark_prior_focal:
        for camera in cameras.values():
            camera.has_prior_focal_length = True
            database.update_camera(camera)
    images = {int(image.image_id): image for image in database.read_all_images()}
    keypoints = {
        image_id: np.asarray(database.read_keypoints(image_id)[:, :2], dtype=np.float64)
        for image_id in images
    }
    pair_ids, pair_matches = database.read_all_matches()

    options = pycolmap.TwoViewGeometryOptions()
    options.min_num_inliers = args.min_inliers
    options.ransac.max_error = args.max_error_px
    options.ransac.random_seed = args.seed
    options.ransac.num_threads = 1
    options.ransac.min_num_trials = args.ransac_min_trials
    options.ransac.max_num_trials = args.ransac_max_trials
    options.ransac.confidence = args.ransac_confidence
    options.ransac.dyn_num_trials_multiplier = args.ransac_dyn_multiplier

    total_matches = 0
    total_inliers = 0
    geometry_pairs = 0
    rejected_pairs = 0
    configs: Counter[str] = Counter()
    for index, (pair_id, matches) in enumerate(
        zip(pair_ids, pair_matches, strict=True), start=1
    ):
        image_id1, image_id2 = pycolmap.pair_id_to_image_pair(pair_id)
        image1 = images[int(image_id1)]
        image2 = images[int(image_id2)]
        matches = np.asarray(matches, dtype=np.uint32)
        total_matches += len(matches)
        geometry = pycolmap.estimate_two_view_geometry(
            cameras[int(image1.camera_id)],
            keypoints[int(image_id1)],
            cameras[int(image2.camera_id)],
            keypoints[int(image_id2)],
            matches,
            options,
        )
        inlier_count = len(geometry.inlier_matches)
        if inlier_count < args.min_inliers:
            if database.exists_two_view_geometry(image_id1, image_id2):
                database.delete_two_view_geometry(image_id1, image_id2)
            rejected_pairs += 1
        else:
            if database.exists_two_view_geometry(image_id1, image_id2):
                database.update_two_view_geometry(image_id1, image_id2, geometry)
            else:
                database.write_two_view_geometry(image_id1, image_id2, geometry)
            geometry_pairs += 1
            total_inliers += inlier_count
            configs[str(geometry.config)] += 1
        if index % 100 == 0 or index == len(pair_ids):
            print(f"geometry {index}/{len(pair_ids)} pairs", flush=True)
    database.close()

    stats = {
        "schema": "pocketworld_reestimate_two_view_geometries_v1",
        "pycolmap_version": pycolmap.__version__,
        "input_db": str(args.input),
        "output_db": str(args.output),
        "seed": args.seed,
        "ransac_min_trials": args.ransac_min_trials,
        "ransac_max_trials": args.ransac_max_trials,
        "ransac_confidence": args.ransac_confidence,
        "ransac_dyn_multiplier": args.ransac_dyn_multiplier,
        "max_error_px": args.max_error_px,
        "min_inliers": args.min_inliers,
        "mark_prior_focal": args.mark_prior_focal,
        "match_pairs": len(pair_ids),
        "matches": total_matches,
        "geometry_pairs": geometry_pairs,
        "rejected_pairs": rejected_pairs,
        "inliers": total_inliers,
        "geometry_configs": dict(sorted(configs.items())),
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
