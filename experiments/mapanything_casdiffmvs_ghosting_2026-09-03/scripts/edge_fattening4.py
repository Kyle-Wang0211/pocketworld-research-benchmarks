#!/usr/bin/env python3
"""Third pass: foreground fattening, not intermediate depths.

The bimodality test left only 11,890 intermediate-depth bridges in the whole
cloud (0.03%), too few to be what the eye sees as "the wall sticking to the
luggage". The other classic MVS silhouette defect fits the description better:
the object's depth extends a few pixels PAST its true silhouette because the
cost-aggregation window straddles the edge, so wall pixels get the object's
depth. Those points are not between the two surfaces -- they sit exactly on the
object's layer, but carry the wall's colour and are wall in every other view.
A depth-only test cannot see them.

So near every bimodal discontinuity, every pixel that pc.ply keeps is asked two
questions: which side does CasDiffMVS's depth put it on, and which side does
MapAnything's depth put it on. At a silhouette the two sides differ by far more
than MapAnything's 1.4% error, so its answer is trustworthy here even though its
absolute depth is not. Disagreements are the fattening (CasDiffMVS says near,
MapAnything says far) or its opposite (erosion).
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
ap.add_argument("--cluster_min", type=float, default=0.15,
                help="each of the near and far clusters must hold at least this fraction of the window")
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 80, 120])
ap.add_argument("--overlay_dir", default="/root/edge_overlays4")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo)
os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"
of = a.out_folder
V = 132
Path(a.overlay_dir).mkdir(parents=True, exist_ok=True)
anc = np.load(a.anchored_depth).astype(np.float32)
s2f = json.load(open(a.mapping))
Hm, Wm = anc.shape[1:]
s_m = Wm / 1500.0
off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5
y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5
vm = (x_l + 0.5) * s_m - 0.5 - off_v
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)


def ma_depth_on_cas(src):
    return F.grid_sample(torch.from_numpy(anc[int(s2f[src])])[None, None].to(dev), GRID,
                         mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]


k = 2 * a.radius + 1
T = dict(final=0, near_disc=0, ma_avail=0, agree=0, fatten=0, erode=0,
         fatten_depth_rel=[], fatten_dist_to_edge=[])
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), 0) > 0).to(dev)
    valid = d > 0
    big = torch.where(valid, d, torch.full_like(d, float("inf")))
    small = torch.where(valid, d, torch.full_like(d, -float("inf")))
    nmin = -F.max_pool2d(-big[None, None], k, 1, a.radius)[0, 0]
    nmax = F.max_pool2d(small[None, None], k, 1, a.radius)[0, 0]
    disc = valid & torch.isfinite(nmin) & torch.isfinite(nmax) & (nmax / nmin.clamp_min(1e-6) > a.jump)
    # A silhouette window holds a cluster at the near depth AND a cluster at the far
    # depth. The earlier "gap must be nearly empty" test failed exactly where the
    # fattening is heaviest, because a thick fattening band fills the gap; the
    # overlays showed it rejecting every luggage edge. A grazing slope has neither
    # cluster -- its depths spread uniformly -- so two-cluster presence separates
    # the cases without punishing a full gap.
    vf = F.avg_pool2d(valid.float()[None, None], k, 1, a.radius)[0, 0].clamp_min(1e-6)
    near_frac = F.avg_pool2d((valid & (d < nmin * 1.03)).float()[None, None], k, 1, a.radius)[0, 0] / vf
    far_frac = F.avg_pool2d((valid & (d > nmax * 0.97)).float()[None, None], k, 1, a.radius)[0, 0] / vf
    bimodal = disc & (near_frac >= a.cluster_min) & (far_frac >= a.cluster_min)
    cand = bimodal & fin                       # every kept pixel inside a bimodal silhouette window
    m = ma_depth_on_cas(v)
    ok = cand & (m > 0)
    cas_near = (d - nmin).abs() < (d - nmax).abs()
    ma_near = (m - nmin).abs() < (m - nmax).abs()
    agree = ok & (cas_near == ma_near)
    fatten = ok & cas_near & ~ma_near          # CasDiffMVS put wall pixel on the object
    erode = ok & ~cas_near & ma_near
    T["final"] += int(fin.sum()); T["near_disc"] += int(cand.sum()); T["ma_avail"] += int(ok.sum())
    T["agree"] += int(agree.sum()); T["fatten"] += int(fatten.sum()); T["erode"] += int(erode.sum())
    if fatten.any():
        T["fatten_depth_rel"].append(((nmax[fatten] - d[fatten]) / nmax[fatten]).cpu().numpy()[::5])
    if v in a.overlay_views:
        img = cv2.imread(os.path.join(of, f"images/{v:08d}.jpg"))
        if img.shape[:2] != (576, 768):
            img = cv2.resize(img, (768, 576), interpolation=cv2.INTER_AREA)
        ov = img.copy()
        ov[(cand & ~ok).cpu().numpy()] = (80, 80, 80)
        ov[agree.cpu().numpy()] = (0, 200, 0)
        ov[fatten.cpu().numpy()] = (0, 0, 255)      # red = wall pixel glued onto the object
        ov[erode.cpu().numpy()] = (255, 0, 0)       # blue = object pixel pushed to the wall
        nf = (~fin).cpu().numpy(); ov[nf] = (ov[nf] * 0.35).astype(np.uint8)
        cv2.imwrite(f"{a.overlay_dir}/view{v:03d}_fatten.jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if v % 20 == 0:
        print(f"  view {v}: kept {int(fin.sum())}  in silhouette windows {int(cand.sum())}  agree {int(agree.sum())}"
              f"  FATTEN {int(fatten.sum())}  erode {int(erode.sum())}", flush=True)
fr = np.concatenate(T["fatten_depth_rel"]) if T["fatten_depth_rel"] else np.zeros(0)
r = {"pixels_in_pc": T["final"], "kept_pixels_in_silhouette_windows": T["near_disc"],
     "with_mapanything_depth": T["ma_avail"], "sides_agree": T["agree"],
     "FATTEN_wall_pixel_on_object": T["fatten"], "erode_object_pixel_on_wall": T["erode"],
     "fatten_frac_of_pc": T["fatten"] / T["final"], "fatten_frac_of_silhouette_pixels": T["fatten"] / max(T["ma_avail"], 1),
     "disagree_frac_of_silhouette_pixels": (T["fatten"] + T["erode"]) / max(T["ma_avail"], 1),
     "fatten_how_far_in_front_of_wall_rel_p50": float(np.median(fr)) if fr.size else None,
     "params": {k_: v_ for k_, v_ in vars(a).items()}}
print(json.dumps({k_: v_ for k_, v_ in r.items() if k_ != "params"}, indent=2))
Path(a.out).write_text(json.dumps(r, indent=2, default=str) + "\n")
