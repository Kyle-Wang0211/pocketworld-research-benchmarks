#!/usr/bin/env python3
"""Build globally consistent tracks from geometrically verified physical sites.

SIFT orientation/scale variants at bit-identical x/y remain independent through
matching and two-view RANSAC.  Afterwards they vote for one physical-site edge.
Candidate edges are processed as a maximum-support forest; a merge is refused
when it would put two physical sites from the same image into one track.

The input database is immutable.  Raw matches are retained in the snapshot for
future re-verification; only verified track-birth hypotheses are rewritten.
No image, frame, generated Point3D, LiDAR, or sceneDepth is read or removed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pycolmap


Node = tuple[int, int]


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


def canonical_sites(keypoints: np.ndarray) -> np.ndarray:
    xy_bits = np.ascontiguousarray(keypoints[:, :2], dtype=np.float32).view(np.uint32)
    canonical_by_xy: dict[tuple[int, int], int] = {}
    canonical = np.empty(len(keypoints), dtype=np.uint32)
    for feature_id, bits in enumerate(xy_bits):
        key = int(bits[0]), int(bits[1])
        canonical[feature_id] = canonical_by_xy.setdefault(key, feature_id)
    return canonical


@dataclass
class EdgeEvidence:
    pair_id: int
    image_id1: int
    image_id2: int
    site1: int
    site2: int
    support: int = 0
    max_dot: int = 0
    min_sampson_px: float = float("inf")

    @property
    def nodes(self) -> tuple[Node, Node]:
        return (self.image_id1, self.site1), (self.image_id2, self.site2)


class ConflictFreeForest:
    def __init__(self) -> None:
        self.parent: dict[Node, Node] = {}
        self.images: dict[Node, set[int]] = {}

    def find(self, node: Node) -> Node:
        if node not in self.parent:
            self.parent[node] = node
            self.images[node] = {node[0]}
            return node
        if self.parent[node] != node:
            self.parent[node] = self.find(self.parent[node])
        return self.parent[node]

    def admit(self, first: Node, second: Node) -> str:
        root1 = self.find(first)
        root2 = self.find(second)
        if root1 == root2:
            return "cycle"
        if self.images[root1].intersection(self.images[root2]):
            return "same_image_conflict"
        if root2 < root1:
            root1, root2 = root2, root1
        self.parent[root2] = root1
        self.images[root1].update(self.images.pop(root2))
        return "merged"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--min-inliers", type=int, default=15)
    parser.add_argument(
        "--ordering",
        choices=("backbone", "geometry", "descriptor"),
        default="backbone",
    )
    args = parser.parse_args()
    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")
    sqlite_snapshot(args.input, args.output)

    with pycolmap.Database.open(args.output) as database:
        images = {int(image.image_id): image for image in database.read_all_images()}
        descriptors = {
            image_id: np.asarray(
                database.read_descriptors(image_id).data, dtype=np.int32
            )
            for image_id in images
        }
        keypoints = {
            image_id: np.asarray(database.read_keypoints(image_id), dtype=np.float32)
            for image_id in images
        }
        sites = {
            image_id: canonical_sites(keypoints[image_id]) for image_id in images
        }
        pair_ids, geometries = database.read_two_view_geometries()
        geometry_by_pair = {
            int(pair_id): geometry
            for pair_id, geometry in zip(pair_ids, geometries, strict=True)
        }

        evidence: dict[tuple[int, int, int], EdgeEvidence] = {}
        raw_inliers = 0
        for pair_id, geometry in geometry_by_pair.items():
            image_id1, image_id2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
            fundamental = np.asarray(geometry.F, dtype=np.float64)
            for feature1, feature2 in np.asarray(
                geometry.inlier_matches, dtype=np.uint32
            ):
                raw_inliers += 1
                site1 = int(sites[image_id1][int(feature1)])
                site2 = int(sites[image_id2][int(feature2)])
                key = pair_id, site1, site2
                edge = evidence.get(key)
                if edge is None:
                    edge = EdgeEvidence(pair_id, image_id1, image_id2, site1, site2)
                    evidence[key] = edge
                edge.support += 1
                dot = int(
                    np.dot(
                        descriptors[image_id1][int(feature1)],
                        descriptors[image_id2][int(feature2)],
                    )
                )
                edge.max_dot = max(edge.max_dot, dot)
                point1 = np.append(
                    keypoints[image_id1][int(feature1), :2].astype(np.float64), 1.0
                )
                point2 = np.append(
                    keypoints[image_id2][int(feature2), :2].astype(np.float64), 1.0
                )
                line2 = fundamental @ point1
                line1 = fundamental.T @ point2
                denominator = (
                    line1[0] ** 2
                    + line1[1] ** 2
                    + line2[0] ** 2
                    + line2[1] ** 2
                )
                if denominator > 1e-18:
                    sampson_px = abs(float(point2 @ fundamental @ point1)) / np.sqrt(
                        denominator
                    )
                    edge.min_sampson_px = min(edge.min_sampson_px, sampson_px)

        node_neighbors: dict[Node, set[Node]] = defaultdict(set)
        node_support: Counter[Node] = Counter()
        for edge in evidence.values():
            first, second = edge.nodes
            node_neighbors[first].add(second)
            node_neighbors[second].add(first)
            node_support[first] += edge.support
            node_support[second] += edge.support

        edges = list(evidence.values())
        if args.ordering in ("backbone", "geometry"):
            edges.sort(
                key=lambda edge: (
                    -min(len(node_neighbors[node]) for node in edge.nodes),
                    *(
                        (edge.min_sampson_px,)
                        if args.ordering == "geometry"
                        else (-min(node_support[node] for node in edge.nodes),)
                    ),
                    -edge.support,
                    edge.min_sampson_px,
                    -sum(len(node_neighbors[node]) for node in edge.nodes),
                    -edge.max_dot,
                    edge.image_id1,
                    edge.image_id2,
                    edge.site1,
                    edge.site2,
                )
            )
        else:
            edges.sort(
                key=lambda edge: (
                    -edge.max_dot,
                    -edge.support,
                    edge.image_id1,
                    edge.image_id2,
                    edge.site1,
                    edge.site2,
                )
            )

        forest = ConflictFreeForest()
        decisions: Counter[str] = Counter()
        admitted: dict[int, set[tuple[int, int]]] = defaultdict(set)
        rejected: dict[int, set[tuple[int, int]]] = defaultdict(set)
        for edge in edges:
            decision = forest.admit(*edge.nodes)
            decisions[decision] += 1
            pair = edge.site1, edge.site2
            if decision == "same_image_conflict":
                rejected[edge.pair_id].add(pair)
            else:
                admitted[edge.pair_id].add(pair)

        pairs_written = 0
        pairs_below_gate = 0
        for pair_id, geometry in geometry_by_pair.items():
            image_id1, image_id2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
            kept = np.asarray(sorted(admitted[pair_id]), dtype=np.uint32).reshape(-1, 2)
            database.delete_two_view_geometry(image_id1, image_id2)
            if len(kept) >= args.min_inliers:
                geometry.inlier_matches = kept
                database.write_two_view_geometry(image_id1, image_id2, geometry)
                pairs_written += 1
            else:
                pairs_below_gate += 1

    component_sizes: Counter[Node] = Counter()
    for node in forest.parent:
        component_sizes[forest.find(node)] += 1
    stats = {
        "schema": "pocketworld_global_physical_site_track_forest_v2",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "pycolmap_version": pycolmap.__version__,
        "ordering": args.ordering,
        "raw_geometry_inliers": raw_inliers,
        "unique_physical_site_edges": len(evidence),
        "admitted_site_edges": sum(map(len, admitted.values())),
        "rejected_same_image_conflicts": sum(map(len, rejected.values())),
        "decisions": dict(sorted(decisions.items())),
        "geometry_pairs_written": pairs_written,
        "geometry_pairs_below_min_inliers": pairs_below_gate,
        "track_components": len(component_sizes),
        "track_length_median": (
            float(np.median(list(component_sizes.values())))
            if component_sizes
            else 0.0
        ),
        "track_length_max": max(component_sizes.values(), default=0),
        "raw_matches_modified": False,
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_or_generated_points": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
