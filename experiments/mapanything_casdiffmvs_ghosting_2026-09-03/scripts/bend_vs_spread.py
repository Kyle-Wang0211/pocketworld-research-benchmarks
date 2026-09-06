#!/usr/bin/env python3
"""Separate the two things that have been conflated all session: SPREAD and BEND.

The user reads the anchored version as the least distorted in the outer 70% of
the room, while the spread ruler says it is the WORST there (>2cm 21.2% vs the
robust surface version's 14.8%). Both can be true if the eye is reacting to a
different quantity:

  SPREAD  the same surface appears thick / hazy -- 132 views disagreeing
  BEND    the surface itself is deformed -- introduced by a correction that
          followed weak evidence

Every version after the anchored one traded bend for spread: they used
cross-view evidence to thin the surface, and in the periphery that evidence is
weak, so the correction deformed the geometry MapAnything had produced.

This measures both, restricted to the periphery, against the same reference
(the affine-only cloud = MapAnything's own geometry in metric scale):

  disp_mm            how far each point was moved
  bend_mm            local spatial variation of that displacement inside a 10 cm
                     neighbourhood -- a rigid or smoothly varying correction has
                     a low value however large the displacement; a correction
                     that deforms the surface has a high one

All candidates keep the same point ordering, so displacement is per-point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--ref_geom", required=True, help="affine-only cloud = MapAnything's own geometry")
ap.add_argument("--coverage_ref", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--cell", type=float, default=0.10, help="neighbourhood for the bend statistic")
ap.add_argument("--keep", type=float, default=0.05)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"

R = np.asarray(o3d.io.read_point_cloud(a.ref_geom).points)
Rt = torch.from_numpy(R).to(dev)
N = R.shape[0]
print(f"reference geometry {N} points", flush=True)

# coverage mask of the reference method, to split centre from periphery
Cv = np.asarray(o3d.io.read_point_cloud(a.coverage_ref).points)
Ct = torch.from_numpy(Cv).to(dev)
hk = a.keep
o0 = Ct.min(0).values - 3 * hk
vi = torch.floor((Ct - o0) / hk).long()
dm = vi.max(0).values + 4
st = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
occ = torch.unique((vi * st).sum(1))
v = torch.floor((Rt - o0) / hk).long()
inside = torch.zeros(N, dtype=torch.bool, device=dev)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = ((v + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * st).sum(1)
            pos = torch.searchsorted(occ, t).clamp(max=occ.numel() - 1)
            inside |= occ[pos] == t
outside = ~inside
print(f"centre {int(inside.sum())}  periphery {int(outside.sum())}", flush=True)

# cells for the bend statistic
hc = a.cell
oc = Rt.min(0).values - hc
vc = torch.floor((Rt - oc) / hc).long()
dc = vc.max(0).values + 2
sc = torch.tensor([int(dc[1]) * int(dc[2]), int(dc[2]), 1], device=dev, dtype=torch.long)
uq, invc = torch.unique((vc * sc).sum(1), return_inverse=True)
Mc = uq.numel()

report = {}
for spec in a.sets:
    name, path = spec.split("=", 1)
    P = np.asarray(o3d.io.read_point_cloud(path).points)
    if P.shape[0] != N:
        print(f"{name}: SKIP, {P.shape[0]} points != reference {N}", flush=True)
        continue
    D = torch.from_numpy(P).to(dev) - Rt
    cnt = torch.zeros(Mc, device=dev, dtype=torch.float64)
    cnt.scatter_add_(0, invc, torch.ones(N, device=dev, dtype=torch.float64))
    s1 = torch.zeros(Mc, 3, device=dev, dtype=torch.float64)
    s2 = torch.zeros(Mc, 3, device=dev, dtype=torch.float64)
    for k in range(3):
        s1[:, k].scatter_add_(0, invc, D[:, k])
        s2[:, k].scatter_add_(0, invc, D[:, k] ** 2)
    mu = s1 / cnt[:, None].clamp_min(1)
    var = (s2 / cnt[:, None].clamp_min(1) - mu ** 2).clamp_min(0)
    bend_cell = var.sum(1).sqrt()          # spatial std of the displacement inside the cell
    bend = bend_cell[invc]
    row = {}
    for tag, m in (("centre", inside), ("periphery", outside)):
        if m.sum() < 1000:
            continue
        d = D[m].norm(dim=1)
        b = bend[m]
        row[tag] = {
            "disp_mm_p50": float(d.median() * 1000),
            "disp_mm_p95": float(torch.quantile(d[::37].float(), 0.95) * 1000),
            "bend_mm_p50": float(b.median() * 1000),
            "bend_mm_p95": float(torch.quantile(b[::37].float(), 0.95) * 1000),
            "frac_bend_over_5mm": float((b > 0.005).double().mean()),
        }
    report[name] = row
    p = row.get("periphery", {})
    c = row.get("centre", {})
    print("%-16s periphery: moved %6.1fmm  BEND p50 %5.2fmm p95 %6.2fmm  >5mm %.3f   |  centre: BEND p50 %5.2fmm" % (
        name, p.get("disp_mm_p50", 0), p.get("bend_mm_p50", 0), p.get("bend_mm_p95", 0),
        p.get("frac_bend_over_5mm", 0), c.get("bend_mm_p50", 0)), flush=True)
    del D, s1, s2, mu, var
    torch.cuda.empty_cache()
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
