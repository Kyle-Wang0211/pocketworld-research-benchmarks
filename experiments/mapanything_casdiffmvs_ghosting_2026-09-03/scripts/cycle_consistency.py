#!/usr/bin/env python3
"""Is the disagreement a per-view field, or is it irreducible?

The observation count killed the easy explanation: the outer 70% is seen by 36
views at the median, not by two. So the geometry there is not unconstrained for
lack of cameras -- CasDiffMVS refuses it for lack of texture, and MapAnything
fills it from its prior instead. The question that decides whether any per-view
correction can work is whether the disagreement decomposes as one field per view.

If view v carries its own multiplicative depth error f_v, then in log depth the
pairwise disagreement is r(v,w) = f_v - f_w, and around any loop of three views

    r(v,w) + r(w,x) + r(x,v) = 0

exactly, whatever the fields are. Loop closure is therefore a direct test of the
model, and it needs no fit: measure the loop sums on real triples and compare
their spread against the spread of the individual pairwise terms.

  closes            a per-view correction can remove the disagreement, and with
                    36 views voting the solution is over-determined, not a guess
  does not close    no per-view correction can, however it is parameterised, and
                    every field solve this session was fitting an unsatisfiable
                    system -- which is exactly how a fit ends up inventing shape

Measured per point rather than per image: for a triple of views, take the 3D
points visible in all three and evaluate all three pairwise log-depth ratios on
the same points, so the loop is closed on identical geometry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="/root/mapanything_layer_audit_A_imgs132_up_20260903/")
ap.add_argument("--triples", type=int, default=300)
ap.add_argument("--tol", type=float, default=0.10)
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
Rinv = T[:, :3, :3].transpose(1, 2).contiguous()
tinv = -torch.einsum("vij,vj->vi", Rinv, T[:, :3, 3])
C = T[:, :3, 3]
dist = torch.cdist(C, C); dist.fill_diagonal_(float("inf"))
nb = dist.topk(6, largest=False).indices


def logratio(P, w):
    """log(depth of P in view w according to the geometry) - log(view w's own depth there)"""
    Xc = P @ Rinv[w].T + tinv[w]
    z = Xc[:, 2]
    uv = Xc @ K[w].T
    u = (uv[:, 0] / uv[:, 2].clamp_min(1e-6)).round().long()
    vv = (uv[:, 1] / uv[:, 2].clamp_min(1e-6)).round().long()
    ok = (z > 1e-3) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
    uu, vc = u.clamp(0, W - 1), vv.clamp(0, H - 1)
    zw = dz[w][vc, uu]
    ok = ok & msk[w][vc, uu] & (zw > 1e-3)
    return torch.log(z.clamp_min(1e-6)) - torch.log(zw.clamp_min(1e-6)), ok


g = torch.Generator(device="cpu").manual_seed(20260904)
pair_sq, pair_n = 0.0, 0
loop_sq, loop_n = 0.0, 0
loop_abs = []
done = 0
for _ in range(a.triples * 8):
    if done >= a.triples:
        break
    v = int(torch.randint(0, V, (1,), generator=g))
    cand = nb[v].tolist()
    if len(cand) < 2:
        continue
    i, j = torch.randperm(len(cand), generator=g)[:2].tolist()
    w, x = cand[i], cand[j]
    if len({v, w, x}) < 3:
        continue
    P = pts[v].reshape(-1, 3)
    base = msk[v].reshape(-1)
    r_vw, ok1 = logratio(P, w)
    r_vx, ok2 = logratio(P, x)
    # third leg on the SAME points: what w and x say about each other there.
    # r(w,x) evaluated on these points is r_vx - r_vw only if the model holds;
    # to avoid assuming it, take view w's own reconstruction of the same pixels
    Xc = P @ Rinv[w].T + tinv[w]
    uv = Xc @ K[w].T
    u = (uv[:, 0] / uv[:, 2].clamp_min(1e-6)).round().long().clamp(0, W - 1)
    vv = (uv[:, 1] / uv[:, 2].clamp_min(1e-6)).round().long().clamp(0, H - 1)
    Pw = pts[w][vv, u]                       # w's own 3D point for the same surface
    r_wx, ok3 = logratio(Pw, x)
    ok = base & ok1 & ok2 & ok3
    ok &= (r_vw.abs() < a.tol) & (r_vx.abs() < a.tol) & (r_wx.abs() < a.tol)
    n = int(ok.sum())
    if n < 20000:
        continue
    # loop v->w->x->v :  r(v,w) + r(w,x) - r(v,x)
    loop = r_vw[ok] + r_wx[ok] - r_vx[ok]
    loop_sq += float((loop ** 2).sum()); loop_n += n
    pair_sq += float((r_vw[ok] ** 2).sum() + r_vx[ok] ** 2).sum() if False else float((r_vw[ok] ** 2).sum())
    pair_n += n
    loop_abs.append(float(loop.abs().median()))
    done += 1

pair_rms = (pair_sq / max(pair_n, 1)) ** 0.5 * 100
loop_rms = (loop_sq / max(loop_n, 1)) ** 0.5 * 100
# a loop of three independent pairwise terms would be sqrt(3) times one term if
# the disagreement carried no per-view structure at all
print(f"\ntriples used          {done}")
print(f"pairwise term  RMS    {pair_rms:.4f} %")
print(f"loop sum       RMS    {loop_rms:.4f} %")
print(f"ratio loop/pair       {loop_rms/pair_rms:.3f}   (0 = perfect per-view field, 1.73 = no per-view structure)")
print(f"explained by a per-view field: {100*(1-(loop_rms/pair_rms/(3**0.5))**2):.1f} %")
Path(a.out).write_text(json.dumps({
    "triples": done, "pair_rms_pct": pair_rms, "loop_rms_pct": loop_rms,
    "ratio": loop_rms / pair_rms, "explained_by_per_view_field": 1 - (loop_rms / pair_rms / 3 ** 0.5) ** 2,
}, indent=2) + "\n")
