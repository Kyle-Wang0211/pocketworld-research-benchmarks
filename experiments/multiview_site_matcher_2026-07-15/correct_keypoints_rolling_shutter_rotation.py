#!/usr/bin/env python3
"""Rotate keypoint rays to one reference time within each rolling-shutter frame.

This is a diagnostic, not a frame filter.  It preserves every image, feature,
descriptor, match, and two-view geometry identity.  Only the stored 2D
keypoint coordinates move.  Angular velocity is estimated from the neighboring
capture-time ARKit camera rotations; no LiDAR, scene depth, or learned model is
used.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial.transform import Rotation


def copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    source_db = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    output_db = sqlite3.connect(destination)
    try:
        source_db.backup(output_db)
        output_db.execute("PRAGMA journal_mode=DELETE")
        output_db.commit()
    finally:
        output_db.close()
        source_db.close()


def summary(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def camera_rotation(frame: dict) -> np.ndarray:
    transform = np.asarray(frame["cameraTransform"], dtype=np.float64).reshape(
        4, 4, order="F"
    )
    rotation = transform[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=2e-4):
        raise RuntimeError("cameraTransform rotation is not orthonormal")
    return rotation


def body_angular_velocities(
    rotations: list[np.ndarray], timestamps: np.ndarray
) -> np.ndarray:
    velocities: list[np.ndarray] = []
    for index, current in enumerate(rotations):
        estimates: list[np.ndarray] = []
        if index > 0:
            dt = float(timestamps[index - 1] - timestamps[index])
            estimates.append(
                Rotation.from_matrix(current.T @ rotations[index - 1]).as_rotvec()
                / dt
            )
        if index + 1 < len(rotations):
            dt = float(timestamps[index + 1] - timestamps[index])
            estimates.append(
                Rotation.from_matrix(current.T @ rotations[index + 1]).as_rotvec()
                / dt
            )
        velocities.append(np.mean(estimates, axis=0))
    return np.asarray(velocities, dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photo-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--readout-ms", type=float, required=True)
    parser.add_argument("--direction", type=int, choices=(-1, 1), required=True)
    parser.add_argument(
        "--reference-row-fraction",
        type=float,
        default=0.5,
        help="0=top row, 0.5=middle row, 1=bottom row",
    )
    args = parser.parse_args()
    if args.stats.exists():
        raise FileExistsError(args.stats)
    if not 0.0 <= args.readout_ms <= 50.0:
        raise ValueError("--readout-ms must be within 0...50")
    if not 0.0 <= args.reference_row_fraction <= 1.0:
        raise ValueError("--reference-row-fraction must be within 0...1")

    ledger_rows = [
        json.loads(line) for line in args.ledger.read_text().splitlines() if line
    ]
    ledger_rows.sort(key=lambda row: int(row["frameId"]))
    bundle = json.loads(args.photo_bundle.read_text())
    bundle_by_name = {
        os.path.basename(frame["highresFilename"]): frame
        for frame in bundle.get("frames", [])
    }
    frames = [
        bundle_by_name[os.path.basename(row["jpegPath"])] for row in ledger_rows
    ]
    timestamps = np.asarray([frame["timestamp"] for frame in frames], dtype=np.float64)
    if not np.all(np.diff(timestamps) > 0):
        raise RuntimeError("capture timestamps are not strictly increasing in ledger order")
    rotations = [camera_rotation(frame) for frame in frames]
    angular_velocities = body_angular_velocities(rotations, timestamps)

    copy_database(args.input, args.output)
    all_shifts: list[np.ndarray] = []
    readout_seconds = args.readout_ms / 1000.0
    with pycolmap.Database.open(args.output) as database:
        images = sorted(database.read_all_images(), key=lambda image: int(image.image_id))
        if len(images) != len(frames):
            raise RuntimeError(
                f"database has {len(images)} images but ledger has {len(frames)} frames"
            )
        for frame_index, image in enumerate(images):
            camera = database.read_camera(image.camera_id)
            keypoints = database.read_keypoints(image.image_id)
            xy = keypoints[:, :2].astype(np.float64)
            frame = frames[frame_index]
            fx, fy, cx, cy = np.asarray(frame["intrinsics"][:4], dtype=np.float64)
            if int(camera.width) != int(frame["imageWidth"]) or int(camera.height) != int(
                frame["imageHeight"]
            ):
                raise RuntimeError(f"image dimensions disagree for image {image.image_id}")

            row_fraction = xy[:, 1] / max(1.0, float(camera.height - 1))
            row_dt = (
                args.direction
                * (row_fraction - args.reference_row_fraction)
                * readout_seconds
            )
            rotation_vectors = row_dt[:, None] * angular_velocities[frame_index]
            normalized_x = (xy[:, 0] - cx) / fx
            normalized_y = (xy[:, 1] - cy) / fy
            # ARKit camera coordinates: +X right, +Y up, -Z forward.
            rays = np.column_stack(
                (normalized_x, -normalized_y, -np.ones(len(xy), dtype=np.float64))
            )
            corrected = Rotation.from_rotvec(rotation_vectors).apply(rays)
            depth = -corrected[:, 2]
            valid = depth > 1e-6
            if not np.all(valid):
                raise RuntimeError(f"rolling-shutter correction flipped a ray in image {image.image_id}")
            corrected_xy = np.column_stack(
                (fx * corrected[:, 0] / depth + cx, -fy * corrected[:, 1] / depth + cy)
            )
            shifts = np.linalg.norm(corrected_xy - xy, axis=1)
            all_shifts.append(shifts)
            keypoints[:, :2] = corrected_xy.astype(np.float32)
            database.update_keypoints(image.image_id, keypoints)

    shifts = np.concatenate(all_shifts)
    omega = np.linalg.norm(angular_velocities, axis=1)
    result = {
        "schema": "pocketworld_rotation_only_rolling_shutter_keypoints_v1",
        "diagnostic_only": True,
        "input_db": str(args.input),
        "output_db": str(args.output),
        "ledger": str(args.ledger),
        "photo_bundle": str(args.photo_bundle),
        "images": len(frames),
        "parameters": {
            "readout_ms": args.readout_ms,
            "direction": args.direction,
            "reference_row_fraction": args.reference_row_fraction,
            "angular_velocity_source": "neighboring_arkit_camera_rotations",
        },
        "angular_velocity_rad_per_sec": summary(omega),
        "keypoint_shift_px": summary(shifts),
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_features_matches_or_points": False,
    }
    args.stats.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
