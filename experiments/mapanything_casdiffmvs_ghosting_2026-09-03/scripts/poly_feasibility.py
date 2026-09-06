#!/usr/bin/env python3
"""How much of the cross-view disagreement fits a low-order per-view polynomial?

Two measurements narrowed it down. Radial: flat (outer/inner 0.986), so the
disagreement is not the focal artefact. Spatial: 74% of its std survives a 64x64
block average, so it is a smooth field, not pixel noise.

Smooth is not the same as low-order, and the difference decides everything. If a
handful of coefficients per view can represent it, the correction has too few
degrees of freedom to bend a wall locally, and it can be constrained by cross-view
agreement over the WHOLE image -- including the outer 70% where the sparse anchors
do not reach and where every previous field was left to the regulariser to invent.

Per pair (v,w) the observed disagreement is f_v - f_w composed through the
reprojection, so fitting a polynomial to each pair separately is optimistic: it
gives the best case for a per-view polynomial model. If even that leaves most of
the disagreement standing, the parameterisation is dead and there is no point
solving the global system.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="/root/mapanything_layer_audit_A_imgs132_up_20260903/")
ap.add_argument("--neighbours", type=int, default=4)
ap.add_argument("--views", type=int, default=40)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"
D = Path(a.dir)

pts = torch.from_numpy(np.load(D / "pts3d.npy")).to(dev)
dz = torch.from_numpy(np.load(D / "depth_z.npy")).to(dev)[..., 0]
K = torch.from_numpy(np.load(D / "intrinsics.npy")).to(dev)
T = torch.from_numpy(np.load(D / "camera_poses.npy")).to(dev)
msk = torch.from_numpy(np.load(D / "mask.npy")).to(dev)[..., 0]
V, H, W = dz.shape
C = T[:, :3, 3]
dist = torch.cdist(C, C); dist.fill_diagonal_(float("inf"))
nb = dist.topk(a.neighbours, largest=False).indices
Rinv = T[:, :3, :3].transpose(1, 2)
tinv = -torch.einsum("vij,vj->vi", Rinv, T[:, :3, 3])

yy, xx = torch.meshgrid(torch.arange(H, device=dev, dtype=torch.float64),
                        torch.arange(W, device=dev, dtype=torch.float64), indexing="ij")
X = (xx / (W - 1) * 2 - 1).reshape(-1)
Y = (yy / (H - 1) * 2 - 1).reshape(-1)


def basis(deg):
    cols = []
    for i in range(deg + 1):
        for j in range(deg + 1 - i):
            cols.append((X ** i) * (Y ** j))
    return torch.stack(cols, 1)


B = {d: basis(d) for d in (0, 1, 2, 3, 4)}
tot = {d: [0.0, 0] for d in B}
raw = [0.0, 0]
sel = torch.linspace(0, V - 1, min(a.views, V)).long().tolist()

for v in sel:
    P = pts[v].reshape(-1, 3)
    for w in nb[v].tolist():
        Xc = P @ Rinv[w].T + tinv[w]
        z = Xc[:, 2]
        uv = Xc @ K[w].T
        u = (uv[:, 0] / uv[:, 2].clamp_min(1e-6)).round().long()
        vv = (uv[:, 1] / uv[:, 2].clamp_min(1e-6)).round().long()
        ok = msk[v].reshape(-1) & (z > 1e-3) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
        uu, vvv = u.clamp(0, W - 1), vv.clamp(0, H - 1)
        zw = dz[w][vvv, uu]
        rel = ((z - zw) / zw.clamp_min(1e-6)).double()
        good = ok & msk[w][vvv, uu] & (rel.abs() < 0.10)
        n = int(good.sum())
        if n < 20000:
            continue
        r = rel[good]
        raw[0] += float(((r - r.mean()) ** 2).sum()); raw[1] += n
        for d, Bd in B.items():
            A = Bd[good]
            sol = torch.linalg.lstsq(A, r[:, None]).solution
            res = r - (A @ sol)[:, 0]
            tot[d][0] += float((res ** 2).sum()); tot[d][1] += n

s0 = (raw[0] / raw[1]) ** 0.5 * 100
print(f"\nraw disagreement std (mean removed): {s0:.4f} %\n")
out = {"raw_std_pct": s0, "by_degree": {}}
print(" degree  coeffs/view   residual std      variance explained")
for d in sorted(B):
    sd = (tot[d][0] / tot[d][1]) ** 0.5 * 100
    k = B[d].shape[1]
    out["by_degree"][d] = {"coeffs": int(k), "residual_std_pct": sd, "explained": 1 - (sd / s0) ** 2}
    print("   %d        %2d        %8.4f %%          %6.1f %%" % (d, k, sd, 100 * (1 - (sd / s0) ** 2)))
Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
