#!/usr/bin/env python3
"""Filter tentative physical-site matches with captured RGB camera poses.

This is an upstream correspondence birth gate.  It copies the input COLMAP
database and writes only match pairs that satisfy symmetric epipolar distance
under the captured camera poses.  It never edits an existing reconstruction or
deletes generated 3D points.

The implementation follows hloc's known-pose geometric verification: points
are undistorted into normalized camera coordinates, then checked against both
epipolar lines.  Unlike hloc, this script also writes the known relative pose
and essential matrix so the resulting database is self-describing.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import numpy as np
import pycolmap


FRAME_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def quaternion_wxyz_to_rotation(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.asarray([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def homogeneous(points: np.ndarray) -> np.ndarray:
    return np.pad(points, ((0, 0), (0, 1)), constant_values=1.0)


def epipolar_errors(
    essential: np.ndarray, points1: np.ndarray, points2: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    points1_h = homogeneous(points1)
    points2_h = homogeneous(points2)
    lines2 = points1_h @ essential.T
    lines1 = points2_h @ essential
    numerator = np.abs(np.sum(points1_h * lines1, axis=1))
    errors1 = numerator / np.maximum(np.linalg.norm(lines1[:, :2], axis=1), 1e-15)
    errors2 = numerator / np.maximum(np.linalg.norm(lines2[:, :2], axis=1), 1e-15)
    return errors1, errors2


def frame_id(image: pycolmap.Image) -> int:
    match = FRAME_RE.search(image.name)
    if match is None:
        raise ValueError(f"cannot infer frame id from {image.name!r}")
    return int(match.group(1))


def copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as output_db:
        source_db.backup(output_db)
        output_db.execute("PRAGMA journal_mode=DELETE")
        output_db.commit()


def percentile_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"median": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--max-error-px", type=float, required=True)
    parser.add_argument("--min-inliers", type=int, default=15)
    args = parser.parse_args()

    ledger = {
        int(row["frameId"]): row
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    copy_database(args.input, args.output)

    total_matches = 0
    accepted_matches = 0
    accepted_pairs = 0
    rejected_pairs = 0
    recovered_pairs = 0
    residuals_px: list[float] = []

    with pycolmap.Database.open(args.output) as database:
        images = {image.image_id: image for image in database.read_all_images()}
        cameras = {
            image_id: database.read_camera(image.camera_id)
            for image_id, image in images.items()
        }
        poses: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        keypoints: dict[int, np.ndarray] = {}
        # ARKit camera axes are +X right, +Y up, -Z forward.  COLMAP uses
        # +X right, +Y down, +Z forward.  This is exactly the conversion used
        # by the production C++ add-frame path (C = diag(1, -1, -1)).
        arkit_to_colmap = np.diag([1.0, -1.0, -1.0])
        for image_id, image in images.items():
            row = ledger[frame_id(image)]
            poses[image_id] = (
                arkit_to_colmap
                @ quaternion_wxyz_to_rotation(row["arkitCamFromWorldQwxyz"]),
                arkit_to_colmap
                @ np.asarray(row["arkitCamFromWorldTxyz"], dtype=np.float64),
            )
            keypoints[image_id] = database.read_keypoints(image_id)[:, :2]

        pair_ids, match_arrays = database.read_all_matches()
        geometry_ids, geometries = database.read_two_view_geometries()
        old_geometries = dict(zip(geometry_ids, geometries, strict=True))
        for index, (pair_id, matches) in enumerate(
            zip(pair_ids, match_arrays, strict=True), start=1
        ):
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
            camera1 = cameras[image1]
            camera2 = cameras[image2]
            rotation1, translation1 = poses[image1]
            rotation2, translation2 = poses[image2]
            rotation21 = rotation2 @ rotation1.T
            translation21 = translation2 - rotation21 @ translation1
            relative_pose = pycolmap.Rigid3d(
                pycolmap.Rotation3d(rotation21), translation21
            )
            essential = skew(translation21) @ rotation21

            points1 = camera1.cam_from_img(keypoints[image1][matches[:, 0]])
            points2 = camera2.cam_from_img(keypoints[image2][matches[:, 1]])
            errors1, errors2 = epipolar_errors(essential, points1, points2)
            threshold1 = float(camera1.cam_from_img_threshold(args.max_error_px))
            threshold2 = float(camera2.cam_from_img_threshold(args.max_error_px))
            valid = (errors1 <= threshold1) & (errors2 <= threshold2)
            filtered = np.asarray(matches[valid], dtype=np.uint32)
            total_matches += len(matches)

            database.delete_matches(image1, image2)
            if database.exists_two_view_geometry(image1, image2):
                database.delete_two_view_geometry(image1, image2)
            if len(filtered) < args.min_inliers:
                rejected_pairs += 1
                continue

            database.write_matches(image1, image2, filtered)
            geometry = old_geometries.get(pair_id, pycolmap.TwoViewGeometry())
            geometry.config = pycolmap.TwoViewGeometryConfiguration.CALIBRATED
            geometry.E = essential
            geometry.cam2_from_cam1 = relative_pose
            geometry.inlier_matches = filtered
            database.write_two_view_geometry(image1, image2, geometry)
            accepted_pairs += 1
            accepted_matches += len(filtered)
            recovered_pairs += int(pair_id not in old_geometries)
            residuals_px.extend(
                np.maximum(errors1[valid] / threshold1, errors2[valid] / threshold2)
                * args.max_error_px
            )
            if index % 100 == 0 or index == len(pair_ids):
                print(f"known-pose verification {index}/{len(pair_ids)} pairs")

    stats = {
        "schema": "pocketworld_known_pose_match_verification_v1",
        "input_db": str(args.input),
        "output_db": str(args.output),
        "ledger": str(args.ledger),
        "pycolmap_version": pycolmap.__version__,
        "pose_source": (
            "captured RGB ARKit CamFromWorld transformed by diag(1,-1,-1) "
            "to COLMAP axes; no LiDAR/sceneDepth"
        ),
        "max_error_px": args.max_error_px,
        "min_inliers": args.min_inliers,
        "input_pairs": len(pair_ids),
        "accepted_pairs": accepted_pairs,
        "rejected_pairs": rejected_pairs,
        "recovered_pairs_without_ransac_geometry": recovered_pairs,
        "input_matches": total_matches,
        "accepted_matches": accepted_matches,
        "accepted_match_pct": 100.0 * accepted_matches / max(1, total_matches),
        "accepted_symmetric_epipolar_error_px": percentile_summary(residuals_px),
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
