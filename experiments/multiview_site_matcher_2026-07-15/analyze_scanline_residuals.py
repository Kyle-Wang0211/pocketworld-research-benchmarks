#!/usr/bin/env python3
"""Measure scanline- and column-correlated reprojection residuals.

This is a diagnostic, not a rolling-shutter correction.  For each registered
image it robustly fits the two-dimensional reprojection residual as an affine
function of normalized image x/y.  A rolling-shutter-like signature should
produce a coherent residual vector that changes with scanline y and is larger
than the corresponding column term.  Pose, lens, and feature-localization
errors can produce similar fields, so this tool reports evidence rather than a
causal label.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap


def robust_affine(coordinates: np.ndarray, residuals: np.ndarray) -> np.ndarray:
    """Return a 3x2 Cauchy-IRLS fit for [1, normalized_x, normalized_y]."""
    design = np.column_stack((np.ones(len(coordinates)), coordinates))
    weights = np.ones(len(design), dtype=np.float64)
    coefficients = np.zeros((3, 2), dtype=np.float64)
    for _ in range(12):
        root_weights = np.sqrt(weights)[:, None]
        coefficients, *_ = np.linalg.lstsq(
            design * root_weights, residuals * root_weights, rcond=None
        )
        errors = np.linalg.norm(residuals - design @ coefficients, axis=1)
        scale = max(0.15, 1.4826 * float(np.median(np.abs(errors - np.median(errors)))))
        weights = 1.0 / (1.0 + (errors / (2.5 * scale)) ** 2)
    return coefficients


def partial_r2(
    coordinates: np.ndarray, residuals: np.ndarray, axis: int
) -> float:
    """Contribution of one coordinate after accounting for the other."""
    other = 1 - axis
    reduced = np.column_stack((np.ones(len(coordinates)), coordinates[:, other]))
    full = np.column_stack((reduced, coordinates[:, axis]))
    reduced_fit, *_ = np.linalg.lstsq(reduced, residuals, rcond=None)
    full_fit, *_ = np.linalg.lstsq(full, residuals, rcond=None)
    reduced_sse = float(np.sum((residuals - reduced @ reduced_fit) ** 2))
    full_sse = float(np.sum((residuals - full @ full_fit) ** 2))
    return max(0.0, (reduced_sse - full_sse) / max(reduced_sse, 1e-12))


def summarize(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "max": float(np.max(array)),
    }


def analyze(model: Path) -> dict:
    reconstruction = pycolmap.Reconstruction(model)
    per_image = []
    all_errors = []
    for image_id in sorted(reconstruction.images):
        image = reconstruction.images[image_id]
        camera = reconstruction.cameras[image.camera_id]
        coordinates = []
        residuals = []
        for point2d in image.points2D:
            if not point2d.has_point3D():
                continue
            point = reconstruction.points3D[int(point2d.point3D_id)]
            camera_point = image.cam_from_world() * point.xyz
            if camera_point[2] <= 0.0:
                continue
            predicted = camera.img_from_cam(camera_point)
            if predicted is None:
                continue
            residual = np.asarray(point2d.xy, dtype=np.float64) - np.asarray(
                predicted, dtype=np.float64
            )
            coordinates.append(
                (
                    float(point2d.xy[0]) / float(camera.width) - 0.5,
                    float(point2d.xy[1]) / float(camera.height) - 0.5,
                )
            )
            residuals.append(residual)
            all_errors.append(float(np.linalg.norm(residual)))
        coordinates_array = np.asarray(coordinates, dtype=np.float64)
        residuals_array = np.asarray(residuals, dtype=np.float64)
        if len(residuals_array) < 20:
            continue
        coefficients = robust_affine(coordinates_array, residuals_array)
        column_vector = coefficients[1]
        row_vector = coefficients[2]
        per_image.append(
            {
                "image_id": int(image_id),
                "observations": int(len(residuals_array)),
                "residual_rms_px": float(
                    np.sqrt(np.mean(np.sum(residuals_array**2, axis=1)))
                ),
                "column_vector_px_per_full_width": column_vector.tolist(),
                "column_slope_px_per_full_width": float(np.linalg.norm(column_vector)),
                "row_vector_px_per_full_height": row_vector.tolist(),
                "row_slope_px_per_full_height": float(np.linalg.norm(row_vector)),
                "column_partial_r2": partial_r2(
                    coordinates_array, residuals_array, axis=0
                ),
                "row_partial_r2": partial_r2(
                    coordinates_array, residuals_array, axis=1
                ),
            }
        )

    row_slopes = [row["row_slope_px_per_full_height"] for row in per_image]
    column_slopes = [row["column_slope_px_per_full_width"] for row in per_image]
    row_r2 = [row["row_partial_r2"] for row in per_image]
    column_r2 = [row["column_partial_r2"] for row in per_image]
    return {
        "schema": "pocketworld_scanline_residual_diagnostic_v1",
        "diagnostic_only": True,
        "model": str(model),
        "registered_images": int(reconstruction.num_reg_images()),
        "points3D": int(reconstruction.num_points3D()),
        "observations": int(len(all_errors)),
        "global_residual_rms_px": float(
            np.sqrt(np.mean(np.asarray(all_errors, dtype=np.float64) ** 2))
        ),
        "row_slope_px_per_full_height": summarize(row_slopes),
        "column_slope_px_per_full_width": summarize(column_slopes),
        "row_to_column_slope_ratio_median": float(
            np.median(np.asarray(row_slopes) / np.maximum(column_slopes, 1e-12))
        ),
        "row_partial_r2": summarize(row_r2),
        "column_partial_r2": summarize(column_r2),
        "per_image": per_image,
        "interpretation_guard": (
            "A row-correlated field is not by itself proof of rolling shutter; "
            "pose, distortion, and feature localization remain confounders."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm", action="append", required=True)
    args = parser.parse_args()
    arms = {}
    for arm in args.arm:
        name, separator, model = arm.partition("=")
        if not separator:
            raise ValueError(f"invalid --arm {arm!r}; expected name=model")
        arms[name] = analyze(Path(model))
    result = {"schema": "pocketworld_scanline_residual_ab_v1", "arms": arms}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
