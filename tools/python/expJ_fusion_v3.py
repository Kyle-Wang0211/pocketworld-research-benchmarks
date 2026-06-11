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


def solve_global_affine(wins, conf_meds, *, k: int, stride: int, anchor_bar: float, anchor_weight: float, sample_per_edge: int = 20000):
    """Per-window affine depth correction depth' = a_w*depth + b_w.

    Shared pixels give linear constraints a_w*d1 + b_w - a_{w+1}*d2 - b_{w+1} = 0;
    accumulated as normal equations (90 unknowns), one robust re-fit pass
    (trim worst 20% residuals per edge), anchors prior (a=1, b=0).
    """
    n = len(wins)
    n_shared = k - stride
    rng = np.random.default_rng(8121)

    def edge_pixels(w):
        a, b = wins[w], wins[w + 1]
        ca = np.maximum(a["conf"] - 1.0, 0.0)
        cb = np.maximum(b["conf"] - 1.0, 0.0)
        ta, tb = ca.mean() * 0.5, cb.mean() * 0.5
        d1s, d2s = [], []
        for s in range(n_shared):
            m = (ca[stride + s] >= ta) & (cb[s] >= tb)
            d1s.append(a["depth"][stride + s][m])
            d2s.append(b["depth"][s][m])
        d1 = np.concatenate(d1s).astype(np.float64)
        d2 = np.concatenate(d2s).astype(np.float64)
        if d1.size > sample_per_edge:
            idx = rng.choice(d1.size, sample_per_edge, replace=False)
            d1, d2 = d1[idx], d2[idx]
        return d1, d2

    edges = [edge_pixels(w) for w in range(n - 1)]
    x = np.zeros(2 * n)
    x[0::2] = 1.0  # init a=1, b=0

    for _ in range(2):  # robust re-fit
        ata = np.zeros((2 * n, 2 * n))
        atb = np.zeros(2 * n)
        for w, (d1, d2) in enumerate(edges):
            ia, ib = 2 * w, 2 * w + 1
            ja, jb = 2 * (w + 1), 2 * (w + 1) + 1
            r = x[ia] * d1 + x[ib] - x[ja] * d2 - x[jb]
            keep = np.abs(r) <= np.quantile(np.abs(r), 0.8)
            d1k, d2k = d1[keep], d2[keep]
            wgt = min(conf_meds[w], conf_meds[w + 1])
            # row: [d1, 1, -d2, -1] over (a_w, b_w, a_{w+1}, b_{w+1}) = 0
            cols = [ia, ib, ja, jb]
            vals = [d1k, np.ones_like(d1k), -d2k, -np.ones_like(d2k)]
            for p in range(4):
                for q in range(4):
                    ata[cols[p], cols[q]] += wgt * float(np.dot(vals[p], vals[q]))
        for w in range(n):
            if conf_meds[w] >= anchor_bar:
                ata[2 * w, 2 * w] += anchor_weight**2
                atb[2 * w] += anchor_weight**2 * 1.0
                ata[2 * w + 1, 2 * w + 1] += anchor_weight**2
        # soft prior toward identity for conditioning
        for w in range(n):
            ata[2 * w, 2 * w] += 1e-4
            atb[2 * w] += 1e-4
            ata[2 * w + 1, 2 * w + 1] += 1e-4
        x = np.linalg.solve(ata, atb)

    return x[0::2].copy(), x[1::2].copy()


def solve_global_scales_quality(edge_stats, conf_meds, *, anchor_bar: float, anchor_weight: float):
    """Same LSQ as solve_global_scales but edges weighted by the official
    estimator's quality score (scaled to the conf-weight range)."""
    n = len(conf_meds)
    rows, rhs, weights = [], [], []
    for e in edge_stats:
        a, b = (int(v) for v in e["edge"].split("->"))
        row = np.zeros(n)
        row[a], row[b] = 1.0, -1.0
        rows.append(row)
        rhs.append(-np.log(e["median_ratio"]))
        weights.append(10.0 * max(e.get("quality", 0.0), 0.05))
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
    parser.add_argument(
        "--edge-estimator",
        choices=["median", "official"],
        default="median",
        help="'official' uses vendor compute_chunk_scale_advanced (RANSAC+weighted auto)"
        " on the shared-frame stacks; its quality score becomes the LSQ edge weight.",
    )
    parser.add_argument(
        "--correction",
        choices=["scale", "affine"],
        default="scale",
        help="'affine' solves per-window (a, b) with depth' = a*depth + b via global"
        " normal-equation LSQ over shared pixels (anchors prior a=1, b=0); captures"
        " the monotone-with-depth layer structure exp L found on hard edges.",
    )
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

    # 2) global LSQ scales
    if args.edge_estimator == "official":
        # official DA3-Streaming inter-chunk scale estimator (scale+se3 family),
        # imported verbatim from the proven vendor tree
        vendor = Path(__file__).resolve().parents[1] / "vendor" / "official_da3_streaming"
        sys.path.insert(0, str(vendor))
        from da3base_official_streaming_oracle import install_triton_stub

        install_triton_stub()  # vendor sim3utils imports triton at module level
        from loop_utils.sim3utils import compute_chunk_scale_advanced

        edge_stats = []
        n_shared = args.k - args.stride
        for w in range(n_windows - 1):
            a, b = wins[w], wins[w + 1]
            d1 = a["depth"][args.stride :]
            c1 = a["conf"][args.stride :]
            d2 = b["depth"][:n_shared]
            c2 = b["conf"][:n_shared]
            # estimator returns s with depth1 ≈ s * depth2  →  ratio(D_w/D_{w+1}) = s
            s, quality, method = compute_chunk_scale_advanced(d1, d2, c1, c2, "auto")
            edge_stats.append(
                {
                    "edge": f"{w:03d}->{w + 1:03d}",
                    "median_ratio": float(s),
                    "offset_pct": (float(s) - 1.0) * 100.0,
                    "quality": float(quality),
                    "method": method,
                }
            )
        scales, anchors = solve_global_scales_quality(
            edge_stats, conf_meds, anchor_bar=args.anchor_bar, anchor_weight=args.anchor_weight
        )
    else:
        _, edge_stats = chain_scales(wins, args.stride, args.k)
        scales, anchors = solve_global_scales(
            edge_stats, conf_meds, anchor_bar=args.anchor_bar, anchor_weight=args.anchor_weight
        )

    shifts = np.zeros(n_windows)
    if args.correction == "affine":
        scales, shifts = solve_global_affine(
            wins, conf_meds, k=args.k, stride=args.stride,
            anchor_bar=args.anchor_bar, anchor_weight=args.anchor_weight,
        )
        anchors = [w for w in range(n_windows) if conf_meds[w] >= args.anchor_bar]
        print(f"affine: a span [{scales.min():.4f}, {scales.max():.4f}]  "
              f"b span [{shifts.min():+.4f}, {shifts.max():+.4f}] m", flush=True)
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
        depth[g] = wins[wi]["depth"][slot] * scales[wi] + shifts[wi]
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
        "correction": args.correction,
        "scales": [float(s) for s in scales],
        "shifts": [float(s) for s in shifts],
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
