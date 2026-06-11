#!/usr/bin/env python3
"""Experiment I: easy-windows-only fused reference (quality ceiling probe).

Assembles a fused cloud from only the windows whose conf median clears a bar
(default >= 6): per exp C, such windows' own official umeyama metric scale is
trustworthy to ~1-2%, so no chain alignment and no consistency filter are
applied — this is pure official per-window semantics + official GLB export,
restricted to good windows. Shows what multi-window fusion looks like when
window quality is high; the gap to the all-windows cloud is the cost of the
hard zones.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from strict_k35_window_official_filter_micro_audit import (  # noqa: E402
    official_depths_to_world_points_with_colors,
    official_glb_alignment_transform,
    official_glb_conf_threshold,
    official_glb_filter_and_downsample,
    transform_points,
    write_point_cloud,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--conf-bar", type=float, default=6.0)
    parser.add_argument("--num-max-points", type=int, default=8_000_000)
    parser.add_argument("--seed", type=int, default=8121)
    args = parser.parse_args()

    report = json.loads((args.run_dir / "expG_run_report.json").read_text())["windows"]
    easy = sorted(k for k, w in report.items() if w["conf_median"] >= args.conf_bar)
    print(f"easy windows (conf>={args.conf_bar}): {easy}", flush=True)

    depths, confs, intrs, extrs, rgbs = [], [], [], [], []
    for wid in easy:
        wd = args.run_dir / f"window_{wid}"
        depths.append(np.load(wd / "pytorch_depth.npy"))
        confs.append(np.load(wd / "pytorch_conf.npy"))
        intrs.append(np.load(wd / "pytorch_intrinsics.npy"))
        extrs.append(np.load(wd / "pytorch_extrinsics.npy")[:, :3, :])
        rgbs.append(np.load(wd / "processed_images_uint8.npy"))
    depth = np.concatenate(depths)
    conf = np.concatenate(confs)
    intr = np.concatenate(intrs)
    extr = np.concatenate(extrs)
    rgb = np.concatenate(rgbs)
    print(f"frames pooled: {depth.shape[0]} (windows may share frames; duplicates fine for point export)", flush=True)

    threshold = official_glb_conf_threshold(conf, conf_thresh=1.05, conf_thresh_percentile=40.0, ensure_thresh_percentile=90.0)
    points, colors = official_depths_to_world_points_with_colors(depth, intr, extr, rgb, conf, threshold)
    valid = int(points.shape[0])
    transform = official_glb_alignment_transform(extr[0], points)
    points = transform_points(points, transform)
    points, colors = official_glb_filter_and_downsample(points, colors, num_max=args.num_max_points, seed=args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ply = args.out_dir / "easy_windows_reference_rgb.ply"
    write_point_cloud(ply, points, colors)
    print(f"threshold {threshold:.3f}  valid {valid:,} -> exported {points.shape[0]:,}  ply {ply}", flush=True)

    (args.out_dir / "expI_easy_reference_report.json").write_text(
        json.dumps(
            {
                "schema_version": "pocketworld_expI_easy_windows_reference_v1",
                "conf_bar": args.conf_bar,
                "windows": easy,
                "conf_threshold": float(threshold),
                "valid": valid,
                "exported": int(points.shape[0]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
