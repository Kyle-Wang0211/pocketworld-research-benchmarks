#!/usr/bin/env python3
"""Express per-frame keypoint rays in one deterministic shared camera.

The capture sidecar contains the RGB intrinsics measured for each AR frame.
SfM currently uses a single camera initialized from frame zero.  When focus
changes, identical pixel coordinates no longer represent identical rays.  This
tool removes that input inconsistency without introducing per-frame camera/BA
degrees of freedom:

    normalized ray under K_i -> pixel coordinate under median K_ref

Descriptors and match identities are unchanged.  Two-view geometries must be
re-estimated after running this tool.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path

import numpy as np
import pycolmap


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as output_db:
        source_db.backup(output_db)
        output_db.execute("PRAGMA journal_mode=DELETE")
        output_db.commit()


def frame_id(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match is None:
        raise ValueError(f"cannot infer frame id from {image.name!r}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photo-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--interpolate-missing", action="store_true")
    parser.add_argument(
        "--reference", choices=("median", "database"), default="median"
    )
    args = parser.parse_args()

    ledger = {
        int(row["frameId"]): os.path.basename(row["jpegPath"])
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    bundle = json.loads(args.photo_bundle.read_text())
    intrinsics_by_name: dict[str, np.ndarray] = {}
    for row in bundle.get("frames", []):
        values = row.get("intrinsics") or row.get("intrinsics_fxfycxcy")
        if values is None or len(values) < 4:
            continue
        intrinsics_by_name[row["highresFilename"]] = np.asarray(
            values[:4], dtype=np.float64
        )
    if not intrinsics_by_name:
        raise RuntimeError("photo bundle has no per-frame intrinsics")

    measured = np.stack(list(intrinsics_by_name.values()))
    if args.reference == "database":
        with pycolmap.Database.open(args.input) as input_database:
            input_cameras = input_database.read_all_cameras()
            if len(input_cameras) != 1:
                raise RuntimeError(
                    f"expected one input camera, found {len(input_cameras)}"
                )
            input_camera = input_cameras[0]
            reference_f = float(input_camera.focal_length)
            reference_cx = float(input_camera.principal_point_x)
            reference_cy = float(input_camera.principal_point_y)
    else:
        reference = np.median(measured, axis=0)
        reference_f = float(np.median(reference[:2]))
        reference_cx = float(reference[2])
        reference_cy = float(reference[3])

    copy_database(args.input, args.output)
    known_by_frame = {
        image_frame_id: intrinsics_by_name[image_name]
        for image_frame_id, image_name in ledger.items()
        if image_name in intrinsics_by_name
    }
    known_frame_ids = np.asarray(sorted(known_by_frame), dtype=np.float64)
    known_values = np.stack([known_by_frame[int(value)] for value in known_frame_ids])
    interpolation_loo_errors = []
    if len(known_frame_ids) >= 3:
        for index, held_out in enumerate(known_frame_ids):
            keep = np.ones(len(known_frame_ids), dtype=bool)
            keep[index] = False
            estimate = np.asarray(
                [
                    np.interp(held_out, known_frame_ids[keep], known_values[keep, axis])
                    for axis in range(4)
                ]
            )
            interpolation_loo_errors.append(np.abs(estimate - known_values[index]))

    transformed = 0
    interpolated = []
    missing = []
    shifts = []
    with pycolmap.Database.open(args.output) as database:
        cameras = database.read_all_cameras()
        if len(cameras) != 1:
            raise RuntimeError(f"expected one shared camera, found {len(cameras)}")
        camera = cameras[0]
        if camera.model.name != "SIMPLE_PINHOLE":
            raise RuntimeError(f"expected SIMPLE_PINHOLE, found {camera.model.name}")
        camera.params = np.asarray(
            [reference_f, reference_cx, reference_cy], dtype=np.float64
        )
        database.update_camera(camera)

        for image in database.read_all_images():
            image_frame_id = frame_id(image)
            image_name = ledger[image_frame_id]
            measured_k = intrinsics_by_name.get(image_name)
            if measured_k is None:
                missing.append(image_frame_id)
                if not args.interpolate_missing:
                    continue
                measured_k = np.asarray(
                    [
                        np.interp(image_frame_id, known_frame_ids, known_values[:, axis])
                        for axis in range(4)
                    ],
                    dtype=np.float64,
                )
                interpolated.append(image_frame_id)
            fx, fy, cx, cy = measured_k
            keypoints = database.read_keypoints(image.image_id)
            original_xy = keypoints[:, :2].astype(np.float64)
            transformed_xy = np.empty_like(original_xy)
            transformed_xy[:, 0] = reference_f * (original_xy[:, 0] - cx) / fx + reference_cx
            transformed_xy[:, 1] = reference_f * (original_xy[:, 1] - cy) / fy + reference_cy
            keypoints[:, :2] = transformed_xy.astype(np.float32)
            database.update_keypoints(image.image_id, keypoints)
            shifts.extend(np.linalg.norm(transformed_xy - original_xy, axis=1))
            transformed += 1

    shifts_array = np.asarray(shifts, dtype=np.float64)
    loo_array = np.asarray(interpolation_loo_errors, dtype=np.float64)
    stats = {
        "schema": "pocketworld_shared_intrinsics_ray_normalization_v1",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "ledger": str(args.ledger),
        "photo_bundle": str(args.photo_bundle),
        "pycolmap_version": pycolmap.__version__,
        "reference_intrinsics_f_cx_cy": [reference_f, reference_cx, reference_cy],
        "reference_mode": args.reference,
        "measured_fx_min_median_max": [
            float(measured[:, 0].min()),
            float(np.median(measured[:, 0])),
            float(measured[:, 0].max()),
        ],
        "transformed_frames": transformed,
        "missing_intrinsics_frame_ids": missing,
        "interpolated_intrinsics_frame_ids": interpolated,
        "interpolation_leave_one_out_abs_error": (
            {
                "fx_median_p90_max": [
                    float(np.median(loo_array[:, 0])),
                    float(np.percentile(loo_array[:, 0], 90)),
                    float(np.max(loo_array[:, 0])),
                ],
                "cx_median_p90_max": [
                    float(np.median(loo_array[:, 2])),
                    float(np.percentile(loo_array[:, 2], 90)),
                    float(np.max(loo_array[:, 2])),
                ],
                "cy_median_p90_max": [
                    float(np.median(loo_array[:, 3])),
                    float(np.percentile(loo_array[:, 3], 90)),
                    float(np.max(loo_array[:, 3])),
                ],
            }
            if len(loo_array)
            else None
        ),
        "keypoint_shift_px": {
            "median": float(np.median(shifts_array)),
            "p90": float(np.percentile(shifts_array, 90)),
            "p95": float(np.percentile(shifts_array, 95)),
            "max": float(shifts_array.max()),
        },
        "adds_bundle_adjustment_degrees_of_freedom": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
