#!/usr/bin/env python3
"""Build deterministic two-view geometry from a fixed RANSAC seed ensemble.

COLMAP's robust estimator can return materially different inlier graphs for
different random seeds even when keypoints and descriptor matches are frozen.
This tool admits a correspondence to track establishment only when it appears
in at least ``min_votes`` independently seeded geometry rows.  It therefore
changes correspondence birth, never an already generated 3D reconstruction.
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


def pair_rows(path: Path) -> dict[int, pycolmap.TwoViewGeometry]:
    with pycolmap.Database.open(path) as database:
        pair_ids, geometries = database.read_two_view_geometries()
    return {
        int(pair_id): geometry
        for pair_id, geometry in zip(pair_ids, geometries, strict=True)
    }


def match_set(geometry: pycolmap.TwoViewGeometry | None) -> set[tuple[int, int]]:
    if geometry is None:
        return set()
    return {
        (int(first), int(second))
        for first, second in np.asarray(geometry.inlier_matches, dtype=np.uint32)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-db", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--min-votes", type=int, required=True)
    parser.add_argument("--min-inliers", type=int, default=15)
    args = parser.parse_args()

    if len(args.geometry_db) < 2:
        raise ValueError("at least two --geometry-db inputs are required")
    if not 1 <= args.min_votes <= len(args.geometry_db):
        raise ValueError("--min-votes must be within the seed ensemble size")
    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")

    sqlite_snapshot(args.geometry_db[0], args.output)
    rows_by_db = [pair_rows(path) for path in args.geometry_db]
    pair_ids = sorted(set().union(*(rows.keys() for rows in rows_by_db)))

    admitted_total = 0
    geometry_pairs = 0
    rejected_pairs = 0
    vote_histogram: Counter[int] = Counter()
    pair_agreement: list[float] = []

    with pycolmap.Database.open(args.output) as output:
        for pair_id in pair_ids:
            geometries = [rows.get(pair_id) for rows in rows_by_db]
            sets = [match_set(geometry) for geometry in geometries]
            votes: Counter[tuple[int, int]] = Counter()
            for matches in sets:
                votes.update(matches)
            vote_histogram.update(votes.values())
            consensus = sorted(
                match for match, count in votes.items() if count >= args.min_votes
            )

            union = set().union(*sets)
            unanimous = set.intersection(*sets) if sets else set()
            pair_agreement.append(len(unanimous) / max(1, len(union)))

            image_id1, image_id2 = pycolmap.pair_id_to_image_pair(pair_id)
            if output.exists_two_view_geometry(image_id1, image_id2):
                output.delete_two_view_geometry(image_id1, image_id2)
            if len(consensus) < args.min_inliers:
                rejected_pairs += 1
                continue

            consensus_set = set(consensus)
            # Preserve the matrix/relative-pose hypothesis whose inliers agree
            # most strongly with the deterministic consensus.  Input order is
            # the stable tie-breaker.
            _, reference = max(
                (
                    (index, geometry)
                    for index, geometry in enumerate(geometries)
                    if geometry is not None
                ),
                key=lambda indexed: (
                    len(match_set(indexed[1]) & consensus_set),
                    len(match_set(indexed[1])),
                    -indexed[0],
                ),
            )
            reference.inlier_matches = np.asarray(consensus, dtype=np.uint32)
            output.write_two_view_geometry(image_id1, image_id2, reference)
            admitted_total += len(consensus)
            geometry_pairs += 1

    agreement = np.asarray(pair_agreement, dtype=np.float64)
    stats = {
        "schema": "pocketworld_multiseed_tvg_consensus_v1",
        "geometry_dbs": [str(path) for path in args.geometry_db],
        "output_db": str(args.output),
        "pycolmap_version": pycolmap.__version__,
        "ensemble_size": len(args.geometry_db),
        "min_votes": args.min_votes,
        "min_inliers": args.min_inliers,
        "input_pair_union": len(pair_ids),
        "geometry_pairs": geometry_pairs,
        "rejected_pairs": rejected_pairs,
        "admitted_inliers": admitted_total,
        "edge_vote_histogram": {
            str(votes): int(count) for votes, count in sorted(vote_histogram.items())
        },
        "pair_unanimous_over_union": {
            "median": float(np.median(agreement)),
            "p10": float(np.percentile(agreement, 10)),
            "min": float(np.min(agreement)),
        },
        "deletes_frames_or_generated_points": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
