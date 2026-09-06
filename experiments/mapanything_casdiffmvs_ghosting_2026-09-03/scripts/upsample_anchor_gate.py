#!/usr/bin/env python3
"""Anchored MapAnything depth, joint-bilaterally upsampled to CasDiffMVS density,
then passed through the official CasDiffMVS consistency gate.

Why this and not a higher inference resolution: the model is trained at 518 and
measured worse at 770 and 1036 on every scale, including fine detail. So the
518 depth stays the only geometry; what changes is the sampling. Every target
pixel (777 x 588, 1.5x the native grid, 457k per view against CasDiffMVS's
442k) takes a weighted mean of the 4x4 surrounding native depths, weighted by
distance on the native grid AND by colour similarity between the target pixel
and each native sample in the same photograph (Kopf et al. 2007). Where the
photo has an edge -- slipper against floor -- the weights follow it, so the
depth edge lands where the colour edge is instead of being smeared across it.

Colours come from the 1500 x 2000 upright photograph sampled at each target
pixel, not from the 518 image enlarged. Intrinsics scale by 1.5 with the
half-pixel offset; poses are the production COLMAP poses, unchanged. The gate
is the upstream check_geometric_consistency imported verbatim, at 1 px / 1% /
>= 3 views -- the same criterion CasDiffMVS applied to itself at essentially
the same resolution -- with failing pixels deleted and no depth averaging.

The added points are interpolated, not native model output. That is stated
here because it is the one property this cloud lacks that the 518 cloud has.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

sys.path.insert(0, "/root"); sys.path.insert(0, "/root/map-anything")
from crossview_field import build_ref_cameras  # noqa: E402
sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from filter import check_geometric_consistency  # noqa: E402


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--images", default="/root/imgs132_up")
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--pair", default="/root/casdiffmvs_official_20260903/mvs_P16k/pair.txt")
ap.add_argument("--depth", default="/root/mapanything_native_anchored_20260903/depth_native_final.npy")
ap.add_argument("--scale", type=float, default=1.5)
ap.add_argument("--sigma_s", type=float, default=0.75, help="spatial sigma, native pixels")
ap.add_argument("--sigma_r", type=float, default=0.08, help="range sigma, RGB in [0,1]")
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="up15_gated")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
D0 = torch.from_numpy(np.load(a.depth).astype(np.float32)).to(dev)          # V,518,392 metric, 0 = masked
C0 = torch.from_numpy(np.load(f"{a.saved}/img_no_norm.npy")).to(dev).float() / 255.0   # V,518,392,3
V, Hm, Wm = D0.shape
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)                 # K at 518x392, cam->world
s = a.scale; Ht, Wt = int(round(Hm * s)), int(round(Wm * s))
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
EXT = np.stack([np.linalg.inv(C2W[i]) for i in range(V)])
print(f"{V} views: native {Hm}x{Wm} -> target {Ht}x{Wt} ({Ht*Wt:,} px/view; CasDiffMVS 442,368)", flush=True)

# target pixel -> native float coords -> upright 1500x2000 photo coords
vt, ut = torch.meshgrid(torch.arange(Ht, device=dev, dtype=torch.float32), torch.arange(Wt, device=dev, dtype=torch.float32), indexing="ij")
un = (ut + 0.5) / s - 0.5; vn = (vt + 0.5) / s - 0.5
s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
photo_grid = torch.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1)[None]
u0 = torch.floor(un).long(); v0 = torch.floor(vn).long()

depth_up = torch.zeros(V, Ht, Wt, device=dev); rgb_up = torch.zeros(V, Ht, Wt, 3, device=dev)
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    assert photo.shape[:2] == (2000, 1500), photo.shape
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    rgb_up[f] = g
    num = torch.zeros(Ht, Wt, device=dev); den = torch.zeros(Ht, Wt, device=dev)
    for dy in range(-1, 3):
        for dx in range(-1, 3):
            iu = (u0 + dx).clamp(0, Wm - 1); iv = (v0 + dy).clamp(0, Hm - 1)
            inb = ((u0 + dx) >= 0) & ((u0 + dx) < Wm) & ((v0 + dy) >= 0) & ((v0 + dy) < Hm)
            dn = D0[f][iv, iu]; cn = C0[f][iv, iu]
            ws = torch.exp(-((un - iu.float()) ** 2 + (vn - iv.float()) ** 2) / (2 * a.sigma_s ** 2))
            wr = torch.exp(-((g - cn) ** 2).sum(-1) / (2 * a.sigma_r ** 2))
            w = ws * wr * inb.float() * (dn > 0).float()
            num += w * dn; den += w
    depth_up[f] = torch.where(den > 1e-3, num / den.clamp_min(1e-9), torch.zeros_like(num))
    if f % 33 == 0: print(f"  upsampled view {f}: valid {int((depth_up[f] > 0).sum()):,}", flush=True)
depth = depth_up.cpu().numpy().astype(np.float64); valid = depth > 0
np.save(out / "depth_up.npy", depth.astype(np.float32))
print(f"upsampling done in {time.time()-t0:.0f}s; valid px total {int(valid.sum()):,}", flush=True)

# official gate on the upsampled depths, same pairs as CasDiffMVS
s2f = json.load(open(a.mapping)); lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; src = []
    for j in range(k): src.append(int(lines[p])); p += 2
    pairs[ref_s] = src
gate = np.zeros(valid.shape, dtype=bool); gfrac = []
for ref_s, src_s in pairs.items():
    f = int(s2f[ref_s]); dref = depth[f]
    dmin = float(np.percentile(dref[valid[f]], 0.05)); dmax = float(np.percentile(dref[valid[f]], 99.95))
    gsum = np.zeros(dref.shape, np.int32)
    for sidx in src_s[: a.num_src]:
        j = int(s2f[int(sidx)])
        gmask, _, _, _ = check_geometric_consistency(dref, K[f], EXT[f], depth[j], K[j], EXT[j], dmax, dmin, a.geo_pixel_thres, a.geo_depth_thres)
        gsum += gmask.astype(np.int32)
    gate[f] = valid[f] & (gsum >= a.geo_mask_thres); gfrac.append(float(gate[f][valid[f]].mean()))
    if ref_s % 33 == 0: print(f"  gate ref {ref_s}: pass {gfrac[-1]*100:.1f}%", flush=True)
np.save(out / "gate_keep.npy", gate)
print(f"gate: {int(gate.sum()):,} of {int(valid.sum()):,} pass ({100*gate.sum()/valid.sum():.1f}%, per-view p50 {100*np.median(gfrac):.1f}%)", flush=True)

xyz, col = [], []
rgb8 = (rgb_up.clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()
for f in range(V):
    yy, xx = np.nonzero(gate[f]); z = depth[f][yy, xx]
    x = (xx - K[f][0, 2]) / K[f][0, 0] * z; y = (yy - K[f][1, 2]) / K[f][1, 1] * z
    pc = np.stack([x, y, z, np.ones_like(z)], 1)
    xyz.append((C2W[f] @ pc.T).T[:, :3]); col.append(rgb8[f][gate[f]])
xyz = np.concatenate(xyz); col = np.concatenate(col)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "anchored MapAnything depth, joint-bilateral upsampled x1.5 with the photo as guide, official CasDiffMVS gate (delete, no averaging)",
       "native": [Hm, Wm], "target": [Ht, Wt], "scale": s, "sigma_s": a.sigma_s, "sigma_r": a.sigma_r,
       "valid_px": int(valid.sum()), "gate_pass": int(gate.sum()), "gate_pass_frac": float(gate.sum() / valid.sum()),
       "gate": {"pixel": a.geo_pixel_thres, "depth": a.geo_depth_thres, "views": a.geo_mask_thres, "num_src": a.num_src},
       "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps(res, indent=2))
