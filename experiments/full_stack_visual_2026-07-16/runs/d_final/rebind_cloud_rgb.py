#!/usr/bin/env python3
"""Replace RGB only after proving point order through an exact old-RGB anchor."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


ASSEMBLER = Path(__file__).resolve().parents[2] / "assemble_full_stack.py"
SPEC = importlib.util.spec_from_file_location("assemble_full_stack", ASSEMBLER)
assert SPEC is not None and SPEC.loader is not None
assembler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assembler
SPEC.loader.exec_module(assembler)


def bits(xyz: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(xyz.astype("<f4")).view("<u4").reshape((-1, 3))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-ply", type=Path, required=True)
    parser.add_argument("--old-order-anchor", type=Path, required=True)
    parser.add_argument("--new-rgb-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    geometry = assembler.read_rgb_ply(args.geometry_ply)
    old = assembler.read_rgb_ply(args.old_order_anchor)
    new = assembler.read_rgb_ply(args.new_rgb_source)
    if len(geometry.xyz) != len(old.xyz) or len(old.xyz) != len(new.xyz):
        raise ValueError("cloud counts differ")
    if not np.array_equal(bits(old.xyz), bits(new.xyz)):
        raise ValueError("new RGB source point order/geometry differs from old anchor")
    if not np.array_equal(geometry.rgb, old.rgb):
        raise ValueError("geometry cloud RGB does not bind the old order anchor")
    assembler.write_rgb_ply(args.output, [assembler.Cloud(geometry.xyz.copy(), new.rgb.copy())])
    reread = assembler.read_rgb_ply(args.output)
    if not np.array_equal(bits(reread.xyz), bits(geometry.xyz)) or not np.array_equal(reread.rgb, new.rgb):
        raise ValueError("RGB rebound output changed geometry/order or RGB")
    manifest = {
        "schema": "pw_exact_order_rgb_rebind_v1",
        "geometry_ply": {"path": str(args.geometry_ply.resolve()), "sha256": assembler.sha256_file(args.geometry_ply)},
        "old_order_anchor": {"path": str(args.old_order_anchor.resolve()), "sha256": assembler.sha256_file(args.old_order_anchor)},
        "new_rgb_source": {"path": str(args.new_rgb_source.resolve()), "sha256": assembler.sha256_file(args.new_rgb_source)},
        "output": {"path": str(args.output.resolve()), "sha256": assembler.sha256_file(args.output), "point_count": len(reread.xyz)},
        "xyz_f32_bits_and_order_exact": True,
        "rgb_exact_from_new_source": True,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["output"], sort_keys=True))


if __name__ == "__main__":
    main()
