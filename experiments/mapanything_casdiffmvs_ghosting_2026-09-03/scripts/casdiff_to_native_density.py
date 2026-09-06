#!/usr/bin/env python3
"""DIAGNOSTIC ONLY: CasDiffMVS's own geometry at MapAnything's pixel density.

The user sees the slippers in the anchored+gate cloud as slightly collapsed
against CasDiffMVS, yet the thin-object ruler (positive control passed) puts the
two within +-3% of the protrusion for 75% of thin pixels -- about 1 mm on a
slipper, below what the eye resolved elsewhere today. The remaining suspect is
not geometry but sampling: MapAnything runs at 518x392 per view, CasDiffMVS at
768x576, so the same slipper carries 45% as many points and the floor shows
through between them.

This keeps CasDiffMVS's geometry untouched and only thins its sampling to the
MapAnything grid: every 768x576 pixel is mapped to its 518x392 cell and one
pixel per cell survives (the one nearest the cell centre). Same surfaces, same
depths, MapAnything's density. If this reads as "collapsed" the residual is
resolution; if it stays solid, the residual is MapAnything's geometry.

Output is a keep-mask in pc.ply vertex order, applied locally by the same
byte-identical filter used for the debridge test. Never a deliverable.
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
os.chdir("/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pair_file  # noqa: E402

of = "/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10"
pair = read_pair_file("/root/casdiffmvs_official_20260903/mvs_P16k/pair.txt", "general")
dev = "cuda"
Hm, Wm = 518, 392; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
cu, cv = np.round(um), np.round(vm)
cell = (cv * Wm + cu).astype(np.int64)                       # native cell id per 768x576 pixel
dist = (um - cu) ** 2 + (vm - cv) ** 2                       # distance to that cell's centre
cell_t = torch.from_numpy(cell).to(dev); dist_t = torch.from_numpy(dist).to(dev)

keep_all = []
kept_total = 0
for ref, _ in pair:
    fin = torch.from_numpy(cv2.imread(f"{of}/mask/{ref:08d}_final.png", 0) > 0).to(dev)
    idx = torch.nonzero(fin.reshape(-1), as_tuple=True)[0]           # raster order = pc.ply order within the view
    c = cell_t.reshape(-1)[idx]; d = dist_t.reshape(-1)[idx]
    # one survivor per cell: the pixel nearest the cell centre
    order = torch.argsort(c * 10.0 + d.clamp(max=9.0))               # cells ascending, distance ascending within a cell
    c_s = c[order]
    first = torch.ones_like(c_s, dtype=torch.bool); first[1:] = c_s[1:] != c_s[:-1]
    keep = torch.zeros(idx.numel(), dtype=torch.bool, device=dev); keep[order[first]] = True
    keep_all.append(keep.cpu().numpy().astype(np.uint8)); kept_total += int(keep.sum())
    if ref % 33 == 0: print(f"  view {ref}: {idx.numel()} -> {int(keep.sum())}", flush=True)
keep = np.concatenate(keep_all)
assert keep.size == 36845039, keep.size
open("/root/casdiff_debridged_20260906/keep_native_density.u8", "wb").write(keep.tobytes())
print(f"kept {kept_total:,} of {keep.size:,} ({100*kept_total/keep.size:.1f}%) -- MapAnything-density CasDiffMVS")
