#!/usr/bin/env python3
"""Replay the official CasDiffMVS fusion with the bridge pixels removed.

Everything is the upstream filter.py path, imported rather than rewritten:
depth_est_averaged over the source views, photo_mask & (geo_mask_sum >= 3),
back-projection with the reference camera. The single change is one extra AND:

    final_mask &= ~bridge_mask[view]

where bridge_mask marks kept pixels that sit inside a genuine silhouette window
(a near cluster and a far cluster both present) at a depth strictly between the
two -- the fattening band that reads as the wall stuck to the luggage.

Removal, not repair, because the user accepts geometric deletion as a policy and
a deleted bridge cannot come back as a bent surface. The replay is self-checked
against pc.ply: with the bridge masks disabled it must reproduce 36,845,039
points exactly, so any difference in the output is the bridge removal alone.
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


ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="/root/casdiffmvs_official_20260903/diffmvs_upstream")
ap.add_argument("--pair_folder", default="/root/casdiffmvs_official_20260903/mvs_P16k")
ap.add_argument("--out_folder", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
ap.add_argument("--bridge_dir", default="/root/bridge_masks")
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", default="debridged")
ap.add_argument("--expect_points", type=int, default=36845039)
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--photo_thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
ap.add_argument("--dataset", default="general")
a = ap.parse_args()
t0 = time.time()
sys.path.insert(0, a.repo); os.chdir(a.repo)
from datasets.data_io import read_pfm, read_camera_parameters, read_pair_file, read_img  # noqa: E402
from filter import check_geometric_consistency  # noqa: E402

out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
of = a.out_folder
pair_data = read_pair_file(os.path.join(a.pair_folder, "pair.txt"), a.dataset)

xyz_all, col_all = [], []
kept_official, removed, per_view = 0, 0, []
for ref_view, src_views in pair_data:
    ref_intr, ref_extr, depth_max, depth_min = read_camera_parameters(os.path.join(of, f"cams/{ref_view:08d}_cam.txt"))
    ref_img = read_img(os.path.join(of, f"images/{ref_view:08d}.jpg"))
    ref_depth = read_pfm(os.path.join(of, f"depth_est/{ref_view:08d}.pfm"))[0]
    c0 = read_pfm(os.path.join(of, f"conf0/{ref_view:08d}.pfm"))[0]
    c1 = read_pfm(os.path.join(of, f"conf1/{ref_view:08d}.pfm"))[0]
    c2 = read_pfm(os.path.join(of, f"conf2/{ref_view:08d}.pfm"))[0]
    photo_mask = (c0 > a.photo_thres[0]) & (c1 > a.photo_thres[1]) & (c2 > a.photo_thres[2])
    acc, gsum = [], 0
    for src_view in src_views:
        src_intr, src_extr, _, _ = read_camera_parameters(os.path.join(of, f"cams/{src_view:08d}_cam.txt"))
        src_depth = read_pfm(os.path.join(of, f"depth_est/{src_view:08d}.pfm"))[0]
        geo_mask, depth_reproj, _, _ = check_geometric_consistency(
            ref_depth, ref_intr, ref_extr, src_depth, src_intr, src_extr,
            depth_max, depth_min, a.geo_pixel_thres, a.geo_depth_thres)
        gsum = gsum + geo_mask.astype(np.int32); acc.append(depth_reproj)
    depth_avg = (sum(acc) + ref_depth) / (gsum + 1)
    final_mask = np.logical_and(photo_mask, gsum >= a.geo_mask_thres)
    kept_official += int(final_mask.sum())
    bridge = cv2.imread(os.path.join(a.bridge_dir, f"{ref_view:08d}_bridge.png"), 0) > 0
    keep = final_mask & ~bridge
    removed += int((final_mask & bridge).sum())
    per_view.append({"view": ref_view, "official": int(final_mask.sum()), "removed": int((final_mask & bridge).sum())})
    h, w = depth_avg.shape
    x, y = np.meshgrid(np.arange(w), np.arange(h))
    xs, ys, zs = x[keep], y[keep], depth_avg[keep]
    xyz_ref = np.linalg.inv(ref_intr) @ (np.vstack((xs, ys, np.ones_like(xs))) * zs)
    xyz_w = (np.linalg.inv(ref_extr) @ np.vstack((xyz_ref, np.ones_like(xs))))[:3]
    xyz_all.append(xyz_w.T.astype(np.float64))
    col = ref_img[keep]
    col_all.append((col * 255).astype(np.uint8) if col.dtype != np.uint8 else col)
    if ref_view % 20 == 0:
        print(f"  view {ref_view}: official {int(final_mask.sum())}  removed {int((final_mask & bridge).sum())}", flush=True)

assert kept_official == a.expect_points, f"replay {kept_official} != pc.ply {a.expect_points}"
print(f"self-check OK: official replay = {kept_official:,} = pc.ply", flush=True)
XYZ = np.concatenate(xyz_all); COL = np.concatenate(col_all)
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(XYZ)
pcd.colors = o3d.utility.Vector3dVector(COL.astype(np.float64) / 255.0)
ply = out / f"pc_{a.tag}.ply"
o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"purpose": "official CasDiffMVS fusion replayed with silhouette bridge pixels removed",
       "official_points": kept_official, "removed": removed, "removed_frac": removed / kept_official,
       "points": int(XYZ.shape[0]),
       "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
       "seconds": time.time() - t0, "per_view": per_view}
(out / f"result_{a.tag}.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps({k: v for k, v in res.items() if k != "per_view"}, indent=2))
