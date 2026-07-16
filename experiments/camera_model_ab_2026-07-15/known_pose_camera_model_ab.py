#!/usr/bin/env python3
"""Fixed-ARKit-pose camera-model diagnostic on one immutable match graph.

The three arms share images, keypoints, verified matches, poses, and
triangulation thresholds.  Only intrinsic refinement/model complexity differs:

* SIMPLE_PINHOLE fixed (the current input calibration),
* SIMPLE_PINHOLE with focal refinement,
* SIMPLE_RADIAL with shared focal and one shared radial coefficient refinement.

No database row or captured frame is modified or deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import struct
from pathlib import Path

import numpy as np
import pycolmap


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_table_hash(path: Path, table: str) -> str:
    """Hash a SQLite table by typed values, independent of page layout."""
    digest = hashlib.sha256()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    digest.update(json.dumps(columns, separators=(",", ":")).encode())
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    connection.close()
    for row in rows:
        for value in row:
            if value is None:
                payload = b"N"
            elif isinstance(value, int):
                payload = b"I" + struct.pack("<q", value)
            elif isinstance(value, float):
                payload = b"F" + struct.pack("<d", value)
            elif isinstance(value, bytes):
                payload = b"B" + value
            else:
                payload = b"S" + str(value).encode()
            digest.update(struct.pack("<Q", len(payload)))
            digest.update(payload)
    return digest.hexdigest()


def graph_hashes(path: Path) -> dict[str, str]:
    return {
        "matches": sqlite_table_hash(path, "matches"),
        "two_view_geometries": sqlite_table_hash(path, "two_view_geometries"),
        "keypoints": sqlite_table_hash(path, "keypoints"),
        "descriptors": sqlite_table_hash(path, "descriptors"),
        "images": sqlite_table_hash(path, "images"),
    }


def clone_with_camera_model(source: Path, destination: Path, model_name: str) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    shutil.copy2(source, destination)
    database = pycolmap.Database.open(str(destination))
    cameras = database.read_all_cameras()
    for camera in cameras:
        database.update_camera(converted_camera(camera, model_name))
    del database


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
            poses[int(row["frameId"])] = pycolmap.Rigid3d(
                np.column_stack((conversion @ rotation, conversion @ translation))
            )
    return poses


def converted_camera(source: pycolmap.Camera, model_name: str) -> pycolmap.Camera:
    if source.model.name not in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL"}:
        raise RuntimeError(f"unsupported input camera model {source.model.name}")
    focal, cx, cy = map(float, source.params[:3])
    camera = pycolmap.Camera.create_from_model_name(
        source.camera_id, model_name, focal, source.width, source.height
    )
    if model_name == "SIMPLE_PINHOLE":
        camera.params = np.asarray([focal, cx, cy], dtype=np.float64)
    elif model_name == "SIMPLE_RADIAL":
        radial = float(source.params[3]) if source.model.name == model_name else 0.0
        camera.params = np.asarray([focal, cx, cy, radial], dtype=np.float64)
    else:
        raise ValueError(model_name)
    camera.has_prior_focal_length = True
    return camera


def build_registered_reconstruction(
    database_path: Path,
    poses: dict[int, pycolmap.Rigid3d],
    model_name: str,
) -> pycolmap.Reconstruction:
    database = pycolmap.Database.open(str(database_path))
    reconstruction = pycolmap.Reconstruction()
    for source in database.read_all_cameras():
        reconstruction.add_camera_with_trivial_rig(converted_camera(source, model_name))
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


def camera_payload(camera: pycolmap.Camera) -> dict:
    return {
        "camera_id": int(camera.camera_id),
        "model": camera.model.name,
        "width": int(camera.width),
        "height": int(camera.height),
        "params": [float(value) for value in camera.params],
    }


def run_arm(
    database_path: Path,
    poses: dict[int, pycolmap.Rigid3d],
    output_path: Path,
    model_name: str,
    refine_intrinsics: bool,
) -> dict:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    reconstruction = build_registered_reconstruction(database_path, poses, model_name)
    initial_cameras = [
        camera_payload(reconstruction.cameras[camera_id])
        for camera_id in sorted(reconstruction.cameras)
    ]
    options = pycolmap.IncrementalPipelineOptions()
    options.extract_colors = False
    options.random_seed = 0
    options.triangulation.random_seed = 0
    options.triangulation.ignore_two_view_tracks = False
    options.triangulation.min_angle = 2.0
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
        refine_intrinsics=refine_intrinsics,
    )
    final_cameras = [
        camera_payload(result.cameras[camera_id])
        for camera_id in sorted(result.cameras)
    ]
    return {
        "database": str(database_path),
        "database_sha256": sha256(database_path),
        "model": model_name,
        "refine_intrinsics": refine_intrinsics,
        "registered": int(result.num_reg_images()),
        "points": int(result.num_points3D()),
        "observations": int(result.compute_num_observations()),
        "mean_reprojection_px": float(result.compute_mean_reprojection_error()),
        "initial_cameras": initial_cameras,
        "final_cameras": final_cameras,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_root}")
    args.output_root.mkdir(parents=True)
    poses = load_poses(args.ledger)
    radial_database = args.output_root / "simple_radial_input.db"
    clone_with_camera_model(args.database, radial_database, "SIMPLE_RADIAL")
    source_graph = graph_hashes(args.database)
    radial_graph = graph_hashes(radial_database)
    if radial_graph != source_graph:
        raise RuntimeError("camera conversion changed the immutable match graph")
    payload = {
        "schema": "pocketworld_known_pose_camera_model_ab_v1",
        "pycolmap_version": pycolmap.__version__,
        "diagnostic_only_until_colmap_4_1_rerun": pycolmap.__version__ != "4.1.0",
        "database": str(args.database),
        "database_sha256": sha256(args.database),
        "ledger": str(args.ledger),
        "ledger_sha256": sha256(args.ledger),
        "source_graph_hashes": source_graph,
        "radial_graph_hashes": radial_graph,
        "graph_identity_verified": True,
        "arms": {},
    }
    for name, model, refine in (
        ("simple_pinhole_fixed", "SIMPLE_PINHOLE", False),
        ("simple_pinhole_refined", "SIMPLE_PINHOLE", True),
        ("simple_radial_refined", "SIMPLE_RADIAL", True),
    ):
        database = radial_database if model == "SIMPLE_RADIAL" else args.database
        payload["arms"][name] = run_arm(
            database, poses, args.output_root / name, model, refine
        )
    baseline = payload["arms"]["simple_pinhole_fixed"]
    for arm in payload["arms"].values():
        arm["delta_vs_fixed"] = {
            "points_pct": 100.0 * (arm["points"] / baseline["points"] - 1.0),
            "observations_pct": 100.0
            * (arm["observations"] / baseline["observations"] - 1.0),
            "mean_reprojection_pct": 100.0
            * (
                arm["mean_reprojection_px"]
                / baseline["mean_reprojection_px"]
                - 1.0
            ),
        }
    output = args.output_root / "run.json"
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
