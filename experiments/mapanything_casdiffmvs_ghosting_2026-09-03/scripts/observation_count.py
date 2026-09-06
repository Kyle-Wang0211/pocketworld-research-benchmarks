#!/usr/bin/env python3
"""How many of the 132 views actually observe each point?

Everything measured today converges on one thing. The disagreement is smooth
(74% survives a 64x64 block average) but not low-order (a quartic per view
explains only 43%), so its structure sits around 64-128 px -- about 0.7 m at
3 m range. Any correction able to remove it must act at that same 0.7 m scale,
which is exactly the scale at which a wrong correction reads as a bent wall.
There is no frequency band separating the fix from the artefact.

What decides whether such a correction is a measurement or a guess is how many
views agree on each surface. A point seen by twenty cameras from spread angles
has an over-determined correction; a point seen by two has none, and every
version built this session had to invent geometry there.

Counted the same way a multi-view method would: a view observes a point if the
point falls in its frustum and its depth matches that view's own depth there, so
occluded points are not counted. Reported separately for the region CasDiffMVS
reconstructs and the region it refuses to.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="/root/mapanything_layer_audit_A_imgs132_up_20260903/")
ap.add_argument("--anchored", default="/root/mapanything_native_anchored_20260903/mapanything_native_anchored.ply")
ap.add_argument("--coverage_ref", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--tol", type=float, default=0.03, help="relative depth tolerance for 'this view sees it'")
ap.add_argument("--chunk", type=int, default=4_000_000)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"
D = Path(a.dir)

pts = torch.from_numpy(np.load(D / "pts3d.npy")).to(dev).reshape(-1, 3)
dz = torch.from_numpy(np.load(D / "depth_z.npy")).to(dev)[..., 0]
K = torch.from_numpy(np.load(D / "intrinsics.npy")).to(dev)
T = torch.from_numpy(np.load(D / "camera_poses.npy")).to(dev)
msk = torch.from_numpy(np.load(D / "mask.npy")).to(dev)[..., 0]
V, H, W = dz.shape
flat = msk.reshape(-1)
keep = torch.nonzero(flat, as_tuple=True)[0]
P = pts[keep]                               # model-frame points, same order as the exported cloud
N = P.shape[0]
print(f"{N} points, {V} views", flush=True)

Rinv = T[:, :3, :3].transpose(1, 2).contiguous()
tinv = -torch.einsum("vij,vj->vi", Rinv, T[:, :3, 3])
Cw = T[:, :3, 3]

nobs = torch.zeros(N, dtype=torch.int16, device=dev)
# angular spread: accumulate the unit viewing directions, so |sum|/n near 1 means
# every camera looks from essentially the same place and the geometry is weakly
# constrained however many views there are
dsum = torch.zeros(N, 3, device=dev)
for s in range(0, N, a.chunk):
    e = min(N, s + a.chunk)
    Q = P[s:e]
    n = torch.zeros(e - s, dtype=torch.int16, device=dev)
    acc = torch.zeros(e - s, 3, device=dev)
    for w in range(V):
        Xc = Q @ Rinv[w].T + tinv[w]
        z = Xc[:, 2]
        uv = Xc @ K[w].T
        u = (uv[:, 0] / uv[:, 2].clamp_min(1e-6)).round().long()
        vv = (uv[:, 1] / uv[:, 2].clamp_min(1e-6)).round().long()
        ok = (z > 1e-3) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
        uu, vc = u.clamp(0, W - 1), vv.clamp(0, H - 1)
        zw = dz[w][vc, uu]
        seen = ok & msk[w][vc, uu] & (((z - zw) / zw.clamp_min(1e-6)).abs() < a.tol)
        n += seen.to(torch.int16)
        d = Cw[w][None] - Q
        d = d / d.norm(dim=1, keepdim=True).clamp_min(1e-9)
        acc += torch.where(seen[:, None], d, torch.zeros_like(d))
    nobs[s:e] = n
    dsum[s:e] = acc
    print(f"  {e}/{N}", flush=True)

A = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.anchored).points)).to(dev)
assert A.shape[0] == N
Cv = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.coverage_ref).points)).to(dev)
h = 0.05
o0 = Cv.min(0).values - 3 * h
vi = torch.floor((Cv - o0) / h).long()
dm = vi.max(0).values + 4
stk = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
occ = torch.unique((vi * stk).sum(1))
vg = torch.floor((A - o0) / h).long()
inside = torch.zeros(N, dtype=torch.bool, device=dev)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = ((vg + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * stk).sum(1)
            pos = torch.searchsorted(occ, t).clamp(max=occ.numel() - 1)
            inside |= occ[pos] == t

nf = nobs.float()
conc = dsum.norm(dim=1) / nf.clamp_min(1)      # 1 = all cameras in one direction
out = {}
print("\n region        points     views/point p10  p50  p90    <=2 views   <=4 views   direction concentration p50")
for tag, m in (("all", torch.ones(N, dtype=torch.bool, device=dev)), ("centre", inside), ("periphery", ~inside)):
    x = nf[m]
    row = {"points": int(m.sum()),
           "views_p10": float(torch.quantile(x[::13], 0.10)), "views_p50": float(x.median()),
           "views_p90": float(torch.quantile(x[::13], 0.90)),
           "frac_le_2": float((x <= 2).double().mean()), "frac_le_4": float((x <= 4).double().mean()),
           "dir_concentration_p50": float(conc[m].median())}
    out[tag] = row
    print("  %-10s %10d      %5.1f %4.1f %5.1f     %7.3f     %7.3f            %.3f" % (
        tag, row["points"], row["views_p10"], row["views_p50"], row["views_p90"],
        row["frac_le_2"], row["frac_le_4"], row["dir_concentration_p50"]))
Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
