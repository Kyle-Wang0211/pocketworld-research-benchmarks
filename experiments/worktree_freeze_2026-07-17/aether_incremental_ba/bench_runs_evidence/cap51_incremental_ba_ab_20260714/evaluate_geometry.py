#!/usr/bin/env python3
"""Geometry diagnostics for the cap51 incremental-BA OFF/ON replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap


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
    translation = dst_mean - scale * (rotation @ src_mean)
    return scale, rotation, translation


def occupied_cells(points: np.ndarray, axes: tuple[int, int], cell: float = 0.05) -> int:
    if len(points) == 0:
        return 0
    cells = np.floor(points[:, axes] / cell).astype(np.int64)
    return int(len(np.unique(cells, axis=0)))


def fit_residual(points: np.ndarray, dependent: int, independent: tuple[int, int]) -> np.ndarray:
    design = np.column_stack(
        [points[:, independent[0]], points[:, independent[1]], np.ones(len(points))]
    )
    coef, _, _, _ = np.linalg.lstsq(design, points[:, dependent], rcond=None)
    return points[:, dependent] - design @ coef


def score(model_dir: Path, ledger: list[dict]) -> dict[str, float | int]:
    reconstruction = pycolmap.Reconstruction(model_dir)
    rec_centers = []
    arkit_centers = []
    for image in reconstruction.images.values():
        frame_id = int(Path(image.name).stem.split("_")[-1])
        rec_centers.append(image.projection_center())
        arkit_centers.append(ledger[frame_id]["arkitCameraCenterWorld"])
    rec_centers_array = np.asarray(rec_centers, dtype=np.float64)
    arkit_centers_array = np.asarray(arkit_centers, dtype=np.float64)
    scale, rotation, translation = umeyama(rec_centers_array, arkit_centers_array)
    aligned_centers = scale * (rotation @ rec_centers_array.T).T + translation
    camera_residual = np.linalg.norm(aligned_centers - arkit_centers_array, axis=1)

    xyz = np.asarray([point.xyz for point in reconstruction.points3D.values()])
    metric = scale * (rotation @ xyz.T).T + translation
    y = metric[:, 1]
    y02, y15, y85, y98 = np.percentile(y, [2, 15, 85, 98])

    floor = metric[(y >= y02) & (y <= y15)]
    floor_residual = fit_residual(floor, dependent=1, independent=(0, 2))
    floor_thickness_mm = float(
        (np.percentile(floor_residual, 84) - np.percentile(floor_residual, 16)) * 1000
    )

    ceiling = metric[(y >= y85) & (y <= y98)]
    ceiling_residual = fit_residual(ceiling, dependent=1, independent=(0, 2))
    ceiling_inliers = ceiling[np.abs(ceiling_residual) <= 0.05]

    lo = np.percentile(metric, 2, axis=0)
    hi = np.percentile(metric, 98, axis=0)
    wall_masks = (
        metric[:, 0] <= lo[0] + 0.12,
        metric[:, 0] >= hi[0] - 0.12,
        metric[:, 2] <= lo[2] + 0.12,
        metric[:, 2] >= hi[2] - 0.12,
    )
    wall_cells = 0
    wall_points = 0
    for index, mask in enumerate(wall_masks):
        slab = metric[mask]
        if len(slab) < 3:
            continue
        if index < 2:
            residual = fit_residual(slab, dependent=0, independent=(1, 2))
            axes = (1, 2)
        else:
            residual = fit_residual(slab, dependent=2, independent=(0, 1))
            axes = (0, 1)
        inliers = slab[np.abs(residual) <= 0.05]
        wall_points += len(inliers)
        wall_cells += occupied_cells(inliers, axes)

    return {
        "registered_frames": len(reconstruction.images),
        "sparse_points": len(reconstruction.points3D),
        "arkit_alignment_scale": scale,
        "arkit_camera_median_mm": float(np.median(camera_residual) * 1000),
        "arkit_camera_p95_mm": float(np.percentile(camera_residual, 95) * 1000),
        "floor_band_points": len(floor),
        "floor_thickness_mm": floor_thickness_mm,
        "floor_5cm_cells": occupied_cells(floor, (0, 2)),
        "ceiling_inlier_points": len(ceiling_inliers),
        "ceiling_5cm_cells": occupied_cells(ceiling_inliers, (0, 2)),
        "wall_inlier_points": wall_points,
        "wall_5cm_cells": wall_cells,
        "wall_ceiling_coverage_cells": wall_cells + occupied_cells(ceiling_inliers, (0, 2)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    ledger = [json.loads(line) for line in args.ledger.read_text().splitlines() if line]
    result = {arm: score(args.root / arm, ledger) for arm in ("off", "on")}
    result["delta_on_vs_off"] = {
        key: result["on"][key] - result["off"][key]
        for key in result["off"]
        if isinstance(result["off"][key], (int, float))
    }
    output = args.root / "geometry_metrics.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"WROTE {output}")


if __name__ == "__main__":
    main()
