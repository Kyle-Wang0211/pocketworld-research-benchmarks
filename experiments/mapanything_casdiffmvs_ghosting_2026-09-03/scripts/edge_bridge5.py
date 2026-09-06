#!/usr/bin/env python3
"""Fifth pass, the count that matters: kept pixels that sit in a genuine
silhouette window (a near cluster AND a far cluster) with a depth strictly
between the two. That is the bridge the eye sees as the wall sticking to the
luggage. The two-cluster gate rejects grazing floors (pass 1's false positives);
the between test keeps the fattening band that the gap-emptiness test threw away
(pass 2) and the nearest-side classification hid (pass 4).

Also records, for each bridge, which side MapAnything's depth assigns it to --
the side its depth should be snapped to if snapping rather than deleting is
wanted -- and the per-view bridge mask, so the fix can be applied on replay.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="/root/casdiffmvs_official_20260903/diffmvs_upstream")
ap.add_argument("--out_folder", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
ap.add_argument("--anchored_depth", default="/root/mapanything_native_anchored_20260903/depth_native_final.npy")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--radius", type=int, default=6)
ap.add_argument("--jump", type=float, default=1.12)
ap.add_argument("--margin", type=float, default=0.03)
ap.add_argument("--cluster_min", type=float, default=0.15)
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 80, 120])
ap.add_argument("--overlay_dir", default="/root/edge_overlays5")
ap.add_argument("--mask_dir", default="/root/bridge_masks", help="per-view bridge masks, for the fix")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"; of = a.out_folder; V = 132
Path(a.overlay_dir).mkdir(parents=True, exist_ok=True); Path(a.mask_dir).mkdir(parents=True, exist_ok=True)
anc = np.load(a.anchored_depth).astype(np.float32)
s2f = json.load(open(a.mapping))
Hm, Wm = anc.shape[1:]; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)
k = 2 * a.radius + 1

T = dict(final=0, silhouette=0, bridge=0, bridge_ma=0, ma_wall=0, ma_obj=0)
depth_pos = []
per_view = []
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), 0) > 0).to(dev)
    valid = d > 0
    big = torch.where(valid, d, torch.full_like(d, float("inf"))); small = torch.where(valid, d, torch.full_like(d, -float("inf")))
    nmin = -F.max_pool2d(-big[None, None], k, 1, a.radius)[0, 0]; nmax = F.max_pool2d(small[None, None], k, 1, a.radius)[0, 0]
    disc = valid & torch.isfinite(nmin) & torch.isfinite(nmax) & (nmax / nmin.clamp_min(1e-6) > a.jump)
    vf = F.avg_pool2d(valid.float()[None, None], k, 1, a.radius)[0, 0].clamp_min(1e-6)
    near_frac = F.avg_pool2d((valid & (d < nmin * (1 + a.margin))).float()[None, None], k, 1, a.radius)[0, 0] / vf
    far_frac = F.avg_pool2d((valid & (d > nmax * (1 - a.margin))).float()[None, None], k, 1, a.radius)[0, 0] / vf
    sil = disc & (near_frac >= a.cluster_min) & (far_frac >= a.cluster_min) & fin
    between = (d > nmin * (1 + a.margin)) & (d < nmax * (1 - a.margin))
    bridge = sil & between
    m = F.grid_sample(torch.from_numpy(anc[int(s2f[v])])[None, None].to(dev), GRID, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]
    bm = bridge & (m > 0)
    ma_wall = bm & ((m - nmax).abs() < (m - nmin).abs())
    ma_obj = bm & ~((m - nmax).abs() < (m - nmin).abs())
    T["final"] += int(fin.sum()); T["silhouette"] += int(sil.sum()); T["bridge"] += int(bridge.sum())
    T["bridge_ma"] += int(bm.sum()); T["ma_wall"] += int(ma_wall.sum()); T["ma_obj"] += int(ma_obj.sum())
    if bridge.any():
        # where in the gap the bridge sits: 0 = at the object, 1 = at the wall
        depth_pos.append((((d - nmin) / (nmax - nmin).clamp_min(1e-6))[bridge]).cpu().numpy()[::5])
    cv2.imwrite(f"{a.mask_dir}/{v:08d}_bridge.png", (bridge.cpu().numpy() * 255).astype(np.uint8))
    per_view.append({"view": v, "kept": int(fin.sum()), "silhouette": int(sil.sum()), "bridge": int(bridge.sum())})
    if v in a.overlay_views:
        img = cv2.imread(os.path.join(of, f"images/{v:08d}.jpg"))
        if img.shape[:2] != (576, 768): img = cv2.resize(img, (768, 576), interpolation=cv2.INTER_AREA)
        ov = img.copy()
        ov[(sil & ~bridge).cpu().numpy()] = (0, 200, 0)      # green  = silhouette window, depth on a side (fine)
        ov[ma_wall.cpu().numpy()] = (0, 0, 255)               # red    = bridge, MapAnything says it is wall
        ov[ma_obj.cpu().numpy()] = (255, 0, 0)                # blue   = bridge, MapAnything says it is object
        ov[(bridge & ~bm).cpu().numpy()] = (0, 255, 255)      # yellow = bridge, MapAnything has no depth here
        nf = (~fin).cpu().numpy(); ov[nf] = (ov[nf] * 0.35).astype(np.uint8)
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_bridge.jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if v % 20 == 0:
        print(f"  view {v}: kept {int(fin.sum())}  silhouette {int(sil.sum())}  BRIDGE {int(bridge.sum())}"
              f"  MA: wall {int(ma_wall.sum())} / object {int(ma_obj.sum())}", flush=True)
dp = np.concatenate(depth_pos) if depth_pos else np.zeros(0)
r = {"pixels_in_pc": T["final"], "kept_in_silhouette_windows": T["silhouette"], "BRIDGE": T["bridge"],
     "bridge_frac_of_pc": T["bridge"] / T["final"], "bridge_frac_of_silhouette": T["bridge"] / max(T["silhouette"], 1),
     "bridge_with_mapanything_depth": T["bridge_ma"], "mapanything_says_wall": T["ma_wall"], "mapanything_says_object": T["ma_obj"],
     "wall_frac": T["ma_wall"] / max(T["bridge_ma"], 1),
     "bridge_position_in_gap_p10_p50_p90": [float(np.percentile(dp, q)) for q in (10, 50, 90)] if dp.size else None,
     "params": {k_: v_ for k_, v_ in vars(a).items()}}
print(json.dumps({k_: v_ for k_, v_ in r.items() if k_ != "params"}, indent=2))
Path(a.out).write_text(json.dumps({"summary": r, "per_view": per_view}, indent=2, default=str) + "\n")
