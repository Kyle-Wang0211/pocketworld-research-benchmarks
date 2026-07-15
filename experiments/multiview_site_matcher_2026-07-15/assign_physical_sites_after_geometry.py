#!/usr/bin/env python3
"""Resolve SIFT orientation aliases after robust two-view geometry.

Descriptor-level one-to-many hypotheses are useful to RANSAC, but exact-x/y
orientation aliases must not become independent track identities.  This tool
first estimates COLMAP two-view geometry from every original descriptor match,
then collapses inliers to physical sites and solves a maximum-weight bipartite
assignment per connected component.  Only the assigned canonical site pairs
are persisted for track establishment.  The input database is never modified.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pycolmap
from scipy.optimize import linear_sum_assignment


@dataclass
class SiteTable:
    site_of_descriptor: np.ndarray
    canonical_descriptor: np.ndarray


@dataclass
class EdgeEvidence:
    support: int = 0
    max_dot: int = 0


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


def build_sites(keypoints: np.ndarray) -> SiteTable:
    xy_bits = np.ascontiguousarray(keypoints[:, :2], dtype=np.float32).view(np.uint32)
    site_by_xy: dict[tuple[int, int], int] = {}
    site_of_descriptor = np.empty(len(keypoints), dtype=np.int32)
    canonical: list[int] = []
    for descriptor, bits in enumerate(xy_bits):
        key = (int(bits[0]), int(bits[1]))
        site = site_by_xy.get(key)
        if site is None:
            site = len(canonical)
            site_by_xy[key] = site
            canonical.append(descriptor)
        site_of_descriptor[descriptor] = site
    return SiteTable(site_of_descriptor, np.asarray(canonical, dtype=np.uint32))


def assigned_site_pairs(
    inliers: np.ndarray,
    sites1: SiteTable,
    sites2: SiteTable,
    descriptors1: np.ndarray,
    descriptors2: np.ndarray,
) -> tuple[np.ndarray, int, int]:
    evidence: dict[tuple[int, int], EdgeEvidence] = {}
    adjacency1: dict[int, set[int]] = defaultdict(set)
    adjacency2: dict[int, set[int]] = defaultdict(set)
    for descriptor1, descriptor2 in np.asarray(inliers, dtype=np.uint32):
        site1 = int(sites1.site_of_descriptor[int(descriptor1)])
        site2 = int(sites2.site_of_descriptor[int(descriptor2)])
        key = (site1, site2)
        edge = evidence.setdefault(key, EdgeEvidence())
        edge.support += 1
        dot = int(
            np.dot(
                descriptors1[int(descriptor1)].astype(np.int32),
                descriptors2[int(descriptor2)].astype(np.int32),
            )
        )
        edge.max_dot = max(edge.max_dot, dot)
        adjacency1[site1].add(site2)
        adjacency2[site2].add(site1)

    selected: list[tuple[int, int]] = []
    remaining = set(adjacency1)
    max_component = 0
    while remaining:
        first = min(remaining)
        queue: deque[tuple[int, int]] = deque([(0, first)])
        component1: set[int] = set()
        component2: set[int] = set()
        while queue:
            side, site = queue.popleft()
            if side == 0:
                if site in component1:
                    continue
                component1.add(site)
                queue.extend((1, other) for other in adjacency1[site])
            else:
                if site in component2:
                    continue
                component2.add(site)
                queue.extend((0, other) for other in adjacency2[site])
        remaining.difference_update(component1)
        rows = sorted(component1)
        cols = sorted(component2)
        max_component = max(max_component, len(rows), len(cols))
        size = max(len(rows), len(cols))
        weights = np.zeros((size, size), dtype=np.int64)
        row_of = {site: index for index, site in enumerate(rows)}
        col_of = {site: index for index, site in enumerate(cols)}
        for (site1, site2), edge in evidence.items():
            row = row_of.get(site1)
            col = col_of.get(site2)
            if row is None or col is None:
                continue
            # Support from independent SIFT orientations dominates the best
            # descriptor similarity; both are deterministic integer evidence.
            weights[row, col] = edge.support * 1_000_000 + edge.max_dot
        assigned_rows, assigned_cols = linear_sum_assignment(weights, maximize=True)
        for row, col in zip(assigned_rows, assigned_cols, strict=True):
            if row >= len(rows) or col >= len(cols) or weights[row, col] <= 0:
                continue
            selected.append((rows[row], cols[col]))

    selected.sort()
    pairs = np.asarray(
        [
            (sites1.canonical_descriptor[site1], sites2.canonical_descriptor[site2])
            for site1, site2 in selected
        ],
        dtype=np.uint32,
    ).reshape((-1, 2))
    return pairs, len(evidence), max_component


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--max-error-px", type=float, default=4.0)
    parser.add_argument("--min-inliers", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")
    sqlite_snapshot(args.input, args.output)

    database = pycolmap.Database.open(str(args.output))
    cameras = {int(camera.camera_id): camera for camera in database.read_all_cameras()}
    images = {int(image.image_id): image for image in database.read_all_images()}
    keypoints = {
        image_id: np.asarray(database.read_keypoints(image_id), dtype=np.float32)
        for image_id in images
    }
    descriptors = {
        image_id: np.asarray(
            database.read_descriptors(image_id).data, dtype=np.uint8
        )
        for image_id in images
    }
    sites = {image_id: build_sites(keypoints[image_id]) for image_id in images}
    pair_ids, pair_matches = database.read_all_matches()

    options = pycolmap.TwoViewGeometryOptions()
    options.min_num_inliers = args.min_inliers
    options.ransac.max_error = args.max_error_px
    options.ransac.random_seed = args.seed
    options.ransac.num_threads = 1

    matches_before = 0
    raw_inliers = 0
    unique_site_edges = 0
    assigned_inliers = 0
    geometry_pairs = 0
    rejected_pairs = 0
    max_component = 0
    configs: Counter[str] = Counter()
    for index, (pair_id, matches) in enumerate(
        zip(pair_ids, pair_matches, strict=True), start=1
    ):
        image_id1, image_id2 = pycolmap.pair_id_to_image_pair(pair_id)
        image1 = images[int(image_id1)]
        image2 = images[int(image_id2)]
        matches = np.asarray(matches, dtype=np.uint32)
        matches_before += len(matches)
        geometry = pycolmap.estimate_two_view_geometry(
            cameras[int(image1.camera_id)],
            keypoints[int(image_id1)][:, :2].astype(np.float64),
            cameras[int(image2.camera_id)],
            keypoints[int(image_id2)][:, :2].astype(np.float64),
            matches,
            options,
        )
        raw_inliers += len(geometry.inlier_matches)
        assigned, edge_count, component_size = assigned_site_pairs(
            geometry.inlier_matches,
            sites[int(image_id1)],
            sites[int(image_id2)],
            descriptors[int(image_id1)],
            descriptors[int(image_id2)],
        )
        unique_site_edges += edge_count
        max_component = max(max_component, component_size)
        if len(assigned) < args.min_inliers:
            if database.exists_two_view_geometry(image_id1, image_id2):
                database.delete_two_view_geometry(image_id1, image_id2)
            rejected_pairs += 1
        else:
            database.delete_matches(image_id1, image_id2)
            database.write_matches(image_id1, image_id2, assigned)
            geometry.inlier_matches = assigned
            if database.exists_two_view_geometry(image_id1, image_id2):
                database.update_two_view_geometry(image_id1, image_id2, geometry)
            else:
                database.write_two_view_geometry(image_id1, image_id2, geometry)
            assigned_inliers += len(assigned)
            geometry_pairs += 1
            configs[str(geometry.config)] += 1
        if index % 100 == 0 or index == len(pair_ids):
            print(f"physical assignment {index}/{len(pair_ids)} pairs", flush=True)
    database.close()

    stats = {
        "schema": "pocketworld_post_geometry_physical_site_assignment_v1",
        "pycolmap_version": pycolmap.__version__,
        "input_db": str(args.input),
        "output_db": str(args.output),
        "seed": args.seed,
        "max_error_px": args.max_error_px,
        "min_inliers": args.min_inliers,
        "match_pairs": len(pair_ids),
        "matches_before": matches_before,
        "raw_geometry_inliers": raw_inliers,
        "unique_physical_site_edges": unique_site_edges,
        "assigned_inliers": assigned_inliers,
        "geometry_pairs": geometry_pairs,
        "rejected_pairs": rejected_pairs,
        "max_assignment_component": max_component,
        "geometry_configs": dict(sorted(configs.items())),
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
