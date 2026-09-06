#!/usr/bin/env python3
"""Hysteresis fusion for CasDiffMVS: two thresholds and spatial connectivity,
so a surface that is 90% consistent does not lose isolated pixels in its middle.

The official filter.py judges every pixel on its own: photometric confidence
above (0.3, 0.5, 0.5) AND geometric agreement in >= 3 source views within
1 px / 1%. A specular patch on the luggage, a grazing strip of floor, or a
pixel whose best three sources happen to be blurred fails that test while
everything around it passes -- and the eye reads the result as a hole punched
into an otherwise complete surface.

A surface is spatially coherent, and the gate can use that. Canny's rule:
pixels passing the STRICT test are seeds; pixels passing only a LOOSE test
(confidence halved, 2 px / 2%) are kept when they belong to a connected region
that contains a seed, and dropped when they float on their own. Nothing is
interpolated or invented: every kept pixel carries its own measured depth and
still agrees with >= 3 views, only under the looser tolerance. Isolated loose
blobs -- the ones that would be ghosts -- never touch a seed and are discarded.

Depth averaging stays exactly as filter.py does it, over the strict masks.
Hole statistics (enclosed background components smaller than --hole_px inside
each view's mask) are reported before and after, so the effect is a number
rather than an impression.
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


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def enclosed_holes(mask: np.ndarray, max_px: int):
    """count and area of background components fully inside the mask, smaller than max_px"""
    n, lab, stats, _ = cv2.connectedComponentsWithStats((~mask).astype(np.uint8), connectivity=8)
    H, W = mask.shape
    cnt = area = 0
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a <= max_px and x > 0 and y > 0 and x + w < W and y + h < H:
            cnt += 1; area += int(a)
    return cnt, area


ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="/root/casdiffmvs_official_20260903/diffmvs_upstream")
ap.add_argument("--pair_folder", default="/root/casdiffmvs_official_20260903/mvs_P16k")
ap.add_argument("--out_folder", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="hyst")
ap.add_argument("--photo_strict", type=float, nargs=3, default=[0.3, 0.5, 0.5])
ap.add_argument("--photo_loose", type=float, nargs=3, default=[0.15, 0.3, 0.3])
ap.add_argument("--geo_strict", type=float, nargs=2, default=[1.0, 0.01], help="pixel, relative depth")
ap.add_argument("--geo_loose", type=float, nargs=2, default=[2.0, 0.02])
ap.add_argument("--geo_views", type=int, default=3)
ap.add_argument("--hole_px", type=int, default=2000)
ap.add_argument("--dataset", default="general")
a = ap.parse_args()
t0 = time.time()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm, read_camera_parameters, read_pair_file, read_img  # noqa: E402
from filter import check_geometric_consistency  # noqa: E402

out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True); (out / "mask").mkdir(exist_ok=True)
of = a.out_folder
pair_data = read_pair_file(os.path.join(a.pair_folder, "pair.txt"), a.dataset)
xyz_all, col_all = [], []
T = dict(strict=0, loose=0, final=0, grown=0, holes_before=0, holes_after=0, hole_px_before=0, hole_px_after=0)
for ref_view, src_views in pair_data:
    ref_intr, ref_extr, depth_max, depth_min = read_camera_parameters(os.path.join(of, f"cams/{ref_view:08d}_cam.txt"))
    ref_img = read_img(os.path.join(of, f"images/{ref_view:08d}.jpg"))
    ref_depth = read_pfm(os.path.join(of, f"depth_est/{ref_view:08d}.pfm"))[0]
    c = [read_pfm(os.path.join(of, f"conf{i}/{ref_view:08d}.pfm"))[0] for i in range(3)]
    photo_s = (c[0] > a.photo_strict[0]) & (c[1] > a.photo_strict[1]) & (c[2] > a.photo_strict[2])
    photo_l = (c[0] > a.photo_loose[0]) & (c[1] > a.photo_loose[1]) & (c[2] > a.photo_loose[2])
    acc, gs, gl = [], 0, 0
    for src_view in src_views:
        src_intr, src_extr, _, _ = read_camera_parameters(os.path.join(of, f"cams/{src_view:08d}_cam.txt"))
        src_depth = read_pfm(os.path.join(of, f"depth_est/{src_view:08d}.pfm"))[0]
        m_s, drep, _, _ = check_geometric_consistency(ref_depth, ref_intr, ref_extr, src_depth, src_intr, src_extr, depth_max, depth_min, a.geo_strict[0], a.geo_strict[1])
        m_l, _, _, _ = check_geometric_consistency(ref_depth, ref_intr, ref_extr, src_depth, src_intr, src_extr, depth_max, depth_min, a.geo_loose[0], a.geo_loose[1])
        gs = gs + m_s.astype(np.int32); gl = gl + m_l.astype(np.int32); acc.append(drep)
    depth_avg = (sum(acc) + ref_depth) / (gs + 1)                      # official averaging, strict masks
    strict = photo_s & (gs >= a.geo_views)
    loose = photo_l & (gl >= a.geo_views)
    # hysteresis: keep loose components that contain at least one strict pixel
    n, lab = cv2.connectedComponents(loose.astype(np.uint8), connectivity=8)
    seeded = np.zeros(n, dtype=bool); seeded[np.unique(lab[strict & loose])] = True; seeded[0] = False
    final = strict | (loose & seeded[lab])
    hb, hpb = enclosed_holes(strict, a.hole_px); ha, hpa = enclosed_holes(final, a.hole_px)
    T["strict"] += int(strict.sum()); T["loose"] += int(loose.sum()); T["final"] += int(final.sum()); T["grown"] += int((final & ~strict).sum())
    T["holes_before"] += hb; T["holes_after"] += ha; T["hole_px_before"] += hpb; T["hole_px_after"] += hpa
    cv2.imwrite(str(out / "mask" / f"{ref_view:08d}_final.png"), (final * 255).astype(np.uint8))
    h, w = depth_avg.shape; x, y = np.meshgrid(np.arange(w), np.arange(h))
    xs, ys, zs = x[final], y[final], depth_avg[final]
    xyz_ref = np.linalg.inv(ref_intr) @ (np.vstack((xs, ys, np.ones_like(xs))) * zs)
    xyz_all.append((np.linalg.inv(ref_extr) @ np.vstack((xyz_ref, np.ones_like(xs))))[:3].T.astype(np.float64))
    col = ref_img[final]; col_all.append((col * 255).astype(np.uint8) if col.dtype != np.uint8 else col)
    if ref_view % 20 == 0:
        print(f"  view {ref_view}: strict {int(strict.sum()):,}  +grown {int((final & ~strict).sum()):,}  holes {hb}->{ha} ({hpb:,}->{hpa:,} px)", flush=True)
xyz = np.concatenate(xyz_all); col = np.concatenate(col_all)
pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(xyz); pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
ply = out / f"pc_{a.tag}.ply"; o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"tag": a.tag, "purpose": "CasDiffMVS official fusion with hysteresis: strict seeds, loose growth into seeded connected components; no interpolation",
       "photo_strict": a.photo_strict, "photo_loose": a.photo_loose, "geo_strict": a.geo_strict, "geo_loose": a.geo_loose, "geo_views": a.geo_views,
       **T, "grown_frac": T["grown"] / max(T["strict"], 1), "hole_px_reduction": 1 - T["hole_px_after"] / max(T["hole_px_before"], 1),
       "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps({k: v for k, v in res.items() if k != "ply"}, indent=2))
