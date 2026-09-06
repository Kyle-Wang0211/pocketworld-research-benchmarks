#!/usr/bin/env python3
"""At what spatial scale does MapAnything's cross-view disagreement live?

The radial test came back flat (outer/inner 0.986), so the disagreement is not a
focal artefact and has no low-order per-view structure to remove. The remaining
question decides what -- if anything -- can fix it without deforming the cloud:

  smooth over tens of pixels  a per-view smooth field can cancel it, and the
                              field solves should have worked
  white at the pixel scale    no field can cancel it; only fitting a surface to
                              the points can, and that is a local operation which
                              cannot bend a wall

Measured by block averaging: build the relative-depth-disagreement image between
a view and a neighbour, then take the variance of its block means at increasing
block sizes. For white noise that variance falls as 1/area; for a field smooth at
scale L it stays flat until the block exceeds L. The half-decay point is the
correlation length in pixels.

Split by whether the pixel's 3D point lies in the region CasDiffMVS reconstructs,
because that is exactly the split between the part of the room that looks right
and the 70% that does not.
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
ap.add_argument("--coverage_ref", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10/pc.ply")
ap.add_argument("--anchored", default="/root/mapanything_native_anchored_20260903/mapanything_native_anchored.ply",
                help="used only to map the model frame onto the metric frame for the coverage test")
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

# coverage grid, in the anchored (metric) frame; the anchored cloud is this same
# per-view pixel grid re-projected, so pixel n of view v is point v*H*W + n
A = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.anchored).points)).to(dev)
assert A.shape[0] == V * H * W, f"{A.shape[0]} != {V*H*W}"
Cv = torch.from_numpy(np.asarray(o3d.io.read_point_cloud(a.coverage_ref).points)).to(dev)
h = 0.05
o0 = Cv.min(0).values - 3 * h
vi = torch.floor((Cv - o0) / h).long()
dm = vi.max(0).values + 4
stk = torch.tensor([int(dm[1]) * int(dm[2]), int(dm[2]), 1], device=dev, dtype=torch.long)
occ = torch.unique((vi * stk).sum(1))
vg = torch.floor((A - o0) / h).long()
inside = torch.zeros(A.shape[0], dtype=torch.bool, device=dev)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = ((vg + torch.tensor([ox, oy, oz], device=dev)).clamp_min(0) * stk).sum(1)
            pos = torch.searchsorted(occ, t).clamp(max=occ.numel() - 1)
            inside |= occ[pos] == t
inside = inside.view(V, H, W)
print(f"{V} views {H}x{W}; inside coverage {float(inside.double().mean()):.3f}", flush=True)
del A, Cv, vg
torch.cuda.empty_cache()

C = T[:, :3, 3]
dist = torch.cdist(C, C)
dist.fill_diagonal_(float("inf"))
nb = dist.topk(a.neighbours, largest=False).indices
Rinv = T[:, :3, :3].transpose(1, 2)
tinv = -torch.einsum("vij,vj->vi", Rinv, T[:, :3, 3])
BLOCKS = [1, 2, 4, 8, 16, 32, 64]
sel = torch.linspace(0, V - 1, min(a.views, V)).long().tolist()

res = {}
for tag in ("all", "centre", "periphery"):
    res[tag] = {b: [0.0, 0.0, 0.0] for b in BLOCKS}   # sum, sumsq, n over block means

for v in sel:
    P = pts[v].reshape(-1, 3)
    for w in nb[v].tolist():
        Xc = P @ Rinv[w].T + tinv[w]
        z = Xc[:, 2]
        uv = Xc @ K[w].T
        u = (uv[:, 0] / uv[:, 2].clamp_min(1e-6)).round().long()
        vv = (uv[:, 1] / uv[:, 2].clamp_min(1e-6)).round().long()
        ok = msk[v].reshape(-1) & (z > 1e-3) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
        img = torch.full((H * W,), float("nan"), device=dev)
        uu, vvv, zz = u.clamp(0, W - 1), vv.clamp(0, H - 1), z
        zw = dz[w][vvv, uu]
        mw = msk[w][vvv, uu]
        rel = (zz - zw) / zw.clamp_min(1e-6)
        good = ok & mw & (rel.abs() < 0.10)
        img[good] = rel[good]
        img = img.view(H, W)
        for tag in ("all", "centre", "periphery"):
            if tag == "all":
                m = torch.isfinite(img)
            elif tag == "centre":
                m = torch.isfinite(img) & inside[v]
            else:
                m = torch.isfinite(img) & (~inside[v])
            X = torch.where(m, img, torch.zeros_like(img))
            Mf = m.double()
            for b in BLOCKS:
                hh, ww = (H // b) * b, (W // b) * b
                s = X[:hh, :ww].reshape(hh // b, b, ww // b, b).sum((1, 3))
                c = Mf[:hh, :ww].reshape(hh // b, b, ww // b, b).sum((1, 3))
                full = c >= max(1, b * b // 2)
                if not full.any():
                    continue
                bm = (s[full] / c[full]).double()
                res[tag][b][0] += float(bm.sum())
                res[tag][b][1] += float((bm ** 2).sum())
                res[tag][b][2] += float(bm.numel())
    if v % 10 == 0:
        print(f"  view {v}", flush=True)

out = {}
print("\n            block   1x1      2x2      4x4      8x8     16x16    32x32    64x64   (std of block mean, %)")
for tag in ("all", "centre", "periphery"):
    row = []
    for b in BLOCKS:
        s, s2, n = res[tag][b]
        row.append((s2 / max(n, 1) - (s / max(n, 1)) ** 2) ** 0.5 * 100 if n else float("nan"))
    out[tag] = {"block_px": BLOCKS, "std_pct": row,
                "retained_at_64": row[-1] / row[0] if row[0] else None,
                "white_noise_prediction_at_64": row[0] / 64.0}
    print("%-12s      " % tag + "  ".join("%7.4f" % x for x in row))
print("\nwhite noise would fall by 64x from 1x1 to 64x64; a field smooth over >64 px would not fall at all")
for tag in out:
    print("  %-10s retained at 64 px: %.3f   (white noise would give %.3f)"
          % (tag, out[tag]["retained_at_64"], 1 / 64.0))
Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
