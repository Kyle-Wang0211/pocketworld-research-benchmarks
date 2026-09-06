#!/usr/bin/env python3
"""Where do CasDiffMVS and MapAnything disagree, over EVERY kept pixel?

The intermediate-depth bridge hypothesis is dead: removing 110,683 of them
changed nothing the eye could see and the wall still sticks to the luggage. The
user's crop shows a white apron hugging the luggage, not a thin rim.

The mechanism that fits: the wall is textureless, so the cost volume there is
flat and the regulariser propagates the depth of the nearest textured thing --
the luggage -- into the wall pixels beside it. That is a smooth ramp, not a jump,
so the two-cluster silhouette test never fires; and because every view's nearest
texture is the same luggage, the error is consistent across views and passes
the geometric gate. CasDiffMVS cannot see its own mistake. MapAnything, being a
monocular planar prior, puts the wall where a wall goes; its 1.4% absolute error
is irrelevant against a ramp of tens of percent.

So: per view, the relative depth difference between the two on every kept pixel,
its distribution, and an overlay -- red where CasDiffMVS is much NEARER than
MapAnything (pulled toward the luggage), blue where much farther.
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
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 60, 80])
ap.add_argument("--overlay_dir", default="/root/edge_overlays6")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"; of = a.out_folder; V = 132
Path(a.overlay_dir).mkdir(parents=True, exist_ok=True)
anc = np.load(a.anchored_depth).astype(np.float32)
s2f = json.load(open(a.mapping))
Hm, Wm = anc.shape[1:]; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)

edges = np.array([-1, -0.5, -0.3, -0.2, -0.1, -0.05, -0.02, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 10])
hist = np.zeros(len(edges) - 1, dtype=np.int64)
hist_bright = np.zeros(len(edges) - 1, dtype=np.int64)
tot = dict(kept=0, with_ma=0, nearer10=0, nearer10_bright=0, farther10=0, bright=0)
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), 0) > 0).to(dev)
    img = cv2.imread(os.path.join(of, f"images/{v:08d}.jpg"))
    if img.shape[:2] != (576, 768): img = cv2.resize(img, (768, 576), interpolation=cv2.INTER_AREA)
    gray = torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)).to(dev).float()
    bright = gray > 150                                          # wall / cabinet-like brightness
    m = F.grid_sample(torch.from_numpy(anc[int(s2f[v])])[None, None].to(dev), GRID, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]
    ok = fin & (m > 0) & (d > 0)
    rel = ((d - m) / m.clamp_min(1e-6))                          # <0: CasDiffMVS nearer than MapAnything
    r = rel[ok].cpu().numpy()
    h, _ = np.histogram(r, bins=edges); hist += h
    hb, _ = np.histogram(rel[ok & bright].cpu().numpy(), bins=edges); hist_bright += hb
    nearer = ok & (rel < -0.10); farther = ok & (rel > 0.10)
    tot["kept"] += int(fin.sum()); tot["with_ma"] += int(ok.sum()); tot["bright"] += int((ok & bright).sum())
    tot["nearer10"] += int(nearer.sum()); tot["nearer10_bright"] += int((nearer & bright).sum()); tot["farther10"] += int(farther.sum())
    if v in a.overlay_views:
        ov = img.copy()
        mag = (rel.abs().clamp(max=0.5) / 0.5)                   # 0..1 strength
        red = (nearer.float() * (0.35 + 0.65 * mag)).cpu().numpy()
        blue = (farther.float() * (0.35 + 0.65 * mag)).cpu().numpy()
        ov = ov.astype(np.float32)
        ov[..., 2] = ov[..., 2] * (1 - red) + 255 * red; ov[..., 1] *= (1 - red); ov[..., 0] *= (1 - red)
        ov[..., 0] = ov[..., 0] * (1 - blue) + 255 * blue; ov[..., 1] *= (1 - blue); ov[..., 2] *= (1 - blue)
        nf = (~fin).cpu().numpy(); ov[nf] *= 0.3
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_casVSma.jpg", ov.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 88])
    if v % 20 == 0:
        print(f"  view {v}: kept {int(fin.sum())}  cas nearer>10% {int(nearer.sum())} (bright {int((nearer & bright).sum())})  farther>10% {int(farther.sum())}", flush=True)

print("\n rel = (cas - ma)/ma      all kept        bright(>150) kept")
for i in range(len(edges) - 1):
    print(f"  [{edges[i]:+6.2f},{edges[i+1]:+6.2f})   {hist[i]:>12,}   {hist_bright[i]:>12,}")
r = {**tot, "nearer10_frac_of_kept": tot["nearer10"] / max(tot["with_ma"], 1),
     "nearer10_frac_of_bright": tot["nearer10_bright"] / max(tot["bright"], 1),
     "farther10_frac_of_kept": tot["farther10"] / max(tot["with_ma"], 1),
     "hist_edges": edges.tolist(), "hist_all": hist.tolist(), "hist_bright": hist_bright.tolist()}
print(json.dumps({k: v for k, v in r.items() if not k.startswith("hist")}, indent=2))
Path(a.out).write_text(json.dumps(r, indent=2) + "\n")
