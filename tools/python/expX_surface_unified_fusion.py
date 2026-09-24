#!/usr/bin/env python3
"""Experiment X (v8): surface-reprojection unified alignment for easy windows.

User diagnosis (2026-06-11): expW's anchored affine pinned every good window to
its OWN umeyama scale, so window-runs without shared frames (10-11 / 24-27 /
40-42 / isolated 0,14) were never mutually aligned — measured inter-run surface
misalignment 1.3-6.9% (= the floor/cabinet layering). Fix ("强制对齐"):

1. Edges from SHARED SURFACES, not shared frames: window A's depth is
   backprojected with ARKit poses and reprojected into window B's frames;
   median(D_B / z_A->B) over matched pixels gives log m = log s_A - log s_B.
   All window pairs with frustum overlap get an edge (graph fully connected).
2. Single gauge: anchor only the strongest window; every other window floats
   to mutual consistency (no per-window umeyama pinning).
3. Consistency filter + per-window P40 official threshold + full export,
   restricted to the easy-window subset.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from expH_window_chain_fusion import consistency_filter, load_windows  # noqa: E402
from strict_k35_window_official_filter_micro_audit import (  # noqa: E402
    official_depths_to_world_points_with_colors,
    official_glb_alignment_transform,
    official_glb_conf_threshold,
    official_glb_filter_and_downsample,
    transform_points,
    write_point_cloud,
)


def as44(e: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    out[:3, :] = e[:3, :]
    return out


def surface_edge(a, b, *, frame_step: int = 3, max_px: int = 4000, seed: int = 1):
    """median(D_b / z_{a->b}) pooled over frame pairs; ratio ~ s_a / s_b."""
    ca = np.maximum(a["conf"] - 1, 0)
    cb = np.maximum(b["conf"] - 1, 0)
    ta, tb = ca.mean() * 0.5, cb.mean() * 0.5
    rng = np.random.default_rng(seed)
    pool = []
    h, w = b["depth"].shape[1:]
    for sa in range(0, a["depth"].shape[0], frame_step):
        m = ca[sa] >= ta
        ys, xs = np.where(m)
        if ys.size < 500:
            continue
        sel = rng.choice(ys.size, min(max_px, ys.size), replace=False)
        K = a["intrinsics"][sa]
        z = a["depth"][sa][ys[sel], xs[sel]].astype(np.float64)
        x = (xs[sel] - K[0, 2]) / K[0, 0] * z
        y = (ys[sel] - K[1, 2]) / K[1, 1] * z
        pw = np.linalg.inv(as44(a["extrinsics"][sa])) @ np.stack([x, y, z, np.ones_like(z)])
        for sb in range(0, b["depth"].shape[0], frame_step):
            cam = (as44(b["extrinsics"][sb]) @ pw)[:3]
            zt = cam[2]
            Kb = b["intrinsics"][sb]
            ut = Kb[0, 0] * cam[0] / np.maximum(zt, 1e-6) + Kb[0, 2]
            vt = Kb[1, 1] * cam[1] / np.maximum(zt, 1e-6) + Kb[1, 2]
            ok = (zt > 1e-3) & (ut >= 0) & (ut < w - 1) & (vt >= 0) & (vt < h - 1)
            if ok.sum() < 200:
                continue
            ui = np.rint(ut[ok]).astype(int)
            vi = np.rint(vt[ok]).astype(int)
            db = b["depth"][sb][vi, ui]
            good = (db > 1e-3) & (cb[sb][vi, ui] >= tb)
            if good.sum() < 200:
                continue
            pool.append(db[good] / zt[ok][good])
    if not pool:
        return None, 0
    allr = np.concatenate(pool)
    return float(np.median(allr)), int(allr.size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--windows", required=True, help="comma list, e.g. 0,10,11,...")
    parser.add_argument("--gauge-window", type=int, default=-1, help="-1 = highest-conf window")
    parser.add_argument("--gate-percentile", type=float, default=40.0)
    parser.add_argument("--k", type=int, default=18)
    parser.add_argument("--stride", type=int, default=9)
    parser.add_argument("--neighbors", type=int, default=4)
    parser.add_argument("--rel-thresh", type=float, default=0.01)
    parser.add_argument("--min-consistent", type=int, default=2)
    parser.add_argument("--num-max-points", type=int, default=200_000_000)
    parser.add_argument("--seed", type=int, default=8121)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_wins = load_windows(args.run_dir)
    ids = sorted(int(v) for v in args.windows.split(","))
    wins = {i: all_wins[i] for i in ids}
    conf_meds = {i: float(np.median(wins[i]["conf"])) for i in ids}
    gauge = args.gauge_window if args.gauge_window >= 0 else max(ids, key=lambda i: conf_meds[i])
    print(f"windows={ids} gauge={gauge}", flush=True)

    # 1) surface-reprojection edges over all pairs
    edges = []
    for ii, a in enumerate(ids):
        for b in ids[ii + 1:]:
            r, n = surface_edge(wins[a], wins[b])
            if r is not None and n >= 2000:
                edges.append((a, b, r, n))
                print(f"edge {a:02d}->{b:02d}: ratio {r:.4f} ({(r-1)*100:+.1f}%) n={n:,}", flush=True)
    print(f"edges: {len(edges)}", flush=True)

    # 2) log-scale LSQ, single gauge anchor
    idx = {w: i for i, w in enumerate(ids)}
    rows, rhs, wts = [], [], []
    for a, b, r, n in edges:
        row = np.zeros(len(ids))
        row[idx[a]], row[idx[b]] = 1.0, -1.0
        rows.append(row)
        rhs.append(np.log(r))  # log s_a - log s_b = log r
        wts.append(np.sqrt(n))
    row = np.zeros(len(ids))
    row[idx[gauge]] = 1.0
    rows.append(row)
    rhs.append(0.0)
    wts.append(1e4)
    A = np.asarray(rows) * np.asarray(wts)[:, None]
    bv = np.asarray(rhs) * np.asarray(wts)
    x, *_ = np.linalg.lstsq(A, bv, rcond=None)
    scales = {w: float(np.exp(x[idx[w]])) for w in ids}
    print("unified scales:", {w: round(s, 4) for w, s in scales.items()}, flush=True)

    # residual check after unification
    post = []
    for a, b, r, n in edges:
        post.append(abs(np.log(r) - (np.log(scales[a]) - np.log(scales[b]))))
    print(f"边残差: before med {np.median([abs(np.log(r)) for _,_,r,_ in edges])*100:.2f}% "
          f"-> after med {np.median(post)*100:.2f}% max {np.max(post)*100:.2f}%", flush=True)

    # 3) assemble subset frames (primary = most central among subset windows)
    frame_owner: dict[int, tuple[int, int]] = {}
    for w in ids:
        for slot in range(args.k):
            g = w * args.stride + slot
            cand = (w, slot)
            if g not in frame_owner or abs(slot - (args.k - 1) / 2) < abs(frame_owner[g][1] - (args.k - 1) / 2):
                frame_owner[g] = cand
    frames = sorted(frame_owner)
    n_f = len(frames)
    h, w_px = all_wins[ids[0]]["depth"].shape[1:]
    depth = np.empty((n_f, h, w_px), dtype=np.float32)
    conf = np.empty((n_f, h, w_px), dtype=np.float32)
    intr = np.empty((n_f, 3, 3), dtype=np.float32)
    extr = np.empty((n_f, 3, 4), dtype=np.float32)
    rgb = np.empty((n_f, h, w_px, 3), dtype=np.uint8)
    thresholds = {
        w: float(official_glb_conf_threshold(wins[w]["conf"], conf_thresh=1.05,
                 conf_thresh_percentile=args.gate_percentile, ensure_thresh_percentile=90.0))
        for w in ids
    }
    img_cache: dict[int, np.ndarray] = {}
    for gi, g in enumerate(frames):
        w, slot = frame_owner[g]
        depth[gi] = wins[w]["depth"][slot] * scales[w]
        c = wins[w]["conf"][slot]
        conf[gi] = np.where(c >= thresholds[w], c, 0.0)
        intr[gi] = wins[w]["intrinsics"][slot]
        extr[gi] = wins[w]["extrinsics"][slot][:3, :]
        if w not in img_cache:
            img_cache[w] = np.load(wins[w]["dir"] / "processed_images_uint8.npy")
        rgb[gi] = img_cache[w][slot]
    img_cache.clear()
    print(f"subset frames: {n_f}", flush=True)

    # 4) consistency filter with run-gap-aware adaptive votes: a frame's required
    # vote count is capped by how many of its array neighbors are genuinely
    # spatially close (run-edge frames lost real neighbors to the subset cut and
    # must not be starved into deletion).
    keep = consistency_filter(depth, conf, intr, extr, neighbors=args.neighbors,
                              rel_thresh=args.rel_thresh, min_consistent=1)
    # keep here is a count>=1 mask; recompute counts for adaptive thresholding
    from expH_window_chain_fusion import consistency_filter as _cf  # noqa
    # cheap second pass: count close neighbors per frame
    centers = np.stack([-extr[i, :3, :3].T @ extr[i, :3, 3] for i in range(n_f)])
    close = np.zeros(n_f, dtype=int)
    for i in range(n_f):
        for dn in range(-args.neighbors, args.neighbors + 1):
            j = i + dn
            if dn != 0 and 0 <= j < n_f and np.linalg.norm(centers[i] - centers[j]) < 0.6:
                close[i] += 1
    required = np.minimum(args.min_consistent, np.maximum(close, 1))
    keep_strict = consistency_filter(depth, conf, intr, extr, neighbors=args.neighbors,
                                     rel_thresh=args.rel_thresh, min_consistent=args.min_consistent)
    conf_final = np.empty_like(conf)
    for i in range(n_f):
        mask = keep_strict[i] if required[i] >= args.min_consistent else keep[i]
        conf_final[i] = np.where(mask, conf[i], 0.0)
    print(f"adaptive votes: {int((required < args.min_consistent).sum())}/{n_f} 帧降级为 1 票", flush=True)
    conf_final = conf_final.astype(np.float32)
    print(f"gate {((conf>0).mean())*100:.1f}% -> +consistency {((conf_final>0).mean())*100:.1f}%", flush=True)

    points, colors = official_depths_to_world_points_with_colors(depth, intr, extr, rgb, conf_final, 1.05)
    valid = int(points.shape[0])
    transform = official_glb_alignment_transform(extr[0], points)
    points = transform_points(points, transform)
    points, colors = official_glb_filter_and_downsample(points, colors, num_max=args.num_max_points, seed=args.seed)
    ply = args.out_dir / "fused_v8_surface_unified_rgb.ply"
    write_point_cloud(ply, points, colors)
    print(f"v8: valid {valid:,} -> {points.shape[0]:,} -> {ply}", flush=True)

    (args.out_dir / "expX_v8_report.json").write_text(json.dumps({
        "schema_version": "pocketworld_expX_surface_unified_v8_v1",
        "windows": ids, "gauge": gauge,
        "edges": [{"a": a, "b": b, "ratio": r, "n": n} for a, b, r, n in edges],
        "scales": scales, "thresholds": thresholds,
        "valid": valid,
    }, indent=2))
    print("EXPX-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
