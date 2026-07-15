#!/usr/bin/env python3
"""Measure stored TVG inliers against capture-time RGB pose geometry."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from canonicalize_match_sites import decode_matches, image_pair


def skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.asarray([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def fundamental(first: dict, second: dict, intrinsic: np.ndarray) -> np.ndarray:
    q1 = np.asarray(first["arkitCamFromWorldQwxyz"], dtype=np.float64)
    q2 = np.asarray(second["arkitCamFromWorldQwxyz"], dtype=np.float64)
    # The ledger stores native ARKit camera axes (+X right, +Y up, -Z
    # forward).  The streaming core applies this exact 180-degree X flip
    # before using the pose with pixel coordinates (+X right, +Y down, +Z
    # forward); mirror that production convention here.
    flip = np.diag([1.0, -1.0, -1.0])
    r1 = flip @ Rotation.from_quat([q1[1], q1[2], q1[3], q1[0]]).as_matrix()
    r2 = flip @ Rotation.from_quat([q2[1], q2[2], q2[3], q2[0]]).as_matrix()
    t1 = flip @ np.asarray(first["arkitCamFromWorldTxyz"], dtype=np.float64)
    t2 = flip @ np.asarray(second["arkitCamFromWorldTxyz"], dtype=np.float64)
    rotation = r2 @ r1.T
    translation = t2 - rotation @ t1
    essential = skew(translation) @ rotation
    inverse = np.linalg.inv(intrinsic)
    return inverse.T @ essential @ inverse


def sampson_px(
    points1: np.ndarray, points2: np.ndarray, matrix: np.ndarray
) -> np.ndarray:
    ones = np.ones((len(points1), 1), dtype=np.float64)
    x1 = np.column_stack((points1, ones))
    x2 = np.column_stack((points2, ones))
    lines2 = (matrix @ x1.T).T
    lines1 = (matrix.T @ x2.T).T
    numerator = np.sum(x2 * lines2, axis=1)
    denominator = (
        lines1[:, 0] ** 2
        + lines1[:, 1] ** 2
        + lines2[:, 0] ** 2
        + lines2[:, 1] ** 2
    )
    return np.abs(numerator) / np.sqrt(np.maximum(denominator, 1e-20))


def summary(values: np.ndarray) -> dict[str, float]:
    return {
        "median": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(np.max(values)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument(
        "--geometry-database",
        type=Path,
        help="optional database supplying fixed verified match identities",
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = {
        row["frameId"]: row
        for row in (
            json.loads(line) for line in args.ledger.read_text().splitlines() if line
        )
    }
    database = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    try:
        cameras = database.execute(
            "SELECT camera_id, model, width, height, params FROM cameras"
        ).fetchall()
        if len(cameras) != 1:
            raise RuntimeError(f"expected one shared camera, got {len(cameras)}")
        _, model, _, _, params_blob = cameras[0]
        params = np.frombuffer(params_blob, dtype=np.float64)
        # SIMPLE_PINHOLE=0 [f,cx,cy], PINHOLE=1 [fx,fy,cx,cy].
        if model == 0:
            fx = fy = params[0]
            cx, cy = params[1:3]
        elif model == 1:
            fx, fy, cx, cy = params[:4]
        else:
            raise RuntimeError(f"unsupported diagnostic camera model {model}")
        intrinsic = np.asarray(
            [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64
        )
        keypoints = {
            image_id: np.frombuffer(data, dtype=np.float32).reshape(rows, cols)[:, :2]
            for image_id, rows, cols, data in database.execute(
                "SELECT image_id, rows, cols, data FROM keypoints"
            )
        }
        residuals: list[np.ndarray] = []
        pair_medians: list[float] = []
        geometry_database = database
        if args.geometry_database is not None:
            geometry_database = sqlite3.connect(
                f"file:{args.geometry_database}?mode=ro", uri=True
            )
        for pair_id, rows, cols, data in geometry_database.execute(
            "SELECT pair_id, rows, cols, data FROM two_view_geometries "
            "WHERE rows > 0 ORDER BY pair_id"
        ):
            image1, image2 = image_pair(pair_id)
            matches = decode_matches(rows, cols, data)
            matrix = fundamental(ledger[image1 - 1], ledger[image2 - 1], intrinsic)
            values = sampson_px(
                keypoints[image1][matches[:, 0]],
                keypoints[image2][matches[:, 1]],
                matrix,
            )
            residuals.append(values)
            pair_medians.append(float(np.median(values)))
        if geometry_database is not database:
            geometry_database.close()
    finally:
        database.close()
    all_values = np.concatenate(residuals)
    thresholds = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0]
    result = {
        "schema": "pocketworld_arkit_epipolar_diagnostic_v1",
        "database": str(args.database),
        "geometry_database": str(args.geometry_database or args.database),
        "pairs": len(residuals),
        "inliers": len(all_values),
        "sampson_residual_px": summary(all_values),
        "pair_median_residual_px": summary(np.asarray(pair_medians)),
        "retained_pct_by_threshold_px": {
            str(threshold): float(100.0 * np.mean(all_values <= threshold))
            for threshold in thresholds
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
