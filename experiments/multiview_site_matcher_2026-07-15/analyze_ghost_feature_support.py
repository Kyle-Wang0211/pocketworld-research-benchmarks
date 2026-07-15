#!/usr/bin/env python3
"""Compare feature-level evidence of persistent multi-depth competitors.

The analysis is diagnostic only.  It does not filter frames, matches, tracks,
or points.  It measures whether a future pre-birth ownership decision can be
grounded in local RGB evidence and multi-view geometry rather than a
surface-specific or post-generation deletion rule.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from scipy.spatial import cKDTree


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def frame_id(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match is None:
        raise ValueError(f"cannot infer frame id from {image.name!r}")
    return int(match.group(1))


def umeyama_scale(source: np.ndarray, target: np.ndarray) -> float:
    source0 = source - source.mean(axis=0)
    target0 = target - target.mean(axis=0)
    covariance = target0.T @ source0 / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    diagonal = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        diagonal[-1] = -1
    variance = np.mean(np.sum(source0 * source0, axis=1))
    return float(np.sum(singular * diagonal) / variance)


def distribution(values) -> dict:
    array = np.asarray(list(values), dtype=np.float64)
    if len(array) == 0:
        return {"count": 0, "median": None, "p10": None, "p90": None}
    return {
        "count": int(len(array)),
        "median": float(np.median(array)),
        "p10": float(np.percentile(array, 10)),
        "p90": float(np.percentile(array, 90)),
    }


def quality_maps(path: Path, width: int, height: int, stride: int):
    expected = width * height
    if path.stat().st_size != expected:
        raise RuntimeError(f"{path}: expected {expected} bytes")
    full = np.memmap(path, dtype=np.uint8, mode="r", shape=(height, width))
    gray = np.asarray(full[::stride, ::stride], dtype=np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    window = (7, 7)
    xx = cv2.boxFilter(gx * gx, cv2.CV_32F, window, normalize=True)
    xy = cv2.boxFilter(gx * gy, cv2.CV_32F, window, normalize=True)
    yy = cv2.boxFilter(gy * gy, cv2.CV_32F, window, normalize=True)
    trace = xx + yy
    delta = np.sqrt(np.maximum((xx - yy) ** 2 + 4.0 * xy * xy, 0.0))
    lambda_min = np.maximum(0.5 * (trace - delta), 0.0)
    lambda_max = np.maximum(0.5 * (trace + delta), 0.0)
    corner_ratio = lambda_min / np.maximum(lambda_max, 1e-9)
    gradient = np.sqrt(gx * gx + gy * gy)
    return lambda_min, corner_ratio, gradient


def sample_map(image: np.ndarray, x: float, y: float, stride: int) -> float:
    ix = int(np.clip(round(x / stride), 0, image.shape[1] - 1))
    iy = int(np.clip(round(y / stride), 0, image.shape[0] - 1))
    return float(image[iy, ix])


def canonical_edge(image1: int, index1: int, image2: int, index2: int):
    if image1 < image2:
        return image1, index1, image2, index2
    return image2, index2, image1, index1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photo-bundle", type=Path, required=True)
    parser.add_argument("--gray-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius-px", type=float, default=8.0)
    parser.add_argument("--min-gap-mm", type=float, default=12.0)
    parser.add_argument("--max-gap-mm", type=float, default=100.0)
    parser.add_argument("--min-images", type=int, default=2)
    parser.add_argument("--sample-stride", type=int, default=4)
    parser.add_argument("--shared-ray-normalized", action="store_true")
    args = parser.parse_args()

    ledger = {
        int(row["frameId"]): row
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    bundle = json.loads(args.photo_bundle.read_text())
    bundle_by_name = {row["highresFilename"]: row for row in bundle["frames"]}
    reconstruction = pycolmap.Reconstruction(args.model)
    images = {frame_id(image): image for image in reconstruction.images.values()}

    database = pycolmap.Database.open(str(args.database))
    input_cameras = database.read_all_cameras()
    if len(input_cameras) != 1:
        raise RuntimeError(f"expected one shared camera, found {len(input_cameras)}")
    reference_camera = input_cameras[0]
    reference_f = float(reference_camera.focal_length_x)
    reference_cx = float(reference_camera.principal_point_x)
    reference_cy = float(reference_camera.principal_point_y)

    descriptors = {}
    for image in database.read_all_images():
        descriptor = database.read_descriptors(image.image_id)
        values = np.asarray(descriptor.data, dtype=np.float32)
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        descriptors[int(image.image_id)] = values / np.maximum(norms, 1e-9)
    raw_edges = set()
    pair_ids, pair_matches = database.read_all_matches()
    for pair_id, matches in zip(pair_ids, pair_matches, strict=True):
        image1, image2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
        for index1, index2 in np.asarray(matches, dtype=np.uint32):
            raw_edges.add((image1, int(index1), image2, int(index2)))
    verified_edges = set()
    pair_ids, geometries = database.read_two_view_geometries()
    for pair_id, geometry in zip(pair_ids, geometries, strict=True):
        image1, image2 = map(int, pycolmap.pair_id_to_image_pair(pair_id))
        for index1, index2 in np.asarray(geometry.inlier_matches, dtype=np.uint32):
            verified_edges.add((image1, int(index1), image2, int(index2)))
    database.close()

    source_centers = np.asarray(
        [images[index].projection_center() for index in sorted(images)], dtype=np.float64
    )
    target_centers = np.asarray(
        [ledger[index]["arkitCameraCenterWorld"] for index in sorted(images)],
        dtype=np.float64,
    )
    metric_scale = umeyama_scale(source_centers, target_centers)

    observation_quality: dict[int, list[dict]] = defaultdict(list)
    pairs_in_images: dict[tuple[int, int], set[int]] = defaultdict(set)
    pair_pixel_distances: dict[tuple[int, int], list[float]] = defaultdict(list)
    pair_depth_gaps: dict[tuple[int, int], list[float]] = defaultdict(list)

    for index in sorted(images):
        image = images[index]
        jpeg_name = Path(ledger[index]["jpegPath"]).name
        frame = bundle_by_name[jpeg_name]
        fx, fy, cx, cy = map(float, frame["intrinsics"][:4])
        gray_path = args.gray_dir / Path(jpeg_name).with_suffix(".sfm-gray").name
        min_eigen, corner_ratio, gradient = quality_maps(
            gray_path,
            int(frame["imageWidth"]),
            int(frame["imageHeight"]),
            args.sample_stride,
        )
        rows = []
        cam_from_world = image.cam_from_world()
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point_id = int(point2d.point3D_id)
            x, y = map(float, point2d.xy)
            if args.shared_ray_normalized:
                raw_x = fx * (x - reference_cx) / reference_f + cx
                raw_y = fy * (y - reference_cy) / reference_f + cy
            else:
                raw_x, raw_y = x, y
            point_cam = cam_from_world * reconstruction.points3D[point_id].xyz
            depth = float(point_cam[2])
            if depth <= 0.0:
                continue
            observation_quality[point_id].append(
                {
                    "frame_id": index,
                    "min_eigen": sample_map(min_eigen, raw_x, raw_y, args.sample_stride),
                    "corner_ratio": sample_map(
                        corner_ratio, raw_x, raw_y, args.sample_stride
                    ),
                    "gradient": sample_map(gradient, raw_x, raw_y, args.sample_stride),
                }
            )
            rows.append((x, y, point_id, depth))
        if len(rows) < 2:
            continue
        xy_points = np.asarray([(row[0], row[1]) for row in rows], dtype=np.float64)
        for first, second in cKDTree(xy_points).query_pairs(
            args.radius_px, output_type="set"
        ):
            point1, point2 = rows[first][2], rows[second][2]
            if point1 == point2:
                continue
            depth_gap_mm = abs(rows[first][3] - rows[second][3]) * metric_scale * 1000.0
            if depth_gap_mm < args.min_gap_mm or depth_gap_mm > args.max_gap_mm:
                continue
            pair = (min(point1, point2), max(point1, point2))
            pairs_in_images[pair].add(index)
            pair_pixel_distances[pair].append(
                float(np.linalg.norm(xy_points[first] - xy_points[second]))
            )
            pair_depth_gaps[pair].append(depth_gap_mm)

    persistent_pairs = {
        pair for pair, image_ids in pairs_in_images.items() if len(image_ids) >= args.min_images
    }
    ghost_points = {point_id for pair in persistent_pairs for point_id in pair}

    point_rows = {}
    for point_id, point in reconstruction.points3D.items():
        qualities = observation_quality.get(int(point_id), [])
        if not qualities:
            continue
        reprojection = []
        centers = []
        for element in point.track.elements:
            image = reconstruction.images[element.image_id]
            camera = reconstruction.cameras[image.camera_id]
            point_cam = image.cam_from_world() * point.xyz
            projected = camera.img_from_cam(point_cam) if point_cam[2] > 0 else None
            if projected is not None:
                reprojection.append(
                    float(
                        np.linalg.norm(
                            np.asarray(projected) - image.points2D[element.point2D_idx].xy
                        )
                    )
                )
            centers.append(np.asarray(image.projection_center()))
        angles = []
        for first in range(len(centers)):
            ray1 = np.asarray(point.xyz) - centers[first]
            ray1 /= np.linalg.norm(ray1)
            for second in range(first + 1, len(centers)):
                ray2 = np.asarray(point.xyz) - centers[second]
                ray2 /= np.linalg.norm(ray2)
                angles.append(float(np.degrees(np.arccos(np.clip(ray1 @ ray2, -1, 1)))))
        point_rows[int(point_id)] = {
            "ghost_participant": int(point_id) in ghost_points,
            "track_length": int(point.track.length()),
            "max_triangulation_angle_deg": max(angles, default=0.0),
            "reprojection_median_px": float(np.median(reprojection)),
            "reprojection_p90_px": float(np.percentile(reprojection, 90)),
            "min_eigen_median": float(np.median([row["min_eigen"] for row in qualities])),
            "corner_ratio_median": float(
                np.median([row["corner_ratio"] for row in qualities])
            ),
            "gradient_median": float(np.median([row["gradient"] for row in qualities])),
            "_observations": [
                (int(element.image_id), int(element.point2D_idx))
                for element in point.track.elements
            ],
        }

    fields = [
        "track_length",
        "max_triangulation_angle_deg",
        "reprojection_median_px",
        "reprojection_p90_px",
        "min_eigen_median",
        "corner_ratio_median",
        "gradient_median",
    ]
    group_summary = {}
    for label, predicate in {
        "ghost_participants": lambda row: row["ghost_participant"],
        "other_points": lambda row: not row["ghost_participant"],
    }.items():
        selected = [row for row in point_rows.values() if predicate(row)]
        group_summary[label] = {field: distribution(row[field] for row in selected) for field in fields}

    pair_rows = []
    dominance_margins = defaultdict(list)
    pairs_with_raw_edge = 0
    pairs_with_verified_edge = 0
    same_image_descriptor_distances = []
    cross_track_descriptor_minima = []
    for first, second in sorted(persistent_pairs):
        row1, row2 = point_rows[first], point_rows[second]
        cross_distances = []
        same_image_distances = []
        raw_edge_count = 0
        verified_edge_count = 0
        for image1, index1 in row1["_observations"]:
            descriptor1 = descriptors[image1][index1]
            for image2, index2 in row2["_observations"]:
                descriptor2 = descriptors[image2][index2]
                distance = float(np.linalg.norm(descriptor1 - descriptor2))
                cross_distances.append(distance)
                if image1 == image2:
                    same_image_distances.append(distance)
                    continue
                edge = canonical_edge(image1, index1, image2, index2)
                raw_edge_count += edge in raw_edges
                verified_edge_count += edge in verified_edges
        if raw_edge_count:
            pairs_with_raw_edge += 1
        if verified_edge_count:
            pairs_with_verified_edge += 1
        same_image_descriptor_distances.extend(same_image_distances)
        cross_track_descriptor_minima.append(min(cross_distances))
        margins = {
            "track_length_abs": abs(row1["track_length"] - row2["track_length"]),
            "parallax_abs_deg": abs(
                row1["max_triangulation_angle_deg"]
                - row2["max_triangulation_angle_deg"]
            ),
            "reprojection_p90_abs_px": abs(
                row1["reprojection_p90_px"] - row2["reprojection_p90_px"]
            ),
            "corner_ratio_abs": abs(
                row1["corner_ratio_median"] - row2["corner_ratio_median"]
            ),
        }
        for key, value in margins.items():
            dominance_margins[key].append(value)
        pair_rows.append(
            {
                "point_ids": [first, second],
                "distinct_images": len(pairs_in_images[(first, second)]),
                "pixel_distance_px": distribution(pair_pixel_distances[(first, second)]),
                "depth_gap_mm": distribution(pair_depth_gaps[(first, second)]),
                "evidence_margins": margins,
                "raw_cross_track_edges": raw_edge_count,
                "verified_cross_track_edges": verified_edge_count,
                "same_image_descriptor_l2": distribution(same_image_distances),
                "cross_track_descriptor_l2": distribution(cross_distances),
            }
        )

    result = {
        "schema": "pocketworld_ghost_feature_support_v1",
        "diagnostic_only": True,
        "frame_policy": "all accepted user frames remain retained and registered",
        "model": str(args.model),
        "database": str(args.database),
        "metric_scale": metric_scale,
        "shared_ray_normalized": args.shared_ray_normalized,
        "ghost_definition": {
            "radius_px": args.radius_px,
            "min_gap_mm": args.min_gap_mm,
            "max_gap_mm": args.max_gap_mm,
            "min_images": args.min_images,
            "persistence_unit": "distinct_registered_images",
        },
        "sparse_points": len(reconstruction.points3D),
        "persistent_pairs": len(persistent_pairs),
        "persistent_point_ids": len(ghost_points),
        "group_summary": group_summary,
        "pair_evidence_margin_summary": {
            key: distribution(values) for key, values in dominance_margins.items()
        },
        "cross_track_graph_summary": {
            "pairs_with_raw_cross_track_edge": pairs_with_raw_edge,
            "pairs_with_verified_cross_track_edge": pairs_with_verified_edge,
            "same_image_descriptor_l2": distribution(
                same_image_descriptor_distances
            ),
            "per_pair_min_cross_track_descriptor_l2": distribution(
                cross_track_descriptor_minima
            ),
        },
        "persistent_point_evidence": {
            str(point_id): {
                key: value
                for key, value in point_rows[point_id].items()
                if not key.startswith("_")
            }
            for point_id in sorted(ghost_points)
        },
        "persistent_pair_details": pair_rows,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "persistent_pairs": len(persistent_pairs),
                "persistent_point_ids": len(ghost_points),
                "sparse_points": len(reconstruction.points3D),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
