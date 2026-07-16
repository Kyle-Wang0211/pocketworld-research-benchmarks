#!/usr/bin/env python3
"""Triangulate the same verified graph with shared-K versus captured per-frame K.

All camera poses are fixed to the AR-frame pose ledger.  This deliberately
removes incremental registration and pose BA from the experiment so the only
question is whether using the ray calibration captured with each image changes
the born geometry.  No image, feature, match, observation, or user frame is
deleted by this harness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pycolmap


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quaternion_rotation(qwxyz: list[float]) -> np.ndarray:
    w, x, y, z = np.asarray(qwxyz, dtype=np.float64)
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def load_poses(path: Path) -> dict[int, pycolmap.Rigid3d]:
    conversion = np.diag([1.0, -1.0, -1.0])
    poses: dict[int, pycolmap.Rigid3d] = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            rotation = quaternion_rotation(row["arkitCamFromWorldQwxyz"])
            translation = np.asarray(row["arkitCamFromWorldTxyz"], dtype=np.float64)
            matrix = np.column_stack(
                (conversion @ rotation, conversion @ translation)
            )
            poses[int(row["frameId"])] = pycolmap.Rigid3d(matrix)
    return poses


def build_registered_reconstruction(
    database_path: Path, poses: dict[int, pycolmap.Rigid3d]
) -> pycolmap.Reconstruction:
    database = pycolmap.Database.open(str(database_path))
    reconstruction = pycolmap.Reconstruction()
    for camera in database.read_all_cameras():
        reconstruction.add_camera_with_trivial_rig(camera)
    images = sorted(database.read_all_images(), key=lambda image: image.image_id)
    if len(images) != len(poses):
        raise RuntimeError(f"images={len(images)} poses={len(poses)}")
    for source in images:
        frame_id = int(source.image_id) - 1
        if frame_id not in poses:
            raise RuntimeError(f"missing pose for frame {frame_id}")
        image = pycolmap.Image(
            name=source.name,
            camera_id=source.camera_id,
            image_id=source.image_id,
        )
        reconstruction.add_image_with_trivial_frame(image, poses[frame_id])
    return reconstruction


def run_arm(
    database_path: Path,
    poses: dict[int, pycolmap.Rigid3d],
    output_path: Path,
) -> dict:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    reconstruction = build_registered_reconstruction(database_path, poses)
    options = pycolmap.IncrementalPipelineOptions()
    options.extract_colors = False
    options.random_seed = 0
    options.triangulation.random_seed = 0
    options.triangulation.ignore_two_view_tracks = False
    options.triangulation.min_angle = 2.0
    # Product live creation uses 2 px and roughly f=2600 px.
    angular_error = float(np.degrees(np.arctan2(2.0, 2600.0)))
    options.triangulation.create_max_angle_error = angular_error
    options.triangulation.continue_max_angle_error = angular_error
    options.triangulation.merge_max_reproj_error = 2.0
    options.triangulation.complete_max_reproj_error = 2.0
    result = pycolmap.triangulate_points(
        reconstruction,
        str(database_path),
        ".",
        str(output_path),
        clear_points=True,
        options=options,
        refine_intrinsics=False,
    )
    return {
        "database": str(database_path),
        "database_sha256": sha256(database_path),
        "registered": int(result.num_reg_images()),
        "points": int(result.num_points3D()),
        "observations": int(result.compute_num_observations()),
        "mean_reprojection_px": float(result.compute_mean_reprojection_error()),
        "cameras": int(result.num_cameras()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-db", type=Path, required=True)
    parser.add_argument("--per-frame-db", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    poses = load_poses(args.ledger)
    payload = {
        "schema": "pocketworld_known_pose_intrinsics_ab_v1",
        "ledger": str(args.ledger),
        "ledger_sha256": sha256(args.ledger),
        "shared": run_arm(args.shared_db, poses, args.output_root / "shared"),
        "per_frame": run_arm(
            args.per_frame_db, poses, args.output_root / "per_frame"
        ),
    }
    payload["delta"] = {
        "point_count_pct": 100.0
        * (payload["per_frame"]["points"] / payload["shared"]["points"] - 1.0),
        "mean_reprojection_pct": 100.0
        * (
            payload["per_frame"]["mean_reprojection_px"]
            / payload["shared"]["mean_reprojection_px"]
            - 1.0
        ),
    }
    output = args.output_root / "run.json"
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
