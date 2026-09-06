#!/usr/bin/env python3
"""Second pass on the sticking: separate true bridges from grazing slopes, decide
each bridge's side with MapAnything's depth, and draw the result on the images.

The first pass flagged 429k pixels in pc.ply as sitting between a near and a far
surface. That test has a known hole: a wall or floor seen at a grazing angle also
puts the centre pixel "between" the window's min and max, with no discontinuity
at all. A real silhouette is bimodal -- most of the window sits at one of the two
depths and almost nothing in the gap -- so a bimodality test separates the two.

For the bridges that survive, MapAnything's depth is used only to answer one
binary question: is this pixel nearer the object or nearer the wall? At a
silhouette the two candidates differ by tens of percent, far beyond
MapAnything's 1.4% cross-view error, so the classification is robust even though
its absolute depth is not. The MVS depth of the chosen side is then the depth the
pixel should have had.
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
ap.add_argument("--gap_frac_max", type=float, default=0.25,
                help="a window is bimodal if at most this fraction of its valid pixels lie in the gap between the two modes")
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 80, 120])
ap.add_argument("--overlay_dir", default="/root/edge_overlays")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo)
os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"
of = a.out_folder
V = 132
Path(a.overlay_dir).mkdir(parents=True, exist_ok=True)

anc = np.load(a.anchored_depth).astype(np.float32)      # frame index, 518x392, metric, 0 = masked
s2f = json.load(open(a.mapping))
Hm, Wm = anc.shape[1:]
s_m = Wm / 1500.0
off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5
y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
x15 = 1500.0 - 1.0 - y_l
y15 = x_l
um = (x15 + 0.5) * s_m - 0.5
vm = (y15 + 0.5) * s_m - 0.5 - off_v
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)


def ma_depth_on_cas(src):
    f = int(s2f[src])
    m = torch.from_numpy(anc[f])[None, None].to(dev)
    return F.grid_sample(m, GRID, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]


k = 2 * a.radius + 1
tot = dict(final=0, bridge_v1=0, bridge_bimodal=0, ma_avail=0, side_wall=0, side_object=0,
           wall_side_depth_err_rel=[], object_side_depth_err_rel=[])
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), 0) > 0).to(dev)
    valid = d > 0
    big = torch.where(valid, d, torch.full_like(d, float("inf")))
    small = torch.where(valid, d, torch.full_like(d, -float("inf")))
    nmin = -F.max_pool2d(-big[None, None], k, 1, a.radius)[0, 0]
    nmax = F.max_pool2d(small[None, None], k, 1, a.radius)[0, 0]
    disc = valid & torch.isfinite(nmin) & torch.isfinite(nmax) & (nmax / nmin.clamp_min(1e-6) > a.jump)
    between = (d > nmin * (1 + a.margin)) & (d < nmax * (1 - a.margin))
    b1 = disc & between & fin
    # bimodality: fraction of valid window pixels that sit in the gap
    gap = (valid & (d > nmin * (1 + a.margin)) & (d < nmax * (1 - a.margin))).float()
    # note nmin/nmax are per-centre; approximate by counting pixels whose depth lies in
    # the centre pixel's gap band -- evaluated with the centre's band via a second pool
    # of indicator images is not separable, so use the ratio of "mid" pixels computed
    # against each pixel's OWN window extremes, then average over the window.
    gap_frac = F.avg_pool2d(gap[None, None], k, 1, a.radius)[0, 0]
    vfrac = F.avg_pool2d(valid.float()[None, None], k, 1, a.radius)[0, 0]
    bimodal = (gap_frac / vfrac.clamp_min(1e-6)) <= a.gap_frac_max
    b2 = b1 & bimodal
    # which side does MapAnything put it on
    m = ma_depth_on_cas(v)
    ma_ok = b2 & (m > 0)
    to_near = (m - nmin).abs()
    to_far = (m - nmax).abs()
    wall = ma_ok & (to_far < to_near)
    obj = ma_ok & ~(to_far < to_near)
    tot["final"] += int(fin.sum()); tot["bridge_v1"] += int(b1.sum()); tot["bridge_bimodal"] += int(b2.sum())
    tot["ma_avail"] += int(ma_ok.sum()); tot["side_wall"] += int(wall.sum()); tot["side_object"] += int(obj.sum())
    if wall.any():
        tot["wall_side_depth_err_rel"].append(((nmax[wall] - d[wall]) / nmax[wall]).cpu().numpy()[::7])
    if obj.any():
        tot["object_side_depth_err_rel"].append(((d[obj] - nmin[obj]) / nmin[obj]).cpu().numpy()[::7])
    if v in a.overlay_views:
        img = cv2.imread(os.path.join(of, f"images/{v:08d}.jpg"))
        if img.shape[:2] != (576, 768):
            img = cv2.resize(img, (768, 576), interpolation=cv2.INTER_AREA)
        ov = img.copy()
        ov[(b1 & ~b2).cpu().numpy()] = (0, 200, 255)     # v1-only = grazing slope, yellow
        ov[wall.cpu().numpy()] = (0, 0, 255)             # bridge, MapAnything says wall, red
        ov[obj.cpu().numpy()] = (255, 0, 0)              # bridge, MapAnything says object, blue
        ov[~fin.cpu().numpy()] = (ov[~fin.cpu().numpy()] * 0.35).astype(np.uint8)   # dim what pc.ply does not contain
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_overlay.jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_rgb.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if v % 20 == 0:
        print(f"  view {v}: final {int(fin.sum())}  bridge {int(b1.sum())} -> bimodal {int(b2.sum())}"
              f"  MA side: wall {int(wall.sum())} / object {int(obj.sum())}", flush=True)

w = np.concatenate(tot["wall_side_depth_err_rel"]) if tot["wall_side_depth_err_rel"] else np.zeros(0)
o = np.concatenate(tot["object_side_depth_err_rel"]) if tot["object_side_depth_err_rel"] else np.zeros(0)
r = {"pixels_in_pc": tot["final"],
     "bridge_pass1": tot["bridge_v1"], "bridge_bimodal": tot["bridge_bimodal"],
     "grazing_false_positives_removed": tot["bridge_v1"] - tot["bridge_bimodal"],
     "bimodal_frac_of_pc": tot["bridge_bimodal"] / tot["final"],
     "mapanything_depth_available": tot["ma_avail"],
     "side_wall": tot["side_wall"], "side_object": tot["side_object"],
     "wall_side_frac": tot["side_wall"] / max(tot["ma_avail"], 1),
     "wall_side_how_far_from_wall_rel_p50": float(np.median(w)) if w.size else None,
     "wall_side_how_far_from_wall_rel_p90": float(np.percentile(w, 90)) if w.size else None,
     "object_side_how_far_from_object_rel_p50": float(np.median(o)) if o.size else None,
     "params": vars(a)}
print(json.dumps({k: v for k, v in r.items() if k != "params"}, indent=2))
Path(a.out).write_text(json.dumps(r, indent=2, default=str) + "\n")
