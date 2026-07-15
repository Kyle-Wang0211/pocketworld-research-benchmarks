#!/usr/bin/env python3
"""Measure RGB capture quality and relate it to structural ghost evidence.

This is a read-only diagnostic.  It never rejects a captured frame and never
removes a sparse point.  The purpose is to identify whether image formation
(blur, exposure, weak texture, autofocus intrinsics, or motion) predicts the
multi-depth conflicts that later become visible ghost layers.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from scipy.spatial import cKDTree
from scipy.stats import spearmanr


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def frame_id(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match is None:
        raise ValueError(f"cannot infer frame id from {image.name!r}")
    return int(match.group(1))


def umeyama(source: np.ndarray, target: np.ndarray):
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_zero = source - source_mean
    target_zero = target - target_mean
    covariance = target_zero.T @ source_zero / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    diagonal = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        diagonal[-1] = -1
    rotation = u @ np.diag(diagonal) @ vt
    variance = np.mean(np.sum(source_zero * source_zero, axis=1))
    scale = float(np.sum(singular * diagonal) / variance)
    translation = target_mean - scale * (rotation @ source_mean)
    return scale, rotation, translation


def tile_texture_ratio(gradient: np.ndarray, rows: int = 18, cols: int = 32) -> float:
    tile_scores = []
    for y_indices in np.array_split(np.arange(gradient.shape[0]), rows):
        for x_indices in np.array_split(np.arange(gradient.shape[1]), cols):
            tile_scores.append(float(np.mean(gradient[np.ix_(y_indices, x_indices)])))
    scores = np.asarray(tile_scores, dtype=np.float64)
    # A relative threshold avoids treating exposure gain as scene texture.
    threshold = max(2.0, float(np.median(scores)) * 0.55)
    return float(np.mean(scores >= threshold))


def signal_metrics(path: Path, width: int, height: int, stride: int) -> dict:
    expected = width * height
    if path.stat().st_size != expected:
        raise RuntimeError(
            f"{path}: expected {expected} raw gray bytes, found {path.stat().st_size}"
        )
    full = np.memmap(path, dtype=np.uint8, mode="r", shape=(height, width))
    gray = np.asarray(full[::stride, ::stride], dtype=np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient2 = gx * gx + gy * gy
    gradient = np.sqrt(gradient2)
    laplacian = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    histogram = np.bincount(gray.astype(np.uint8).ravel(), minlength=256).astype(float)
    probability = histogram[histogram > 0] / histogram.sum()
    entropy = float(-np.sum(probability * np.log2(probability)))
    contrast = float(np.std(gray))
    gx_energy = float(np.mean(np.abs(gx)))
    gy_energy = float(np.mean(np.abs(gy)))
    return {
        "gray_path": str(path),
        "sample_stride": stride,
        "sample_width": int(gray.shape[1]),
        "sample_height": int(gray.shape[0]),
        "mean_luma": float(np.mean(gray)),
        "luma_std": contrast,
        "underexposed_ratio": float(np.mean(gray <= 16.0)),
        "overexposed_ratio": float(np.mean(gray >= 239.0)),
        "entropy_bits": entropy,
        "laplacian_variance": float(np.var(laplacian)),
        "laplacian_over_contrast2": float(np.var(laplacian) / max(contrast * contrast, 1e-9)),
        "tenengrad_mean": float(np.mean(gradient2)),
        "gradient_mean": float(np.mean(gradient)),
        "gradient_p90": float(np.percentile(gradient, 90)),
        "gradient_axis_anisotropy": float(
            abs(math.log(max(gx_energy, 1e-9) / max(gy_energy, 1e-9)))
        ),
        "texture_tile_ratio": tile_texture_ratio(gradient),
    }


def motion_proxies(ledger: dict[int, dict], bundle_by_name: dict[str, dict]) -> dict[int, dict]:
    ordered = sorted(ledger)
    timestamps = np.asarray(
        [bundle_by_name[Path(ledger[index]["jpegPath"]).name]["timestamp"] for index in ordered],
        dtype=np.float64,
    )
    centers = np.asarray(
        [ledger[index]["arkitCameraCenterWorld"] for index in ordered], dtype=np.float64
    )
    quaternions = np.asarray(
        [ledger[index]["arkitCamFromWorldQwxyz"] for index in ordered], dtype=np.float64
    )
    quaternions /= np.linalg.norm(quaternions, axis=1, keepdims=True)
    result = {}
    for position, index in enumerate(ordered):
        first = max(0, position - 1)
        last = min(len(ordered) - 1, position + 1)
        dt = max(float(timestamps[last] - timestamps[first]), 1e-9)
        linear = float(np.linalg.norm(centers[last] - centers[first]) / dt)
        cosine = float(np.clip(abs(quaternions[first] @ quaternions[last]), -1.0, 1.0))
        angular = float(np.degrees(2.0 * np.arccos(cosine)) / dt)
        result[index] = {
            "neighbor_motion_linear_m_s": linear,
            "neighbor_motion_angular_deg_s": angular,
        }
    return result


def reconstruction_evidence(
    model_path: Path,
    ledger: dict[int, dict],
    radius_px: float,
    min_gap_mm: float,
    max_gap_mm: float,
    min_images: int,
):
    reconstruction = pycolmap.Reconstruction(model_path)
    image_by_frame = {frame_id(image): image for image in reconstruction.images.values()}
    shared_frames = sorted(set(image_by_frame) & set(ledger))
    source = np.asarray(
        [image_by_frame[index].projection_center() for index in shared_frames],
        dtype=np.float64,
    )
    target = np.asarray(
        [ledger[index]["arkitCameraCenterWorld"] for index in shared_frames],
        dtype=np.float64,
    )
    scale, rotation, translation = umeyama(source, target)
    aligned = scale * (rotation @ source.T).T + translation
    camera_error = np.linalg.norm(aligned - target, axis=1) * 1000.0

    pair_images: dict[tuple[int, int], set[int]] = defaultdict(set)
    pairs_by_frame: dict[int, list[tuple[int, int]]] = defaultdict(list)
    per_frame = {}
    for index in shared_frames:
        image = image_by_frame[index]
        camera = reconstruction.cameras[image.camera_id]
        cam_from_world = image.cam_from_world()
        rows = []
        reprojection_errors = []
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point_id = int(point2d.point3D_id)
            point = reconstruction.points3D[point_id]
            point_cam = cam_from_world * point.xyz
            depth = float(point_cam[2])
            if depth <= 0.0:
                continue
            projected = camera.img_from_cam(point_cam)
            if projected is not None:
                reprojection_errors.append(
                    float(np.linalg.norm(np.asarray(projected) - np.asarray(point2d.xy)))
                )
            rows.append((float(point2d.xy[0]), float(point2d.xy[1]), point_id, depth))
        if len(rows) >= 2:
            xy = np.asarray([(row[0], row[1]) for row in rows], dtype=np.float64)
            for first, second in cKDTree(xy).query_pairs(radius_px, output_type="set"):
                point1, point2 = rows[first][2], rows[second][2]
                if point1 == point2:
                    continue
                gap_mm = abs(rows[first][3] - rows[second][3]) * scale * 1000.0
                if gap_mm < min_gap_mm or gap_mm > max_gap_mm:
                    continue
                pair = (min(point1, point2), max(point1, point2))
                pair_images[pair].add(index)
                pairs_by_frame[index].append(pair)
        per_frame[index] = {
            "triangulated_observations": len(rows),
            "reprojection_median_px": float(np.median(reprojection_errors)),
            "reprojection_p90_px": float(np.percentile(reprojection_errors, 90)),
        }
    persistent = {pair for pair, images in pair_images.items() if len(images) >= min_images}
    for offset, index in enumerate(shared_frames):
        count = sum(pair in persistent for pair in pairs_by_frame[index])
        observations = per_frame[index]["triangulated_observations"]
        per_frame[index].update(
            {
                "camera_center_error_mm": float(camera_error[offset]),
                "persistent_layer_pair_observations": int(count),
                "persistent_layer_pairs_per_1000_observations": float(
                    1000.0 * count / max(1, observations)
                ),
            }
        )
    return {
        "registered_frames": len(reconstruction.images),
        "sparse_points": len(reconstruction.points3D),
        "metric_alignment_scale": scale,
        "persistent_point_pairs": len(persistent),
        "per_frame": per_frame,
    }


def correlations(rows: list[dict]) -> dict:
    predictors = [
        "mean_luma",
        "luma_std",
        "underexposed_ratio",
        "overexposed_ratio",
        "entropy_bits",
        "laplacian_variance",
        "laplacian_over_contrast2",
        "tenengrad_mean",
        "gradient_mean",
        "gradient_p90",
        "gradient_axis_anisotropy",
        "texture_tile_ratio",
        "intrinsics_focal_delta_pct",
        "neighbor_motion_linear_m_s",
        "neighbor_motion_angular_deg_s",
    ]
    outcomes = [
        "persistent_layer_pairs_per_1000_observations",
        "reprojection_median_px",
        "reprojection_p90_px",
        "camera_center_error_mm",
    ]
    result = {}
    for outcome in outcomes:
        result[outcome] = {}
        y = np.asarray([row[outcome] for row in rows], dtype=np.float64)
        for predictor in predictors:
            x = np.asarray([row[predictor] for row in rows], dtype=np.float64)
            if np.ptp(x) == 0.0 or np.ptp(y) == 0.0:
                rho, pvalue = 0.0, 1.0
            else:
                statistic = spearmanr(x, y)
                rho, pvalue = float(statistic.statistic), float(statistic.pvalue)
            result[outcome][predictor] = {"spearman_rho": rho, "pvalue": pvalue}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photo-bundle", type=Path, required=True)
    parser.add_argument("--gray-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-stride", type=int, default=4)
    parser.add_argument("--radius-px", type=float, default=8.0)
    parser.add_argument("--min-gap-mm", type=float, default=12.0)
    parser.add_argument("--max-gap-mm", type=float, default=100.0)
    parser.add_argument("--min-images", type=int, default=2)
    args = parser.parse_args()

    ledger = {
        int(row["frameId"]): row
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    bundle = json.loads(args.photo_bundle.read_text())
    bundle_by_name = {row["highresFilename"]: row for row in bundle["frames"]}
    reference_focal = float(np.mean(bundle["frames"][0]["intrinsics"][:2]))
    motion = motion_proxies(ledger, bundle_by_name)
    evidence = reconstruction_evidence(
        args.model,
        ledger,
        args.radius_px,
        args.min_gap_mm,
        args.max_gap_mm,
        args.min_images,
    )

    rows = []
    for index in sorted(evidence["per_frame"]):
        jpeg_name = Path(ledger[index]["jpegPath"]).name
        frame = bundle_by_name[jpeg_name]
        gray_path = args.gray_dir / Path(jpeg_name).with_suffix(".sfm-gray").name
        row = {
            "frame_id": index,
            "jpeg_name": jpeg_name,
            **signal_metrics(
                gray_path,
                int(frame["imageWidth"]),
                int(frame["imageHeight"]),
                args.sample_stride,
            ),
            **motion[index],
            **evidence["per_frame"][index],
        }
        focal = float(np.mean(frame["intrinsics"][:2]))
        row["intrinsics_focal_px"] = focal
        row["intrinsics_focal_delta_pct"] = 100.0 * (focal - reference_focal) / reference_focal
        rows.append(row)

    result = {
        "schema": "pocketworld_capture_signal_vs_ghost_v1",
        "diagnostic_only": True,
        "frame_policy": "all accepted user frames remain retained and registered",
        "model": str(args.model),
        "ledger": str(args.ledger),
        "photo_bundle": str(args.photo_bundle),
        "gray_dir": str(args.gray_dir),
        "pycolmap_version": pycolmap.__version__,
        "ghost_definition": {
            "radius_px": args.radius_px,
            "min_gap_mm": args.min_gap_mm,
            "max_gap_mm": args.max_gap_mm,
            "min_images": args.min_images,
        },
        "reconstruction": {key: value for key, value in evidence.items() if key != "per_frame"},
        "frames": rows,
        "correlations": correlations(rows),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "frames": len(rows),
                "registered_frames": evidence["registered_frames"],
                "persistent_point_pairs": evidence["persistent_point_pairs"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
