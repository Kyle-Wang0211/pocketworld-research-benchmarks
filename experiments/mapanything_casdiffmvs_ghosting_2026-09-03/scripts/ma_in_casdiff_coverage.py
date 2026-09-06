#!/usr/bin/env python3
"""MapAnything's points, admitted only where CasDiffMVS has verified coverage.

Two things were measured earlier in this campaign and both point here. Inside
the region CasDiffMVS reconstructs, MapAnything's anchored cloud is at least as
good as CasDiffMVS on every ruler tried (median 1.3 vs 5.5 mm, >5 cm tail equal);
all of MapAnything's ghosting lives in the 70% CasDiffMVS refuses. And the
sticking the user sees is CasDiffMVS geometry -- the same wall in MapAnything is
either masked out by its own edge mask or simply planar.

So CasDiffMVS defines the admissible region and MapAnything supplies the points.
The one design choice is how to treat CasDiffMVS's own holes: its geometric gate
drops floor and wall patches at grazing angles and in shadow, and those holes
would be inherited verbatim by a plain occupancy test. A morphological closing
(dilate by R, erode by R) fills every hole narrower than 2R while leaving the
outer boundary -- the line between "verified" and "textureless wall" -- where it
was. R is the only knob, and it is reported with the result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
import torch.nn.functional as F


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--coverage", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--sets", nargs="+", required=True, help="name=path of MapAnything clouds to admit")
ap.add_argument("--voxel", type=float, default=0.05)
ap.add_argument("--close_r", type=float, default=0.15, help="metres; holes narrower than 2R are filled")
ap.add_argument("--tol_cells", type=int, default=1, help="final dilation so the surface's own thickness is admitted")
ap.add_argument("--out_dir", required=True)
a = ap.parse_args()
dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

C = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.coverage).points)).to(dev).float()
h = a.voxel
pad = int(round(a.close_r / h)) + a.tol_cells + 2
o0 = C.min(0).values - pad * h
dims = (torch.floor((C.max(0).values - o0) / h).long() + pad + 1)
grid = torch.zeros(tuple(int(x) for x in dims), dtype=torch.bool, device=dev)
vi = torch.floor((C - o0) / h).long()
grid[vi[:, 0], vi[:, 1], vi[:, 2]] = True
occ0 = int(grid.sum())
print(f"coverage cloud {C.shape[0]:,} pts -> grid {tuple(grid.shape)} = {grid.numel():,} cells, occupied {occ0:,}", flush=True)


def ball(rc):
    r = torch.arange(-rc, rc + 1, device=dev).float()
    zz, yy, xx = torch.meshgrid(r, r, r, indexing="ij")
    return ((xx ** 2 + yy ** 2 + zz ** 2) <= rc * rc + 0.5).float()[None, None]


def dilate(g, rc):
    k = ball(rc)
    return (F.conv3d(g.float()[None, None], k, padding=rc)[0, 0] > 0.5)


def erode(g, rc):
    return ~dilate(~g, rc)


rc = int(round(a.close_r / h))
closed = erode(dilate(grid, rc), rc)            # fill holes narrower than 2R, keep the outer boundary
admit = dilate(closed, a.tol_cells)             # admit the surface's own thickness
print(f"closing radius {rc} cells ({rc*h*100:.0f} cm): occupied {occ0:,} -> closed {int(closed.sum()):,} -> admitted {int(admit.sum()):,}", flush=True)

report = {"coverage": a.coverage, "voxel_m": h, "close_r_m": a.close_r, "close_r_cells": rc, "tol_cells": a.tol_cells,
          "cells_occupied": occ0, "cells_closed": int(closed.sum()), "cells_admitted": int(admit.sum()), "sets": {}}
for spec in a.sets:
    name, path = spec.split("=", 1)
    pcd = o3d.io.read_point_cloud(path)
    P = torch.from_numpy(np.asarray(pcd.points)).to(dev).float()
    col = np.asarray(pcd.colors)
    v = torch.floor((P - o0) / h).long()
    inb = ((v >= 0) & (v < torch.tensor(admit.shape, device=dev))).all(1)
    keep = torch.zeros(P.shape[0], dtype=torch.bool, device=dev)
    vv = v[inb]
    keep[inb] = admit[vv[:, 0], vv[:, 1], vv[:, 2]]
    k = keep.cpu().numpy()
    q = o3d.geometry.PointCloud()
    q.points = o3d.utility.Vector3dVector(np.asarray(pcd.points)[k])
    if col.shape[0]: q.colors = o3d.utility.Vector3dVector(col[k])
    dst = out / f"{name}_in_casdiff_cov_R{int(a.close_r*100)}.ply"
    o3d.io.write_point_cloud(str(dst), q, write_ascii=False, compressed=False)
    np.save(out / f"{name}_keep_R{int(a.close_r*100)}.npy", k)
    report["sets"][name] = {"source": path, "total": int(P.shape[0]), "kept": int(k.sum()), "frac": float(k.mean()),
                            "ply": {"path": str(dst), "bytes": dst.stat().st_size, "sha256": sha256_file(dst)}}
    print(f"  {name:12s} {P.shape[0]:>11,} -> {int(k.sum()):>11,} admitted ({100*k.mean():.1f}%)", flush=True)
    del P, v, keep; torch.cuda.empty_cache()
(out / f"result_R{int(a.close_r*100)}.json").write_text(json.dumps(report, indent=2) + "\n")
