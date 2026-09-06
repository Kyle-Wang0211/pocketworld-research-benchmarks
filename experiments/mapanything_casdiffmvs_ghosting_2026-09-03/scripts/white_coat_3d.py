#!/usr/bin/env python3
"""Find the sticking in 3D, without any per-view hypothesis.

Every per-view test so far has come back empty or irrelevant: the intermediate
bridges (0.3%) changed nothing visible, and CasDiffMVS agrees with MapAnything
to within 2% wherever both have a depth. Yet the eye sees white wall glued to
the luggage. So look for it where the eye sees it: in 3D, bright (wall-coloured)
points lying within a few centimetres of dark (luggage-coloured) points.

If those bright points are the wall, they sit on one plane and the luggage
merely touches it. If they are a "coat" -- wall colour wrapped onto the object
by the cost-volume regulariser -- they follow the object's shape instead and
PCA of their positions will not be planar. Either way they are written out as a
small cloud so they can be looked at on their own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--ply", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--dark", type=int, default=70, help="gray below this = object-coloured")
ap.add_argument("--bright", type=int, default=150, help="gray above this = wall-coloured")
ap.add_argument("--near", type=float, default=0.03, help="metres; bright point counts as touching if a dark point is this close")
ap.add_argument("--out_dir", default="/root/white_coat_20260906")
a = ap.parse_args()
dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
pcd = o3d.io.read_point_cloud(a.ply)
P = torch.from_numpy(np.asarray(pcd.points)).to(dev).float()
C = np.asarray(pcd.colors)
gray = torch.from_numpy((0.299 * C[:, 0] + 0.587 * C[:, 1] + 0.114 * C[:, 2]) * 255).to(dev).float()
dark = gray < a.dark; bright = gray > a.bright
print(f"{P.shape[0]:,} points  dark {int(dark.sum()):,}  bright {int(bright.sum()):,}", flush=True)

# voxel hash on dark points, then for each bright point test the 27 cells around it
h = a.near
o0 = P.min(0).values - 3 * h
D = P[dark]
vi = torch.floor((D - o0) / h).long(); dm = vi.max(0).values + 4
st = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
key = (vi * st).sum(1); order = torch.argsort(key); key_s, D_s = key[order], D[order]
B = P[bright]; bi = torch.nonzero(bright, as_tuple=True)[0]
vb = torch.floor((B - o0) / h).long()
best = torch.full((B.shape[0],), float("inf"), device=dev)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = ((vb + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * st).sum(1)
            lo = torch.searchsorted(key_s, t); hi = torch.searchsorted(key_s, t, right=True)
            cnt = (hi - lo).clamp(max=6)
            for kk in range(int(cnt.max()) if cnt.numel() else 0):
                m = kk < cnt
                if not m.any(): continue
                idx = (lo[m] + kk).clamp(max=D_s.shape[0] - 1)
                dd = (D_s[idx] - B[m]).norm(dim=1)
                best[m] = torch.minimum(best[m], dd)
coat = best < a.near
Cidx = bi[coat]
print(f"bright points within {h*100:.0f} cm of a dark point: {int(coat.sum()):,}  ({100*float(coat.float().mean()):.2f}% of bright)", flush=True)

# planarity of the coat: PCA eigenvalue ratio, plus the same for a random equal-size
# sample of ALL bright points as the reference (walls are planar; a coat is not)
def planarity(X):
    X = X - X.mean(0)
    cov = X.T @ X / X.shape[0]
    ev = torch.linalg.eigvalsh(cov.double())
    return float(ev[0] / ev[2]), float(ev[0].sqrt() * 1000)
pc_coat, thick_coat = planarity(P[Cidx])
ref = bi[torch.randperm(bi.numel(), device=dev)[:Cidx.numel()]]
pc_ref, thick_ref = planarity(P[ref])
res = {"points": int(P.shape[0]), "dark": int(dark.sum()), "bright": int(bright.sum()),
       "coat_points": int(coat.sum()), "coat_frac_of_bright": float(coat.float().mean()),
       "coat_frac_of_cloud": int(coat.sum()) / P.shape[0],
       "coat_pca_min_over_max": pc_coat, "coat_thickness_mm": thick_coat,
       "random_bright_pca_min_over_max": pc_ref, "random_bright_thickness_mm": thick_ref,
       "params": vars(a)}
sub = o3d.geometry.PointCloud()
sub.points = o3d.utility.Vector3dVector(P[Cidx].double().cpu().numpy())
sub.colors = o3d.utility.Vector3dVector(C[Cidx.cpu().numpy()])
o3d.io.write_point_cloud(str(out / "white_coat.ply"), sub, write_ascii=False, compressed=False)
np.save(out / "coat_index.npy", Cidx.cpu().numpy())
print(json.dumps({k: v for k, v in res.items() if k != "params"}, indent=2))
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n")
