#!/usr/bin/env python3
"""Fusion v3: keep all windows, select at point level (鱼与熊掌 design).

Three changes vs expH (which gated nothing and anchored a chain at window 0):

1. Per-window conf percentile threshold — every window contributes its own
   top-(100-P40)% pixels via the official GLB rule computed per window, so a
   hard window's best background points survive while its garbage stays out
   (fixes the global-P40 dilution, 2.71 vs easy-subset 7.06).
2. conf-weighted global log-LSQ scale solve anchored on high-conf windows —
   per-window scale s_w solved from all adjacent-edge median ratios (weights =
   min(window conf_med) of the edge) plus identity anchors on windows with
   conf_med >= anchor bar (their own official umeyama metric is trusted to
   ~1-2% per exp C). Replaces the drifting window-0 chain.
3. Consistency filter unchanged (COLMAP semantics) as the final geometric
   arbiter on the v3-scaled depths.

Reuses expH's measurement/assignment/filter functions and the official GLB
export functions; no new geometry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from expH_window_chain_fusion import (  # noqa: E402
    assign_primary,
    chain_scales,
    consistency_filter,
    load_windows,
)
from strict_k35_window_official_filter_micro_audit import (  # noqa: E402
    official_depths_to_world_points_with_colors,
    official_glb_alignment_transform,
    official_glb_conf_threshold,
    official_glb_filter_and_downsample,
    transform_points,
    write_point_cloud,
)


def solve_global_scales(edge_stats, conf_meds, *, anchor_bar: float, anchor_weight: float):
    n = len(conf_meds)
    rows, rhs, weights = [], [], []
    for e in edge_stats:
        a, b = (int(v) for v in e["edge"].split("->"))
        row = np.zeros(n)
        row[a], row[b] = 1.0, -1.0
        rows.append(row)
        rhs.append(-np.log(e["median_ratio"]))
        weights.append(min(conf_meds[a], conf_meds[b]))
    anchors = [w for w in range(n) if conf_meds[w] >= anchor_bar]
    for w in anchors:
        row = np.zeros(n)
        row[w] = 1.0
        rows.append(row)
        rhs.append(0.0)
        weights.append(anchor_weight)
    a_mat = np.asarray(rows) * np.asarray(weights)[:, None]
    b_vec = np.asarray(rhs) * np.asarray(weights)
    x, *_ = np.linalg.lstsq(a_mat, b_vec, rcond=None)
    return np.exp(x), anchors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=18)
    parser.add_argument("--stride", type=int, default=9)
    parser.add_argument("--anchor-bar", type=float, default=6.0)
    parser.add_argument("--anchor-weight", type=float, default=20.0)
    parser.add_argument("--neighbors", type=int, default=4)
    parser.add_argument("--rel-thresh", type=float, default=0.01)
    parser.add_argument("--min-consistent", type=int, default=2)
    parser.add_argument("--num-max-points", default="8000000,200000000")
    parser.add_argument("--seed", type=int, default=8121)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    wins = load_windows(args.run_dir)
    n_windows = len(wins)
    n_frames = args.stride * (n_windows - 1) + args.k
    conf_meds = [float(np.median(w["conf"])) for w in wins]

    # 2) global LSQ scales (edge ratios measured by the same routine as expH)
    _, edge_stats = chain_scales(wins, args.stride, args.k)
    scales, anchors = solve_global_scales(
        edge_stats, conf_meds, anchor_bar=args.anchor_bar, anchor_weight=args.anchor_weight
    )
    print(f"anchors (conf>={args.anchor_bar}): {anchors}", flush=True)
    print(f"v3 scales: span [{scales.min():.4f}, {scales.max():.4f}] "
          f"|log| med {np.median(np.abs(np.log(scales))):.4f}", flush=True)

    # 1) per-window official threshold
    win_thresholds = [
        float(official_glb_conf_threshold(w["conf"], conf_thresh=1.05, conf_thresh_percentile=40.0, ensure_thresh_percentile=90.0))
        for w in wins
    ]
    print(f"per-window thresholds: min {min(win_thresholds):.2f} max {max(win_thresholds):.2f}", flush=True)

    primary = assign_primary(n_frames, n_windows, args.stride, args.k)
    h, w_px = wins[0]["depth"].shape[1:]
    depth = np.empty((n_frames, h, w_px), dtype=np.float32)
    conf = np.empty((n_frames, h, w_px), dtype=np.float32)
    intr = np.empty((n_frames, 3, 3), dtype=np.float32)
    extr = np.empty((n_frames, 3, 4), dtype=np.float32)
    rgb = np.empty((n_frames, h, w_px, 3), dtype=np.uint8)
    img_cache: dict[int, np.ndarray] = {}
    for g, (wi, slot) in enumerate(primary):
        depth[g] = wins[wi]["depth"][slot] * scales[wi]
        c = wins[wi]["conf"][slot]
        conf[g] = np.where(c >= win_thresholds[wi], c, 0.0)  # per-window gate
        intr[g] = wins[wi]["intrinsics"][slot]
        extr[g] = wins[wi]["extrinsics"][slot][:3, :]
        if wi not in img_cache:
            img_cache[wi] = np.load(wins[wi]["dir"] / "processed_images_uint8.npy")
        rgb[g] = img_cache[wi][slot]
    img_cache.clear()

    # 3) consistency filter on v3-scaled depths
    keep = consistency_filter(
        depth, conf, intr, extr,
        neighbors=args.neighbors, rel_thresh=args.rel_thresh, min_consistent=args.min_consistent,
    )
    conf_final = np.where(keep, conf, 0.0).astype(np.float32)
    gate_rate = float((conf > 0).mean())
    final_rate = float((conf_final > 0).mean())
    print(f"per-window gate keep {gate_rate*100:.1f}% -> +consistency {final_rate*100:.1f}%", flush=True)

    points, colors = official_depths_to_world_points_with_colors(depth, intr, extr, rgb, conf_final, 1.05)
    valid = int(points.shape[0])
    transform = official_glb_alignment_transform(extr[0], points)
    points = transform_points(points, transform)
    results = {}
    for cap in (int(v) for v in str(args.num_max_points).split(",")):
        pts, cols = official_glb_filter_and_downsample(points, colors, num_max=cap, seed=args.seed)
        label = "full" if cap >= valid else f"{cap // 1_000_000}M"
        ply = args.out_dir / f"fused_v3_{label}_rgb.ply"
        write_point_cloud(ply, pts, cols)
        results[label] = {"exported": int(pts.shape[0]), "ply": str(ply)}
        print(f"v3[{label}]: valid {valid:,} -> {pts.shape[0]:,}", flush=True)

    (args.out_dir / "expJ_v3_report.json").write_text(json.dumps({
        "schema_version": "pocketworld_expJ_fusion_v3_v1",
        "anchors": anchors,
        "anchor_bar": args.anchor_bar,
        "anchor_weight": args.anchor_weight,
        "scales": [float(s) for s in scales],
        "per_window_thresholds": win_thresholds,
        "window_conf_medians": conf_meds,
        "gate_keep_rate": gate_rate,
        "final_keep_rate": final_rate,
        "valid_points": valid,
        "exports": results,
    }, indent=2))
    print("EXPJ-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
