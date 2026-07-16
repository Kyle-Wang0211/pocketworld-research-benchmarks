#!/usr/bin/env python3
"""Materialize SfmLiveSnapshot pose metadata from an exact C-ABI pose dump."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poses-npz", type=Path, required=True)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-label", required=True)
    args = parser.parse_args()

    poses_path = args.poses_npz.resolve()
    validation_path = args.validation.resolve() if args.validation else None
    with np.load(poses_path) as archive:
        poses = np.asarray(archive["poses"], dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 9:
        raise RuntimeError(f"unexpected pose shape {poses.shape}")
    frame_ids = poses[:, 0].astype(np.int64)
    if not np.array_equal(frame_ids, np.arange(len(poses))):
        raise RuntimeError("poses are not ordered contiguous frame ids")
    if not np.all(np.isin(poses[:, 1], [0.0, 1.0])):
        raise RuntimeError("registered column is not binary")
    validation = None
    if validation_path is not None:
        validation = json.loads(validation_path.read_text())
        if int(validation["registered"]) != int(np.count_nonzero(poses[:, 1])):
            raise RuntimeError("validation registered count disagrees")

    rows = []
    for row in poses:
        rows.append(
            {
                "frame_id": int(row[0]),
                "registered": bool(row[1]),
                "quat_wxyz": [float(value) for value in row[2:6]],
                "t": [float(value) for value in row[6:9]],
            }
        )
    result = {
        "schema": "pocketworld_exact_c_abi_pose_meta_v1",
        "refined": True,
        "summary": {
            "n_registered": int(np.count_nonzero(poses[:, 1])),
            "pose_rows": int(len(poses)),
            "replay_label": args.replay_label,
        },
        "immutable_source": {
            "poses_npz": {
                "path": str(poses_path),
                "bytes": poses_path.stat().st_size,
                "sha256": sha256(poses_path),
            },
            "validation": (
                {
                    "path": str(validation_path),
                    "bytes": validation_path.stat().st_size,
                    "sha256": sha256(validation_path),
                }
                if validation_path is not None
                else None
            ),
        },
        "poses": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "registered": result["summary"]["n_registered"],
                "source_sha256": result["immutable_source"]["poses_npz"][
                    "sha256"
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
