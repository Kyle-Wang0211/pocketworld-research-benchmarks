#!/usr/bin/env python3
"""Measure systematic image-space residual fields without changing the model.

The diagnostic asks whether a per-frame row-dependent residual model explains
held-out reprojection error better than a constant offset.  A strong row-only
signal is evidence for an unmodelled rolling-shutter/readout-time component;
column and two-axis affine fits are reported as controls for intrinsics or more
general calibration errors.  Tracks are split deterministically by point ID so
the score cannot be improved by fitting and evaluating the same observation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap


def projection(
    camera: pycolmap.Camera, image: pycolmap.Image, xyz: np.ndarray
) -> np.ndarray:
    point_cam = (
        np.asarray(image.cam_from_world().rotation.matrix(), dtype=np.float64)
        @ xyz
        + np.asarray(image.cam_from_world().translation, dtype=np.float64)
    )
    if point_cam[2] <= 1e-12:
        raise RuntimeError(f"point behind image {image.image_id}")
    return np.asarray(camera.img_from_cam(point_cam))


def robust_fit(design: np.ndarray, residual: np.ndarray) -> np.ndarray:
    """Huber IRLS with a fixed pixel scale; returns one model per residual axis."""
    weights = np.ones(len(design), dtype=np.float64)
    coefficients = np.linalg.lstsq(design, residual, rcond=None)[0]
    for _ in range(12):
        error_norm = np.linalg.norm(residual - design @ coefficients, axis=1)
        weights = np.minimum(1.0, 2.0 / np.maximum(error_norm, 1e-12))
        root = np.sqrt(weights)
        candidate = np.linalg.lstsq(
            design * root[:, None], residual * root[:, None], rcond=None
        )[0]
        if np.max(np.abs(candidate - coefficients)) <= 1e-9:
            coefficients = candidate
            break
        coefficients = candidate
    return coefficients


def percentile(values: list[float]) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array):
        return {"count": 0, "median": None, "p90": None, "max": None}
    return {
        "count": int(len(array)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "max": float(np.max(array)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--holdout-modulus", type=int, default=5)
    parser.add_argument("--holdout-remainder", type=int, default=0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    reconstruction = pycolmap.Reconstruction(args.model)
    frames = []
    for image_id, image in sorted(reconstruction.images.items()):
        camera = reconstruction.cameras[image.camera_id]
        point_ids = []
        observed = []
        residuals = []
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point_id = int(point2d.point3D_id)
            predicted = projection(
                camera,
                image,
                np.asarray(reconstruction.points3D[point_id].xyz, dtype=np.float64),
            )
            point_ids.append(point_id)
            observed.append(np.asarray(point2d.xy, dtype=np.float64))
            residuals.append(np.asarray(point2d.xy, dtype=np.float64) - predicted)
        if len(point_ids) < 20:
            continue

        point_ids_array = np.asarray(point_ids, dtype=np.int64)
        observed_array = np.asarray(observed, dtype=np.float64)
        residual_array = np.asarray(residuals, dtype=np.float64)
        holdout = (
            point_ids_array % args.holdout_modulus == args.holdout_remainder
        )
        train = ~holdout
        if np.count_nonzero(train) < 10 or np.count_nonzero(holdout) < 5:
            continue

        x = (observed_array[:, 0] - camera.principal_point_x) / (
            0.5 * camera.width
        )
        y = (observed_array[:, 1] - camera.principal_point_y) / (
            0.5 * camera.height
        )
        designs = {
            "constant": np.column_stack((np.ones(len(x)),)),
            "row": np.column_stack((np.ones(len(x)), y)),
            "column": np.column_stack((np.ones(len(x)), x)),
            "affine": np.column_stack((np.ones(len(x)), x, y)),
        }
        scores = {}
        for name, design in designs.items():
            coefficients = robust_fit(design[train], residual_array[train])
            holdout_error = residual_array[holdout] - design[holdout] @ coefficients
            scores[name] = {
                "holdout_sse_px2": float(np.sum(holdout_error**2)),
                "holdout_rmse_px": float(np.sqrt(np.mean(holdout_error**2))),
                "coefficients": coefficients.tolist(),
            }
        constant_sse = scores["constant"]["holdout_sse_px2"]
        for name in ("row", "column", "affine"):
            scores[name]["holdout_sse_reduction"] = float(
                1.0 - scores[name]["holdout_sse_px2"] / constant_sse
            )
        row_slope = np.asarray(scores["row"]["coefficients"])[1]
        column_slope = np.asarray(scores["column"]["coefficients"])[1]
        frames.append(
            {
                "image_id": int(image_id),
                "image_name": image.name,
                "observations": int(len(point_ids)),
                "train_observations": int(np.count_nonzero(train)),
                "holdout_observations": int(np.count_nonzero(holdout)),
                "raw_reprojection_rmse_px": float(
                    np.sqrt(np.mean(residual_array**2))
                ),
                "row_top_to_bottom_vector_px": (2.0 * row_slope).tolist(),
                "row_top_to_bottom_magnitude_px": float(
                    2.0 * np.linalg.norm(row_slope)
                ),
                "column_left_to_right_vector_px": (2.0 * column_slope).tolist(),
                "column_left_to_right_magnitude_px": float(
                    2.0 * np.linalg.norm(column_slope)
                ),
                "models": scores,
            }
        )

    row_reduction = [f["models"]["row"]["holdout_sse_reduction"] for f in frames]
    column_reduction = [
        f["models"]["column"]["holdout_sse_reduction"] for f in frames
    ]
    affine_reduction = [
        f["models"]["affine"]["holdout_sse_reduction"] for f in frames
    ]
    payload = {
        "schema": "pocketworld_reprojection_field_diagnostic_v1",
        "diagnostic_only": True,
        "changes_model_or_observations": False,
        "model": str(args.model),
        "registered_frames": len(reconstruction.images),
        "evaluated_frames": len(frames),
        "holdout_rule": {
            "unit": "point3D_id",
            "modulus": args.holdout_modulus,
            "remainder": args.holdout_remainder,
        },
        "aggregate": {
            "row_holdout_sse_reduction": percentile(row_reduction),
            "column_holdout_sse_reduction": percentile(column_reduction),
            "affine_holdout_sse_reduction": percentile(affine_reduction),
            "row_top_to_bottom_magnitude_px": percentile(
                [f["row_top_to_bottom_magnitude_px"] for f in frames]
            ),
            "column_left_to_right_magnitude_px": percentile(
                [f["column_left_to_right_magnitude_px"] for f in frames]
            ),
        },
        "frames": frames,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
