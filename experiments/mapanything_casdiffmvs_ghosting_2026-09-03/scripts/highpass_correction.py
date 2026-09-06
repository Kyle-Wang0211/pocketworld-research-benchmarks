#!/usr/bin/env python3
"""Keep only the high-frequency part of a correction.

The wall decomposition showed the two artefacts live at different scales:

  thickness (ghosting)  high frequency -- the same patch is 20-50 mm thick
  waviness  (twisting)  low frequency  -- the wall bows over 30 cm to metres

and that every correction built so far bought a little of the first at a large
cost in the second: anchored 60 mm wavy / 26 mm thick, the field solves 154-165
wavy for no thickness gain at all, robust MLS 78 wavy / 22 thick.

Waviness is what the eye calls "twisted", so a correction must not add any. That
is enforceable rather than hoped for: take the correction's displacement field,
subtract its low-frequency component, and apply only what remains. Structure
coarser than `scale` is removed by construction, so the large-scale shape stays
exactly the base cloud's, while a patch pulled onto its dominant layer -- a few
centimetres, well inside the pass band -- survives untouched.

Every point is kept and colours come from the base cloud unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import torch


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True, help="the cloud whose large-scale shape must be preserved")
ap.add_argument("--corr", required=True, help="the cloud carrying the thickness-reducing correction")
ap.add_argument("--out", required=True)
ap.add_argument("--scale", type=float, default=0.30, help="metres; the cutoff -- structure coarser than this is dropped from the correction")
ap.add_argument("--gain", type=float, default=1.0, help="multiplier on the surviving high-frequency part")
args = ap.parse_args()
t0 = time.time()
dev = "cuda"

pb = o3d.io.read_point_cloud(args.base)
B = np.asarray(pb.points, dtype=np.float64)
C = np.asarray(pb.colors)
P = np.asarray(o3d.io.read_point_cloud(args.corr).points, dtype=np.float64)
assert P.shape == B.shape, f"{P.shape} != {B.shape}"
N = B.shape[0]
Bt = torch.from_numpy(B).to(dev)
D = torch.from_numpy(P).to(dev) - Bt
print(f"{N} points; correction p50 {float(D.norm(dim=1).median())*1000:.2f} mm", flush=True)

# low-frequency component of D: voxel means, box-filtered over 3x3x3 (support 3*scale),
# then trilinearly interpolated back so the result carries no cell boundaries
h = args.scale
origin = Bt.min(0).values - h
c = (Bt - origin) / h
vi = torch.floor(c).long()
dims = vi.max(0).values + 2
strides = torch.tensor([int(dims[1]) * int(dims[2]), int(dims[2]), 1], device=dev, dtype=torch.long)
uniq, inv = torch.unique((vi * strides).sum(1), return_inverse=True)
M = uniq.numel()
cnt = torch.zeros(M, device=dev, dtype=torch.float64)
cnt.scatter_add_(0, inv, torch.ones(N, device=dev, dtype=torch.float64))
s1 = torch.zeros(M, 3, device=dev, dtype=torch.float64)
for k in range(3):
    s1[:, k].scatter_add_(0, inv, D[:, k])
cs, ss = torch.zeros_like(cnt), torch.zeros_like(s1)
for ox in (-1, 0, 1):
    for oy in (-1, 0, 1):
        for oz in (-1, 0, 1):
            t = uniq + ox * strides[0] + oy * strides[1] + oz * strides[2]
            pos = torch.searchsorted(uniq, t).clamp(max=M - 1)
            hit = uniq[pos] == t
            cs[hit] += cnt[pos[hit]]
            ss[hit] += s1[pos[hit]]
mu = ss / cs[:, None].clamp_min(1)
print(f"{M} cells at {h*100:.0f} cm, support {3*h*100:.0f} cm", flush=True)

low = torch.zeros_like(D)
wsum = torch.zeros(N, device=dev, dtype=torch.float64)
base = torch.floor(c - 0.5).long()
frac = (c - 0.5) - base
for dx in (0, 1):
    for dy in (0, 1):
        for dz in (0, 1):
            w = ((1 - frac[:, 0]) if dx == 0 else frac[:, 0]) * \
                ((1 - frac[:, 1]) if dy == 0 else frac[:, 1]) * \
                ((1 - frac[:, 2]) if dz == 0 else frac[:, 2])
            v = base + torch.tensor([dx, dy, dz], device=dev, dtype=torch.long)
            vlin = (v.clamp_min(0) * strides).sum(1)
            pos = torch.searchsorted(uniq, vlin).clamp(max=M - 1)
            hit = (uniq[pos] == vlin) & (w > 0)
            if not hit.any():
                continue
            low[hit] += w[hit][:, None] * mu[pos[hit]]
            wsum[hit] += w[hit]
# where trilinear support is missing, fall back to the point's own cell mean, so
# the high-pass is complete everywhere and no point is left with a raw low term
miss = wsum < 1.0
if miss.any():
    low[miss] += (1.0 - wsum[miss])[:, None] * mu[inv[miss]]

Dh = (D - low) * args.gain
out = (Bt + Dh).cpu().numpy()
o = o3d.geometry.PointCloud()
o.points = o3d.utility.Vector3dVector(out)
if C.shape[0]:
    o.colors = o3d.utility.Vector3dVector(C)
dst = Path(args.out)
dst.parent.mkdir(parents=True, exist_ok=True)
o3d.io.write_point_cloud(str(dst), o, write_ascii=False, compressed=False)
dn = Dh.norm(dim=1)
res = {
    "base": args.base, "corr": args.corr, "scale_m": h, "gain": args.gain, "points": int(N),
    "correction_mm_p50": float(D.norm(dim=1).median() * 1000),
    "lowpass_removed_mm_p50": float(low.norm(dim=1).median() * 1000),
    "applied_mm_p50": float(dn.median() * 1000), "applied_mm_p95": float(torch.quantile(dn[::37].float(), 0.95) * 1000),
    "ply": {"path": str(dst), "bytes": dst.stat().st_size, "sha256": sha256_file(dst)},
    "seconds": time.time() - t0,
}
Path(str(dst) + ".json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps(res, indent=2))
