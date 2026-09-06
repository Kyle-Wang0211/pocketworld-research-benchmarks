#!/usr/bin/env python3
"""Hysteresis gate on the upsampled anchored MapAnything depth (cloud 3's input).

Same rule as hysteresis_gate.py for CasDiffMVS: strict seeds (>= 3 views within
1 px / 1%), loose growth (2 px / 2%) only into connected regions that contain a
seed, no interpolation, every kept pixel carries its own depth. The walls are
MapAnything's territory, and the holes the user sees in otherwise complete walls
are pixels where the 132 views disagree by slightly more than 1% while their
neighbours do not -- exactly what hysteresis is for. Isolated loose blobs, which
would be ghost layers, never touch a seed and are dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def enclosed_holes(mask, max_px):
    n, lab, stats, _ = cv2.connectedComponentsWithStats((~mask).astype(np.uint8), connectivity=8)
    H, W = mask.shape; cnt = area = 0
    for i in range(1, n):
        x, y, w, h, a_ = stats[i]
        if a_ <= max_px and x > 0 and y > 0 and x + w < W and y + h < H: cnt += 1; area += int(a_)
    return cnt, area


ap = argparse.ArgumentParser()
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--images", default="/root/imgs132_up")
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--pair", default="/root/casdiffmvs_official_20260903/mvs_P16k/pair.txt")
ap.add_argument("--up_depth", default="/root/up15_gated_20260906/depth_up.npy")
ap.add_argument("--scale", type=float, default=1.5)
ap.add_argument("--num_src", type=int, default=9)
ap.add_argument("--geo_strict", type=float, nargs=2, default=[1.0, 0.01])
ap.add_argument("--geo_loose", type=float, nargs=2, default=[2.0, 0.02])
ap.add_argument("--geo_views", type=int, default=3)
ap.add_argument("--hole_px", type=int, default=3000)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="up15_hyst")
a = ap.parse_args()
t0 = time.time(); dev = "cuda"
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
depth = np.load(a.up_depth).astype(np.float64); valid = depth > 0
V, Ht, Wt = depth.shape; Hm, Wm = 518, 392; s = a.scale
K0, C2W = build_ref_cameras(names, a.images, a.colmap_sparse)
K = K0.copy(); K[:, 0, 0] *= s; K[:, 1, 1] *= s; K[:, 0, 2] = K[:, 0, 2] * s + (s - 1) / 2; K[:, 1, 2] = K[:, 1, 2] * s + (s - 1) / 2
EXT = np.stack([np.linalg.inv(C2W[i]) for i in range(V)])
s2f = json.load(open(a.mapping)); lines = open(a.pair).read().split(); n_pair = int(lines[0]); p = 1; pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1; k = int(lines[p]); p += 1; srcs = []
    for j in range(k): srcs.append(int(lines[p])); p += 2
    pairs[ref_s] = srcs
keep = np.zeros(valid.shape, dtype=bool); T = dict(strict=0, loose=0, final=0, grown=0, holes_before=0, holes_after=0, hole_px_before=0, hole_px_after=0, dropped_isolated=0)
for ref_s, src_s in pairs.items():
    f = int(s2f[ref_s]); dref = depth[f]
    dmin = float(np.percentile(dref[valid[f]], 0.05)); dmax = float(np.percentile(dref[valid[f]], 99.95))
    gs = np.zeros(dref.shape, np.int32); gl = np.zeros(dref.shape, np.int32)
    for sidx in src_s[: a.num_src]:
        j = int(s2f[int(sidx)])
        m_s, _, _, _ = check_geometric_consistency(dref, K[f], EXT[f], depth[j], K[j], EXT[j], dmax, dmin, a.geo_strict[0], a.geo_strict[1])
        m_l, _, _, _ = check_geometric_consistency(dref, K[f], EXT[f], depth[j], K[j], EXT[j], dmax, dmin, a.geo_loose[0], a.geo_loose[1])
        gs += m_s.astype(np.int32); gl += m_l.astype(np.int32)
    strict = valid[f] & (gs >= a.geo_views); loose = valid[f] & (gl >= a.geo_views)
    n, lab = cv2.connectedComponents(loose.astype(np.uint8), connectivity=8)
    seeded = np.zeros(n, dtype=bool); seeded[np.unique(lab[strict & loose])] = True; seeded[0] = False
    final = strict | (loose & seeded[lab]); keep[f] = final
    hb, hpb = enclosed_holes(strict, a.hole_px); ha, hpa = enclosed_holes(final, a.hole_px)
    T["strict"] += int(strict.sum()); T["loose"] += int(loose.sum()); T["final"] += int(final.sum()); T["grown"] += int((final & ~strict).sum())
    T["dropped_isolated"] += int((loose & ~final).sum()); T["holes_before"] += hb; T["holes_after"] += ha; T["hole_px_before"] += hpb; T["hole_px_after"] += hpa
    if ref_s % 33 == 0: print(f"  ref {ref_s}: strict {int(strict.sum()):,} +grown {int((final & ~strict).sum()):,} holes {hb}->{ha}", flush=True)
np.save(out / "keep.npy", keep)
print(f"strict {T['strict']:,} -> final {T['final']:,} (+{T['grown']:,}, isolated dropped {T['dropped_isolated']:,}); holes {T['holes_before']:,}->{T['holes_after']:,}, px {T['hole_px_before']:,}->{T['hole_px_after']:,}", flush=True)
s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
vt, ut = torch.meshgrid(torch.arange(Ht, device=dev, dtype=torch.float32), torch.arange(Wt, device=dev, dtype=torch.float32), indexing="ij")
un = (ut + 0.5) / s - 0.5; vn = (vt + 0.5) / s - 0.5
x15 = (un + 0.5) / s_m - 0.5; y15 = (vn + 0.5 + off_v) / s_m - 0.5
photo_grid = torch.stack([2 * x15 / 1499.0 - 1, 2 * y15 / 1999.0 - 1], -1)[None]
xyz, col = [], []
for f in range(V):
    photo = torch.from_numpy(np.asarray(PILImage.open(f"{a.images}/{names[f]}").convert("RGB"), dtype=np.float32) / 255.0).to(dev)
    g = F.grid_sample(photo.permute(2, 0, 1)[None], photo_grid, mode="bilinear", align_corners=True, padding_mode="border")[0].permute(1, 2, 0)
    rgb8 = (g.clamp(0, 1) * 255 + 0.5).byte().cpu().numpy()
    yy, xx = np.nonzero(keep[f]); z = depth[f][yy, xx]
    x = (xx - K[f][0, 2]) / K[f][0, 0] * z; y = (yy - K[f][1, 2]) / K[f][1, 1] * z
    pc = np.stack([x, y, z, np.ones_like(z)], 1); xyz.append((C2W[f] @ pc.T).T[:, :3]); col.append(rgb8[keep[f]])
xyz = np.concatenate(xyz); col = np.concatenate(col)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"mapanything_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "upsampled anchored MapAnything depth + hysteresis gate (strict seeds 1px/1%, loose growth 2px/2%, connected)", **T,
       "grown_frac": T["grown"] / max(T["strict"], 1), "hole_px_reduction": 1 - T["hole_px_after"] / max(T["hole_px_before"], 1),
       "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps({k: v for k, v in res.items() if k != "ply"}, indent=2))
