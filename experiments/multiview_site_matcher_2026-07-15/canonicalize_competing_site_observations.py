#!/usr/bin/env python3
"""Canonicalize only competing observations of the same image site.

Unlike whole-track merging, this pass leaves every non-overlapping observation
and correspondence untouched.  If two multi-view tracks repeatedly use nearby,
descriptor-consistent features in the same images, each shared image keeps the
more graph-supported feature and redirects only the competing feature to it.
The rewritten database is consumed before triangulation, so duplicate 3D points
never need to be generated or deleted.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree

from merge_competing_tracks_before_birth import (
    UnionFind,
    frame_id,
    quaternion_wxyz_to_rotation,
    sqlite_snapshot,
    triangulate_track,
)


@dataclass(frozen=True)
class ImageEvidence:
    image_id: int
    feature1: int
    feature2: int
    distance_px: float
    cosine: float


def unique_rows(rows: np.ndarray) -> np.ndarray:
    if not len(rows):
        return np.empty((0, 2), dtype=np.uint32)
    return np.asarray(sorted(set(map(tuple, rows.tolist()))), dtype=np.uint32)


def resolve_alias(aliases: dict[tuple[int, int], int], image_id: int, feature_id: int) -> int:
    seen: set[int] = set()
    while (image_id, feature_id) in aliases and feature_id not in seen:
        seen.add(feature_id)
        feature_id = aliases[(image_id, feature_id)]
    return feature_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--radius-px", type=float, default=12.0)
    parser.add_argument("--min-track-views", type=int, default=3)
    parser.add_argument("--min-common-views", type=int, default=2)
    parser.add_argument("--min-common-fraction", type=float, default=0.3)
    parser.add_argument("--min-cosine", type=float, default=0.75)
    parser.add_argument("--min-median-cosine", type=float, default=0.83)
    parser.add_argument("--max-world-distance-mm", type=float, default=6.0)
    parser.add_argument("--max-track-reprojection-px", type=float, default=20.0)
    parser.add_argument("--degree-owner-ratio", type=float, default=1.5)
    parser.add_argument("--fragment-max-world-distance-mm", type=float, default=4.0)
    parser.add_argument("--fragment-min-common-fraction", type=float, default=0.9)
    parser.add_argument("--fragment-min-view-ratio", type=float, default=2.0)
    parser.add_argument("--reproj-max-world-distance-mm", type=float, default=2.0)
    parser.add_argument("--reproj-min-common-views", type=int, default=4)
    parser.add_argument("--reproj-min-median-cosine", type=float, default=0.88)
    parser.add_argument("--reproj-min-ratio", type=float, default=1.8)
    parser.add_argument("--min-inliers", type=int, default=15)
    args = parser.parse_args()
    if args.stats.exists():
        raise FileExistsError(f"refusing to overwrite {args.stats}")

    sqlite_snapshot(args.input, args.output)
    ledger = {
        int(row["frameId"]): row
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    with pycolmap.Database.open(args.output) as database:
        images = {int(image.image_id): image for image in database.read_all_images()}
        image_ids = sorted(images)
        cameras = {
            image_id: database.read_camera(images[image_id].camera_id)
            for image_id in image_ids
        }
        keypoints = {
            image_id: np.asarray(database.read_keypoints(image_id)[:, :2], dtype=np.float64)
            for image_id in image_ids
        }
        descriptors = {
            image_id: np.asarray(
                database.read_descriptors(image_id).data, dtype=np.float64
            )
            for image_id in image_ids
        }
        norms = {
            image_id: np.maximum(np.linalg.norm(values, axis=1), 1e-12)
            for image_id, values in descriptors.items()
        }
        arkit_to_colmap = np.diag([1.0, -1.0, -1.0])
        poses: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for image_id, image in images.items():
            row = ledger[frame_id(image)]
            poses[image_id] = (
                arkit_to_colmap
                @ quaternion_wxyz_to_rotation(row["arkitCamFromWorldQwxyz"]),
                arkit_to_colmap
                @ np.asarray(row["arkitCamFromWorldTxyz"], dtype=np.float64),
            )
        pair_ids, geometries = database.read_two_view_geometries()
        geometry_by_pair = {
            int(pair_id): geometry
            for pair_id, geometry in zip(pair_ids, geometries, strict=True)
        }

        feature_uf = UnionFind()
        node_degree: Counter[tuple[int, int]] = Counter()
        for pair_id, geometry in geometry_by_pair.items():
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
            for first, second in np.asarray(geometry.inlier_matches, dtype=np.uint32):
                node1 = (int(image1), int(first))
                node2 = (int(image2), int(second))
                feature_uf.union(node1, node2)
                node_degree[node1] += 1
                node_degree[node2] += 1

        grouped: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for node in feature_uf.parent:
            grouped[feature_uf.find(node)].append(node)
        tracks = {
            track_id: sorted(nodes)
            for track_id, nodes in enumerate(
                sorted(grouped.values(), key=lambda values: min(values))
            )
        }
        track_views = {
            track_id: len({image_id for image_id, _ in nodes})
            for track_id, nodes in tracks.items()
        }
        valid_tracks = {
            track_id
            for track_id, views in track_views.items()
            if views >= args.min_track_views
        }
        canonical_track_observations: dict[int, dict[int, int]] = {}
        for track_id in valid_tracks:
            by_image: dict[int, list[int]] = defaultdict(list)
            for image_id, feature_id in tracks[track_id]:
                by_image[image_id].append(feature_id)
            canonical_track_observations[track_id] = {
                image_id: max(
                    feature_ids,
                    key=lambda feature_id: (
                        node_degree[(image_id, feature_id)],
                        -feature_id,
                    ),
                )
                for image_id, feature_ids in by_image.items()
            }
        track_geometry = {
            track_id: triangulate_track(
                observations, keypoints, cameras, poses
            )
            for track_id, observations in canonical_track_observations.items()
        }

        nodes_by_image: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for track_id in valid_tracks:
            for image_id, feature_id in tracks[track_id]:
                nodes_by_image[image_id].append((track_id, feature_id))

        evidence: dict[tuple[int, int], dict[int, ImageEvidence]] = defaultdict(dict)
        for image_id, nodes in nodes_by_image.items():
            if len(nodes) < 2:
                continue
            xy = np.asarray([keypoints[image_id][feature_id] for _, feature_id in nodes])
            for first, second in cKDTree(xy).query_pairs(
                args.radius_px, output_type="set"
            ):
                track1, feature1 = nodes[first]
                track2, feature2 = nodes[second]
                if track1 == track2:
                    continue
                if track2 < track1:
                    track1, track2 = track2, track1
                    feature1, feature2 = feature2, feature1
                cosine = float(
                    np.dot(
                        descriptors[image_id][feature1],
                        descriptors[image_id][feature2],
                    )
                    / (norms[image_id][feature1] * norms[image_id][feature2])
                )
                if cosine < args.min_cosine:
                    continue
                distance = float(
                    np.linalg.norm(
                        keypoints[image_id][feature1] - keypoints[image_id][feature2]
                    )
                )
                candidate = ImageEvidence(
                    image_id=image_id,
                    feature1=feature1,
                    feature2=feature2,
                    distance_px=distance,
                    cosine=cosine,
                )
                previous = evidence[(track1, track2)].get(image_id)
                if previous is None or (
                    cosine,
                    -distance,
                    node_degree[(image_id, feature1)]
                    + node_degree[(image_id, feature2)],
                    -feature1,
                    -feature2,
                ) > (
                    previous.cosine,
                    -previous.distance_px,
                    node_degree[(image_id, previous.feature1)]
                    + node_degree[(image_id, previous.feature2)],
                    -previous.feature1,
                    -previous.feature2,
                ):
                    evidence[(track1, track2)][image_id] = candidate

        candidates: dict[tuple[int, int], dict[str, object]] = {}
        for track_pair, by_image in evidence.items():
            track1, track2 = track_pair
            geometry1 = track_geometry.get(track1)
            geometry2 = track_geometry.get(track2)
            if (
                geometry1 is None
                or geometry2 is None
                or geometry1.positive_depth_fraction != 1.0
                or geometry2.positive_depth_fraction != 1.0
                or geometry1.median_reprojection_px
                > args.max_track_reprojection_px
                or geometry2.median_reprojection_px
                > args.max_track_reprojection_px
            ):
                continue
            world_distance_mm = float(
                np.linalg.norm(geometry1.xyz_world - geometry2.xyz_world) * 1000.0
            )
            if world_distance_mm > args.max_world_distance_mm:
                continue
            values = list(by_image.values())
            common_views = len(values)
            common_fraction = common_views / min(track_views[track1], track_views[track2])
            cosines = np.asarray([value.cosine for value in values])
            distances = np.asarray([value.distance_px for value in values])
            median_cosine = float(np.median(cosines))
            if (
                common_views < args.min_common_views
                or common_fraction < args.min_common_fraction
                or median_cosine < args.min_median_cosine
            ):
                continue
            degree_pairs = [
                (
                    node_degree[(value.image_id, value.feature1)],
                    node_degree[(value.image_id, value.feature2)],
                )
                for value in values
            ]
            degree_owner_index: int | None = None
            if all(
                first >= args.degree_owner_ratio * max(1, second)
                for first, second in degree_pairs
            ):
                degree_owner_index = 0
            elif all(
                second >= args.degree_owner_ratio * max(1, first)
                for first, second in degree_pairs
            ):
                degree_owner_index = 1
            if degree_owner_index is None:
                continue
            view_counts = [track_views[track1], track_views[track2]]
            reprojections = [
                geometry1.median_reprojection_px,
                geometry2.median_reprojection_px,
            ]
            view_ratio = max(view_counts) / min(view_counts)
            reprojection_ratio = max(reprojections) / max(1e-12, min(reprojections))
            fragment_absorption = (
                world_distance_mm <= args.fragment_max_world_distance_mm
                and common_views >= 3
                and common_fraction >= args.fragment_min_common_fraction
                and view_ratio >= args.fragment_min_view_ratio
                and view_counts[degree_owner_index] == max(view_counts)
            )
            reprojection_arbitration = (
                world_distance_mm <= args.reproj_max_world_distance_mm
                and common_views >= args.reproj_min_common_views
                and median_cosine >= args.reproj_min_median_cosine
                and reprojection_ratio >= args.reproj_min_ratio
                and reprojections[degree_owner_index] == min(reprojections)
            )
            if not fragment_absorption and not reprojection_arbitration:
                continue
            score = (
                common_fraction,
                common_views,
                median_cosine,
                -float(np.median(distances)),
                min(track_views[track1], track_views[track2]),
            )
            candidates[track_pair] = {
                "score": score,
                "common_views": common_views,
                "common_fraction": common_fraction,
                "median_cosine": median_cosine,
                "min_cosine": float(np.min(cosines)),
                "median_distance_px": float(np.median(distances)),
                "max_distance_px": float(np.max(distances)),
                "track_views": [track_views[track1], track_views[track2]],
                "world_distance_mm": world_distance_mm,
                "track_reprojection_px": reprojections,
                "degree_owner_track": [track1, track2][degree_owner_index],
                "selection_reason": (
                    "fragment_absorption"
                    if fragment_absorption
                    else "reprojection_arbitration"
                ),
                "evidence": values,
            }

        best_for_track: dict[int, tuple[tuple[object, ...], tuple[int, int]]] = {}
        for track_pair, details in candidates.items():
            score = tuple(details["score"])
            for track_id in track_pair:
                rank = (score, tuple(-value for value in track_pair))
                if track_id not in best_for_track or rank > best_for_track[track_id][0]:
                    best_for_track[track_id] = (rank, track_pair)
        selected = [
            track_pair
            for track_pair in sorted(candidates)
            if best_for_track[track_pair[0]][1] == track_pair
            and best_for_track[track_pair[1]][1] == track_pair
        ]

        aliases: dict[tuple[int, int], int] = {}
        selected_details: list[dict[str, object]] = []
        for track1, track2 in selected:
            details = candidates[(track1, track2)]
            decisions = []
            for value in details["evidence"]:
                degree1 = node_degree[(value.image_id, value.feature1)]
                degree2 = node_degree[(value.image_id, value.feature2)]
                rank1 = (degree1, track_views[track1], -value.feature1)
                rank2 = (degree2, track_views[track2], -value.feature2)
                if rank1 >= rank2:
                    owner, loser = value.feature1, value.feature2
                else:
                    owner, loser = value.feature2, value.feature1
                aliases[(value.image_id, loser)] = owner
                decisions.append(
                    {
                        "image_id": value.image_id,
                        "owner_feature": owner,
                        "redirected_feature": loser,
                        "degree": [degree1, degree2],
                        "distance_px": value.distance_px,
                        "cosine": value.cosine,
                    }
                )
            selected_details.append(
                {
                    "track_ids": [track1, track2],
                    "track_views": details["track_views"],
                    "world_distance_mm": details["world_distance_mm"],
                    "track_reprojection_px": details["track_reprojection_px"],
                    "degree_owner_track": details["degree_owner_track"],
                    "selection_reason": details["selection_reason"],
                    "common_views": details["common_views"],
                    "common_fraction": details["common_fraction"],
                    "median_cosine": details["median_cosine"],
                    "min_cosine": details["min_cosine"],
                    "median_distance_px": details["median_distance_px"],
                    "max_distance_px": details["max_distance_px"],
                    "decisions": decisions,
                }
            )

        raw_rewrites = 0
        verified_rewrites = 0
        raw_deduplicated = 0
        verified_deduplicated = 0
        geometry_pairs_written = 0
        geometry_pairs_below_gate = 0
        for pair_id, geometry in geometry_by_pair.items():
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)

            raw = np.asarray(database.read_matches(image1, image2), dtype=np.uint32)
            if len(raw):
                rewritten = raw.copy()
                for row in rewritten:
                    first = resolve_alias(aliases, int(image1), int(row[0]))
                    second = resolve_alias(aliases, int(image2), int(row[1]))
                    raw_rewrites += int(first != row[0]) + int(second != row[1])
                    row[:] = first, second
                canonical = unique_rows(rewritten)
                raw_deduplicated += len(rewritten) - len(canonical)
                if not np.array_equal(canonical, raw):
                    database.delete_matches(image1, image2)
                    database.write_matches(image1, image2, canonical)

            verified = np.asarray(geometry.inlier_matches, dtype=np.uint32)
            rewritten = verified.copy()
            for row in rewritten:
                first = resolve_alias(aliases, int(image1), int(row[0]))
                second = resolve_alias(aliases, int(image2), int(row[1]))
                verified_rewrites += int(first != row[0]) + int(second != row[1])
                row[:] = first, second
            canonical = unique_rows(rewritten)
            verified_deduplicated += len(rewritten) - len(canonical)
            if np.array_equal(canonical, verified):
                continue
            database.delete_two_view_geometry(image1, image2)
            if len(canonical) >= args.min_inliers:
                geometry.inlier_matches = canonical
                database.write_two_view_geometry(image1, image2, geometry)
                geometry_pairs_written += 1
            else:
                geometry_pairs_below_gate += 1

    serializable_candidates = [
        {
            "track_ids": list(track_pair),
            **{
                key: list(value) if key == "score" else value
                for key, value in details.items()
                if key != "evidence"
            },
        }
        for track_pair, details in sorted(candidates.items())
    ]
    stats = {
        "schema": "pocketworld_competing_site_observation_canonicalization_v1",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "pycolmap_version": pycolmap.__version__,
        "parameters": {
            "radius_px": args.radius_px,
            "min_track_views": args.min_track_views,
            "min_common_views": args.min_common_views,
            "min_common_fraction": args.min_common_fraction,
            "min_cosine": args.min_cosine,
            "min_median_cosine": args.min_median_cosine,
            "max_world_distance_mm": args.max_world_distance_mm,
            "max_track_reprojection_px": args.max_track_reprojection_px,
            "degree_owner_ratio": args.degree_owner_ratio,
            "fragment_max_world_distance_mm": args.fragment_max_world_distance_mm,
            "fragment_min_common_fraction": args.fragment_min_common_fraction,
            "fragment_min_view_ratio": args.fragment_min_view_ratio,
            "reproj_max_world_distance_mm": args.reproj_max_world_distance_mm,
            "reproj_min_common_views": args.reproj_min_common_views,
            "reproj_min_median_cosine": args.reproj_min_median_cosine,
            "reproj_min_ratio": args.reproj_min_ratio,
        },
        "tracks": len(tracks),
        "valid_tracks": len(valid_tracks),
        "candidate_track_pairs": len(candidates),
        "selected_track_pairs": len(selected),
        "aliased_observations": len(aliases),
        "raw_rewrites": raw_rewrites,
        "verified_rewrites": verified_rewrites,
        "raw_deduplicated": raw_deduplicated,
        "verified_deduplicated": verified_deduplicated,
        "geometry_pairs_written": geometry_pairs_written,
        "geometry_pairs_below_min_inliers": geometry_pairs_below_gate,
        "candidate_details": serializable_candidates,
        "selected_details": selected_details,
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_or_generated_points": False,
        "nonoverlapping_track_observations_preserved": True,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
