#!/usr/bin/env python3
"""Attribute persistent sparse-cloud layers to feature/geometry mechanisms.

This is diagnostic-only. It reads an immutable feature database plus a COLMAP
model and never rewrites matches, tracks, frames, or generated points.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pycolmap


def distribution(values) -> dict:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {"count": 0, "median": None, "p10": None, "p90": None}
    return {
        "count": int(len(array)),
        "median": float(np.median(array)),
        "p10": float(np.percentile(array, 10)),
        "p90": float(np.percentile(array, 90)),
    }


def canonical_edge(image1: int, index1: int, image2: int, index2: int):
    if image1 < image2:
        return image1, index1, image2, index2
    return image2, index2, image1, index1


def point_metrics(
    reconstruction: pycolmap.Reconstruction,
    point_id: int,
    duplicate_group_sizes: dict[int, np.ndarray],
) -> dict:
    point = reconstruction.points3D[point_id]
    centers = []
    reprojection = []
    duplicate_sizes = []
    observations = {}
    for element in point.track.elements:
        image_id = int(element.image_id)
        feature_id = int(element.point2D_idx)
        image = reconstruction.images[image_id]
        camera = reconstruction.cameras[image.camera_id]
        observations[image_id] = feature_id
        duplicate_sizes.append(int(duplicate_group_sizes[image_id][feature_id]))
        centers.append(np.asarray(image.projection_center(), dtype=np.float64))
        point_cam = image.cam_from_world() * point.xyz
        projected = camera.img_from_cam(point_cam) if point_cam[2] > 0 else None
        if projected is not None:
            reprojection.append(
                float(
                    np.linalg.norm(
                        np.asarray(projected, dtype=np.float64)
                        - np.asarray(image.points2D[feature_id].xy, dtype=np.float64)
                    )
                )
            )
    angles = []
    for first, second in itertools.combinations(centers, 2):
        ray1 = np.asarray(point.xyz, dtype=np.float64) - first
        ray2 = np.asarray(point.xyz, dtype=np.float64) - second
        ray1 /= max(np.linalg.norm(ray1), 1e-30)
        ray2 /= max(np.linalg.norm(ray2), 1e-30)
        angles.append(float(np.degrees(np.arccos(np.clip(ray1 @ ray2, -1.0, 1.0)))))
    return {
        "track_length": int(point.track.length()),
        "max_triangulation_angle_deg": max(angles, default=0.0),
        "median_reprojection_px": float(np.median(reprojection)),
        "duplicate_observation_fraction": float(
            np.mean(np.asarray(duplicate_sizes) > 1)
        ),
        "duplicate_group_size_median": float(np.median(duplicate_sizes)),
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--competition", type=Path, required=True)
    parser.add_argument("--arm", default="off")
    parser.add_argument("--radius", default="8px")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reconstruction = pycolmap.Reconstruction(args.model)
    competition = json.loads(args.competition.read_text())
    pair_details = competition["arms"][args.arm]["near_ray_competition"][
        args.radius
    ]["2views"]["pair_details"]
    persistent_pairs = [tuple(map(int, row["point_ids"])) for row in pair_details]
    ghost_points = {point_id for pair in persistent_pairs for point_id in pair}

    with pycolmap.Database.open(str(args.database)) as database:
        images = {int(image.image_id): image for image in database.read_all_images()}
        keypoints = {
            image_id: np.asarray(database.read_keypoints(image_id), dtype=np.float32)
            for image_id in images
        }
        descriptors = {
            image_id: np.asarray(
                database.read_descriptors(image_id).data, dtype=np.float64
            )
            for image_id in images
        }
        for image_id, values in descriptors.items():
            descriptors[image_id] = values / np.maximum(
                np.linalg.norm(values, axis=1, keepdims=True), 1e-30
            )

        raw_edges = set()
        pair_ids, match_rows = database.read_all_matches()
        for pair_id, matches in zip(pair_ids, match_rows, strict=True):
            image1, image2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
            raw_edges.update(
                canonical_edge(image1, int(first), image2, int(second))
                for first, second in np.asarray(matches, dtype=np.uint32)
            )
        verified_edges = set()
        pair_ids, geometries = database.read_two_view_geometries()
        for pair_id, geometry in zip(pair_ids, geometries, strict=True):
            image1, image2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
            verified_edges.update(
                canonical_edge(image1, int(first), image2, int(second))
                for first, second in np.asarray(
                    geometry.inlier_matches, dtype=np.uint32
                )
            )

    duplicate_group_sizes = {}
    exact_duplicate_features = 0
    for image_id, rows in keypoints.items():
        xy = np.ascontiguousarray(rows[:, :2]).view(
            np.dtype((np.void, rows[:, :2].dtype.itemsize * 2))
        ).reshape(-1)
        _, inverse, counts = np.unique(xy, return_inverse=True, return_counts=True)
        duplicate_group_sizes[image_id] = counts[inverse]
        exact_duplicate_features += int(np.sum(counts[inverse] > 1))

    metrics = {
        int(point_id): point_metrics(
            reconstruction, int(point_id), duplicate_group_sizes
        )
        for point_id in reconstruction.points3D
    }
    fields = (
        "track_length",
        "max_triangulation_angle_deg",
        "median_reprojection_px",
        "duplicate_observation_fraction",
        "duplicate_group_size_median",
    )
    groups = {}
    for label, point_ids in {
        "ghost_participants": sorted(ghost_points),
        "other_internal_points": sorted(set(metrics) - ghost_points),
    }.items():
        groups[label] = {
            field: distribution(metrics[point_id][field] for point_id in point_ids)
            for field in fields
        }

    pair_rows = []
    exact_shared_views = []
    raw_cross_edges = []
    verified_cross_edges = []
    for point1, point2 in persistent_pairs:
        first = metrics[point1]
        second = metrics[point2]
        common_images = sorted(
            set(first["observations"]) & set(second["observations"])
        )
        pixel_distances = []
        descriptor_cosines = []
        exact_count = 0
        raw_count = 0
        verified_count = 0
        for image_id in common_images:
            index1 = first["observations"][image_id]
            index2 = second["observations"][image_id]
            xy1 = keypoints[image_id][index1, :2]
            xy2 = keypoints[image_id][index2, :2]
            pixel_distances.append(float(np.linalg.norm(xy1 - xy2)))
            exact_count += int(np.array_equal(xy1, xy2))
            descriptor_cosines.append(
                float(descriptors[image_id][index1] @ descriptors[image_id][index2])
            )
        for image1, index1 in first["observations"].items():
            for image2, index2 in second["observations"].items():
                if image1 == image2:
                    continue
                edge = canonical_edge(image1, index1, image2, index2)
                raw_count += int(edge in raw_edges)
                verified_count += int(edge in verified_edges)
        exact_shared_views.append(exact_count)
        raw_cross_edges.append(raw_count)
        verified_cross_edges.append(verified_count)
        pair_rows.append(
            {
                "point_ids": [point1, point2],
                "common_images": common_images,
                "exact_same_xy_views": exact_count,
                "pixel_distance_px": distribution(pixel_distances),
                "same_image_descriptor_cosine": distribution(descriptor_cosines),
                "raw_cross_track_edges": raw_count,
                "verified_cross_track_edges": verified_count,
            }
        )

    result = {
        "schema": "pocketworld_competing_track_birth_attribution_v1",
        "diagnostic_only": True,
        "deletes_or_hides_generated_points": False,
        "uses_lidar_or_scene_depth": False,
        "model": str(args.model),
        "database": str(args.database),
        "competition": str(args.competition),
        "arm": args.arm,
        "radius": args.radius,
        "feature_rows": int(sum(len(rows) for rows in keypoints.values())),
        "features_in_exact_duplicate_groups": exact_duplicate_features,
        "persistent_pairs": len(persistent_pairs),
        "persistent_point_ids": len(ghost_points),
        "group_summary": groups,
        "pair_summary": {
            "exact_same_xy_views": distribution(exact_shared_views),
            "pairs_with_any_exact_same_xy_view": int(
                sum(value > 0 for value in exact_shared_views)
            ),
            "raw_cross_track_edges": distribution(raw_cross_edges),
            "pairs_with_any_raw_cross_track_edge": int(
                sum(value > 0 for value in raw_cross_edges)
            ),
            "verified_cross_track_edges": distribution(verified_cross_edges),
            "pairs_with_any_verified_cross_track_edge": int(
                sum(value > 0 for value in verified_cross_edges)
            ),
        },
        "pair_details": pair_rows,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["pair_summary"], indent=2, sort_keys=True))
    print(json.dumps(result["group_summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
