#!/usr/bin/env python3
"""Is the residual tail real, or is it a coverage artefact?

CasDiffMVS and COLMAP only keep the well-observed centre of the room; our clouds
cover the whole room including corners, edges and object silhouettes, where a
20 cm neighbourhood legitimately holds two surfaces. Comparing tails across
clouds with different coverage repeats the bias that already caught me once
(radius normalised by each cloud's own diagonal).

So: restrict EVERY cloud to the region CasDiffMVS actually covers -- a point is
kept only if a CasDiffMVS point sits within `keep` metres of it -- and only then
compare the tails. Occupancy is tested on a voxel grid, so this is O(N)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--ref", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--keep", type=float, default=0.05)
ap.add_argument("--out_dir", default="/root/eqcov")
ap.add_argument("--invert", action="store_true", help="keep the points OUTSIDE the reference coverage instead")
a = ap.parse_args()
dev = "cuda"
out = Path(a.out_dir)
out.mkdir(parents=True, exist_ok=True)

R = np.asarray(o3d.io.read_point_cloud(a.ref).points)
Rt = torch.from_numpy(R).to(dev)
h = a.keep
origin = Rt.min(0).values - 3 * h
vi = torch.floor((Rt - origin) / h).long()
dims = vi.max(0).values + 4
strides = torch.tensor([int(dims[1]) * int(dims[2]), int(dims[2]), 1], device=dev, dtype=torch.long)
occ = torch.unique((vi * strides).sum(1))
print(f"reference {R.shape[0]} points -> {occ.numel()} occupied {h*100:.0f} cm cells", flush=True)

report = {}
for spec in a.sets:
    name, path = spec.split("=", 1)
    p = o3d.io.read_point_cloud(path)
    P = np.asarray(p.points)
    C = np.asarray(p.colors)
    Pt = torch.from_numpy(P).to(dev)
    v = torch.floor((Pt - origin) / h).long()
    keep = torch.zeros(P.shape[0], dtype=torch.bool, device=dev)
    # a point is inside if any of the 27 cells around it is occupied in the reference
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for oz in (-1, 0, 1):
                t = ((v + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * strides).sum(1)
                pos = torch.searchsorted(occ, t).clamp(max=occ.numel() - 1)
                keep |= occ[pos] == t
    if a.invert:
        keep = ~keep
    k = keep.cpu().numpy()
    q = o3d.geometry.PointCloud()
    q.points = o3d.utility.Vector3dVector(P[k])
    if C.shape[0]:
        q.colors = o3d.utility.Vector3dVector(C[k])
    dst = out / (f"{name}_outcov.ply" if a.invert else f"{name}_incov.ply")
    o3d.io.write_point_cloud(str(dst), q, write_ascii=False, compressed=False)
    report[name] = {"total": int(P.shape[0]), "inside": int(k.sum()), "frac_inside": float(k.mean()), "path": str(dst)}
    print("%-14s %10d -> %10d inside (%.3f)" % (name, P.shape[0], k.sum(), k.mean()), flush=True)
    del Pt, v, keep
    torch.cuda.empty_cache()
Path(out / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
