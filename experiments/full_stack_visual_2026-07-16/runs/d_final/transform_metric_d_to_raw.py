#!/usr/bin/env python3
"""Transform exact D and ghost metric clouds into the certified device/raw gauge."""

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True)
    parser.add_argument("--d-metric", type=Path, required=True)
    parser.add_argument("--ghost-metric", type=Path, required=True)
    parser.add_argument("--metric-to-raw-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.metric_to_raw_source.read_text(encoding="utf-8"))
    raw = source.get("sim3_metric_to_raw") or source.get("metric_to_raw_sim3")
    if not isinstance(raw, dict) or raw.get("residual_gate_passed") is not True:
        raise ValueError("metric-to-raw source Sim3 is absent or uncertified")
    scale = float(raw["scale_metric_to_raw"])
    rotation = np.asarray(raw["rotation_metric_to_raw_row_major"], dtype=np.float64).reshape((3, 3))
    translation = np.asarray(raw["translation_metric_to_raw"], dtype=np.float64)
    if scale <= 0 or translation.shape != (3,) or not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise ValueError("metric-to-raw Sim3 is malformed")
    transform = assembler.Sim3(scale, rotation, translation)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for role, source_path, output_name in (
        ("d_raw", args.d_metric, "d_births_device_raw_gauge.ply"),
        ("ghost_raw", args.ghost_metric, "ghost_owner_full_device_raw_gauge.ply"),
    ):
        cloud = assembler.read_rgb_ply(source_path)
        output_path = args.output_dir / output_name
        assembler.write_rgb_ply(
            output_path,
            [assembler.Cloud(transform.apply(cloud.xyz), cloud.rgb.copy())],
        )
        reread = assembler.read_rgb_ply(output_path)
        if not np.array_equal(reread.rgb, cloud.rgb) or len(reread.xyz) != len(cloud.xyz):
            raise ValueError(f"{role}: transform changed RGB/order/count")
        outputs[role] = record(output_path)

    manifest = {
        "schema": "pw_d_and_ghost_metric_to_device_raw_v1",
        "capture": args.capture,
        "inputs": {"d_metric": record(args.d_metric), "ghost_metric": record(args.ghost_metric)},
        "outputs": outputs,
        "metric_to_raw_sim3": {
            "scale_metric_to_raw": scale,
            "rotation_metric_to_raw_row_major": rotation.reshape(-1).tolist(),
            "translation_metric_to_raw": translation.tolist(),
            "rotation_determinant": float(np.linalg.det(rotation)),
        },
        "source_metric_to_raw_certificate": record(args.metric_to_raw_source),
        "rgb_and_order_preserved": True,
    }
    manifest_path = args.output_dir / "raw_transform_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": record(manifest_path), "outputs": outputs}, sort_keys=True))


if __name__ == "__main__":
    main()
