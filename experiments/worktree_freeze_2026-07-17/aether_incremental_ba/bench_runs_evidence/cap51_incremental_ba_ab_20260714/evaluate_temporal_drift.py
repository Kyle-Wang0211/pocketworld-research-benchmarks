#!/usr/bin/env python3
"""Measure cap51 pose drift after anchoring similarity on the first 25 frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap


FLIP_ARKIT_TO_CV = np.diag([1.0, -1.0, -1.0])


def quaternion_wxyz_to_matrix(q: list[float]) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src0 = src - src_mean
    dst0 = dst - dst_mean
    covariance = dst0.T @ src0 / len(src)
    u, singular, vt = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        correction[-1, -1] = -1
    rotation = u @ correction @ vt
    variance = np.mean(np.sum(src0 * src0, axis=1))
    scale = float(np.sum(singular * np.diag(correction)) / variance)
    translation = dst_mean - scale * rotation @ src_mean
    return scale, rotation, translation


def geodesic_deg(a: np.ndarray, b: np.ndarray) -> float:
    cosine = np.clip((np.trace(a.T @ b) - 1.0) * 0.5, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def summarize(values: np.ndarray) -> dict[str, float]:
    return {
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def score(model_dir: Path, ledger: list[dict], anchor_count: int) -> dict:
    reconstruction = pycolmap.Reconstruction(model_dir)
    centers_rec = np.empty((len(ledger), 3), dtype=np.float64)
    rotations_rec = np.empty((len(ledger), 3, 3), dtype=np.float64)
    for image in reconstruction.images.values():
        frame_id = int(Path(image.name).stem.split("_")[-1])
        centers_rec[frame_id] = image.projection_center()
        rotations_rec[frame_id] = image.cam_from_world().rotation.matrix().T
    centers_target = np.asarray([row["arkitCameraCenterWorld"] for row in ledger])
    rotations_target = np.stack(
        [quaternion_wxyz_to_matrix(row["arkitCamFromWorldQwxyz"]).T @ FLIP_ARKIT_TO_CV for row in ledger]
    )
    scale, rotation, translation = umeyama(
        centers_rec[:anchor_count], centers_target[:anchor_count]
    )
    centers_aligned = scale * (rotation @ centers_rec.T).T + translation
    position_mm = np.linalg.norm(centers_aligned - centers_target, axis=1) * 1000
    gravity_mm = np.abs(centers_aligned[:, 1] - centers_target[:, 1]) * 1000
    orientation_deg = np.asarray(
        [geodesic_deg(rotation @ rotations_rec[index], rotations_target[index]) for index in range(len(ledger))]
    )
    segments = {}
    for start in range(0, len(ledger), 25):
        stop = min(start + 25, len(ledger))
        key = f"frames_{start:03d}_{stop - 1:03d}"
        segments[key] = {
            "position_mm": summarize(position_mm[start:stop]),
            "gravity_mm": summarize(gravity_mm[start:stop]),
            "orientation_deg": summarize(orientation_deg[start:stop]),
        }
    frame_index = np.arange(len(ledger), dtype=np.float64)
    return {
        "anchor_frames": [0, anchor_count - 1],
        "similarity_scale": scale,
        "position_mm_all": summarize(position_mm),
        "gravity_mm_all": summarize(gravity_mm),
        "orientation_deg_all": summarize(orientation_deg),
        "position_drift_slope_mm_per_frame": float(np.polyfit(frame_index, position_mm, 1)[0]),
        "gravity_drift_slope_mm_per_frame": float(np.polyfit(frame_index, gravity_mm, 1)[0]),
        "orientation_drift_slope_deg_per_frame": float(np.polyfit(frame_index, orientation_deg, 1)[0]),
        "last25_minus_first25_position_median_mm": float(
            np.median(position_mm[-25:]) - np.median(position_mm[:25])
        ),
        "last25_minus_first25_gravity_median_mm": float(
            np.median(gravity_mm[-25:]) - np.median(gravity_mm[:25])
        ),
        "last25_minus_first25_orientation_median_deg": float(
            np.median(orientation_deg[-25:]) - np.median(orientation_deg[:25])
        ),
        "segments": segments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--anchor-count", type=int, default=25)
    args = parser.parse_args()
    ledger = [json.loads(line) for line in args.ledger.read_text().splitlines() if line]
    result = {arm: score(args.root / arm, ledger, args.anchor_count) for arm in ("off", "on")}
    output = args.root / "temporal_drift_metrics.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
