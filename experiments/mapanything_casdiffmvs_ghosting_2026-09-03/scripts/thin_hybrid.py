#!/usr/bin/env python3
"""CasDiffMVS only on thin objects, MapAnything everywhere else.

The per-pixel hybrid settled the two open questions at once: with CasDiffMVS's
depth inside its coverage the slippers stand up again, and CasDiffMVS's wall
sticking comes back with it. Each reconstruction is right exactly where the
other is wrong -- CasDiffMVS on thin textured objects, MapAnything on walls
and large surfaces. So the split is by pixel class, not by coverage.

A thin-object pixel is one where CasDiffMVS's depth is 1-8% nearer than the
farthest surface within 15 px (the slipper against the floor, the wheel against
the floor), the test that passed its positive control earlier today; the mask
is dilated a few pixels so the seam between the two sources lands on the floor
beside the object rather than at its foot. Luggage stands 30 cm and more off
the wall, far outside the band, so its surroundings -- where the sticking
lives -- stay MapAnything's.

MapAnything pixels keep the MapAnything-only gate behind cloud 3, and are vetoed
where CasDiffMVS's thin-object pixels contradict them in >= 2 neighbour views,
so a collapsed slipper in one view loses to a solid one in the others.
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
ap.add_argument("--radius", type=int, default=15)
ap.add_argument("--thin_lo", type=float, default=0.01)
ap.add_argument("--thin_hi", type=float, default=0.08)
ap.add_argument("--dilate", type=int, default=4)
ap.add_argument("--cluster_min", type=float, default=0.15, help="near and far clusters must each hold this fraction of the window")
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--depth_tol", type=float, default=0.01)
ap.add_argument("--veto_min", type=int, default=2)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="thin_hybrid")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
UP = torch.from_numpy(np.load(f"{a.up_dir}/depth_up.npy")).to(dev).float()
UPG = torch.from_numpy(np.load(f"{a.up_dir}/gate_keep.npy")).to(dev)
HYB = torch.from_numpy(np.load(f"{a.hybrid_dir}/depth_hybrid.npy")).to(dev).float()
SRC = torch.from_numpy(np.load(f"{a.hybrid_dir}/source.npy")).to(dev)
V, Ht, Wt = UP.shape; Hm, Wm = 518, 392; s = a.scale
CAS = torch.where(SRC == 1, HYB, torch.zeros_like(HYB))
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
Kt = torch.from_numpy(K).to(dev).float(); C2Wt = torch.from_numpy(C2W).to(dev).float(); W2C = torch.linalg.inv(C2Wt)
s2f = json.load(open(a.mapping)); lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; srcs = []
    for j in range(k): srcs.append(int(lines[p])); p += 2
    pairs[ref_s] = srcs

# thin-object mask on CasDiffMVS's depth, per view
kk = 2 * a.radius + 1
THIN = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev)
for f in range(V):
    d = CAS[f]; ok = d > 0
    small = torch.where(ok, d, torch.full_like(d, -float("inf")))
    bg = F.max_pool2d(small[None, None], kk, 1, a.radius)[0, 0]
    vf = F.avg_pool2d(ok.float()[None, None], kk, 1, a.radius)[0, 0]
    prot = (bg - d) / bg.clamp_min(1e-6)
    # A slanted wall or floor also puts every pixel 1-8% nearer than its window's
    # farthest point, which is how the first version of this mask swallowed 93% of
    # CasDiffMVS's pixels. A real thin object against a background is bimodal: a
    # near cluster and a far cluster both present in the window. Same two-cluster
    # test that separated luggage rims from grazing floors in the bridge search.
    nmin = -F.max_pool2d(-torch.where(ok, d, torch.full_like(d, float("inf")))[None, None], kk, 1, a.radius)[0, 0]
    near_frac = F.avg_pool2d((ok & (d < nmin * 1.03)).float()[None, None], kk, 1, a.radius)[0, 0] / vf.clamp_min(1e-6)
    far_frac = F.avg_pool2d((ok & (d > bg * 0.97)).float()[None, None], kk, 1, a.radius)[0, 0] / vf.clamp_min(1e-6)
    bimodal = (near_frac >= a.cluster_min) & (far_frac >= a.cluster_min)
    thin = ok & torch.isfinite(bg) & (vf > 0.5) & (prot > a.thin_lo) & (prot < a.thin_hi) & bimodal
    if a.dilate > 0:
        thin = F.max_pool2d(thin.float()[None, None], 2 * a.dilate + 1, 1, a.dilate)[0, 0] > 0.5
    THIN[f] = thin & ok
CASK = THIN                                                            # CasDiffMVS is used only here
THIN_D = torch.where(CASK, CAS, torch.zeros_like(CAS))
print(f"thin-object pixels (CasDiffMVS kept): {int(CASK.sum()):,} of {int((SRC==1).sum()):,} covered ({100*CASK.sum()/max((SRC==1).sum(),1):.1f}%)", flush=True)

vv, uu = torch.meshgrid(torch.arange(Ht, device=dev, dtype=torch.float32), torch.arange(Wt, device=dev, dtype=torch.float32), indexing="ij")
keep = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev); SRC_OUT = torch.zeros(V, Ht, Wt, dtype=torch.uint8, device=dev)
st = dict(cas=0, ma_cand=0, ma_kept=0, vetoed=0)
for ref_s, src_s in pairs.items():
    f = int(s2f[ref_s])
    cand = ~CASK[f] & (UP[f] > 0) & UPG[f]
    d = UP[f]
    x = (uu - Kt[f, 0, 2]) / Kt[f, 0, 0] * d; y = (vv - Kt[f, 1, 2]) / Kt[f, 1, 1] * d
    Xw = torch.stack([x, y, d], -1) @ C2Wt[f, :3, :3].T + C2Wt[f, :3, 3]
    veto = torch.zeros(Ht, Wt, dtype=torch.int32, device=dev)
    for sidx in src_s[: a.num_src]:
        j = int(s2f[int(sidx)])
        Xc = Xw @ W2C[j, :3, :3].T + W2C[j, :3, 3]; z = Xc[..., 2]
        u = (Xc[..., 0] / z.clamp_min(1e-6) * Kt[j, 0, 0] + Kt[j, 0, 2]).round().long(); v = (Xc[..., 1] / z.clamp_min(1e-6) * Kt[j, 1, 1] + Kt[j, 1, 2]).round().long()
        inb = (z > 1e-3) & (u >= 0) & (u < Wt) & (v >= 0) & (v < Ht)
        cj = THIN_D[j][v.clamp(0, Ht - 1), u.clamp(0, Wt - 1)]
        veto += (inb & (cj > 0) & (((z - cj).abs() / cj.clamp_min(1e-6)) > a.depth_tol)).int()
    ma_keep = cand & (veto < a.veto_min)
    keep[f] = CASK[f] | ma_keep
    SRC_OUT[f] = torch.where(CASK[f], 1, torch.where(ma_keep, 2, 0)).to(torch.uint8)
    st["cas"] += int(CASK[f].sum()); st["ma_cand"] += int(cand.sum()); st["ma_kept"] += int(ma_keep.sum()); st["vetoed"] += int((cand & ~ma_keep).sum())
    if ref_s % 33 == 0: print(f"  ref {ref_s}: thin/cas {int(CASK[f].sum()):,}  ma cand {int(cand.sum()):,}  kept {int(ma_keep.sum()):,}", flush=True)
print(f"thin-hybrid: cas {st['cas']:,} + ma {st['ma_kept']:,} of {st['ma_cand']:,} ({100*st['ma_kept']/max(st['ma_cand'],1):.1f}%, vetoed {st['vetoed']:,})", flush=True)
np.save(out / "keep.npy", keep.cpu().numpy()); np.save(out / "source.npy", SRC_OUT.cpu().numpy())

DEPTH = torch.where(CASK, CAS, UP)
s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
un = (uu + 0.5) / s - 0.5; vn = (vv + 0.5) / s - 0.5
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
photo_grid = torch.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1)[None]
xyz, col, srcl = [], [], []
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    yy, xx = torch.nonzero(keep[f], as_tuple=True); z = DEPTH[f][yy, xx].double()
    x = (xx.double() - K[f][0, 2]) / K[f][0, 0] * z; y = (yy.double() - K[f][1, 2]) / K[f][1, 1] * z
    pc = torch.stack([x, y, z], 1) @ torch.from_numpy(C2W[f][:3, :3]).to(dev).T + torch.from_numpy(C2W[f][:3, 3]).to(dev)
    xyz.append(pc.cpu().numpy()); col.append((g[yy, xx].clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()); srcl.append(SRC_OUT[f][yy, xx].cpu().numpy())
xyz = np.concatenate(xyz); col = np.concatenate(col); srcl = np.concatenate(srcl)
np.save(out / "point_source.npy", srcl)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "CasDiffMVS depth only on thin-object pixels (1-8% protrusion within 15px, dilated), MapAnything (own gate) elsewhere, CasDiffMVS-thin veto >= 2 views",
       "thin": {"radius": a.radius, "lo": a.thin_lo, "hi": a.thin_hi, "dilate": a.dilate}, **st, "depth_tol": a.depth_tol, "veto_min": a.veto_min,
       "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps(res, indent=2))
