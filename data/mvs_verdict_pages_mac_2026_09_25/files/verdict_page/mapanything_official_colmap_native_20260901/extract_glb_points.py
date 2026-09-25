#!/usr/bin/env python3
"""Extract the official GLB vertex/color accessors without changing geometry.

The output positions are the exact concatenation of the GLB POSITION accessors.
The RGB stream drops only the constant alpha channel from COLOR_0.  The GLB node
matrix is stored in meta.json and is applied by the viewer, not baked into the
position stream.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import struct
from pathlib import Path

import numpy as np


GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_header(stream):
    magic, version, declared_size = struct.unpack("<III", stream.read(12))
    if magic != GLB_MAGIC or version != 2:
        raise ValueError("expected a GLB 2.0 file")
    json_size, json_type = struct.unpack("<II", stream.read(8))
    if json_type != JSON_CHUNK:
        raise ValueError("first GLB chunk is not JSON")
    model = json.loads(stream.read(json_size))
    bin_size, bin_type = struct.unpack("<II", stream.read(8))
    if bin_type != BIN_CHUNK:
        raise ValueError("second GLB chunk is not BIN")
    binary_offset = stream.tell()
    if declared_size != stream.seek(0, 2):
        raise ValueError("GLB declared size does not match file size")
    if binary_offset + bin_size > declared_size:
        raise ValueError("GLB binary chunk exceeds file size")
    return model, binary_offset, bin_size


def accessor_span(model, accessor_index: int, binary_offset: int, item_size: int):
    accessor = model["accessors"][accessor_index]
    view = model["bufferViews"][accessor["bufferView"]]
    count = int(accessor["count"])
    stride = int(view.get("byteStride", item_size))
    if stride != item_size:
        raise ValueError(
            f"accessor {accessor_index} is interleaved: stride {stride}, expected {item_size}"
        )
    offset = binary_offset + int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, offset, count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    pos_path = args.out / "official_colmap_native.pos"
    col_path = args.out / "official_colmap_native.col"
    meta_path = args.out / "meta.json"

    with args.glb.open("rb") as stream:
        model, binary_offset, _ = read_header(stream)
        nodes_by_mesh = {
            int(node["mesh"]): node
            for node in model.get("nodes", [])
            if "mesh" in node
        }
        meshes = model.get("meshes", [])
        if len(nodes_by_mesh) != len(meshes):
            raise ValueError("every mesh must have exactly one scene node")

        matrices = []
        samples = []
        total = 0
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped, pos_path.open(
            "wb"
        ) as pos_out, col_path.open("wb") as col_out:
            for mesh_index, mesh in enumerate(meshes):
                primitives = mesh.get("primitives", [])
                if len(primitives) != 1:
                    raise ValueError(f"mesh {mesh_index} does not have exactly one primitive")
                primitive = primitives[0]
                attrs = primitive["attributes"]
                pos_accessor, pos_offset, pos_count = accessor_span(
                    model, int(attrs["POSITION"]), binary_offset, 12
                )
                col_accessor, col_offset, col_count = accessor_span(
                    model, int(attrs["COLOR_0"]), binary_offset, 4
                )
                if (
                    pos_accessor["componentType"] != 5126
                    or pos_accessor["type"] != "VEC3"
                ):
                    raise ValueError(f"mesh {mesh_index} POSITION is not float32 VEC3")
                if (
                    col_accessor["componentType"] != 5121
                    or col_accessor["type"] != "VEC4"
                    or not col_accessor.get("normalized", False)
                ):
                    raise ValueError(f"mesh {mesh_index} COLOR_0 is not normalized uint8 VEC4")
                if pos_count != col_count:
                    raise ValueError(f"mesh {mesh_index} position/color count mismatch")

                pos_bytes = memoryview(mapped)[pos_offset : pos_offset + pos_count * 12]
                pos_out.write(pos_bytes)
                del pos_bytes

                colors = np.frombuffer(
                    mapped, dtype=np.uint8, count=pos_count * 4, offset=col_offset
                ).reshape(pos_count, 4)
                if not np.all(colors[:, 3] == 255):
                    raise ValueError(f"mesh {mesh_index} alpha is not uniformly 255")
                for start in range(0, pos_count, 1_000_000):
                    np.ascontiguousarray(colors[start : start + 1_000_000, :3]).tofile(col_out)

                matrix_values = nodes_by_mesh[mesh_index].get(
                    "matrix",
                    [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                )
                matrices.append([float(value) for value in matrix_values])
                matrix = np.asarray(matrix_values, dtype=np.float64).reshape(4, 4, order="F")
                xyz = np.frombuffer(
                    mapped, dtype="<f4", count=pos_count * 3, offset=pos_offset
                ).reshape(pos_count, 3)
                stride = max(1, pos_count // 4096)
                sample = xyz[::stride].astype(np.float64)
                sample = sample @ matrix[:3, :3].T + matrix[:3, 3]
                samples.append(sample)
                total += pos_count
                # NumPy's frombuffer arrays export the mmap buffer.  Drop the
                # per-mesh views before the mmap context attempts to close.
                del colors, xyz

    if any(matrix != matrices[0] for matrix in matrices[1:]):
        raise ValueError("viewer contract requires one common official node matrix")

    sample = np.concatenate(samples, axis=0)
    low, high = np.percentile(sample, [1, 99], axis=0)
    median = np.median(sample, axis=0)
    radius = float(np.percentile(np.linalg.norm(sample - median, axis=1), 95))
    meta = {
        "tag": "official_colmap_native",
        "n": int(total),
        "raw_inference_points": 24751408,
        "center": ((low + high) / 2).astype(float).tolist(),
        "ext": (high - low).astype(float).tolist(),
        "med": median.astype(float).tolist(),
        "radius": radius,
        "node_matrix": matrices[0],
        "source_glb": str(args.glb),
        "source_glb_sha256": sha256(args.glb),
        "position_sha256": sha256(pos_path),
        "color_sha256": sha256(col_path),
        "position_bytes": pos_path.stat().st_size,
        "color_bytes": col_path.stat().st_size,
        "extraction": "POSITION accessors concatenated byte-for-byte; COLOR_0 RGB retained; alpha=255 dropped; official node matrix applied only by viewer",
    }
    if meta["position_bytes"] != total * 12 or meta["color_bytes"] != total * 3:
        raise ValueError("output byte count does not match vertex count")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
