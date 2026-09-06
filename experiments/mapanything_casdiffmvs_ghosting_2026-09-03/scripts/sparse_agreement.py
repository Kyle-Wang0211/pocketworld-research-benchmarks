#!/usr/bin/env python3
"""Check the solved field against evidence it never saw.

Cross-view agreement has a blind spot: a deformation every view agrees on -- a
gauge drift -- improves nothing and costs nothing, so the held-out test cannot
see it. The only way to catch one is a reference built without MapAnything at
all. COLMAP's sparse model is exactly that: 292k points triangulated from feature
matches across the same 132 images, independent of anything the network predicts.

For each sparse point, take the nearest points of each cloud within a small ball
and report the distance. A field that corrects real error moves the cloud toward
these points; a field that has drifted moves it away, however well its own views
agree with each other.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/root")
from mapanything.utils.colmap import read_model  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--radius", type=float, default=0.10)
ap.add_argument("--voxel", type=float, default=0.02)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"

cams, imgs, p3d = read_model(a.colmap_sparse, ext=".bin")
X = np.stack([p.xyz for p in p3d.values()])
ntrack = np.array([len(p.image_ids) for p in p3d.values()])
# rotate_world_to_camera turns the CAMERA axes only, leaving the world frame
# untouched, so the exported clouds are already in COLMAP's own world frame and
# the sparse points need no transform. Rotating them here is what made the first
# run of this check meaningless: only 16% of points found a neighbour within
# 10 cm and every p90 sat pinned against the search radius.
print(f"{X.shape[0]} sparse points, track length p50 {np.median(ntrack):.0f}", flush=True)
S = torch.from_numpy(X).to(dev).double()

report = {}
for spec in a.sets:
    name, path = spec.split("=", 1)
    P = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(path).points)).to(dev)
    h = a.voxel
    o0 = P.min(0).values - 3 * h
    vi = torch.floor((P - o0) / h).long()
    dm = vi.max(0).values + 4
    st = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
    lin = (vi * st).sum(1)
    order = torch.argsort(lin)
    lin_s, P_s = lin[order], P[order]
    R = int(round(a.radius / h))
    best = torch.full((S.shape[0],), float("inf"), device=dev, dtype=torch.float64)
    vs = torch.floor((S - o0) / h).long()
    for ox in range(-R, R + 1):
        for oy in range(-R, R + 1):
            for oz in range(-R, R + 1):
                if ox * ox + oy * oy + oz * oz > R * R:
                    continue
                t = ((vs + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * st).sum(1)
                lo = torch.searchsorted(lin_s, t, right=False)
                hi = torch.searchsorted(lin_s, t, right=True)
                cnt = (hi - lo).clamp(max=8)
                for k in range(int(cnt.max()) if int(cnt.max()) > 0 else 0):
                    sel = k < cnt
                    if not sel.any():
                        continue
                    idx = (lo[sel] + k).clamp(max=P_s.shape[0] - 1)
                    d = (P_s[idx] - S[sel]).norm(dim=1)
                    cur = best[sel]
                    best[sel] = torch.minimum(cur, d)
    hit = torch.isfinite(best)
    b = best[hit]
    report[name] = {"matched": int(hit.sum()), "frac_matched": float(hit.double().mean()),
                    "dist_mm_p50": float(b.median() * 1000),
                    "dist_mm_p90": float(torch.quantile(b.float(), 0.90) * 1000),
                    "frac_within_1cm": float((b < 0.01).double().mean()),
                    "frac_within_2cm": float((b < 0.02).double().mean())}
    print("%-18s matched %.3f   nearest point  p50 %6.2f mm  p90 %7.2f mm   <1cm %.3f  <2cm %.3f" % (
        name, report[name]["frac_matched"], report[name]["dist_mm_p50"], report[name]["dist_mm_p90"],
        report[name]["frac_within_1cm"], report[name]["frac_within_2cm"]), flush=True)
    del P, P_s, lin, lin_s, best
    torch.cuda.empty_cache()
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
