#!/usr/bin/env python3
"""Experiment D1: quantify ARKit pose error against COLMAP recalibration.

Parses a COLMAP TXT model (images.txt named 000.jpg..NNN.jpg in manifest
order), aligns the COLMAP trajectory onto the ARKit trajectory with the
official DA3 umeyama (align_poses_umeyama, the exact routine the k-sweep
uses), and reports per-frame camera-center and rotation deltas. Optionally
writes a manifest with extrinsics replaced by the aligned COLMAP poses
(ARKit intrinsics kept) for the D2 re-inference run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


def read_colmap_images_txt(path: Path) -> dict[int, np.ndarray]:
    """Return {frame_index: w2c 4x4} keyed by int(NAME stem)."""
    poses: dict[int, np.ndarray] = {}
    lines = [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    for i in range(0, len(lines), 2):
        parts = lines[i].split()
        qw, qx, qy, qz = (float(v) for v in parts[1:5])
        tx, ty, tz = (float(v) for v in parts[5:8])
        name = parts[9]
        # quaternion -> rotation (COLMAP: x_cam = R x_world + t)
        r = np.array(
            [
                [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
            ],
            dtype=np.float64,
        )
        w2c = np.eye(4)
        w2c[:3, :3] = r
        w2c[:3, 3] = [tx, ty, tz]
        poses[int(Path(name).stem)] = w2c
    return poses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--colmap-model-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--official-src", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--write-colmap-manifest", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.official_src))
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    man = json.loads(args.manifest.read_text())
    frames = man["frames"]
    n = len(frames)
    arkit = np.stack(
        [np.asarray(f["cameraExtrinsic4x4"], dtype=np.float64).reshape(4, 4) for f in frames]
    )
    colmap_map = read_colmap_images_txt(args.colmap_model_dir / "images.txt")
    missing = [i for i in range(n) if i not in colmap_map]
    colmap = np.stack([colmap_map.get(i, np.eye(4)) for i in range(n)])

    # align_poses_umeyama(ext_ref, ext_est): first arg is the reference frame,
    # second is the trajectory being aligned. We want COLMAP poses expressed in
    # the ARKit metric world, so ref=ARKit, est=COLMAP.
    _, _, scale, aligned = align_poses_umeyama(
        arkit.astype(np.float32),
        colmap.astype(np.float32),
        ransac=n >= 10,
        return_aligned=True,
        random_state=42,
    )
    aligned = np.asarray(aligned, dtype=np.float64)

    def center(w2c: np.ndarray) -> np.ndarray:
        return -w2c[:3, :3].T @ w2c[:3, 3]

    rows = []
    for i in range(n):
        if i in missing:
            rows.append({"frame": i, "registered": False})
            continue
        c_err = float(np.linalg.norm(center(aligned[i]) - center(arkit[i])) * 1000.0)
        r_rel = aligned[i, :3, :3] @ arkit[i, :3, :3].T
        ang = float(np.degrees(np.arccos(np.clip((np.trace(r_rel) - 1) / 2, -1, 1))))
        rows.append({"frame": i, "registered": True, "center_err_mm": c_err, "rot_err_deg": ang})

    reg = [r for r in rows if r["registered"]]
    c_errs = np.array([r["center_err_mm"] for r in reg])
    r_errs = np.array([r["rot_err_deg"] for r in reg])
    summary = {
        "registered": len(reg),
        "total": n,
        "umeyama_scale_colmap_to_arkit": float(scale),
        "center_err_mm": {
            "median": float(np.median(c_errs)),
            "mean": float(np.mean(c_errs)),
            "max": float(np.max(c_errs)),
        },
        "rot_err_deg": {
            "median": float(np.median(r_errs)),
            "mean": float(np.mean(r_errs)),
            "max": float(np.max(r_errs)),
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "pocketworld_expD_colmap_vs_arkit_pose_audit_v1",
        "colmap_model_dir": str(args.colmap_model_dir),
        "manifest": str(args.manifest),
        "summary": summary,
        "per_frame": rows,
    }
    (args.out_dir / "expD_colmap_vs_arkit_pose_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("per-frame center_err_mm:", [round(r.get("center_err_mm", -1), 1) for r in rows])
    print("per-frame rot_err_deg:  ", [round(r.get("rot_err_deg", -1), 3) for r in rows])

    if args.write_colmap_manifest:
        if missing:
            print(f"WARN: {len(missing)} frames unregistered, manifest not written: {missing}")
        else:
            man2 = dict(man)
            man2["frames"] = []
            for i, f in enumerate(frames):
                f2 = dict(f)
                f2["cameraExtrinsic4x4"] = [float(v) for v in aligned[i].reshape(-1)]
                man2["frames"].append(f2)
            args.write_colmap_manifest.write_text(json.dumps(man2, indent=2), encoding="utf-8")
            print("colmap-pose manifest written:", args.write_colmap_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
