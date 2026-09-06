#!/usr/bin/env python3
"""Cloud 3 as the base; CasDiffMVS depth substituted only where it is
colour-depth coherent AND MapAnything has demonstrably collapsed or has a hole.

The two earlier "thin object" masks (93%, then 60% of CasDiffMVS's pixels)
failed because the stuck-wall pixel and the slipper pixel look identical in
depth: both are nearer than MapAnything says. They differ in colour-depth
coherence. A stuck wall pixel is wall-coloured but sits at the luggage's depth,
so most of its same-coloured neighbours (the real wall) disagree with it. A
slipper pixel is slipper-coloured and its same-coloured neighbours are the
slipper, at the same depth. So, per CasDiffMVS pixel that passed the official
strict gate: among the neighbours within 13x13 whose colour is within tau_c,
the fraction whose depth agrees within tau_d must be >= 0.5.

Coherent CasDiffMVS pixels replace MapAnything's only where (a) MapAnything is
farther by more than tau_rep -- the collapsed object -- or (b) MapAnything has
no depth there at all -- a hole on a textured object. Everywhere else the base
cloud is untouched. Replaced pixels veto MapAnything's collapsed copies of the
same surface in other views (>= 2 contradictions), as before.

The first thing printed is the fraction of CasDiffMVS pixels selected. If it
is not a few percent, the rule is wrong and nothing downstream matters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

sys.path.insert(0, "/root"); sys.path.insert(0, "/root/map-anything")
from crossview_field import build_ref_cameras  # noqa: E402
sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pfm  # noqa: E402


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
ap.add_argument("--cas", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
ap.add_argument("--up_dir", default="/root/up15_gated_20260906")
ap.add_argument("--ma_keep", default=None, help="keep mask for the MapAnything side (default: cloud 3's gate_keep.npy)")
ap.add_argument("--scale", type=float, default=1.5)
ap.add_argument("--radius", type=int, default=6)
ap.add_argument("--tau_c", type=float, default=0.12, help="RGB distance for 'same colour'")
ap.add_argument("--tau_d", type=float, default=0.01, help="relative depth for 'same depth'")
ap.add_argument("--min_same", type=int, default=8)
ap.add_argument("--coh_min", type=float, default=0.5)
ap.add_argument("--tau_rep", type=float, default=0.01, help="MapAnything farther than CasDiffMVS by this much -> collapsed -> replace")
ap.add_argument("--tau_rep_max", type=float, default=0.06, help="collapses larger than this are not thin objects (stuck wall patches sit 20-50% in front)")
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--veto_min", type=int, default=2)
ap.add_argument("--overlay_views", type=int, nargs="*", default=[20, 40, 80])
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="coherent")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True); (out / "overlay").mkdir(exist_ok=True)
info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
UP = torch.from_numpy(np.load(f"{a.up_dir}/depth_up.npy")).to(dev).float()
UPG = torch.from_numpy(np.load(a.ma_keep or f"{a.up_dir}/gate_keep.npy")).to(dev)
V, Ht, Wt = UP.shape; Hm, Wm = 518, 392; s = a.scale
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
Kt = torch.from_numpy(K).to(dev).float(); C2Wt = torch.from_numpy(C2W).to(dev).float(); W2C = torch.linalg.inv(C2Wt)
s2f = json.load(open(a.mapping)); f2s = {int(f): src for src, f in enumerate(s2f)}
lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; srcs = []
    for j in range(k): srcs.append(int(lines[p])); p += 2
    pairs[ref_s] = srcs

# target grid -> CasDiffMVS 768x576 nearest lookup (same chain as hybrid_gate.py)
vt, ut = np.meshgrid(np.arange(Ht, dtype=np.float64), np.arange(Wt, dtype=np.float64), indexing="ij")
un = (ut + 0.5) / s - 0.5; vn = (vt + 0.5) / s - 0.5
s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
x_l = y15; y_l = 1500.0 - 1.0 - x15
x768 = (x_l + 0.5) * (768.0 / 2000.0) - 0.5; y576 = (y_l + 0.5) * (576.0 / 1500.0) - 0.5
cu = torch.from_numpy(np.clip(np.round(x768).astype(int), 0, 767)).to(dev); cv_ = torch.from_numpy(np.clip(np.round(y576).astype(int), 0, 575)).to(dev)
inb = torch.from_numpy((x768 >= -0.5) & (x768 < 767.5) & (y576 >= -0.5) & (y576 < 575.5)).to(dev)
photo_grid = torch.from_numpy(np.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1).astype(np.float32))[None].to(dev)

# 1) colour-depth coherence on CasDiffMVS's own grid, per source view
kk = 2 * a.radius + 1
COH = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev); CAS = torch.zeros(V, Ht, Wt, device=dev); STRICT = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev)
tot_strict = tot_coh = 0
for f in range(V):
    src = f2s[f]
    D = torch.from_numpy(read_pfm(os.path.join(a.cas, f"depth_est/{src:08d}.pfm"))[0].astype(np.float32)).to(dev)
    Fm = torch.from_numpy(cv2.imread(os.path.join(a.cas, f"mask/{src:08d}_final.png"), 0) > 0).to(dev)
    img = cv2.imread(os.path.join(a.cas, f"images/{src:08d}.jpg"))
    if img.shape[:2] != D.shape: img = cv2.resize(img, (D.shape[1], D.shape[0]), interpolation=cv2.INTER_AREA)
    I = torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).to(dev).float() / 255.0          # H,W,3
    valid = D > 0
    Dp = F.pad(D[None, None], (a.radius,) * 4, mode="replicate")[0, 0]; Vp = F.pad(valid[None, None].float(), (a.radius,) * 4)[0, 0] > 0.5
    Ip = F.pad(I.permute(2, 0, 1)[None], (a.radius,) * 4, mode="replicate")[0].permute(1, 2, 0)
    # Planar-prior coherence (the ACMP/ACMMP idea): fit a plane d = a + b*dx + c*dy through the
    # SAME-COLOURED neighbours by least squares, then ask how far the centre pixel sits from
    # that plane. A slanted floor lies on its own plane and is coherent; a wall-coloured pixel
    # dragged to the luggage's depth is far from the wall's plane and is not. The previous
    # "neighbour depth within 1%" test flagged every slanted textureless surface instead.
    H, W = D.shape
    n = torch.zeros(H, W, device=dev); sx = torch.zeros_like(n); sy = torch.zeros_like(n); sxx = torch.zeros_like(n); sxy = torch.zeros_like(n); syy = torch.zeros_like(n)
    sd = torch.zeros_like(n); sdx = torch.zeros_like(n); sdy = torch.zeros_like(n)
    for dy in range(kk):
        for dx in range(kk):
            if dy == a.radius and dx == a.radius: continue
            Dq = Dp[dy:dy + H, dx:dx + W]; Vq = Vp[dy:dy + H, dx:dx + W]; Iq = Ip[dy:dy + H, dx:dx + W]
            w = (Vq & ((Iq - I).norm(dim=-1) < a.tau_c)).float()
            ox, oy = float(dx - a.radius), float(dy - a.radius)
            n += w; sx += w * ox; sy += w * oy; sxx += w * ox * ox; sxy += w * ox * oy; syy += w * oy * oy
            sd += w * Dq; sdx += w * Dq * ox; sdy += w * Dq * oy
    # solve the 3x3 normal equations per pixel
    A = torch.stack([torch.stack([n, sx, sy], -1), torch.stack([sx, sxx, sxy], -1), torch.stack([sy, sxy, syy], -1)], -2)
    b = torch.stack([sd, sdx, sdy], -1)
    # pixels with fewer than 3 same-coloured neighbours cannot define a plane; give them an
    # identity system (solution 0) so one singular element cannot abort the whole batch --
    # they are excluded below by min_same anyway
    ill = (n < 3)[..., None, None]
    A = torch.where(ill, torch.eye(3, device=dev).expand_as(A), A + 1e-4 * torch.eye(3, device=dev))
    b = torch.where(ill[..., 0], torch.zeros_like(b), b)
    coef = torch.linalg.solve(A, b[..., None])[..., 0]                # a, b, c ; plane value at centre = a
    plane_at_centre = coef[..., 0]
    resid = (D - plane_at_centre).abs() / D.clamp_min(1e-6)
    coh = Fm & valid & (n >= a.min_same) & (resid < a.tau_d)
    tot_strict += int(Fm.sum()); tot_coh += int(coh.sum())
    # to the target grid
    CAS[f] = torch.where(inb, D[cv_, cu], torch.zeros_like(UP[f])); STRICT[f] = inb & Fm[cv_, cu] & (CAS[f] > 0); COH[f] = STRICT[f] & coh[cv_, cu]
    if f in a.overlay_views:
        ov = img.copy(); ov[(Fm & ~coh).cpu().numpy()] = (0, 0, 255); nf = (~Fm).cpu().numpy(); ov[nf] = (ov[nf] * 0.3).astype(np.uint8)
        cv2.imwrite(str(out / "overlay" / f"view{f:03d}_incoherent_red.jpg"), ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if f % 33 == 0: print(f"  view {f}: strict {int(Fm.sum()):,}  coherent {int(coh.sum()):,} ({100*coh.sum()/max(Fm.sum(),1):.1f}%)", flush=True)
print(f"coherence: {tot_coh:,} of {tot_strict:,} strict CasDiffMVS pixels coherent ({100*tot_coh/max(tot_strict,1):.1f}%); incoherent = {tot_strict-tot_coh:,}", flush=True)

# 2) where to replace: coherent AND (MapAnything collapsed OR MapAnything hole)
# collapse relative to the surroundings: the two reconstructions carry a systematic offset
# (0.77% median), so subtract each pixel's local median offset (61x61) before thresholding
rel = torch.where((UP > 0) & (CAS > 0), (UP - CAS) / UP.clamp_min(1e-6), torch.zeros_like(UP))
valid2 = ((UP > 0) & (CAS > 0)).float()
local = F.avg_pool2d(rel[:, None], 61, 1, 30)[:, 0] / F.avg_pool2d(valid2[:, None], 61, 1, 30)[:, 0].clamp_min(1e-6)
# Upper bound on the collapse. A patch of wall dragged to the luggage's depth is coherent
# within itself, multi-view consistent, and nearer than MapAnything -- every local or
# consistency test passes it, which is how it came back in cloud 7. What separates it is
# magnitude: a slipper is 1.5-3% in front of the floor, a wheel 2-3%, while a stuck wall
# patch sits 20-50% in front of the real wall. Only small collapses are thin objects.
excess = rel - local
collapsed = COH & (UP > 0) & (excess > a.tau_rep) & (excess < a.tau_rep_max)
# a hole in MapAnything gives no depth to compare against; fill it from CasDiffMVS only if
# CasDiffMVS there is within tau_rep_max of MapAnything's local (61x61) depth, so a stuck
# patch cannot ride in through a hole either
up_local = F.avg_pool2d(torch.where(UP > 0, UP, torch.zeros_like(UP))[:, None], 61, 1, 30)[:, 0] / F.avg_pool2d((UP > 0).float()[:, None], 61, 1, 30)[:, 0].clamp_min(1e-6)
hole = COH & (UP == 0) & (up_local > 0) & (((up_local - CAS) / up_local.clamp_min(1e-6)).abs() < a.tau_rep_max)
REP = collapsed | hole
print(f"REPLACE with CasDiffMVS: {int(REP.sum()):,} px = {100*REP.sum()/max(STRICT.sum(),1):.1f}% of strict CasDiffMVS  (collapsed {int(collapsed.sum()):,}, MapAnything-hole {int(hole.sum()):,})", flush=True)
for f in a.overlay_views:
    src = f2s[f]; img = cv2.imread(os.path.join(a.cas, f"images/{src:08d}.jpg"))
    # draw REP on the 768x576 image by inverse-mapping: mark cas pixels hit by any REP target pixel
    m = torch.zeros(576, 768, dtype=torch.bool, device=dev); sel = REP[f]
    m[cv_[sel], cu[sel]] = True
    ov = img.copy(); ov[m.cpu().numpy()] = (0, 255, 0)
    cv2.imwrite(str(out / "overlay" / f"view{f:03d}_replaced_green.jpg"), ov, [cv2.IMWRITE_JPEG_QUALITY, 88])

# 3) MapAnything pixels: base gate, then veto by replaced CasDiffMVS pixels in neighbours
vv, uu = torch.meshgrid(torch.arange(Ht, device=dev, dtype=torch.float32), torch.arange(Wt, device=dev, dtype=torch.float32), indexing="ij")
REPD = torch.where(REP, CAS, torch.zeros_like(CAS))
keep = torch.zeros(V, Ht, Wt, dtype=torch.bool, device=dev); SRCO = torch.zeros(V, Ht, Wt, dtype=torch.uint8, device=dev); vetoed = 0
for ref_s, src_s in pairs.items():
    f = int(s2f[ref_s])
    cand = ~REP[f] & (UP[f] > 0) & UPG[f]
    d = UP[f]; x = (uu - Kt[f, 0, 2]) / Kt[f, 0, 0] * d; y = (vv - Kt[f, 1, 2]) / Kt[f, 1, 1] * d
    Xw = torch.stack([x, y, d], -1) @ C2Wt[f, :3, :3].T + C2Wt[f, :3, 3]
    veto = torch.zeros(Ht, Wt, dtype=torch.int32, device=dev)
    for sidx in src_s[: a.num_src]:
        j = int(s2f[int(sidx)])
        Xc = Xw @ W2C[j, :3, :3].T + W2C[j, :3, 3]; z = Xc[..., 2]
        u = (Xc[..., 0] / z.clamp_min(1e-6) * Kt[j, 0, 0] + Kt[j, 0, 2]).round().long(); v = (Xc[..., 1] / z.clamp_min(1e-6) * Kt[j, 1, 1] + Kt[j, 1, 2]).round().long()
        ib = (z > 1e-3) & (u >= 0) & (u < Wt) & (v >= 0) & (v < Ht)
        cj = REPD[j][v.clamp(0, Ht - 1), u.clamp(0, Wt - 1)]
        veto += (ib & (cj > 0) & (((z - cj).abs() / cj.clamp_min(1e-6)) > a.tau_d)).int()
    ma_keep = cand & (veto < a.veto_min); vetoed += int((cand & ~ma_keep).sum())
    keep[f] = REP[f] | ma_keep; SRCO[f] = torch.where(REP[f], 1, torch.where(ma_keep, 2, 0)).to(torch.uint8)
print(f"MapAnything vetoed by replaced pixels: {vetoed:,}", flush=True)
np.save(out / "keep.npy", keep.cpu().numpy()); np.save(out / "source.npy", SRCO.cpu().numpy())

DEPTH = torch.where(REP, CAS, UP)
xyz, col, srcl = [], [], []
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    yy, xx = torch.nonzero(keep[f], as_tuple=True); z = DEPTH[f][yy, xx].double()
    x = (xx.double() - K[f][0, 2]) / K[f][0, 0] * z; y = (yy.double() - K[f][1, 2]) / K[f][1, 1] * z
    pc = torch.stack([x, y, z], 1) @ torch.from_numpy(C2W[f][:3, :3]).to(dev).T + torch.from_numpy(C2W[f][:3, 3]).to(dev)
    xyz.append(pc.cpu().numpy()); col.append((g[yy, xx].clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()); srcl.append(SRCO[f][yy, xx].cpu().numpy())
xyz = np.concatenate(xyz); col = np.concatenate(col); srcl = np.concatenate(srcl); np.save(out / "point_source.npy", srcl)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "cloud 3 base; CasDiffMVS substituted only where colour-depth coherent and MapAnything collapsed (>tau_rep farther) or has a hole; replaced pixels veto MapAnything in >=2 views",
       "params": {k: v for k, v in vars(a).items() if k not in ("overlay_views",)},
       "strict_cas_px": int(STRICT.sum()), "coherent_px": int(COH.sum()), "replaced_px": int(REP.sum()), "replaced_collapsed": int(collapsed.sum()), "replaced_hole": int(hole.sum()),
       "replaced_frac_of_strict": float(REP.sum() / max(STRICT.sum(), 1)), "ma_vetoed": vetoed,
       "points": int(xyz.shape[0]), "points_from_cas": int((srcl == 1).sum()), "points_from_ma": int((srcl == 2).sum()),
       "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps({k: v for k, v in res.items() if k not in ("ply", "params")}, indent=2))
