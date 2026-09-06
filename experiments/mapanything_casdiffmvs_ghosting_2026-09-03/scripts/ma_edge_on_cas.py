#!/usr/bin/env python3
"""The pixels the disagreement map could not see.

CasDiffMVS and MapAnything agree within 2% on 96.5% of the kept pixels that both
have a depth for -- but 1.4M kept pixels (3.8%) have no MapAnything depth at all,
because MapAnything's own mask (non_ambiguous & edge) refuses them. That mask is
a learned detector of exactly the silhouette-ambiguity zone, and the sticking
lives at silhouettes. So this pass overlays those refused-but-kept pixels, counts
how many are wall-bright, and checks where their CasDiffMVS depth sits relative
to the surrounding near/far surfaces.
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
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 60, 80])
ap.add_argument("--overlay_dir", default="/root/edge_overlays7")
ap.add_argument("--mask_dir", default="/root/ma_edge_masks")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"; of = a.out_folder; V = 132
Path(a.overlay_dir).mkdir(parents=True, exist_ok=True); Path(a.mask_dir).mkdir(parents=True, exist_ok=True)
ma_mask = np.load(Path(a.saved) / "mask.npy")[..., 0].astype(bool)
nam = np.load(Path(a.saved) / "non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4: nam = nam[..., 0]
ma_valid = (ma_mask & nam).astype(np.float32)
s2f = json.load(open(a.mapping))
Hm, Wm = ma_mask.shape[1:]; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
inb = (um >= 0) & (um <= Wm - 1) & (vm >= 0) & (vm <= Hm - 1)          # inside MapAnything's frame at all
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)
INB = torch.from_numpy(inb).to(dev)
k = 13; r6 = 6
T = dict(kept=0, in_frame=0, refused=0, refused_bright=0, refused_near_disc=0, refused_between=0)
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), 0) > 0).to(dev)
    img = cv2.imread(os.path.join(of, f"images/{v:08d}.jpg"))
    if img.shape[:2] != (576, 768): img = cv2.resize(img, (768, 576), interpolation=cv2.INTER_AREA)
    bright = torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)).to(dev) > 150
    mv = F.grid_sample(torch.from_numpy(ma_valid[int(s2f[v])])[None, None].to(dev), GRID, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0] > 0.5
    refused = fin & INB & ~mv                       # kept by CasDiffMVS, refused by MapAnything's own mask
    valid = d > 0
    big = torch.where(valid, d, torch.full_like(d, float("inf"))); small = torch.where(valid, d, torch.full_like(d, -float("inf")))
    nmin = -F.max_pool2d(-big[None, None], k, 1, r6)[0, 0]; nmax = F.max_pool2d(small[None, None], k, 1, r6)[0, 0]
    disc = torch.isfinite(nmin) & torch.isfinite(nmax) & (nmax / nmin.clamp_min(1e-6) > 1.12)
    between = (d > nmin * 1.03) & (d < nmax * 0.97)
    T["kept"] += int(fin.sum()); T["in_frame"] += int((fin & INB).sum()); T["refused"] += int(refused.sum())
    T["refused_bright"] += int((refused & bright).sum()); T["refused_near_disc"] += int((refused & disc).sum())
    T["refused_between"] += int((refused & disc & between).sum())
    cv2.imwrite(f"{a.mask_dir}/{v:08d}_refused.png", (refused.cpu().numpy() * 255).astype(np.uint8))
    if v in a.overlay_views:
        ov = img.copy()
        ov[(refused & bright).cpu().numpy()] = (0, 0, 255)      # red  = refused by MapAnything AND wall-bright
        ov[(refused & ~bright).cpu().numpy()] = (255, 0, 0)     # blue = refused, dark (object-side)
        nf = (~fin).cpu().numpy(); ov[nf] = (ov[nf] * 0.3).astype(np.uint8)
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_refused.jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if v % 20 == 0:
        print(f"  view {v}: kept {int(fin.sum())}  refused-by-MA {int(refused.sum())}  bright {int((refused & bright).sum())}", flush=True)
r = {**T, "refused_frac_of_kept": T["refused"] / T["kept"], "refused_bright_frac": T["refused_bright"] / max(T["refused"], 1),
     "refused_near_disc_frac": T["refused_near_disc"] / max(T["refused"], 1), "refused_between_frac": T["refused_between"] / max(T["refused"], 1)}
print(json.dumps(r, indent=2))
Path(a.out).write_text(json.dumps(r, indent=2) + "\n")
