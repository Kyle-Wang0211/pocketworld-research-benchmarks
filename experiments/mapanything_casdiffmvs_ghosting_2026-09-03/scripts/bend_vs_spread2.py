#!/usr/bin/env python3
"""BEND and SPREAD, measured separately, relative to the version the user keeps
choosing (the anchored one), split into centre and periphery.

First attempt measured bend as the spatial variation of the displacement field
inside a cell. That is dominated by the fact that any depth-dependent correction
moves far points more than near ones, so every candidate scored 32-47 mm and the
metric had no discriminating power. It measured "the correction varies with
depth", not "the surface got bent".

This measures the two things the eye actually separates:

  BEND    the angle between the local plane normal before and after, per 10 cm
          cell. A correction that slides a surface along its own normal, however
          large, leaves this at zero; one that deforms the surface turns it.
  SPREAD  the RMS distance of the cell's points to their own local plane, i.e.
          how thick that patch is.

Reference is the anchored cloud, so the question asked is precisely: what did
each later step do, on top of the version the user prefers, and where.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch


def plane_per_cell(P, inv, M, minpts):
    """mean, unit normal and RMS residual of the best-fit plane in every cell."""
    dev = P.device
    cnt = torch.zeros(M, device=dev, dtype=torch.float64)
    cnt.scatter_add_(0, inv, torch.ones(P.shape[0], device=dev, dtype=torch.float64))
    s1 = torch.zeros(M, 3, device=dev, dtype=torch.float64)
    for k in range(3):
        s1[:, k].scatter_add_(0, inv, P[:, k])
    mu = s1 / cnt[:, None].clamp_min(1)
    pairs = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]
    s2 = torch.zeros(M, 6, device=dev, dtype=torch.float64)
    for q, (x_, y_) in enumerate(pairs):
        s2[:, q].scatter_add_(0, inv, P[:, x_] * P[:, y_])
    m2 = s2 / cnt[:, None].clamp_min(1)
    cov = torch.zeros(M, 3, 3, device=dev, dtype=torch.float64)
    for q, (x_, y_) in enumerate(pairs):
        cov[:, x_, y_] = m2[:, q] - mu[:, x_] * mu[:, y_]
        cov[:, y_, x_] = cov[:, x_, y_]
    cov = torch.where(torch.isfinite(cov), cov, torch.zeros_like(cov))
    # closed-form smallest eigenpair of a symmetric 3x3
    a00, a01, a02 = cov[:, 0, 0], cov[:, 0, 1], cov[:, 0, 2]
    a11, a12, a22 = cov[:, 1, 1], cov[:, 1, 2], cov[:, 2, 2]
    p1 = a01 ** 2 + a02 ** 2 + a12 ** 2
    q_ = (a00 + a11 + a22) / 3.0
    p2 = (a00 - q_) ** 2 + (a11 - q_) ** 2 + (a22 - q_) ** 2 + 2.0 * p1
    pp = torch.sqrt((p2 / 6.0).clamp_min(1e-300))
    iv = 1.0 / pp
    b00, b11, b22 = (a00 - q_) * iv, (a11 - q_) * iv, (a22 - q_) * iv
    b01, b02, b12 = a01 * iv, a02 * iv, a12 * iv
    detB = (b00 * (b11 * b22 - b12 * b12) - b01 * (b01 * b22 - b12 * b02) + b02 * (b01 * b12 - b11 * b02))
    r = (detB / 2.0).clamp(-1.0, 1.0)
    phi = torch.acos(r) / 3.0
    e1 = q_ + 2.0 * pp * torch.cos(phi)
    e3 = q_ + 2.0 * pp * torch.cos(phi + 2.0 * np.pi / 3.0)
    e2 = 3.0 * q_ - e1 - e3
    I = torch.eye(3, device=dev, dtype=torch.float64)[None]
    Mm = (cov - e1[:, None, None] * I) @ (cov - e2[:, None, None] * I)
    pick = Mm.norm(dim=1).argmax(dim=1)
    n = Mm[torch.arange(M, device=dev), :, pick]
    n = n / n.norm(dim=1, keepdim=True).clamp_min(1e-300)
    ok = (cnt >= minpts) & torch.isfinite(n).all(1) & (pp > 0)
    rms = e3.clamp_min(0).sqrt()          # smallest eigenvalue = variance along the normal
    return mu, n, rms, ok


ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True, help="name=path of the reference version (the one the user prefers)")
ap.add_argument("--coverage_ref", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--cell", type=float, default=0.10)
ap.add_argument("--minpts", type=int, default=30)
ap.add_argument("--keep", type=float, default=0.05)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"

rname, rpath = a.ref.split("=", 1)
R = np.asarray(o3d.io.read_point_cloud(rpath).points)
Rt = torch.from_numpy(R).to(dev)
N = R.shape[0]

Cv = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.coverage_ref).points)).to(dev)
hk = a.keep
o0 = Cv.min(0).values - 3 * hk
vi = torch.floor((Cv - o0) / hk).long()
dm = vi.max(0).values + 4
stk = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
occ = torch.unique((vi * stk).sum(1))
v = torch.floor((Rt - o0) / hk).long()
inside = torch.zeros(N, dtype=torch.bool, device=dev)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = ((v + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * stk).sum(1)
            pos = torch.searchsorted(occ, t).clamp(max=occ.numel() - 1)
            inside |= occ[pos] == t

hc = a.cell
oc = Rt.min(0).values - hc
vc = torch.floor((Rt - oc) / hc).long()
dc = vc.max(0).values + 2
sc = torch.tensor([int(dc[1]) * int(dc[2]), int(dc[2]), 1], device=dev, dtype=torch.long)
uq, invc = torch.unique((vc * sc).sum(1), return_inverse=True)
Mc = uq.numel()
# a cell is "centre" if most of its reference points are inside the coverage
ins_cell = torch.zeros(Mc, device=dev, dtype=torch.float64)
ins_cell.scatter_add_(0, invc, inside.double())
cnt_cell = torch.zeros(Mc, device=dev, dtype=torch.float64)
cnt_cell.scatter_add_(0, invc, torch.ones(N, device=dev, dtype=torch.float64))
centre_cell = (ins_cell / cnt_cell.clamp_min(1)) > 0.5
print(f"{Mc} cells at {hc*100:.0f} cm; centre {int(centre_cell.sum())}  periphery {int((~centre_cell).sum())}", flush=True)

mu_r, n_r, rms_r, ok_r = plane_per_cell(Rt, invc, Mc, a.minpts)
report = {rname: {}}
for tag, m in (("centre", centre_cell), ("periphery", ~centre_cell)):
    s = ok_r & m
    report[rname][tag] = {"spread_mm_p50": float(rms_r[s].median() * 1000),
                          "spread_mm_p95": float(torch.quantile(rms_r[s].float(), 0.95) * 1000)}
print("%-14s REFERENCE   spread centre %5.1fmm  periphery %5.1fmm" % (
    rname, report[rname]["centre"]["spread_mm_p50"], report[rname]["periphery"]["spread_mm_p50"]), flush=True)

for spec in a.sets:
    name, path = spec.split("=", 1)
    P = np.asarray(o3d.io.read_point_cloud(path).points)
    if P.shape[0] != N:
        print(f"{name}: SKIP ({P.shape[0]} != {N})", flush=True)
        continue
    Pt = torch.from_numpy(P).to(dev)
    mu_c, n_c, rms_c, ok_c = plane_per_cell(Pt, invc, Mc, a.minpts)
    dot = (n_r * n_c).sum(1).abs().clamp(0, 1)        # normals are sign-free
    ang = torch.rad2deg(torch.acos(dot))
    row = {}
    for tag, m in (("centre", centre_cell), ("periphery", ~centre_cell)):
        s = ok_r & ok_c & m
        if s.sum() < 100:
            continue
        row[tag] = {
            "bend_deg_p50": float(ang[s].median()),
            "bend_deg_p95": float(torch.quantile(ang[s].float(), 0.95)),
            "frac_bend_over_5deg": float((ang[s] > 5).double().mean()),
            "spread_mm_p50": float(rms_c[s].median() * 1000),
            "spread_delta_mm_p50": float((rms_c[s] - rms_r[s]).median() * 1000),
        }
    report[name] = row
    pe, ce = row.get("periphery", {}), row.get("centre", {})
    print("%-14s periphery BEND p50 %5.2f deg  p95 %6.2f  >5deg %.3f   spread %5.1fmm (%+.1f)  |  centre BEND p50 %5.2f deg  spread %5.1fmm (%+.1f)" % (
        name, pe.get("bend_deg_p50", 0), pe.get("bend_deg_p95", 0), pe.get("frac_bend_over_5deg", 0),
        pe.get("spread_mm_p50", 0), pe.get("spread_delta_mm_p50", 0),
        ce.get("bend_deg_p50", 0), ce.get("spread_mm_p50", 0), ce.get("spread_delta_mm_p50", 0)), flush=True)
    del Pt, mu_c, n_c, rms_c, ok_c, dot, ang
    torch.cuda.empty_cache()
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
