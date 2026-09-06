#!/usr/bin/env python3
"""Per-pixel hybrid with COLMAP PatchMatch as the MVS engine: COLMAP's geometrically
consistent depth where it has one, upsampled anchored MapAnything depth everywhere
else, then the official consistency gate over the mixture.

Same rule as the CasDiffMVS hybrid (cloud 4); only the MVS engine changes. The
sticking was shown to be independent of CasDiffMVS's resolution, i.e. an
algorithm-level behaviour of its learned cost-volume regulariser. COLMAP's
PatchMatch has no learned regulariser and is known for crisp depth edges, so
swapping the engine is the universal move -- no thresholds are touched.

Why. Upsampling closed the density gap and the slippers stayed slightly
collapsed, so the collapse is in the 518 depth itself -- thin structures
regressed toward the background, the classic weak spot of feed-forward depth.
That information is absent from MapAnything's output and cannot be
post-processed back. CasDiffMVS has it wherever its photometric gate held.

So each view's depth map is assembled pixel by pixel on the 777x588 upright
grid: CasDiffMVS's depth_est resampled through the same upright/landscape
mapping used all campaign (a 90-degree image rotation leaves per-pixel z
untouched, so the COLMAP-derived upright intrinsics apply unchanged), and the
upsampled anchored depth where CasDiffMVS's final_mask is false. The gate then
runs on the mixture, so a flat MapAnything slipper in one view competes with
CasDiffMVS's solid one in the others and loses.

Recorded: the relative depth step across the seam where the two sources meet,
and a per-pixel source map. Known cost: CasDiffMVS's wall-sticking returns
inside its coverage. That trade is the user's to judge.
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
from filter import check_geometric_consistency  # noqa: E402
from datasets.data_io import read_pfm  # noqa: E402


def read_colmap_map(path):
    """COLMAP .bin depth/normal map: ascii header 'w&h&c&' then float32 row-major."""
    with open(path, "rb") as f:
        hdr = b""
        while hdr.count(b"&") < 3:
            hdr += f.read(1)
        w, h, c = [int(x) for x in hdr.decode().split("&")[:3]]
        arr = np.fromfile(f, dtype=np.float32, count=w * h * c).reshape(h, w, c)
    return arr[..., 0] if c == 1 else arr


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
ap.add_argument("--dense", default="/root/colmap_official_dense_411_20260901_v4/dense", help="COLMAP dense workspace (images/, stereo/depth_maps/*.geometric.bin)")
ap.add_argument("--cas_w", type=int, default=2000)
ap.add_argument("--cas_h", type=int, default=1500)
ap.add_argument("--up_depth", default="/root/up15_gated_20260906/depth_up.npy", help="upsampled anchored depth, (V,777,588)")
ap.add_argument("--scale", type=float, default=1.5)
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="hybrid_gated")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
UP = np.load(a.up_depth).astype(np.float64)                         # V,Ht,Wt
V, Ht, Wt = UP.shape; Hm, Wm = 518, 392; s = a.scale
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
EXT = np.stack([np.linalg.inv(C2W[i]) for i in range(V)])
s2f = json.load(open(a.mapping)); f2s = {int(f): src for src, f in enumerate(s2f)}

# target (upright 777x588) pixel -> native -> upright 1500x2000 -> landscape 2000x1500 -> CasDiffMVS 768x576
vt, ut = np.meshgrid(np.arange(Ht, dtype=np.float64), np.arange(Wt, dtype=np.float64), indexing="ij")
un = (ut + 0.5) / s - 0.5; vn = (vt + 0.5) / s - 0.5
s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
x_l = y15; y_l = 1500.0 - 1.0 - x15
# CasDiffMVS grid of any size (768x576 or 1536x1152): same landscape crop, scaled
x768 = (x_l + 0.5) * (a.cas_w / 2000.0) - 0.5; y576 = (y_l + 0.5) * (a.cas_h / 1500.0) - 0.5
cu = np.clip(np.round(x768).astype(int), 0, a.cas_w - 1); cv = np.clip(np.round(y576).astype(int), 0, a.cas_h - 1)
inb = (x768 >= -0.5) & (x768 < a.cas_w - 0.5) & (y576 >= -0.5) & (y576 < a.cas_h - 0.5)
photo_grid = torch.from_numpy(np.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1).astype(np.float32))[None].to(dev)

depth = np.zeros((V, Ht, Wt), np.float64); source = np.zeros((V, Ht, Wt), np.uint8)
seam = []
for f in range(V):
    cd = read_colmap_map(os.path.join(a.dense, "stereo", "depth_maps", f"{names[f]}.geometric.bin")).astype(np.float64)
    assert cd.shape == (a.cas_h, a.cas_w), (cd.shape, a.cas_h, a.cas_w)
    cas_d = np.where(inb, cd[cv, cu], 0.0); cas_m = inb & (cas_d > 0)          # geometric.bin > 0 = passed COLMAP's own consistency
    ma_d = UP[f]; ma_m = ma_d > 0
    d = np.where(cas_m, cas_d, np.where(ma_m, ma_d, 0.0))
    depth[f] = d; source[f] = np.where(cas_m, 1, np.where(ma_m, 2, 0)).astype(np.uint8)
    # seam: CasDiffMVS pixels with a MapAnything-only 4-neighbour; compare the two sources at the same pixel
    er = cv2.erode(cas_m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    bnd = cas_m & ~er & ma_m
    if bnd.any(): seam.append(((ma_d[bnd] - cas_d[bnd]) / cas_d[bnd]))
    if f % 33 == 0: print(f"  view {f}: cas {int(cas_m.sum()):,}  ma-fill {int((~cas_m & ma_m).sum()):,}", flush=True)
seam = np.concatenate(seam)
valid = depth > 0
print(f"hybrid assembled: cas {int((source==1).sum()):,}  ma {int((source==2).sum()):,}  "
      f"seam rel step p50 {np.median(seam)*100:+.2f}%  |p50| {np.median(np.abs(seam))*100:.2f}%  |p90| {np.percentile(np.abs(seam),90)*100:.2f}%", flush=True)
np.save(out / "depth_hybrid.npy", depth.astype(np.float32)); np.save(out / "source.npy", source)

lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; srcs = []
    for j in range(k): srcs.append(int(lines[p])); p += 2
    pairs[ref_s] = srcs
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
pc = int((gate & (source == 1)).sum()); pm = int((gate & (source == 2)).sum())
print(f"gate: {int(gate.sum()):,} of {int(valid.sum()):,} pass ({100*gate.sum()/valid.sum():.1f}%): from CasDiffMVS {pc:,} ({100*pc/max((source==1).sum(),1):.1f}% of its px), from MapAnything {pm:,} ({100*pm/max((source==2).sum(),1):.1f}%)", flush=True)

xyz, col, srcs_out = [], [], []
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    rgb8 = (g.clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()
    yy, xx = np.nonzero(gate[f]); z = depth[f][yy, xx]
    x = (xx - K[f][0, 2]) / K[f][0, 0] * z; y = (yy - K[f][1, 2]) / K[f][1, 1] * z
    pcx = np.stack([x, y, z, np.ones_like(z)], 1)
    xyz.append((C2W[f] @ pcx.T).T[:, :3]); col.append(rgb8[gate[f]]); srcs_out.append(source[f][gate[f]])
xyz = np.concatenate(xyz); col = np.concatenate(col); srcs_out = np.concatenate(srcs_out)
np.save(out / "point_source.npy", srcs_out)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "per-pixel hybrid (COLMAP PatchMatch geometric depth where present, upsampled anchored MapAnything elsewhere) + official gate, delete only",
       "grid": [Ht, Wt], "px_cas": int((source == 1).sum()), "px_ma": int((source == 2).sum()),
       "seam_rel_step_p50": float(np.median(seam)), "seam_abs_p50": float(np.median(np.abs(seam))), "seam_abs_p90": float(np.percentile(np.abs(seam), 90)),
       "gate_pass": int(gate.sum()), "gate_pass_frac": float(gate.sum() / valid.sum()), "pass_from_cas": pc, "pass_from_ma": pm,
       "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps(res, indent=2))
