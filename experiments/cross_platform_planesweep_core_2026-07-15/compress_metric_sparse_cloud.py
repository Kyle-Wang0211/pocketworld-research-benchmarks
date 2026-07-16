#!/usr/bin/env python3
"""Convert an already-metric product sparse PLY to a compressed NPZ fixture."""

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


def read_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as stream:
        if stream.readline().strip() != b"ply":
            raise RuntimeError("not a PLY file")
        fmt = stream.readline().strip()
        count = None
        properties = []
        while True:
            line = stream.readline().strip()
            if line.startswith(b"element vertex "):
                count = int(line.split()[-1])
            elif line.startswith(b"property "):
                properties.append(line.split()[-1].decode())
            elif line == b"end_header":
                break
        if count is None:
            raise RuntimeError("missing vertex count")
        if fmt == b"format ascii 1.0":
            rows = np.asarray(
                [list(map(float, stream.readline().split())) for _ in range(count)]
            )
            xyz = rows[:, :3].astype(np.float32)
            rgb = rows[:, 3:6].astype(np.uint8) if rows.shape[1] >= 6 else np.zeros((count, 3), np.uint8)
            return xyz, rgb
        if fmt != b"format binary_little_endian 1.0":
            raise RuntimeError(f"unsupported PLY format {fmt!r}")
        dtype = np.dtype(
            [
                (name, "u1" if name in {"red", "green", "blue"} else "<f4")
                for name in properties
            ]
        )
        rows = np.frombuffer(stream.read(count * dtype.itemsize), dtype=dtype, count=count)
        if len(rows) != count:
            raise RuntimeError("truncated PLY body")
        xyz = np.column_stack([rows[name] for name in ("x", "y", "z")]).astype(np.float32)
        if all(name in rows.dtype.names for name in ("red", "green", "blue")):
            rgb = np.column_stack([rows[name] for name in ("red", "green", "blue")]).astype(np.uint8)
        else:
            rgb = np.zeros((count, 3), dtype=np.uint8)
        return xyz, rgb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    xyz, rgb = read_ply(args.input)
    if not np.all(np.isfinite(xyz)):
        raise RuntimeError("non-finite coordinates")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, xyz=xyz, rgb=rgb)
    manifest = {
        "schema": "aether_metric_sparse_npz_v1",
        "input": {"path": str(args.input), "sha256": sha256(args.input)},
        "point_count": int(len(xyz)),
        "bounds_min": xyz.min(axis=0).tolist(),
        "bounds_max": xyz.max(axis=0).tolist(),
        "output": {"path": str(args.output), "sha256": sha256(args.output)},
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
