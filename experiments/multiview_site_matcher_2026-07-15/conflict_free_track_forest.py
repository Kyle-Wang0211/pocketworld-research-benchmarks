#!/usr/bin/env python3
"""Build a conflict-free verified correspondence graph before triangulation.

The old GLOMAP track builder blindly concatenates pairwise inlier components.
That can place two distinct features from the same image in one component, so a
single physical site receives ambiguous track labels before any 3D point is
born.  This experiment follows the maximum-spanning-forest construction used
by Pixel-Perfect SfM: process high-similarity verified edges first and refuse a
component merge whenever the two components already share an image.

Only correspondence rows in a copied COLMAP database are changed.  No image,
frame, observation, or generated Point3D is deleted, and no LiDAR/sceneDepth is
read.
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


class ConflictFreeUnionFind:
    def __init__(self) -> None:
        self.parent: dict[Node, Node] = {}
        self.images: dict[Node, set[int]] = {}

    def add(self, node: Node) -> None:
        if node in self.parent:
            return
        self.parent[node] = node
        self.images[node] = {node[0]}

    def find(self, node: Node) -> Node:
        self.add(node)
        parent = self.parent[node]
        if parent != node:
            self.parent[node] = self.find(parent)
        return self.parent[node]

    def try_union(self, first: Node, second: Node) -> str:
        root1 = self.find(first)
        root2 = self.find(second)
        if root1 == root2:
            return "cycle"
        if self.images[root1].intersection(self.images[root2]):
            return "image_conflict"
        if root2 < root1:
            root1, root2 = root2, root1
        self.parent[root2] = root1
        self.images[root1].update(self.images.pop(root2))
        return "merged"


@dataclass(frozen=True)
class VerifiedEdge:
    pair_id: int
    image_id1: int
    image_id2: int
    feature_id1: int
    feature_id2: int
    cosine: float

    @property
    def nodes(self) -> tuple[Node, Node]:
        return (
            (self.image_id1, self.feature_id1),
            (self.image_id2, self.feature_id2),
        )

    @property
    def match(self) -> tuple[int, int]:
        return self.feature_id1, self.feature_id2


def descriptor_cosine(
    descriptors: dict[int, np.ndarray], norms: dict[int, np.ndarray], edge: VerifiedEdge
) -> float:
    first = descriptors[edge.image_id1][edge.feature_id1]
    second = descriptors[edge.image_id2][edge.feature_id2]
    denominator = norms[edge.image_id1][edge.feature_id1] * norms[edge.image_id2][
        edge.feature_id2
    ]
    return float(np.dot(first, second) / denominator)


def blind_component_conflicts(edges: list[VerifiedEdge]) -> tuple[int, int]:
    parent: dict[Node, Node] = {}

    def find(node: Node) -> Node:
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    for edge in edges:
        first, second = edge.nodes
        root1 = find(first)
        root2 = find(second)
        if root1 != root2:
            if root2 < root1:
                root1, root2 = root2, root1
            parent[root2] = root1
    components: dict[Node, list[Node]] = defaultdict(list)
    for node in parent:
        components[find(node)].append(node)
    conflicting = 0
    duplicate_observations = 0
    for nodes in components.values():
        image_counts = Counter(image_id for image_id, _ in nodes)
        extra = sum(count - 1 for count in image_counts.values() if count > 1)
        if extra:
            conflicting += 1
            duplicate_observations += extra
    return conflicting, duplicate_observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--min-inliers", type=int, default=15)
    parser.add_argument(
        "--ordering",
        choices=("descriptor", "support"),
        default="descriptor",
        help="edge priority before the conflict-free union",
    )
    args = parser.parse_args()
    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")

    sqlite_snapshot(args.input, args.output)
    with pycolmap.Database.open(args.output) as database:
        descriptors = {
            int(image.image_id): np.asarray(
                database.read_descriptors(image.image_id).data, dtype=np.float64
            )
            for image in database.read_all_images()
        }
        norms = {
            image_id: np.maximum(np.linalg.norm(values, axis=1), 1e-12)
            for image_id, values in descriptors.items()
        }
        pair_ids, geometries = database.read_two_view_geometries()
        geometry_by_pair = {
            int(pair_id): geometry
            for pair_id, geometry in zip(pair_ids, geometries, strict=True)
        }

        edges: list[VerifiedEdge] = []
        for pair_id, geometry in geometry_by_pair.items():
            image_id1, image_id2 = pycolmap.pair_id_to_image_pair(pair_id)
            for feature_id1, feature_id2 in np.asarray(
                geometry.inlier_matches, dtype=np.uint32
            ):
                edge = VerifiedEdge(
                    pair_id=pair_id,
                    image_id1=int(image_id1),
                    image_id2=int(image_id2),
                    feature_id1=int(feature_id1),
                    feature_id2=int(feature_id2),
                    cosine=0.0,
                )
                edges.append(
                    VerifiedEdge(
                        **{
                            **edge.__dict__,
                            "cosine": descriptor_cosine(descriptors, norms, edge),
                        }
                    )
                )

        blind_conflicting_components, blind_duplicate_observations = (
            blind_component_conflicts(edges)
        )
        node_degree = Counter(node for edge in edges for node in edge.nodes)
        if args.ordering == "support":
            # A high-similarity edge attached to two isolated repeated-texture
            # features must not outrank the backbone seen consistently across
            # many views.  Bottleneck degree is primary, total degree and
            # RootSIFT cosine are deterministic tie breakers.
            edges.sort(
                key=lambda edge: (
                    -min(node_degree[node] for node in edge.nodes),
                    -sum(node_degree[node] for node in edge.nodes),
                    -edge.cosine,
                    edge.image_id1,
                    edge.image_id2,
                    edge.feature_id1,
                    edge.feature_id2,
                )
            )
        else:
            edges.sort(
                key=lambda edge: (
                    -edge.cosine,
                    edge.image_id1,
                    edge.image_id2,
                    edge.feature_id1,
                    edge.feature_id2,
                )
            )
        forest = ConflictFreeUnionFind()
        admitted: dict[int, set[tuple[int, int]]] = defaultdict(set)
        rejected: dict[int, set[tuple[int, int]]] = defaultdict(set)
        decision_counts: Counter[str] = Counter()
        rejected_cosines: list[float] = []
        for edge in edges:
            decision = forest.try_union(*edge.nodes)
            decision_counts[decision] += 1
            if decision == "image_conflict":
                rejected[edge.pair_id].add(edge.match)
                rejected_cosines.append(edge.cosine)
            else:
                admitted[edge.pair_id].add(edge.match)

        geometry_pairs_written = 0
        geometry_pairs_below_gate = 0
        raw_matches_rejected = 0
        pair_details: list[dict[str, object]] = []
        for pair_id, geometry in geometry_by_pair.items():
            image_id1, image_id2 = pycolmap.pair_id_to_image_pair(pair_id)
            kept = sorted(admitted[pair_id])
            removed = rejected[pair_id]
            original_count = len(geometry.inlier_matches)
            database.delete_two_view_geometry(image_id1, image_id2)
            if len(kept) >= args.min_inliers:
                geometry.inlier_matches = np.asarray(kept, dtype=np.uint32)
                database.write_two_view_geometry(image_id1, image_id2, geometry)
                geometry_pairs_written += 1
            else:
                geometry_pairs_below_gate += 1

            raw = np.asarray(database.read_matches(image_id1, image_id2), dtype=np.uint32)
            if len(raw) and removed:
                filtered = np.asarray(
                    [row for row in raw.tolist() if tuple(map(int, row)) not in removed],
                    dtype=np.uint32,
                ).reshape(-1, 2)
                raw_matches_rejected += len(raw) - len(filtered)
                database.delete_matches(image_id1, image_id2)
                database.write_matches(image_id1, image_id2, filtered)
            if removed:
                pair_details.append(
                    {
                        "pair_id": pair_id,
                        "image_ids": [int(image_id1), int(image_id2)],
                        "verified_before": original_count,
                        "verified_after": len(kept),
                        "rejected": len(removed),
                    }
                )

    component_sizes = Counter()
    for node in forest.parent:
        component_sizes[forest.find(node)] += 1
    rejected_array = np.asarray(rejected_cosines, dtype=np.float64)
    stats = {
        "schema": "pocketworld_conflict_free_track_forest_v1",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "pycolmap_version": pycolmap.__version__,
        "ordering": args.ordering,
        "verified_edges_input": len(edges),
        "verified_edges_admitted": sum(len(values) for values in admitted.values()),
        "verified_edges_rejected_image_conflict": sum(
            len(values) for values in rejected.values()
        ),
        "edge_decisions": dict(sorted(decision_counts.items())),
        "raw_matches_rejected": raw_matches_rejected,
        "geometry_pairs_written": geometry_pairs_written,
        "geometry_pairs_below_min_inliers": geometry_pairs_below_gate,
        "blind_graph_conflicting_components": blind_conflicting_components,
        "blind_graph_duplicate_same_image_observations": blind_duplicate_observations,
        "forest_components": len(component_sizes),
        "forest_track_size": {
            "median": float(np.median(list(component_sizes.values()))),
            "max": int(max(component_sizes.values(), default=0)),
        },
        "rejected_edge_cosine": {
            "median": float(np.median(rejected_array)) if len(rejected_array) else None,
            "min": float(np.min(rejected_array)) if len(rejected_array) else None,
            "max": float(np.max(rejected_array)) if len(rejected_array) else None,
        },
        "pairs_with_rejections": pair_details,
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_or_generated_points": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
