#!/usr/bin/env python3
"""Where in the pipeline do thin objects get pressed into the floor?

The user judged the anchored+gate cloud the best so far, with one residual: the
slippers are slightly collapsed compared with CasDiffMVS, whose slippers they
judge correct. So CasDiffMVS's depth is the reference here, and the question is
which stage introduces the collapse:

    raw MapAnything x per-view affine   (the network's own prior)
    + anchoring offset field            (smooth, low-dimensional)
    + official depth averaging          (src reprojections landing on the floor)
    crossview solve, with/without avg   (already known to flatten)

A thin-object pixel is one where CasDiffMVS is 1-6% nearer than the farthest
surface within 15 px -- the floor behind a slipper, the wall behind a wheel.
For each variant the collapse is expressed as the fraction of the protrusion
lost: (variant - cas) / (background - cas), with the same quantity on flat
background pixels subtracted out so a global scale offset does not masquerade
as collapse.

Positive control: CasDiffMVS's own depth with thin pixels moved half-way to the
background must read ~0.50. Null: CasDiffMVS against itself must read 0.
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
ap.add_argument("--prior_stats", default="/root/casdiffmvs_prior_20260903/priors_blendmvg/prior_stats.json")
ap.add_argument("--variants", nargs="+", required=True, help="name=path to (V,518,392) depth npy")
ap.add_argument("--radius", type=int, default=15)
ap.add_argument("--thin_lo", type=float, default=0.01)
ap.add_argument("--thin_hi", type=float, default=0.06)
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"; of = a.out_folder; V = 132
s2f = json.load(open(a.mapping))
Hm, Wm = 518, 392; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
GRID = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].to(dev)

# variants, plus raw-affine reconstructed the way export_native_anchored does it
variants = {}
for spec in a.variants:
    n, p = spec.split("=", 1); variants[n] = np.load(p).astype(np.float32)
raw = np.load(Path(a.saved) / "depth_z.npy")[..., 0].astype(np.float32)
mask = np.load(Path(a.saved) / "mask.npy")[..., 0].astype(bool)
nam = np.load(Path(a.saved) / "non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4: nam = nam[..., 0]
valid = mask & nam & (raw > 0)
pst = {t["src"]: t for t in json.load(open(a.prior_stats))["per_view"]}
aff = np.zeros_like(raw)
for s in range(V):
    f = int(s2f[s]); st = pst[s]
    aff[f] = np.where(valid[f], float(st["a"]) * raw[f] + float(st["b"]), 0.0)
variants = {"affine_only": aff, **variants}
k = 2 * a.radius + 1


def onto_cas(depth_f):
    return F.grid_sample(torch.from_numpy(depth_f)[None, None].to(dev), GRID, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]


acc = {n: {"thin": [], "flat": []} for n in list(variants) + ["CONTROL_half_collapsed", "NULL_cas_itself"]}
nthin = 0
for s in range(V):
    D = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{s:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = torch.from_numpy(cv2.imread(os.path.join(of, f"mask/{s:08d}_final.png"), 0) > 0).to(dev)
    ok = fin & (D > 0)
    small = torch.where(ok, D, torch.full_like(D, -float("inf")))
    bg = F.max_pool2d(small[None, None], k, 1, a.radius)[0, 0]          # farthest surface nearby
    vf = F.avg_pool2d(ok.float()[None, None], k, 1, a.radius)[0, 0]
    good = ok & torch.isfinite(bg) & (vf > 0.5)
    prot = (bg - D) / bg.clamp_min(1e-6)                                  # how far in front of the background
    thin = good & (prot > a.thin_lo) & (prot < a.thin_hi)
    flat = good & (prot < 0.003)
    nthin += int(thin.sum())
    f = int(s2f[s])
    for n, dep in variants.items():
        M = onto_cas(dep[f]); has = M > 0
        # collapse as fraction of the protrusion; on flat pixels the same expression is
        # dominated by the scale offset, so it is the baseline to subtract
        frac = (M - D) / (bg - D).clamp_min(1e-4)
        rel = (M - D) / D.clamp_min(1e-6)
        acc[n]["thin"].append(frac[thin & has].cpu().numpy()[::3]); acc[n]["flat"].append(rel[flat & has].cpu().numpy()[::23])
    # controls on CasDiffMVS's own depth
    half = torch.where(thin, D + 0.5 * (bg - D), D)
    for n, M in (("CONTROL_half_collapsed", half), ("NULL_cas_itself", D)):
        frac = (M - D) / (bg - D).clamp_min(1e-4); rel = (M - D) / D.clamp_min(1e-6)
        acc[n]["thin"].append(frac[thin].cpu().numpy()[::3]); acc[n]["flat"].append(rel[flat].cpu().numpy()[::23])
    if s % 33 == 0: print(f"  view {s}: thin px {int(thin.sum())}", flush=True)

print(f"\nthin-object pixels total: {nthin:,}\n")
print(" variant                    collapse (fraction of protrusion lost, p50)   scale offset on flat (p50)   thin px w/ depth")
res = {}
for n in acc:
    t = np.concatenate(acc[n]["thin"]) if acc[n]["thin"] else np.zeros(0)
    fl = np.concatenate(acc[n]["flat"]) if acc[n]["flat"] else np.zeros(0)
    # the flat-pixel scale offset (relative) converted to protrusion units is small and
    # variant-specific; report both rather than mixing them
    c = float(np.median(t)) if t.size else float("nan"); o = float(np.median(fl)) if fl.size else float("nan")
    res[n] = {"collapse_frac_p50": c, "collapse_frac_p25": float(np.percentile(t, 25)) if t.size else None,
              "collapse_frac_p75": float(np.percentile(t, 75)) if t.size else None,
              "flat_rel_offset_p50": o, "thin_px": int(t.size * 3)}
    print(f"  {n:26s} {c:+8.3f}                                       {o:+8.4f}                {t.size*3:>10,}")
Path(a.out).write_text(json.dumps({"thin_px_total": nthin, "params": vars(a), "results": res}, indent=2, default=str) + "\n")
