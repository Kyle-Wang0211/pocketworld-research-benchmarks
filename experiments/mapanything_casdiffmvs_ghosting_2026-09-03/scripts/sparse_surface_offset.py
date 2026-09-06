#!/usr/bin/env python3
"""Where is the surface, and how thick is it, judged against evidence the network
never produced.

The nearest-point version of this check is biased and cannot be used to rank:
a thicker cloud scatters more samples near any given reference point, so the
nearest one lands closer. It duly ranked the thickest cloud best.

Distance to the local SURFACE has no such bias. For each COLMAP sparse point,
fit a plane to the cloud points around it and report two separate numbers:

  offset  how far the sparse point sits from that plane -- is the surface in the
          right place
  spread  the RMS of the cloud points about the plane -- how thick it is

Thickening a cloud raises the spread and leaves the offset alone, which is the
positive control run here: the same cloud is measured again with 20 mm of
Gaussian noise added along a random direction. If that control moves the offset,
the ruler is not measuring what it claims and nothing else in the table counts.

COLMAP's sparse points come from feature matches across the same 132 images and
owe nothing to MapAnything, so they can arbitrate a deformation that every view
agrees on -- the one thing cross-view agreement is blind to.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/root")
from mapanything.utils.colmap import read_model  # noqa: E402

def smallest_eigpair_sym3(A):
    """cuSOLVER's batched syevd refuses large 3x3 batches on this build, so the
    smallest eigenpair is computed in closed form instead."""
    a00, a01, a02 = A[:, 0, 0], A[:, 0, 1], A[:, 0, 2]
    a11, a12, a22 = A[:, 1, 1], A[:, 1, 2], A[:, 2, 2]
    p1 = a01 ** 2 + a02 ** 2 + a12 ** 2
    q = (a00 + a11 + a22) / 3.0
    p2 = (a00 - q) ** 2 + (a11 - q) ** 2 + (a22 - q) ** 2 + 2.0 * p1
    pp = torch.sqrt((p2 / 6.0).clamp_min(1e-300))
    iv = 1.0 / pp
    b00, b11, b22 = (a00 - q) * iv, (a11 - q) * iv, (a22 - q) * iv
    b01, b02, b12 = a01 * iv, a02 * iv, a12 * iv
    detB = (b00 * (b11 * b22 - b12 * b12) - b01 * (b01 * b22 - b12 * b02) + b02 * (b01 * b12 - b11 * b02))
    r = (detB / 2.0).clamp(-1.0, 1.0)
    phi = torch.acos(r) / 3.0
    e1 = q + 2.0 * pp * torch.cos(phi)
    e3 = q + 2.0 * pp * torch.cos(phi + 2.0 * np.pi / 3.0)
    e2 = 3.0 * q - e1 - e3
    I = torch.eye(3, device=A.device, dtype=A.dtype)[None]
    M = (A - e1[:, None, None] * I) @ (A - e2[:, None, None] * I)
    pick = M.norm(dim=1).argmax(dim=1)
    v = M[torch.arange(M.shape[0], device=A.device), :, pick]
    v = v / v.norm(dim=1, keepdim=True).clamp_min(1e-300)
    return e3.clamp_min(0), v, torch.isfinite(v).all(1) & (pp > 0)


ap = argparse.ArgumentParser()
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--radius", type=float, default=0.05)
ap.add_argument("--min_pts", type=int, default=20)
ap.add_argument("--min_track", type=int, default=4, help="only sparse points seen in this many images")
ap.add_argument("--noise_control", default=None, help="name=path; measured again with noise added")
ap.add_argument("--noise_mm", type=float, default=20.0)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"

cams, imgs, p3d = read_model(a.colmap_sparse, ext=".bin")
X = np.stack([p.xyz for p in p3d.values()])
ntr = np.array([len(p.image_ids) for p in p3d.values()])
err = np.array([p.error for p in p3d.values()])
sel = (ntr >= a.min_track)
X = X[sel]
print(f"{X.shape[0]} sparse points with >= {a.min_track} observations "
      f"(of {sel.size}); reprojection error p50 {np.median(err[sel]):.3f} px", flush=True)
S = torch.from_numpy(X).to(dev).double()
NS = S.shape[0]


def measure(P):
    """local plane around every sparse point: offset of the point, spread of the cloud"""
    h = a.radius
    o0 = P.min(0).values - 3 * h
    vi = torch.floor((P - o0) / h).long()
    dm = vi.max(0).values + 4
    st = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
    lin = (vi * st).sum(1)
    order = torch.argsort(lin)
    lin_s, P_s = lin[order], P[order]
    vs = torch.floor((S - o0) / h).long()
    n = torch.zeros(NS, device=dev, dtype=torch.float64)
    s1 = torch.zeros(NS, 3, device=dev, dtype=torch.float64)
    s2 = torch.zeros(NS, 6, device=dev, dtype=torch.float64)
    pairs = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for oz in (-1, 0, 1):
                t = ((vs + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * st).sum(1)
                lo = torch.searchsorted(lin_s, t)
                hi = torch.searchsorted(lin_s, t, right=True)
                cnt = (hi - lo).clamp(max=64)
                mx = int(cnt.max()) if cnt.numel() else 0
                for k in range(mx):
                    m = k < cnt
                    if not m.any():
                        continue
                    idx = (lo[m] + k).clamp(max=P_s.shape[0] - 1)
                    q = P_s[idx]
                    d = (q - S[m]).norm(dim=1)
                    inr = d < a.radius
                    if not inr.any():
                        continue
                    who = torch.nonzero(m, as_tuple=True)[0][inr]
                    qq = q[inr]
                    n.scatter_add_(0, who, torch.ones(who.numel(), device=dev, dtype=torch.float64))
                    for c in range(3):
                        s1[:, c].scatter_add_(0, who, qq[:, c])
                    for p_, (x_, y_) in enumerate(pairs):
                        s2[:, p_].scatter_add_(0, who, qq[:, x_] * qq[:, y_])
    mu = s1 / n[:, None].clamp_min(1)
    m2 = s2 / n[:, None].clamp_min(1)
    cov = torch.zeros(NS, 3, 3, device=dev, dtype=torch.float64)
    for p_, (x_, y_) in enumerate(pairs):
        cov[:, x_, y_] = m2[:, p_] - mu[:, x_] * mu[:, y_]
        cov[:, y_, x_] = cov[:, x_, y_]
    cov = torch.where(torch.isfinite(cov), cov, torch.zeros_like(cov))
    lam3, nrm, okv = smallest_eigpair_sym3(cov)
    spread = lam3.sqrt()
    offset = ((S - mu) * nrm).sum(1).abs()
    ok = (n >= a.min_pts) & okv
    return offset, spread, ok, n


report = {}
for spec in a.sets:
    name, path = spec.split("=", 1)
    P = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(path).points)).to(dev).double()
    off, spr, ok, n = measure(P)
    r = {"sparse_points_with_surface": int(ok.sum()), "frac": float(ok.double().mean()),
         "offset_mm_p50": float(off[ok].median() * 1000),
         "offset_mm_p90": float(torch.quantile(off[ok].float(), 0.90) * 1000),
         "spread_mm_p50": float(spr[ok].median() * 1000),
         "neighbours_p50": float(n[ok].median())}
    report[name] = r
    print("%-16s  surface found %.3f   OFFSET p50 %6.2f mm  p90 %7.2f mm    SPREAD p50 %6.2f mm   (%.0f neighbours)"
          % (name, r["frac"], r["offset_mm_p50"], r["offset_mm_p90"], r["spread_mm_p50"], r["neighbours_p50"]), flush=True)
    del P
    torch.cuda.empty_cache()

if a.noise_control:
    name, path = a.noise_control.split("=", 1)
    P = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(path).points)).to(dev).double()
    g = torch.Generator(device=dev).manual_seed(20260904)
    P = P + torch.randn(P.shape, device=dev, dtype=torch.float64, generator=g) * (a.noise_mm / 1000.0)
    off, spr, ok, n = measure(P)
    r = {"offset_mm_p50": float(off[ok].median() * 1000), "spread_mm_p50": float(spr[ok].median() * 1000),
         "frac": float(ok.double().mean())}
    report[f"CONTROL {name} + {a.noise_mm:.0f}mm noise"] = r
    base = report[name]
    print("\nCONTROL  %s with %.0f mm of noise added:" % (name, a.noise_mm))
    print("  offset %6.2f -> %6.2f mm   (must barely move)" % (base["offset_mm_p50"], r["offset_mm_p50"]))
    print("  spread %6.2f -> %6.2f mm   (must rise)" % (base["spread_mm_p50"], r["spread_mm_p50"]))
    ok_ctrl = abs(r["offset_mm_p50"] - base["offset_mm_p50"]) < 0.25 * base["offset_mm_p50"] and r["spread_mm_p50"] > base["spread_mm_p50"] * 1.5
    print("  ruler separates position from thickness: %s" % ("YES" if ok_ctrl else "NO -- do not rank with it"))
    report["control_passed"] = bool(ok_ctrl)
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
