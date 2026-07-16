#!/usr/bin/env python3
"""Scan a sparse wall proposal across depth without reference-plane leakage.

This is a proposal-refinement diagnostic: the sparse wall supplies orientation
and finite domain, while first-party images/poses select the photometric depth.
No scanned plane may own product births until a later unique-depth run certifies
the selected winner against its parallel competitors.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location("aether_wall_depth_scan", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--planes", type=Path, required=True)
    parser.add_argument("--surface-id", required=True)
    parser.add_argument("--offset-start-m", type=float, default=-0.40)
    parser.add_argument("--offset-end-m", type=float, default=0.40)
    parser.add_argument("--offset-step-m", type=float, default=0.05)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.offset_step_m <= 0 or args.offset_end_m < args.offset_start_m:
        raise ValueError("invalid offset scan interval")

    runner = load_runner()
    planes = json.loads(args.planes.read_text())
    matches = [
        surface
        for surface in planes["surfaces"]
        if surface["surface_id"] == args.surface_id
    ]
    if len(matches) != 1 or matches[0]["kind"] != "wall":
        raise ValueError("surface-id must identify exactly one wall")
    wall = matches[0]
    floor = planes["floor"]
    frames = runner.load_frames(args.frame_meta, args.ledger, args.photos)
    config = runner.SweepConfig(
        grid_m=0.10,
        patch_n=9,
        patch_radius_m=0.03,
        min_std=6.0,
        ncc_min=0.80,
        min_views=4,
        min_parallax_deg=10.0,
        max_views=10,
        max_graze_deg=72.0,
        tile_points=64,
        image_cache_images=10,
        depth_competition_offsets_m=(),
        depth_ncc_margin=0.02,
    )
    count = int(
        np.floor((args.offset_end_m - args.offset_start_m) / args.offset_step_m + 1e-9)
    )
    offsets = args.offset_start_m + np.arange(count + 1) * args.offset_step_m
    rows = []
    started = time.perf_counter()
    for offset in offsets:
        _, _, _, metrics = runner.sweep_surface(
            wall, floor, frames, config, float(offset)
        )
        accepted = int(metrics["accepted"])
        median_ncc = float(metrics["zncc_median"] or 0.0)
        rows.append(
            {
                "offset_m": float(offset),
                "plane_value_n_dot_x": float(wall["plane_value_n_dot_x"] + offset),
                "score": accepted * median_ncc,
                "metrics": metrics,
            }
        )
    ranking = sorted(
        rows,
        key=lambda row: (row["score"], row["metrics"]["accepted"]),
        reverse=True,
    )
    winner = ranking[0]
    runner_up = ranking[1] if len(ranking) > 1 else None
    result = {
        "schema": "aether_wall_plane_offset_scan_v1",
        "method": "fixed_orientation_domain_multiview_photometric_depth_scan",
        "birth_authority": False,
        "forbidden_inputs_consumed": {
            "reference_plane": False,
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "inputs": {
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "ledger": {"path": str(args.ledger), "sha256": sha256(args.ledger)},
            "planes": {"path": str(args.planes), "sha256": sha256(args.planes)},
            "photo_count": len(frames),
            "surface_id": args.surface_id,
        },
        "config": config.__dict__,
        "scan": {
            "offset_start_m": args.offset_start_m,
            "offset_end_m": args.offset_end_m,
            "offset_step_m": args.offset_step_m,
        },
        "rows": rows,
        "selection": {
            "winner_offset_m": winner["offset_m"],
            "winner_plane_value_n_dot_x": winner["plane_value_n_dot_x"],
            "winner_score": winner["score"],
            "winner_accepted": winner["metrics"]["accepted"],
            "runner_up_offset_m": runner_up["offset_m"] if runner_up else None,
            "runner_up_score": runner_up["score"] if runner_up else None,
            "note": "diagnostic only; final unique-depth certification required",
        },
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
