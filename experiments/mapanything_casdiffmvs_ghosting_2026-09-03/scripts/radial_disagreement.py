#!/usr/bin/env python3
"""Does MapAnything's cross-view disagreement grow with image radius?

The first broken layer is known: the model self-predicts a focal ~23% shorter
than the truth. A wrong focal distorts a view's geometry radially -- both the ray
directions and the depth values are wrong by an amount that grows with the
distance from the principal point. Re-projecting along the true COLMAP rays (the
anchored version) fixes the lateral half; if the depth values carry the same
radial error, it is still there.

That is falsifiable. Project each view's points into its neighbours, measure the
relative depth disagreement, and bin it by normalised image radius in the SOURCE
view. Growing with radius => a per-view radial depth correction (3 numbers per
view) is the targeted fix, and being 3-dimensional per view it cannot bend a
wall the way a free per-pixel field can. Flat => the hypothesis is dead and the
disagreement is not a focal artefact.

Everything is computed in the model's own frame with its own intrinsics and
poses, so this measures the model's internal disagreement and nothing else.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="/root/mapanything_layer_audit_A_imgs132_up_20260903/")
ap.add_argument("--neighbours", type=int, default=8)
ap.add_argument("--stride", type=int, default=2, help="pixel stride for the source view")
ap.add_argument("--bins", type=int, default=10)
ap.add_argument("--out", required=True)
a = ap.parse_args()
dev = "cuda"
D = Path(a.dir)

pts = torch.from_numpy(np.load(D / "pts3d.npy")).to(dev)              # V,H,W,3 world
dz = torch.from_numpy(np.load(D / "depth_z.npy")).to(dev)[..., 0]      # V,H,W
K = torch.from_numpy(np.load(D / "intrinsics.npy")).to(dev)            # V,3,3
T = torch.from_numpy(np.load(D / "camera_poses.npy")).to(dev)          # V,4,4 cam->world
msk = torch.from_numpy(np.load(D / "mask.npy")).to(dev)[..., 0]
V, H, W = dz.shape
print(f"{V} views {H}x{W}; focal median {float(K[:,0,0].median()):.1f} px", flush=True)

C = T[:, :3, 3]
dist = torch.cdist(C, C)
dist.fill_diagonal_(float("inf"))
nb = dist.topk(a.neighbours, largest=False).indices                    # V,k

yy, xx = torch.meshgrid(torch.arange(H, device=dev), torch.arange(W, device=dev), indexing="ij")
yy, xx = yy[::a.stride, ::a.stride].reshape(-1), xx[::a.stride, ::a.stride].reshape(-1)
cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
rho = torch.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
rho = rho / rho.max()
edges = torch.linspace(0, 1, a.bins + 1, device=dev)
bidx = torch.clamp(torch.bucketize(rho, edges[1:-1]), 0, a.bins - 1)

Rinv = T[:, :3, :3].transpose(1, 2)
tinv = -torch.einsum("vij,vj->vi", Rinv, T[:, :3, 3])

acc_src = torch.zeros(a.bins, device=dev, dtype=torch.float64)
cnt_src = torch.zeros(a.bins, device=dev, dtype=torch.float64)
acc_dst = torch.zeros(a.bins, device=dev, dtype=torch.float64)
cnt_dst = torch.zeros(a.bins, device=dev, dtype=torch.float64)
signed_src = torch.zeros(a.bins, device=dev, dtype=torch.float64)

for v in range(V):
    P = pts[v][::a.stride, ::a.stride].reshape(-1, 3)
    Mv = msk[v][::a.stride, ::a.stride].reshape(-1)
    for w in nb[v].tolist():
        Xc = P @ Rinv[w].T + tinv[w]
        z = Xc[:, 2]
        good = Mv & (z > 1e-3)
        if not good.any():
            continue
        uv = (Xc[good] @ K[w].T)
        u = (uv[:, 0] / uv[:, 2]).round().long()
        vv = (uv[:, 1] / uv[:, 2]).round().long()
        inb = (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
        if not inb.any():
            continue
        gi = torch.nonzero(good, as_tuple=True)[0][inb]
        u, vv, zz = u[inb], vv[inb], z[good][inb]
        zw = dz[w][vv, u]
        mw = msk[w][vv, u]
        ok = mw & (zw > 1e-3)
        if not ok.any():
            continue
        rel = ((zz[ok] - zw[ok]) / zw[ok])
        # points occluded in w give huge one-sided errors; a robust window keeps
        # the statistic about disagreement rather than about visibility
        keep = rel.abs() < 0.10
        if not keep.any():
            continue
        r = rel[keep].abs().double()
        rs = rel[keep].double()
        bs = bidx[gi[ok][keep]]
        acc_src.scatter_add_(0, bs, r)
        signed_src.scatter_add_(0, bs, rs)
        cnt_src.scatter_add_(0, bs, torch.ones_like(r))
        rho_w = torch.sqrt(((u[ok][keep].double() - cx) / cx) ** 2 + ((vv[ok][keep].double() - cy) / cy) ** 2)
        rho_w = (rho_w / float(rho.max().item() if rho.max() > 0 else 1)).clamp(max=1.0)
        bd = torch.clamp(torch.bucketize(rho_w.float(), edges[1:-1]), 0, a.bins - 1)
        acc_dst.scatter_add_(0, bd, r)
        cnt_dst.scatter_add_(0, bd, torch.ones_like(r))
    if v % 20 == 0:
        print(f"  view {v}/{V}", flush=True)

ms = (acc_src / cnt_src.clamp_min(1)).cpu().numpy()
sg = (signed_src / cnt_src.clamp_min(1)).cpu().numpy()
md = (acc_dst / cnt_dst.clamp_min(1)).cpu().numpy()
cs = cnt_src.cpu().numpy()
print("\n radius band      |rel err| by SOURCE radius   signed        by TARGET radius     samples")
for i in range(a.bins):
    print("  %.2f - %.2f      %8.4f %%              %+8.4f %%   %8.4f %%      %12d"
          % (float(edges[i]), float(edges[i + 1]), ms[i] * 100, sg[i] * 100, md[i] * 100, int(cs[i])))
ratio = float(ms[-1] / ms[0]) if ms[0] > 0 else float("nan")
print(f"\nouter/inner ratio (source radius): {ratio:.3f}")
Path(a.out).write_text(json.dumps({
    "bins": [float(x) for x in edges.cpu().numpy()],
    "abs_rel_by_source_radius": [float(x) for x in ms],
    "signed_rel_by_source_radius": [float(x) for x in sg],
    "abs_rel_by_target_radius": [float(x) for x in md],
    "samples": [int(x) for x in cs],
    "outer_over_inner": ratio,
    "focal_px_median": float(K[:, 0, 0].median()),
}, indent=2) + "\n")
