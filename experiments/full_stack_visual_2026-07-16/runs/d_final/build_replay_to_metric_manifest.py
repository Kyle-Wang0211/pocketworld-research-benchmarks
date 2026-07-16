#!/usr/bin/env python3
"""Certify the replay-to-product-metric Sim3 used by exact D execution."""

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


def record(path: Path) -> dict:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": assembler.sha256_file(path)}


def validate_pair(source_path: Path, output_path: Path, transform: assembler.Sim3) -> dict:
    source = assembler.read_rgb_ply(source_path)
    output = assembler.read_rgb_ply(output_path)
    if len(source.xyz) != len(output.xyz) or not np.array_equal(source.rgb, output.rgb):
        raise ValueError("Sim3 pair changed point order/count/RGB")
    residual = np.linalg.norm(transform.apply(source.xyz) - output.xyz, axis=1)
    if float(np.max(residual)) > 1e-5:
        raise ValueError(f"Sim3 pair residual too large: {float(np.max(residual))}")
    return {
        "point_count": len(source.xyz),
        "median_residual_m": float(np.median(residual)),
        "p99_residual_m": float(np.percentile(residual, 99)),
        "max_residual_m": float(np.max(residual)),
        "rgb_and_order_exact": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True)
    parser.add_argument("--exact-certificate", type=Path, required=True)
    parser.add_argument("--source-ghost", type=Path, required=True)
    parser.add_argument("--output-ghost", type=Path, required=True)
    parser.add_argument("--source-d", type=Path, required=True)
    parser.add_argument("--output-d", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exact = json.loads(args.exact_certificate.read_text(encoding="utf-8"))
    sim3 = (exact.get("execution") or {}).get("sim3")
    if not isinstance(sim3, dict):
        raise ValueError("exact D certificate has no execution Sim3")
    transform = assembler.Sim3(
        float(sim3["scale"]),
        np.asarray(sim3["rotation_row_major"], dtype=np.float64).reshape((3, 3)),
        np.asarray(sim3["translation"], dtype=np.float64),
    )
    ghost_validation = validate_pair(args.source_ghost, args.output_ghost, transform)
    d_validation = validate_pair(args.source_d, args.output_d, transform)
    document = {
        "schema": "pw_d_metric_transform_v1",
        "capture": args.capture,
        "source_ghost": record(args.source_ghost),
        "output_ghost": record(args.output_ghost),
        "source_d": record(args.source_d),
        "output_d": record(args.output_d),
        "sim3": {
            "scale": transform.scale,
            "rotation_row_major": transform.rotation.reshape(-1).tolist(),
            "translation": transform.translation.tolist(),
            "paired_frame_ids": sim3.get("paired_frame_ids", []),
            "residuals": sim3.get("residuals"),
        },
        "point_counts": {"ghost": ghost_validation["point_count"], "d": d_validation["point_count"]},
        "pointwise_validation": {"ghost": ghost_validation, "d": d_validation},
        "rgb_preserved": True,
        "source_exact_certificate": record(args.exact_certificate),
    }
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
