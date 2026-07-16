#!/usr/bin/env python3
"""Align a legacy arbitrary-scale PocketWorld PLY to its ARKit pose ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as stream:
        count = None
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("truncated PLY header")
            text = line.decode("ascii").strip()
            if text.startswith("element vertex "):
                count = int(text.split()[-1])
            if text == "end_header":
                break
        if count is None:
            raise RuntimeError("missing PLY vertex count")
        dtype = np.dtype(
            [("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
             ("r", "u1"), ("g", "u1"), ("b", "u1")]
        )
        records = np.frombuffer(stream.read(count * dtype.itemsize), dtype=dtype)
        if len(records) != count:
            raise RuntimeError("truncated PLY body")
        xyz = np.column_stack([records[name] for name in ("x", "y", "z")])
        rgb = np.column_stack([records[name] for name in ("r", "g", "b")])
        return xyz.astype(np.float64), rgb.astype(np.uint8)


def quaternion_rotation(q: list[float]) -> np.ndarray:
    w, x, y, z = np.asarray(q, dtype=np.float64)
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def umeyama(source: np.ndarray, target: np.ndarray):
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_zero = source - source_mean
    target_zero = target - target_mean
    u, singular, vt = np.linalg.svd(target_zero.T @ source_zero / len(source))
    diagonal = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        diagonal[-1] = -1
    rotation = u @ np.diag(diagonal) @ vt
    variance = np.mean(np.sum(source_zero * source_zero, axis=1))
    scale = float(np.sum(singular * diagonal) / variance)
    translation = target_mean - scale * rotation @ source_mean
    return scale, rotation, translation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output-npz", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    cloud = args.capture_dir / "sfm_sparse.ply"
    meta_path = args.capture_dir / "sfm_sparse_meta.json"
    ledger_path = args.capture_dir / "sfm_fed_frames.jsonl"
    meta = json.loads(meta_path.read_text())
    ledger = {
        int(row["frameId"]): np.asarray(row["arkitCameraCenterWorld"], dtype=np.float64)
        for row in map(json.loads, ledger_path.read_text().splitlines())
    }
    source, target, frame_ids = [], [], []
    for pose in meta["poses"]:
        frame_id = int(pose["frame_id"])
        if not pose["registered"] or frame_id not in ledger:
            continue
        rotation = quaternion_rotation(pose["quat_wxyz"])
        source.append(-(rotation.T @ np.asarray(pose["t"], dtype=np.float64)))
        target.append(ledger[frame_id])
        frame_ids.append(frame_id)
    if len(source) < 3:
        raise RuntimeError("fewer than three registered ledger correspondences")
    source_array = np.asarray(source)
    target_array = np.asarray(target)
    scale, rotation, translation = umeyama(source_array, target_array)
    aligned_cameras = scale * (rotation @ source_array.T).T + translation
    errors = np.linalg.norm(aligned_cameras - target_array, axis=1)
    xyz, rgb = read_ply(cloud)
    metric_xyz = np.asarray(scale * (rotation @ xyz.T).T + translation, np.float32)

    args.output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output_npz, xyz=metric_xyz, rgb=rgb)
    output = {
        "schema": "pocketworld_legacy_metric_fixture_v1",
        "inputs": {
            "cloud": {"path": str(cloud), "sha256": sha256(cloud)},
            "meta": {"path": str(meta_path), "sha256": sha256(meta_path)},
            "ledger": {"path": str(ledger_path), "sha256": sha256(ledger_path)},
        },
        "transform": {
            "scale": scale,
            "rotation_row_major": rotation.reshape(-1).tolist(),
            "translation": translation.tolist(),
        },
        "registered_overlap": len(frame_ids),
        "camera_error_median_mm": float(np.median(errors) * 1000),
        "camera_error_p90_mm": float(np.percentile(errors, 90) * 1000),
        "camera_error_max_mm": float(np.max(errors) * 1000),
        "point_count": len(metric_xyz),
        "metric_bounds_min": metric_xyz.min(axis=0).tolist(),
        "metric_bounds_max": metric_xyz.max(axis=0).tolist(),
        "output": {"path": str(args.output_npz), "sha256": sha256(args.output_npz)},
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
