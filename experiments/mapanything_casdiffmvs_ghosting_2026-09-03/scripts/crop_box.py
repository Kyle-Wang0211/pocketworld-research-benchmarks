#!/usr/bin/env python3
"""Spatial crop around the luggage, for comparing clouds too large to view whole.

The 1536 x 1152 CasDiffMVS cloud has 119M points; the viewer cannot hold it
beside anything else and the tunnel would take an hour. The question it has to
answer -- do slippers and wheels gain volume at 4x the pixels -- lives in a few
cubic metres around the luggage. So: find the luggage as the densest connected
cluster of dark points in the reference cloud, pad its bounding box, and keep
every point of every cloud inside that box. Nothing inside the box is thinned.

  box   : write the box from a reference cloud
  crop  : apply the box to a cloud and write the cropped ply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["box", "crop"])
ap.add_argument("--ply", required=True)
ap.add_argument("--box", required=True, help="json path (written by box, read by crop)")
ap.add_argument("--out", default=None)
ap.add_argument("--dark", type=int, default=70)
ap.add_argument("--voxel", type=float, default=0.10)
ap.add_argument("--pad", type=float, default=0.8)
a = ap.parse_args()
dev = "cuda"
pcd = o3d.io.read_point_cloud(a.ply)
P = np.asarray(pcd.points); C = np.asarray(pcd.colors)
if a.mode == "box":
    gray = (0.299 * C[:, 0] + 0.587 * C[:, 1] + 0.114 * C[:, 2]) * 255
    D = torch.from_numpy(P[gray < a.dark]).to(dev).float()
    h = a.voxel; o0 = D.min(0).values - h
    vi = torch.floor((D - o0) / h).long(); dm = (vi.max(0).values + 2).tolist()
    grid = torch.zeros(dm, dtype=torch.int32, device=dev)
    lin = vi[:, 0] * dm[1] * dm[2] + vi[:, 1] * dm[2] + vi[:, 2]
    grid.view(-1).scatter_add_(0, lin, torch.ones_like(lin, dtype=torch.int32))
    occ = (grid >= 20).cpu().numpy()                       # dense dark voxels only
    seed = np.unravel_index(int(grid.argmax()), tuple(dm))
    # flood fill 26-connected from the densest dark voxel
    from collections import deque
    comp = np.zeros_like(occ); q = deque([seed]); comp[seed] = True
    while q:
        z = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    n = (z[0] + dx, z[1] + dy, z[2] + dz)
                    if all(0 <= n[i] < dm[i] for i in range(3)) and occ[n] and not comp[n]:
                        comp[n] = True; q.append(n)
    idx = np.argwhere(comp)
    lo = o0.cpu().numpy() + idx.min(0) * h - a.pad; hi = o0.cpu().numpy() + (idx.max(0) + 1) * h + a.pad
    inside = int(((P >= lo) & (P <= hi)).all(1).sum())
    box = {"lo": lo.tolist(), "hi": hi.tolist(), "size_m": (hi - lo).tolist(), "cluster_voxels": int(comp.sum()),
           "reference": a.ply, "points_inside_reference": inside, "frac_of_reference": inside / P.shape[0]}
    Path(a.box).write_text(json.dumps(box, indent=2) + "\n"); print(json.dumps(box, indent=2))
else:
    b = json.load(open(a.box)); lo = np.array(b["lo"]); hi = np.array(b["hi"])
    k = ((P >= lo) & (P <= hi)).all(1)
    q = o3d.geometry.PointCloud(); q.points = o3d.utility.Vector3dVector(P[k])
    if C.shape[0]: q.colors = o3d.utility.Vector3dVector(C[k])
    o3d.io.write_point_cloud(a.out, q, write_ascii=False, compressed=False)
    print(f"{Path(a.ply).name}: {P.shape[0]:,} -> {int(k.sum()):,} inside the box ({100*k.mean():.1f}%)")
