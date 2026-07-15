#!/usr/bin/env python3
"""Build physical-site matches and conflict-aware multi-view tracks.

This is an experiment-only database transform.  It changes neither images nor
features.  Exact-equal detector locations are treated as one physical site,
descriptor aliases vote for site-to-site correspondences, and verified edges
are processed in descending multi-view support.  An edge may join two track
components only when doing so preserves the invariant "at most one physical
site from each image".  This prevents a single transitive bridge from merging
two scene points before triangulation.

No reconstructed point is deleted: the output correspondence graph controls
which tracks are allowed to be born in the first place.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from canonicalize_match_sites import (
    decode_matches,
    image_pair,
    load_features,
)
from analyze_arkit_epipolar import fundamental, sampson_px


Node = tuple[int, int]
SitePair = tuple[int, int]


@dataclass(frozen=True)
class Candidate:
    pair_id: int
    image1: int
    image2: int
    site1: int
    site2: int
    votes: int
    min_distance: int
    pose_residual_px: float = 0.0

    @property
    def node1(self) -> Node:
        return self.image1, self.site1

    @property
    def node2(self) -> Node:
        return self.image2, self.site2


class ConflictAwareUnionFind:
    def __init__(self) -> None:
        self.parent: dict[Node, Node] = {}
        self.size: dict[Node, int] = {}
        self.images: dict[Node, dict[int, int]] = {}

    def add(self, node: Node) -> None:
        if node in self.parent:
            return
        self.parent[node] = node
        self.size[node] = 1
        self.images[node] = {node[0]: node[1]}

    def find(self, node: Node) -> Node:
        self.add(node)
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != node:
            parent = self.parent[node]
            self.parent[node] = root
            node = parent
        return root

    def union_if_conflict_free(self, first: Node, second: Node) -> tuple[bool, bool]:
        root1 = self.find(first)
        root2 = self.find(second)
        if root1 == root2:
            return True, False
        images1 = self.images[root1]
        images2 = self.images[root2]
        if images1.keys() & images2.keys():
            return False, False
        if self.size[root1] < self.size[root2]:
            root1, root2 = root2, root1
            images1, images2 = images2, images1
        self.parent[root2] = root1
        self.size[root1] += self.size.pop(root2)
        images1.update(images2)
        del self.images[root2]
        return True, True


def descriptor_distance(
    first: int,
    second: int,
    descriptors1: np.ndarray,
    descriptors2: np.ndarray,
) -> int:
    delta = descriptors1[first].astype(np.int16) - descriptors2[second].astype(
        np.int16
    )
    return int(np.sum(delta.astype(np.int32) ** 2, dtype=np.int64))


def aggregate_candidates(
    pair_id: int,
    matches: np.ndarray,
    canonical: dict[int, np.ndarray],
    descriptors: dict[int, np.ndarray],
    pose_residuals: np.ndarray | None = None,
) -> dict[SitePair, Candidate]:
    image1, image2 = image_pair(pair_id)
    accum: dict[SitePair, list[float]] = {}
    for match_index, (first, second) in enumerate(matches):
        raw1 = int(first)
        raw2 = int(second)
        pair = (int(canonical[image1][raw1]), int(canonical[image2][raw2]))
        distance = descriptor_distance(
            raw1, raw2, descriptors[image1], descriptors[image2]
        )
        pose_residual = (
            float(pose_residuals[match_index])
            if pose_residuals is not None
            else 0.0
        )
        state = accum.setdefault(pair, [0, distance, pose_residual])
        state[0] += 1
        state[1] = min(state[1], distance)
        state[2] = min(state[2], pose_residual)
    return {
        pair: Candidate(
            pair_id=pair_id,
            image1=image1,
            image2=image2,
            site1=pair[0],
            site2=pair[1],
            votes=int(state[0]),
            min_distance=int(state[1]),
            pose_residual_px=state[2],
        )
        for pair, state in accum.items()
    }


def direct_triangle_support(candidates: list[Candidate]) -> dict[tuple[int, SitePair], int]:
    neighbors: dict[Node, set[Node]] = defaultdict(set)
    for candidate in candidates:
        neighbors[candidate.node1].add(candidate.node2)
        neighbors[candidate.node2].add(candidate.node1)
    support: dict[tuple[int, SitePair], int] = {}
    for candidate in candidates:
        common = neighbors[candidate.node1] & neighbors[candidate.node2]
        support[(candidate.pair_id, (candidate.site1, candidate.site2))] = len(
            {node[0] for node in common}
        )
    return support


def select_conflict_aware_edges(
    candidates: list[Candidate],
) -> tuple[set[tuple[int, SitePair]], dict[str, int]]:
    triangle_support = direct_triangle_support(candidates)
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -triangle_support[
                (candidate.pair_id, (candidate.site1, candidate.site2))
            ],
            -candidate.votes,
            candidate.pose_residual_px,
            candidate.min_distance,
            candidate.pair_id,
            candidate.site1,
            candidate.site2,
        ),
    )
    union_find = ConflictAwareUnionFind()
    accepted: set[tuple[int, SitePair]] = set()
    rejected = 0
    cycle_edges = 0
    accepted_with_triangle = 0
    for candidate in ordered:
        allowed, merged = union_find.union_if_conflict_free(
            candidate.node1, candidate.node2
        )
        if not allowed:
            rejected += 1
            continue
        accepted.add((candidate.pair_id, (candidate.site1, candidate.site2)))
        if not merged:
            cycle_edges += 1
        if triangle_support[
            (candidate.pair_id, (candidate.site1, candidate.site2))
        ]:
            accepted_with_triangle += 1
    component_sizes = sorted(union_find.size.values(), reverse=True)
    stats = {
        "candidate_edges": len(candidates),
        "accepted_edges": len(accepted),
        "rejected_conflict_edges": rejected,
        "accepted_cycle_edges": cycle_edges,
        "accepted_edges_with_direct_triangle": accepted_with_triangle,
        "components": len(component_sizes),
        "components_length_3plus": sum(size >= 3 for size in component_sizes),
        "largest_component": component_sizes[0] if component_sizes else 0,
    }
    return accepted, stats


def pack_pairs(pairs: list[SitePair]) -> bytes:
    return np.asarray(pairs, dtype=np.uint32).reshape(-1, 2).tobytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-db", type=Path, required=True)
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--max-arkit-sampson-px", type=float, default=0.0)
    parser.add_argument("--rank-by-arkit-sampson", action="store_true")
    args = parser.parse_args()
    if (
        args.max_arkit_sampson_px > 0.0 or args.rank_by_arkit_sampson
    ) and args.ledger is None:
        parser.error("--ledger is required for ARKit Sampson scoring")
    if args.output_db.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_db}")
    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(f"file:{args.input_db}?mode=ro", uri=True)
    output = sqlite3.connect(args.output_db)
    try:
        source.backup(output)
        canonical, descriptors, image_stats = load_features(output)
        pose_rows = None
        intrinsic = None
        if args.max_arkit_sampson_px > 0.0 or args.rank_by_arkit_sampson:
            pose_rows = {
                row["frameId"]: row
                for row in (
                    json.loads(line)
                    for line in args.ledger.read_text().splitlines()
                    if line
                )
            }
            cameras = output.execute(
                "SELECT model, params FROM cameras"
            ).fetchall()
            if len(cameras) != 1:
                raise RuntimeError(
                    f"pose gate requires one shared camera, got {len(cameras)}"
                )
            model, params_blob = cameras[0]
            params = np.frombuffer(params_blob, dtype=np.float64)
            if model == 0:
                fx = fy = params[0]
                cx, cy = params[1:3]
            elif model == 1:
                fx, fy, cx, cy = params[:4]
            else:
                raise RuntimeError(f"unsupported pose-gate camera model {model}")
            intrinsic = np.asarray(
                [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
                dtype=np.float64,
            )
        raw_rows = {
            pair_id: decode_matches(rows, cols, data)
            for pair_id, rows, cols, data in output.execute(
                "SELECT pair_id, rows, cols, data FROM matches ORDER BY pair_id"
            )
        }
        geometry_rows = {
            pair_id: (rows, cols, data)
            for pair_id, rows, cols, data in output.execute(
                "SELECT pair_id, rows, cols, data FROM two_view_geometries "
                "ORDER BY pair_id"
            )
        }

        verified_by_pair: dict[int, dict[SitePair, Candidate]] = {}
        all_candidates: list[Candidate] = []
        inliers_before = 0
        inliers_after_pose_gate = 0
        for pair_id, (rows, cols, data) in geometry_rows.items():
            inliers = decode_matches(rows, cols, data)
            inliers_before += len(inliers)
            pose_residuals = None
            if pose_rows is not None and intrinsic is not None and len(inliers):
                image1, image2 = image_pair(pair_id)
                matrix = fundamental(
                    pose_rows[image1 - 1], pose_rows[image2 - 1], intrinsic
                )
                pose_residuals = sampson_px(
                    # load_features intentionally leaves keypoints in the DB;
                    # read their physical xy here instead of alias descriptors.
                    np.frombuffer(
                        output.execute(
                            "SELECT data FROM keypoints WHERE image_id = ?",
                            (image1,),
                        ).fetchone()[0],
                        dtype=np.float32,
                    ).reshape(len(canonical[image1]), -1)[inliers[:, 0], :2],
                    np.frombuffer(
                        output.execute(
                            "SELECT data FROM keypoints WHERE image_id = ?",
                            (image2,),
                        ).fetchone()[0],
                        dtype=np.float32,
                    ).reshape(len(canonical[image2]), -1)[inliers[:, 1], :2],
                    matrix,
                )
                if args.max_arkit_sampson_px > 0.0:
                    keep = pose_residuals <= args.max_arkit_sampson_px
                    inliers = inliers[keep]
                    pose_residuals = pose_residuals[keep]
            inliers_after_pose_gate += len(inliers)
            aggregated = aggregate_candidates(
                pair_id,
                inliers,
                canonical,
                descriptors,
                pose_residuals if args.rank_by_arkit_sampson else None,
            )
            verified_by_pair[pair_id] = aggregated
            all_candidates.extend(aggregated.values())

        accepted, track_stats = select_conflict_aware_edges(all_candidates)
        selected_by_pair: dict[int, list[SitePair]] = defaultdict(list)
        for pair_id, pair in accepted:
            selected_by_pair[pair_id].append(pair)
        for pairs in selected_by_pair.values():
            pairs.sort()

        raw_before = sum(len(matches) for matches in raw_rows.values())
        raw_after = 0
        inliers_after = 0
        with output:
            for pair_id, raw_matches in raw_rows.items():
                raw_candidates = aggregate_candidates(
                    pair_id, raw_matches, canonical, descriptors
                )
                verified = set(selected_by_pair.get(pair_id, []))
                # The raw table is not used to weaken verified geometry.  It is
                # made consistent by keeping every accepted verified site pair,
                # then adding non-conflicting raw-only pairs in score order.
                image1, image2 = image_pair(pair_id)
                del image1, image2
                used1 = {pair[0] for pair in verified}
                used2 = {pair[1] for pair in verified}
                selected_raw = list(sorted(verified))
                for pair, candidate in sorted(
                    raw_candidates.items(),
                    key=lambda item: (
                        -item[1].votes,
                        item[1].min_distance,
                        item[0],
                    ),
                ):
                    if pair in verified:
                        continue
                    if pair[0] in used1 or pair[1] in used2:
                        continue
                    used1.add(pair[0])
                    used2.add(pair[1])
                    selected_raw.append(pair)
                selected_raw.sort()
                output.execute(
                    "UPDATE matches SET rows = ?, cols = 2, data = ? "
                    "WHERE pair_id = ?",
                    (len(selected_raw), pack_pairs(selected_raw), pair_id),
                )
                raw_after += len(selected_raw)

            for pair_id in geometry_rows:
                selected = selected_by_pair.get(pair_id, [])
                output.execute(
                    "UPDATE two_view_geometries "
                    "SET rows = ?, cols = 2, data = ? WHERE pair_id = ?",
                    (len(selected), pack_pairs(selected), pair_id),
                )
                inliers_after += len(selected)
        output.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        output.close()
        source.close()

    keypoints = sum(row["keypoints"] for row in image_stats.values())
    unique_sites = sum(row["unique_exact_xy_sites"] for row in image_stats.values())
    payload = {
        "schema": "pocketworld_conflict_aware_track_birth_v1",
        "input_db": str(args.input_db),
        "output_db": str(args.output_db),
        "images": len(image_stats),
        "keypoints": keypoints,
        "unique_exact_xy_sites": unique_sites,
        "aliased_descriptors": keypoints - unique_sites,
        "raw_matches_before": raw_before,
        "raw_matches_after": raw_after,
        "two_view_inliers_before": inliers_before,
        "two_view_inliers_after_pose_gate": inliers_after_pose_gate,
        "two_view_inliers_after": inliers_after,
        "max_arkit_sampson_px": args.max_arkit_sampson_px,
        "rank_by_arkit_sampson": args.rank_by_arkit_sampson,
        "track_graph": track_stats,
    }
    args.stats.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
