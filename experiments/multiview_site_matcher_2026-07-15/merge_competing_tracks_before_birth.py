#!/usr/bin/env python3
"""Merge redundant multi-view tracks before any 3D point is born.

The gate is intentionally surface-agnostic.  Two tracks compete for one
physical site only when they repeatedly land on nearly the same image ray,
have similar local descriptors, and triangulate to distinct depths under the
captured RGB camera poses.  The stronger track owns the shared observations;
non-overlapping observations are retained and rewired into the merged track.

This operates on correspondence topology in a copied COLMAP database.  It
does not read LiDAR/sceneDepth, remove frames, or edit an existing point cloud.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, node: tuple[int, int]) -> tuple[int, int]:
        parent = self.parent.setdefault(node, node)
        if parent != node:
            self.parent[node] = self.find(parent)
        return self.parent[node]

    def union(self, first: tuple[int, int], second: tuple[int, int]) -> None:
        root1 = self.find(first)
        root2 = self.find(second)
        if root1 == root2:
            return
        if root2 < root1:
            root1, root2 = root2, root1
        self.parent[root2] = root1


class TrackUnionFind:
    def __init__(self, track_ids: list[int]) -> None:
        self.parent = {track_id: track_id for track_id in track_ids}

    def find(self, track_id: int) -> int:
        parent = self.parent[track_id]
        if parent != track_id:
            self.parent[track_id] = self.find(parent)
        return self.parent[track_id]

    def union(self, first: int, second: int) -> None:
        root1 = self.find(first)
        root2 = self.find(second)
        if root1 == root2:
            return
        if root2 < root1:
            root1, root2 = root2, root1
        self.parent[root2] = root1


@dataclass
class TrackGeometry:
    xyz_world: np.ndarray
    median_reprojection_px: float
    positive_depth_fraction: float


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


def frame_id(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match is None:
        raise ValueError(f"cannot infer frame id from {image.name!r}")
    return int(match.group(1))


def quaternion_wxyz_to_rotation(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def triangulate_track(
    observations: dict[int, int],
    keypoints: dict[int, np.ndarray],
    cameras: dict[int, pycolmap.Camera],
    poses: dict[int, tuple[np.ndarray, np.ndarray]],
) -> TrackGeometry | None:
    if len(observations) < 3:
        return None
    rows = []
    for image_id, feature_id in sorted(observations.items()):
        xy = keypoints[image_id][feature_id]
        normalized = cameras[image_id].cam_from_img(xy)
        rotation, translation = poses[image_id]
        projection = np.column_stack((rotation, translation))
        rows.append(normalized[0] * projection[2] - projection[0])
        rows.append(normalized[1] * projection[2] - projection[1])
    _, _, vt = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    homogeneous = vt[-1]
    if abs(homogeneous[3]) < 1e-12:
        return None
    xyz = homogeneous[:3] / homogeneous[3]

    errors = []
    positive = 0
    for image_id, feature_id in observations.items():
        rotation, translation = poses[image_id]
        cam_point = rotation @ xyz + translation
        if cam_point[2] > 0:
            positive += 1
        projected = cameras[image_id].img_from_cam(cam_point)
        if projected is None:
            return None
        errors.append(float(np.linalg.norm(projected - keypoints[image_id][feature_id])))
    return TrackGeometry(
        xyz_world=xyz,
        median_reprojection_px=float(np.median(errors)),
        positive_depth_fraction=positive / len(observations),
    )


def unique_rows(rows: np.ndarray) -> np.ndarray:
    if not len(rows):
        return np.empty((0, 2), dtype=np.uint32)
    return np.asarray(sorted(set(map(tuple, rows.tolist()))), dtype=np.uint32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--ray-radius-px", type=float, default=12.0)
    parser.add_argument("--min-common-views", type=int, default=2)
    parser.add_argument("--min-common-fraction", type=float, default=0.6)
    parser.add_argument("--min-descriptor-cosine", type=float, default=0.75)
    parser.add_argument("--min-median-descriptor-cosine", type=float, default=0.84)
    parser.add_argument("--min-depth-gap-mm", type=float, default=0.0)
    parser.add_argument("--max-depth-gap-mm", type=float, default=100.0)
    parser.add_argument("--max-track-reprojection-px", type=float, default=20.0)
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
        cameras = {
            image_id: database.read_camera(image.camera_id)
            for image_id, image in images.items()
        }
        keypoints = {
            image_id: np.asarray(database.read_keypoints(image_id)[:, :2], dtype=np.float64)
            for image_id in images
        }
        descriptors = {
            image_id: np.asarray(database.read_descriptors(image_id).data, dtype=np.float64)
            for image_id in images
        }
        descriptor_norms = {
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

        geometry_pair_ids, geometries = database.read_two_view_geometries()
        geometry_by_pair = dict(zip(geometry_pair_ids, geometries, strict=True))
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
        # A track may contain orientation aliases in one image.  Use the most
        # connected observation as its deterministic representative.
        canonical: dict[int, dict[int, int]] = {}
        for track_id, nodes in tracks.items():
            by_image: dict[int, list[int]] = defaultdict(list)
            for image_id, feature_id in nodes:
                by_image[image_id].append(feature_id)
            canonical[track_id] = {
                image_id: max(
                    feature_ids,
                    key=lambda feature_id: (node_degree[(image_id, feature_id)], -feature_id),
                )
                for image_id, feature_ids in by_image.items()
            }

        track_geometry = {
            track_id: triangulate_track(observations, keypoints, cameras, poses)
            for track_id, observations in canonical.items()
        }
        valid_tracks = {
            track_id
            for track_id, geometry in track_geometry.items()
            if geometry is not None
            and geometry.positive_depth_fraction == 1.0
            and geometry.median_reprojection_px <= args.max_track_reprojection_px
        }

        pair_evidence: dict[tuple[int, int], dict[int, tuple[float, float]]] = defaultdict(dict)
        for image_id in sorted(images):
            rows = [
                (track_id, feature_id)
                for track_id, observations in canonical.items()
                if track_id in valid_tracks
                for feature_id in [observations.get(image_id)]
                if feature_id is not None
            ]
            if len(rows) < 2:
                continue
            xy = np.asarray([keypoints[image_id][feature_id] for _, feature_id in rows])
            for first, second in cKDTree(xy).query_pairs(
                args.ray_radius_px, output_type="set"
            ):
                track1, feature1 = rows[first]
                track2, feature2 = rows[second]
                if track2 < track1:
                    track1, track2 = track2, track1
                    feature1, feature2 = feature2, feature1
                descriptor1 = descriptors[image_id][feature1]
                descriptor2 = descriptors[image_id][feature2]
                cosine = float(
                    descriptor1 @ descriptor2
                    / (descriptor_norms[image_id][feature1] * descriptor_norms[image_id][feature2])
                )
                distance = float(
                    np.linalg.norm(keypoints[image_id][feature1] - keypoints[image_id][feature2])
                )
                pair_evidence[(track1, track2)][image_id] = (distance, cosine)

        accepted_candidates = []
        for (track1, track2), evidence in sorted(pair_evidence.items()):
            if len(evidence) < args.min_common_views:
                continue
            common_fraction = len(evidence) / min(
                len(canonical[track1]), len(canonical[track2])
            )
            if common_fraction < args.min_common_fraction:
                continue
            cosines = np.asarray([value[1] for value in evidence.values()])
            if float(np.min(cosines)) < args.min_descriptor_cosine:
                continue
            median_cosine = float(np.median(cosines))
            if median_cosine < args.min_median_descriptor_cosine:
                continue
            geometry1 = track_geometry[track1]
            geometry2 = track_geometry[track2]
            assert geometry1 is not None and geometry2 is not None
            gaps = []
            for image_id in evidence:
                rotation, translation = poses[image_id]
                depth1 = float((rotation @ geometry1.xyz_world + translation)[2])
                depth2 = float((rotation @ geometry2.xyz_world + translation)[2])
                gaps.append(abs(depth1 - depth2) * 1000.0)
            median_gap = float(np.median(gaps))
            if not args.min_depth_gap_mm <= median_gap <= args.max_depth_gap_mm:
                continue
            ranked_tracks = sorted(
                (track1, track2),
                key=lambda track_id: (
                    -len(canonical[track_id]),
                    -sum(node_degree[node] for node in tracks[track_id]),
                    track_geometry[track_id].median_reprojection_px,
                    track_id,
                ),
            )
            merged_observations: dict[int, int] = {}
            for track_id in ranked_tracks:
                for image_id, feature_id in canonical[track_id].items():
                    merged_observations.setdefault(image_id, feature_id)
            merged_geometry = triangulate_track(
                merged_observations, keypoints, cameras, poses
            )
            if (
                merged_geometry is None
                or merged_geometry.positive_depth_fraction != 1.0
                or merged_geometry.median_reprojection_px
                > args.max_track_reprojection_px
            ):
                continue
            median_distance = float(np.median([v[0] for v in evidence.values()]))
            accepted_candidates.append(
                {
                    "track_ids": [track1, track2],
                    "common_image_ids": sorted(evidence),
                    "common_views": len(evidence),
                    "common_fraction": common_fraction,
                    "ray_distance_px": {
                        "median": median_distance,
                        "max": float(np.max([v[0] for v in evidence.values()])),
                    },
                    "descriptor_cosine": {
                        "median": median_cosine,
                        "min": float(np.min(cosines)),
                    },
                    "depth_gap_mm": median_gap,
                    "track_views": [len(canonical[track1]), len(canonical[track2])],
                    "track_reprojection_px": [
                        geometry1.median_reprojection_px,
                        geometry2.median_reprojection_px,
                    ],
                    "merged_reprojection_px": merged_geometry.median_reprojection_px,
                    "score": [
                        common_fraction,
                        len(evidence),
                        median_cosine,
                        -median_distance,
                        -merged_geometry.median_reprojection_px,
                    ],
                }
            )

        # A track may have several nearby neighbors on textured edges.  Only a
        # mutual-best pair can share ownership, and each track can participate
        # once.  This prevents transitive A-B-C merges across real structure.
        best_for_track: dict[int, dict] = {}
        for candidate in accepted_candidates:
            score = tuple(candidate["score"])
            for track_id in candidate["track_ids"]:
                current = best_for_track.get(track_id)
                if current is None or score > tuple(current["score"]):
                    best_for_track[track_id] = candidate
        mutual_candidates = [
            candidate
            for candidate in accepted_candidates
            if all(best_for_track[track_id] is candidate for track_id in candidate["track_ids"])
        ]
        selected_candidates = []
        claimed_tracks: set[int] = set()
        for candidate in sorted(
            mutual_candidates, key=lambda value: tuple(value["score"]), reverse=True
        ):
            if any(track_id in claimed_tracks for track_id in candidate["track_ids"]):
                continue
            selected_candidates.append(candidate)
            claimed_tracks.update(candidate["track_ids"])

        merge_uf = TrackUnionFind(sorted(tracks))
        for candidate in selected_candidates:
            merge_uf.union(*candidate["track_ids"])
        merge_groups: dict[int, list[int]] = defaultdict(list)
        for track_id in tracks:
            merge_groups[merge_uf.find(track_id)].append(track_id)
        merge_groups = {
            root: sorted(group)
            for root, group in merge_groups.items()
            if len(group) > 1
        }

        node_mapping: dict[tuple[int, int], tuple[int, int]] = {}
        group_details = []
        for group in merge_groups.values():
            ranked = sorted(
                group,
                key=lambda track_id: (
                    -len(canonical[track_id]),
                    -sum(node_degree[node] for node in tracks[track_id]),
                    track_geometry[track_id].median_reprojection_px
                    if track_geometry[track_id] is not None
                    else float("inf"),
                    track_id,
                ),
            )
            canonical_by_image: dict[int, tuple[int, int]] = {}
            for track_id in ranked:
                for image_id, feature_id in canonical[track_id].items():
                    canonical_by_image.setdefault(image_id, (image_id, feature_id))
            for track_id in group:
                for node in tracks[track_id]:
                    node_mapping[node] = canonical_by_image[node[0]]
            group_details.append(
                {
                    "track_ids": group,
                    "owner_track_id": ranked[0],
                    "input_unique_views": [len(canonical[track_id]) for track_id in group],
                    "merged_unique_views": len(canonical_by_image),
                }
            )

        rewritten_raw = 0
        deduplicated_raw = 0
        raw_pair_ids, raw_arrays = database.read_all_matches()
        for pair_id, matches in zip(raw_pair_ids, raw_arrays, strict=True):
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
            mapped = []
            for first, second in np.asarray(matches, dtype=np.uint32):
                node1 = (int(image1), int(first))
                node2 = (int(image2), int(second))
                mapped1 = node_mapping.get(node1, node1)
                mapped2 = node_mapping.get(node2, node2)
                rewritten_raw += int(mapped1 != node1 or mapped2 != node2)
                mapped.append((mapped1[1], mapped2[1]))
            unique = unique_rows(np.asarray(mapped, dtype=np.uint32))
            deduplicated_raw += len(mapped) - len(unique)
            database.delete_matches(image1, image2)
            if len(unique):
                database.write_matches(image1, image2, unique)

        rewritten_verified = 0
        deduplicated_verified = 0
        for pair_id, geometry in geometry_by_pair.items():
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
            mapped = []
            for first, second in np.asarray(geometry.inlier_matches, dtype=np.uint32):
                node1 = (int(image1), int(first))
                node2 = (int(image2), int(second))
                mapped1 = node_mapping.get(node1, node1)
                mapped2 = node_mapping.get(node2, node2)
                rewritten_verified += int(mapped1 != node1 or mapped2 != node2)
                mapped.append((mapped1[1], mapped2[1]))
            unique = unique_rows(np.asarray(mapped, dtype=np.uint32))
            deduplicated_verified += len(mapped) - len(unique)
            geometry.inlier_matches = unique
            database.update_two_view_geometry(image1, image2, geometry)

    stats = {
        "schema": "pocketworld_competing_track_birth_ownership_v1",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "ledger": str(args.ledger),
        "pycolmap_version": pycolmap.__version__,
        "parameters": {
            "ray_radius_px": args.ray_radius_px,
            "min_common_views": args.min_common_views,
            "min_common_fraction": args.min_common_fraction,
            "min_descriptor_cosine": args.min_descriptor_cosine,
            "min_median_descriptor_cosine": args.min_median_descriptor_cosine,
            "depth_gap_mm": [args.min_depth_gap_mm, args.max_depth_gap_mm],
            "max_track_reprojection_px": args.max_track_reprojection_px,
        },
        "input_tracks": len(tracks),
        "triangulated_valid_tracks": len(valid_tracks),
        "candidate_track_pairs": len(accepted_candidates),
        "candidate_details": accepted_candidates,
        "mutual_best_track_pairs": len(mutual_candidates),
        "selected_track_pairs": len(selected_candidates),
        "selected_details": selected_candidates,
        "merge_groups": group_details,
        "mapped_observations": len(node_mapping),
        "rewritten_raw_matches": rewritten_raw,
        "deduplicated_raw_matches": deduplicated_raw,
        "rewritten_verified_matches": rewritten_verified,
        "deduplicated_verified_matches": deduplicated_verified,
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_or_generated_points": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
