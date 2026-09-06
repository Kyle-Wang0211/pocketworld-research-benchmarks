#!/usr/bin/env python3
"""Coverage of the upsampled MapAnything cloud, geometry of CasDiffMVS where it
exists: union with CasDiffMVS priority.

The strict hybrid gate (hybrid_gate.py) let only 25% of MapAnything's fill
through, because a fill pixel projected into a neighbour lands on CasDiffMVS's
surface there and the two reconstructions differ by 0.77% at the median against
a 1% threshold, so the >= 3-view requirement is rarely met. That is correct by
the gate's own rule and it costs most of the wall coverage the user values.

This keeps both sources on their own terms and lets CasDiffMVS veto:

  CasDiffMVS pixels     kept as they are (already gated by its own run)
  MapAnything pixels    only where CasDiffMVS is absent in this view AND the
                        MapAnything-only gate (the one behind cloud 3) passed,
                        AND when projected into the neighbour views it is not
                        contradicted by CasDiffMVS in >= 2 of them (one
                        contradiction is allowed: an occluder in a single view
                        looks exactly like a contradiction)

So MapAnything fills where CasDiffMVS has nothing or agrees, and never
overrides it. No third gate runs on the mixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
ap.add_argument("--up_dir", default="/root/up15_gated_20260906")
ap.add_argument("--hybrid_dir", default="/root/hybrid_gated_20260906")
ap.add_argument("--scale", type=float, default=1.5)
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--depth_tol", type=float, default=0.01)
ap.add_argument("--veto_min", type=int, default=2)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="union_priority")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
UP = torch.from_numpy(np.load(f"{a.up_dir}/depth_up.npy")).to(dev).float()          # V,Ht,Wt
UPG = torch.from_numpy(np.load(f"{a.up_dir}/gate_keep.npy")).to(dev)                 # MapAnything-only gate
HYB = torch.from_numpy(np.load(f"{a.hybrid_dir}/depth_hybrid.npy")).to(dev).float()
SRC = torch.from_numpy(np.load(f"{a.hybrid_dir}/source.npy")).to(dev)
V, Ht, Wt = UP.shape; Hm, Wm = 518, 392; s = a.scale
CAS = torch.where(SRC == 1, HYB, torch.zeros_like(HYB))                              # CasDiffMVS-only depth per view
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
Kt = torch.from_numpy(K).to(dev).float(); C2Wt = torch.from_numpy(C2W).to(dev).float(); W2C = torch.linalg.inv(C2Wt)
s2f = json.load(open(a.mapping)); lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; srcs = []
    for j in range(k): srcs.append(int(lines[p])); p += 2
    pairs[ref_s] = srcs
vv, uu = torch.meshgrid(torch.arange(Ht, device=dev, dtype=torch.float32), torch.arange(Wt, device=dev, dtype=torch.float32), indexing="ij")

keep = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev); stats = dict(cas=0, ma_cand=0, ma_kept=0, vetoed=0)
for ref_s, src_s in pairs.items():
    f = int(s2f[ref_s])
    cand = (SRC[f] == 2) & UPG[f]                        # MapAnything fill that passed its own gate
    d = UP[f]
    x = (uu - Kt[f, 0, 2]) / Kt[f, 0, 0] * d; y = (vv - Kt[f, 1, 2]) / Kt[f, 1, 1] * d
    Xw = torch.stack([x, y, d], -1) @ C2Wt[f, :3, :3].T + C2Wt[f, :3, 3]
    veto = torch.zeros(Ht, Wt, dtype=torch.int32, device=dev)
    for sidx in src_s[: a.num_src]:
        j = int(s2f[int(sidx)])
        Xc = Xw @ W2C[j, :3, :3].T + W2C[j, :3, 3]; z = Xc[..., 2]
        u = (Xc[..., 0] / z.clamp_min(1e-6) * Kt[j, 0, 0] + Kt[j, 0, 2]).round().long(); v = (Xc[..., 1] / z.clamp_min(1e-6) * Kt[j, 1, 1] + Kt[j, 1, 2]).round().long()
        inb = (z > 1e-3) & (u >= 0) & (u < Wt) & (v >= 0) & (v < Ht)
        cj = CAS[j][v.clamp(0, Ht - 1), u.clamp(0, Wt - 1)]
        landed = inb & (cj > 0)
        contradicted = landed & (((z - cj).abs() / cj.clamp_min(1e-6)) > a.depth_tol)
        veto += contradicted.int()
    ma_keep = cand & (veto < a.veto_min)
    keep[f] = (SRC[f] == 1) | ma_keep
    stats["cas"] += int((SRC[f] == 1).sum()); stats["ma_cand"] += int(cand.sum()); stats["ma_kept"] += int(ma_keep.sum()); stats["vetoed"] += int((cand & ~ma_keep).sum())
    if ref_s % 33 == 0: print(f"  ref {ref_s}: cas {int((SRC[f]==1).sum()):,}  ma cand {int(cand.sum()):,}  kept {int(ma_keep.sum()):,}", flush=True)
print(f"union: cas {stats['cas']:,} + ma {stats['ma_kept']:,} of {stats['ma_cand']:,} candidates ({100*stats['ma_kept']/max(stats['ma_cand'],1):.1f}%, vetoed {stats['vetoed']:,})", flush=True)
np.save(out / "keep.npy", keep.cpu().numpy())

s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
un = (uu + 0.5) / s - 0.5; vn = (vv + 0.5) / s - 0.5
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
photo_grid = torch.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1)[None]
xyz, col, srcl = [], [], []
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    kf = keep[f]; d = HYB[f]                               # HYB holds cas depth where SRC==1 and MA depth where SRC==2
    yy, xx = torch.nonzero(kf, as_tuple=True); z = d[yy, xx].double()
    x = (xx.double() - K[f][0, 2]) / K[f][0, 0] * z; y = (yy.double() - K[f][1, 2]) / K[f][1, 1] * z
    pc = torch.stack([x, y, z], 1) @ torch.from_numpy(C2W[f][:3, :3]).to(dev).T + torch.from_numpy(C2W[f][:3, 3]).to(dev)
    xyz.append(pc.cpu().numpy()); col.append((g[yy, xx].clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()); srcl.append(SRC[f][yy, xx].cpu().numpy())
xyz = np.concatenate(xyz); col = np.concatenate(col); srcl = np.concatenate(srcl)
np.save(out / "point_source.npy", srcl)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "CasDiffMVS pixels as-is + MapAnything fill (own gate) unless contradicted by CasDiffMVS in >= veto_min neighbour views",
       **stats, "depth_tol": a.depth_tol, "veto_min": a.veto_min, "points": int(xyz.shape[0]),
       "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps(res, indent=2))
