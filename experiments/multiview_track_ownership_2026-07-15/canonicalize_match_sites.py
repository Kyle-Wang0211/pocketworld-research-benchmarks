#!/usr/bin/env python3
"""Give one pairwise-match identity to descriptors at the same image pixel.

DSP-SIFT can emit several descriptors for the same physical image location
(different scale/orientation hypotheses).  Descriptor-level mutual matching
does not prevent those aliases from seeding separate SfM tracks.  This tool
creates an experiment-only database copy in which all exact-equal (x, y)
aliases map to one canonical point2D index before any track is born.

The images, keypoints, descriptors, and user frames are unchanged.  For each
image pair, candidate matches are ranked by RootSIFT descriptor distance and
greedily assigned so a physical pixel site owns at most one endpoint.  Existing
two-view-geometry inliers are only intersected with those assignments; geometry
is never relaxed and no new correspondence is invented.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np


MAX_IMAGE_ID = 2_147_483_647


def image_pair(pair_id: int) -> tuple[int, int]:
    return pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID


def load_features(
    database: sqlite3.Connection,
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray], dict[int, dict]]:
    canonical: dict[int, np.ndarray] = {}
    descriptors: dict[int, np.ndarray] = {}
    stats: dict[int, dict] = {}
    for image_id, rows, cols, data in database.execute(
        "SELECT image_id, rows, cols, data FROM keypoints ORDER BY image_id"
    ):
        keypoints = np.frombuffer(data, dtype=np.float32).reshape(rows, cols)
        representatives: dict[tuple[int, int], int] = {}
        mapping = np.empty(rows, dtype=np.uint32)
        for index, (x, y) in enumerate(keypoints[:, :2]):
            # Bit identity is intentional: this first experiment only collapses
            # descriptors produced at exactly the same detector location.
            key = (
                int(np.float32(x).view(np.uint32)),
                int(np.float32(y).view(np.uint32)),
            )
            mapping[index] = representatives.setdefault(key, index)
        descriptor_row = database.execute(
            "SELECT rows, cols, data FROM descriptors WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        if descriptor_row is None:
            raise RuntimeError(f"image {image_id} has keypoints but no descriptors")
        descriptor_rows, descriptor_cols, descriptor_data = descriptor_row
        if descriptor_rows != rows or descriptor_cols != 128:
            raise RuntimeError(
                f"image {image_id} descriptor shape {descriptor_rows}x"
                f"{descriptor_cols} does not match {rows} keypoints"
            )
        canonical[image_id] = mapping
        descriptors[image_id] = np.frombuffer(
            descriptor_data, dtype=np.uint8
        ).reshape(descriptor_rows, descriptor_cols)
        unique_sites = len(representatives)
        stats[image_id] = {
            "keypoints": int(rows),
            "unique_exact_xy_sites": int(unique_sites),
            "aliased_descriptors": int(rows - unique_sites),
        }
    return canonical, descriptors, stats


def canonical_assignments(
    matches: np.ndarray,
    canonical1: np.ndarray,
    canonical2: np.ndarray,
    descriptors1: np.ndarray,
    descriptors2: np.ndarray,
) -> np.ndarray:
    if len(matches) == 0:
        return np.empty((0, 2), dtype=np.uint32)
    endpoints1 = matches[:, 0]
    endpoints2 = matches[:, 1]
    sites1 = canonical1[endpoints1]
    sites2 = canonical2[endpoints2]
    delta = (
        descriptors1[endpoints1].astype(np.int16)
        - descriptors2[endpoints2].astype(np.int16)
    )
    distance = np.sum(delta.astype(np.int32) ** 2, axis=1, dtype=np.int64)
    # Stable ordering gives deterministic tie-breaking by the stored match row.
    order = np.argsort(distance, kind="stable")
    used1: set[int] = set()
    used2: set[int] = set()
    accepted: list[tuple[int, int]] = []
    for row in order:
        site1 = int(sites1[row])
        site2 = int(sites2[row])
        if site1 in used1 or site2 in used2:
            continue
        used1.add(site1)
        used2.add(site2)
        accepted.append((site1, site2))
    return np.asarray(accepted, dtype=np.uint32).reshape(-1, 2)


def decode_matches(rows: int, cols: int, data: bytes | None) -> np.ndarray:
    if rows <= 0 or not data:
        return np.empty((0, 2), dtype=np.uint32)
    if cols < 2:
        raise RuntimeError(f"match table has unsupported column count {cols}")
    return np.frombuffer(data, dtype=np.uint32).reshape(rows, cols)[:, :2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-db", type=Path, required=True)
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    args = parser.parse_args()
    if args.output_db.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_db}")
    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(f"file:{args.input_db}?mode=ro", uri=True)
    output = sqlite3.connect(args.output_db)
    try:
        source.backup(output)
        canonical, descriptors, image_stats = load_features(output)
        pair_assignments: dict[int, set[tuple[int, int]]] = {}
        match_before = 0
        match_after = 0
        pair_rows = output.execute(
            "SELECT pair_id, rows, cols, data FROM matches ORDER BY pair_id"
        ).fetchall()
        with output:
            for pair_id, rows, cols, data in pair_rows:
                image1, image2 = image_pair(pair_id)
                matches = decode_matches(rows, cols, data)
                assigned = canonical_assignments(
                    matches,
                    canonical[image1],
                    canonical[image2],
                    descriptors[image1],
                    descriptors[image2],
                )
                pair_assignments[pair_id] = {
                    (int(first), int(second)) for first, second in assigned
                }
                output.execute(
                    "UPDATE matches SET rows = ?, cols = 2, data = ? "
                    "WHERE pair_id = ?",
                    (len(assigned), assigned.tobytes(), pair_id),
                )
                match_before += len(matches)
                match_after += len(assigned)

        geometry_before = 0
        geometry_after = 0
        geometry_rows = output.execute(
            "SELECT pair_id, rows, cols, data FROM two_view_geometries "
            "ORDER BY pair_id"
        ).fetchall()
        with output:
            for pair_id, rows, cols, data in geometry_rows:
                image1, image2 = image_pair(pair_id)
                inliers = decode_matches(rows, cols, data)
                allowed = pair_assignments.get(pair_id, set())
                canonical_inliers: list[tuple[int, int]] = []
                seen: set[tuple[int, int]] = set()
                for first, second in inliers:
                    pair = (
                        int(canonical[image1][first]),
                        int(canonical[image2][second]),
                    )
                    if pair not in allowed or pair in seen:
                        continue
                    seen.add(pair)
                    canonical_inliers.append(pair)
                packed = np.asarray(canonical_inliers, dtype=np.uint32).reshape(-1, 2)
                output.execute(
                    "UPDATE two_view_geometries "
                    "SET rows = ?, cols = 2, data = ? WHERE pair_id = ?",
                    (len(packed), packed.tobytes(), pair_id),
                )
                geometry_before += len(inliers)
                geometry_after += len(packed)
        output.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        output.close()
        source.close()

    keypoints = sum(row["keypoints"] for row in image_stats.values())
    unique_sites = sum(row["unique_exact_xy_sites"] for row in image_stats.values())
    payload = {
        "schema": "pocketworld_exact_xy_match_ownership_v1",
        "input_db": str(args.input_db),
        "output_db": str(args.output_db),
        "images": len(image_stats),
        "keypoints": keypoints,
        "unique_exact_xy_sites": unique_sites,
        "aliased_descriptors": keypoints - unique_sites,
        "matches_before": match_before,
        "matches_after": match_after,
        "two_view_inliers_before": geometry_before,
        "two_view_inliers_after": geometry_after,
        "per_image": image_stats,
    }
    args.stats.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
