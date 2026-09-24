#!/usr/bin/env python3
"""Experiment H: multi-window fusion = chain scale alignment + consistency filter.

Consumes expG window outputs (K=18 stride-9 pose-conditioned R1) and lands the
two production fusion components validated this week:

A. Per-window chain scale alignment (component from exp B/C): adjacent windows
   share K/2 frames; the median depth ratio over those shared frames gives one
   scalar per window, chained from window 0. (Exp C: removing this single
   scalar collapses cross-window error to within-window level.)
B. COLMAP-style geometric consistency filter (fusion.h semantics): every pixel
   of a frame's primary-window depth is backprojected and checked against
   +/-neighbor frames; kept iff >=min_consistent neighbors agree within
   rel_thresh relative depth (default 1%, COLMAP max_depth_error). Doubles as
   the specular filter (view-dependent highlights violate consistency).

Export reuses the official GLB filter functions unchanged (conf percentile
threshold computed on UNMASKED conf; rejected pixels get conf=0 so the
official threshold drops them). Produces fused_filtered + fused_control PLYs.
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


def as_4x4(ext: np.ndarray) -> np.ndarray:
    if ext.shape == (4, 4):
        return ext
    out = np.eye(4, dtype=np.float64)
    out[:3, :] = ext
    return out


def load_windows(run_dir: Path):
    wdirs = sorted(run_dir.glob("window_*"))
    wins = []
    for wd in wdirs:
        wins.append(
            {
                "dir": wd,
                "depth": np.load(wd / "pytorch_depth.npy"),
                "conf": np.load(wd / "pytorch_conf.npy"),
                "intrinsics": np.load(wd / "pytorch_intrinsics.npy"),
                "extrinsics": np.load(wd / "pytorch_extrinsics.npy"),
            }
        )
    return wins


def chain_scales(wins, stride: int, k: int):
    """Component A: cumulative per-window scale, window 0 anchored."""
    scales = [1.0]
    edge_stats = []
    for w in range(len(wins) - 1):
        a, b = wins[w], wins[w + 1]
        ca = np.maximum(a["conf"] - 1.0, 0.0)
        cb = np.maximum(b["conf"] - 1.0, 0.0)
        ta, tb = ca.mean() * 0.5, cb.mean() * 0.5
        ratios = []
        for shared_slot in range(k - stride):
            sa = stride + shared_slot  # slot in window w
            sb = shared_slot  # slot in window w+1
            m = (ca[sa] >= ta) & (cb[sb] >= tb)
            if np.count_nonzero(m) < 500:
                continue
            ratios.append(a["depth"][sa][m] / np.maximum(b["depth"][sb][m], 1e-6))
        pooled = np.concatenate(ratios) if ratios else np.asarray([1.0])
        r = float(np.median(pooled))
        scales.append(scales[-1] * r)
        edge_stats.append(
            {
                "edge": f"{w:03d}->{w + 1:03d}",
                "median_ratio": r,
                "offset_pct": (r - 1.0) * 100.0,
                "pixels": int(pooled.size),
            }
        )
    return np.asarray(scales, dtype=np.float64), edge_stats


def assign_primary(n_frames: int, n_windows: int, stride: int, k: int):
    """frame -> (window, slot) with the most-central slot."""
    out = []
    for g in range(n_frames):
        lo = max(0, (g - (k - 1) + stride - 1) // stride)
        hi = min(n_windows - 1, g // stride)
        best = min(range(lo, hi + 1), key=lambda w: abs((g - stride * w) - (k - 1) / 2.0))
        out.append((best, g - stride * best))
    return out


def consistency_filter(depth, conf, intrinsics, extrinsics, *, neighbors: int, rel_thresh: float, min_consistent: int):
    """Component B: per-pixel cross-frame geometric consistency (COLMAP semantics)."""
    n, h, w = depth.shape
    ys, xs = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
    keep_count = np.zeros((n, h, w), dtype=np.int16)
    c2w = np.stack([np.linalg.inv(as_4x4(extrinsics[i])) for i in range(n)])
    w2c = np.stack([as_4x4(extrinsics[i]) for i in range(n)])
    for g in range(n):
        kg = intrinsics[g]
        z = depth[g]
        x = (xs - kg[0, 2]) / kg[0, 0] * z
        y = (ys - kg[1, 2]) / kg[1, 1] * z
        pts = np.stack([x, y, z, np.ones_like(z)], axis=-1).reshape(-1, 4) @ c2w[g].T
        for dn in range(-neighbors, neighbors + 1):
            nb = g + dn
            if dn == 0 or nb < 0 or nb >= n:
                continue
            cam = pts @ w2c[nb].T
            zt = cam[:, 2]
            kn = intrinsics[nb]
            ut = kn[0, 0] * (cam[:, 0] / np.maximum(zt, 1e-6)) + kn[0, 2]
            vt = kn[1, 1] * (cam[:, 1] / np.maximum(zt, 1e-6)) + kn[1, 2]
            ui = np.rint(ut).astype(np.int32)
            vi = np.rint(vt).astype(np.int32)
            ok = (zt > 1e-6) & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            dn_sample = np.zeros_like(zt, dtype=np.float32)
            dn_sample[ok] = depth[nb][vi[ok], ui[ok]]
            agree = ok & (dn_sample > 1e-6) & (np.abs(zt - dn_sample) / np.maximum(dn_sample, 1e-6) <= rel_thresh)
            keep_count[g] += agree.reshape(h, w).astype(np.int16)
        if g % 50 == 0:
            print(f"consistency: frame {g}/{n}", flush=True)
    return keep_count >= min_consistent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=18)
    parser.add_argument("--stride", type=int, default=9)
    parser.add_argument("--neighbors", type=int, default=4)
    parser.add_argument("--rel-thresh", type=float, default=0.01)
    parser.add_argument("--min-consistent", type=int, default=2)
    parser.add_argument("--num-max-points", default="3000000", help="comma list of caps, e.g. 8000000,200000000")
    parser.add_argument("--seed", type=int, default=8121)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    wins = load_windows(args.run_dir)
    n_windows = len(wins)
    n_frames = args.stride * (n_windows - 1) + args.k
    print(f"windows={n_windows} frames={n_frames}", flush=True)

    # A. chain scale alignment
    scales, edge_stats = chain_scales(wins, args.stride, args.k)
    offsets = [abs(e["offset_pct"]) for e in edge_stats]
    print(f"chain scales: |offset| median {np.median(offsets):.2f}% max {np.max(offsets):.2f}% "
          f"cumulative span [{scales.min():.4f}, {scales.max():.4f}]", flush=True)

    # primary assignment + global arrays (scale applied)
    primary = assign_primary(n_frames, n_windows, args.stride, args.k)
    h, w = wins[0]["depth"].shape[1:]
    depth = np.empty((n_frames, h, w), dtype=np.float32)
    conf = np.empty((n_frames, h, w), dtype=np.float32)
    intr = np.empty((n_frames, 3, 3), dtype=np.float32)
    extr = np.empty((n_frames, 3, 4), dtype=np.float32)
    rgb = np.empty((n_frames, h, w, 3), dtype=np.uint8)
    img_cache: dict[int, np.ndarray] = {}
    for g, (wi, slot) in enumerate(primary):
        depth[g] = wins[wi]["depth"][slot] * scales[wi]
        conf[g] = wins[wi]["conf"][slot]
        intr[g] = wins[wi]["intrinsics"][slot]
        extr[g] = wins[wi]["extrinsics"][slot][:3, :]
        if wi not in img_cache:
            img_cache[wi] = np.load(wins[wi]["dir"] / "processed_images_uint8.npy")
        rgb[g] = img_cache[wi][slot]
    img_cache.clear()

    # post-alignment adjacent-window residual (verification metric)
    post = []
    for w_idx in range(0, n_windows - 1, 5):
        a, b = wins[w_idx], wins[w_idx + 1]
        sa, sb = args.stride, 0
        ca = np.maximum(a["conf"][sa] - 1, 0)
        m = ca >= ca.mean()
        da = a["depth"][sa][m] * scales[w_idx]
        db = b["depth"][sb][m] * scales[w_idx + 1]
        post.append(float(np.median(np.abs(da - db) / np.maximum(db, 1e-6))))
    print(f"post-alignment adjacent residual median {np.median(post) * 100:.2f}%", flush=True)

    # B. consistency filter
    keep = consistency_filter(
        depth, conf, intr, extr,
        neighbors=args.neighbors, rel_thresh=args.rel_thresh, min_consistent=args.min_consistent,
    )
    keep_rate = float(keep.mean())
    print(f"consistency filter keep rate: {keep_rate * 100:.1f}%", flush=True)

    # export: official GLB rules; threshold from unmasked conf, rejected conf -> 0
    threshold = official_glb_conf_threshold(conf, conf_thresh=1.05, conf_thresh_percentile=40.0, ensure_thresh_percentile=90.0)
    results = {}
    caps = [int(v) for v in str(args.num_max_points).split(",")]
    for tag, conf_used in (("control", conf), ("filtered", np.where(keep, conf, 0.0).astype(np.float32))):
        points, colors = official_depths_to_world_points_with_colors(depth, intr, extr, rgb, conf_used, threshold)
        valid = int(points.shape[0])
        transform = official_glb_alignment_transform(extr[0], points)
        points = transform_points(points, transform)
        for cap in caps:
            pts, cols = official_glb_filter_and_downsample(points, colors, num_max=cap, seed=args.seed)
            label = "full" if pts.shape[0] == valid or cap >= valid else f"{cap // 1_000_000}M"
            ply = args.out_dir / f"fused_{tag}_{label}_rgb.ply"
            write_point_cloud(ply, pts, cols)
            results[f"{tag}_{label}"] = {"valid_before_downsample": valid, "exported": int(pts.shape[0]), "ply": str(ply)}
            print(f"{tag}[{label}]: valid {valid:,} -> exported {pts.shape[0]:,}", flush=True)

    report = {
        "schema_version": "pocketworld_expH_window_chain_fusion_v1",
        "run_dir": str(args.run_dir),
        "parameters": vars(args) | {"run_dir": str(args.run_dir), "out_dir": str(args.out_dir)},
        "chain": {
            "edge_offsets_pct_median": float(np.median(offsets)),
            "edge_offsets_pct_max": float(np.max(offsets)),
            "cumulative_scale_min": float(scales.min()),
            "cumulative_scale_max": float(scales.max()),
            "edges": edge_stats,
        },
        "post_alignment_adjacent_residual_median_pct": float(np.median(post) * 100),
        "consistency": {
            "keep_rate": keep_rate,
            "neighbors": args.neighbors,
            "rel_thresh": args.rel_thresh,
            "min_consistent": args.min_consistent,
        },
        "official_conf_threshold": float(threshold),
        "exports": results,
    }
    (args.out_dir / "expH_fusion_report.json").write_text(json.dumps(report, indent=2, default=str))
    print("EXPH-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
