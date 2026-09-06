#!/usr/bin/env python3
"""Split a wall's residual into WAVINESS (bend) and THICKNESS (spread).

Two earlier attempts failed for the same reason: they used a 10 cm neighbourhood,
which is smaller than the artefact being measured.

  attempt 1  bend = spatial std of the displacement in a 10 cm cell. Dominated by
             the fact that any depth-dependent correction moves far points more
             than near ones. Every candidate scored 32-47 mm; no discrimination.
  attempt 2  bend = angle between local plane normals. In a cell holding 19 mm of
             thickness the covariance is near isotropic, so the smallest
             eigenvector is noise and the angle between two noises has a ~40 deg
             median. Also degenerate for MLS, which projects onto exactly the
             plane being compared against, giving a trivial 0.00 deg.

"The far wall is twisted" is a metre-scale phenomenon. So work at that scale:
take a large planar region, subtract each candidate's OWN best-fit plane (so no
candidate is measured against another's geometry), and split what remains by
spatial frequency in the plane:

  WAVINESS  the mean residual per 30 cm in-plane cell -- a wall that bows or
            ripples has a large spread of cell means. This is "bent".
  THICKNESS the residual around that cell mean -- 132 views disagreeing about
            the same patch. This is "ghosted".

Planes are found on the reference cloud (a region selection only, and every
candidate moves points by ~5 cm so the selection stays valid), then every
candidate is fitted and decomposed independently.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch


def fit_plane(P, iters=5, c=0.03):
    """IRLS plane fit (Tukey) so a minority layer cannot tilt the plane."""
    w = torch.ones(P.shape[0], device=P.device, dtype=torch.float64)
    n = None
    mu = None
    for _ in range(iters):
        sw = w.sum().clamp_min(1e-9)
        mu = (P * w[:, None]).sum(0) / sw
        X = (P - mu) * w[:, None].sqrt()
        cov = X.T @ X / sw
        ev, evec = torch.linalg.eigh(cov)
        n = evec[:, 0]
        r = (P - mu) @ n
        u = (r.abs() / c).clamp(max=1.0)
        w = (1.0 - u ** 2) ** 2
    return mu, n


ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True, help="name=path; used only to find the planar regions")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--n_planes", type=int, default=6)
ap.add_argument("--ransac_thresh", type=float, default=0.03)
ap.add_argument("--band", type=float, default=0.06, help="metres; points this far from the plane belong to it")
ap.add_argument("--cell", type=float, default=0.30, help="in-plane cell for the low/high frequency split")
ap.add_argument("--min_cell_pts", type=int, default=200)
ap.add_argument("--min_plane_pts", type=int, default=200000)
ap.add_argument("--cams", default="/root/cam_centers.npy", help="optional camera centres, to split near from far")
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"

rname, rpath = a.ref.split("=", 1)
pcd = o3d.io.read_point_cloud(rpath)
R = np.asarray(pcd.points)
N = R.shape[0]
Rt = torch.from_numpy(R).to(dev)
print(f"reference {rname}: {N} points", flush=True)

# find the big planes on a decimated copy, then take the full-resolution band
step = max(1, N // 3_000_000)
sub = o3d.geometry.PointCloud()
sub.points = o3d.utility.Vector3dVector(R[::step])
planes = []
work = sub
for i in range(a.n_planes):
    if len(work.points) < 50000:
        break
    model, inl = work.segment_plane(a.ransac_thresh, 3, 400)
    if len(inl) < 20000:
        break
    planes.append(np.asarray(model, dtype=np.float64))
    work = work.select_by_index(inl, invert=True)
print(f"{len(planes)} candidate planes", flush=True)

cam = None
if Path(a.cams).exists():
    cam = torch.from_numpy(np.load(a.cams)).to(dev).double()
    print(f"camera centres {tuple(cam.shape)}", flush=True)

regions = []
for i, m in enumerate(planes):
    nv = torch.from_numpy(m[:3]).to(dev)
    d = float(m[3])
    dist = (Rt @ nv + d).abs()
    idx = torch.nonzero(dist < a.band, as_tuple=True)[0]
    if idx.numel() < a.min_plane_pts:
        continue
    ext = Rt[idx]
    span = (ext.max(0).values - ext.min(0).values)
    far = None
    if cam is not None:
        cen = ext.mean(0)
        far = float(torch.cdist(cen[None], cam).min())
    regions.append({"i": i, "idx": idx, "pts": int(idx.numel()),
                    "span_m": [float(x) for x in span], "dist_to_nearest_cam_m": far})
    print(f"  plane {i}: {idx.numel()} points  span {span[0]:.1f}x{span[1]:.1f}x{span[2]:.1f} m"
          + (f"  nearest camera {far:.2f} m" if far is not None else ""), flush=True)

report = {"planes": [{k: v for k, v in r.items() if k != "idx"} for r in regions], "results": {}}
for spec in a.sets:
    name, path = spec.split("=", 1)
    P = np.asarray(o3d.io.read_point_cloud(path).points)
    if P.shape[0] != N:
        print(f"{name}: SKIP ({P.shape[0]} != {N})", flush=True)
        continue
    Pt = torch.from_numpy(P).to(dev)
    rows = []
    for r in regions:
        Q = Pt[r["idx"]]
        mu, nv = fit_plane(Q)
        res = (Q - mu) @ nv                       # signed distance to this candidate's own plane
        # in-plane coordinates
        tmp = torch.tensor([0.0, 0.0, 1.0], device=dev, dtype=torch.float64)
        if abs(float(nv @ tmp)) > 0.9:
            tmp = torch.tensor([1.0, 0.0, 0.0], device=dev, dtype=torch.float64)
        e1 = torch.cross(nv, tmp, dim=0); e1 = e1 / e1.norm()
        e2 = torch.cross(nv, e1, dim=0)
        uv = torch.stack([(Q - mu) @ e1, (Q - mu) @ e2], 1)
        g = torch.floor((uv - uv.min(0).values) / a.cell).long()
        key = g[:, 0] * (int(g[:, 1].max()) + 2) + g[:, 1]
        uq, inv = torch.unique(key, return_inverse=True)
        M = uq.numel()
        cnt = torch.zeros(M, device=dev, dtype=torch.float64)
        cnt.scatter_add_(0, inv, torch.ones_like(res))
        s1 = torch.zeros(M, device=dev, dtype=torch.float64)
        s1.scatter_add_(0, inv, res)
        s2 = torch.zeros(M, device=dev, dtype=torch.float64)
        s2.scatter_add_(0, inv, res ** 2)
        cmean = s1 / cnt.clamp_min(1)
        cvar = (s2 / cnt.clamp_min(1) - cmean ** 2).clamp_min(0)
        ok = cnt >= a.min_cell_pts
        if int(ok.sum()) < 20:
            continue
        cm = cmean[ok]
        wav_std = float(cm.std())                                   # low frequency: is the wall bowed
        wav_pp = float(torch.quantile(cm.float(), 0.95) - torch.quantile(cm.float(), 0.05))
        thick = float(cvar[ok].sqrt().median())                     # high frequency: is the patch thick
        rows.append({"plane": r["i"], "cells": int(ok.sum()),
                     "waviness_std_mm": wav_std * 1000, "waviness_p5p95_mm": wav_pp * 1000,
                     "thickness_mm_p50": thick * 1000,
                     "dist_to_nearest_cam_m": r["dist_to_nearest_cam_m"]})
    if not rows:
        continue
    wav = float(np.mean([x["waviness_p5p95_mm"] for x in rows]))
    thk = float(np.mean([x["thickness_mm_p50"] for x in rows]))
    report["results"][name] = {"per_plane": rows, "mean_waviness_p5p95_mm": wav, "mean_thickness_mm": thk}
    print("%-14s  WAVY %6.1f mm   THICK %5.1f mm   | per plane " % (name, wav, thk)
          + "  ".join("%d:%.0f/%.0f" % (x["plane"], x["waviness_p5p95_mm"], x["thickness_mm_p50"]) for x in rows),
          flush=True)
    del Pt
    torch.cuda.empty_cache()
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
