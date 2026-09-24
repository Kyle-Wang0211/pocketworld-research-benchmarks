#!/usr/bin/env python3
# [2026-09-17] Copy of experiments/mapanything_casdiffmvs_ghosting_2026-09-03/scripts/tsdf_casdiffmvs.py for the full-training
# epoch snapshots: same official-gate replay (filter.py check_geometric_consistency, geo_mask_thres 3 / 1 px / 1 %), same Open3D
# tensor VoxelBlockGrid (block_resolution 16), 3 mm voxel / 40 mm truncation as the 09-08 "过滤版" page. Changes: --device
# (CPU fallback), skip views with zero surviving pixels (09-08 坑 2), defaults pointing at this box's layout.
"""TSDF fusion of the official CasDiffMVS depths -- the same depths that produced
pc.ply, not the point cloud re-meshed.

pc.ply is not built from depth_est. filter.py back-projects `depth_est_averaged`,
the mean of the reference depth and every source view's depth reprojected onto
it, masked by `final_mask = photo_mask & (geo_mask_sum >= 3)`. Feeding TSDF the
raw depth_est instead would silently change the input, so the averaging and the
masks are reproduced here by importing the upstream functions themselves rather
than reimplementing them.

The self-check is the point count: the number of pixels passing final_mask across
all 132 views must equal the vertex count of pc.ply exactly. If it does not, the
inputs differ and nothing downstream means anything.

Fusion settings match tsdf_anchored.py so the two TSDF clouds are comparable.
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
import open3d.core as o3c


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="/root/diffmvs")
ap.add_argument("--pair_folder", default="/root/mvs_P16k")
ap.add_argument("--out_folder", default="/root/arm_full_ep0_tsdf")
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--voxel", type=float, default=0.0126)
ap.add_argument("--sdf_trunc", type=float, default=0.168)
ap.add_argument("--depth_scale", type=float, default=5000.0)
ap.add_argument("--depth_max", type=float, default=30.0)
ap.add_argument("--block_count", type=int, default=200000)
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--photo_thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
ap.add_argument("--dataset", default="general")
ap.add_argument("--expect_points", type=int, default=None, help="vertex count of pc.ply; the run aborts if the replay disagrees")
ap.add_argument("--device", default="CUDA:0", help="CUDA:0 (default) or CPU:0")
a = ap.parse_args()
t0 = time.time()
sys.path.insert(0, a.repo)
os.chdir(a.repo)
from datasets.data_io import read_pfm, read_camera_parameters, read_pair_file, read_img  # noqa: E402
from filter import check_geometric_consistency  # noqa: E402

out = Path(a.out_dir)
out.mkdir(parents=True, exist_ok=True)
of = a.out_folder
pair_data = read_pair_file(os.path.join(a.pair_folder, "pair.txt"), a.dataset)
print(f"{len(pair_data)} reference views", flush=True)

device = o3c.Device(a.device)
vbg = o3d.t.geometry.VoxelBlockGrid(
    attr_names=("tsdf", "weight", "color"),
    attr_dtypes=(o3c.float32, o3c.float32, o3c.float32) if os.environ.get("ATTR_F32") else (o3c.float32, o3c.uint16, o3c.uint16),
    attr_channels=((1), (1), (3)),
    voxel_size=a.voxel, block_resolution=int(os.environ.get("BLOCK_RES", "16")), block_count=a.block_count, device=device)
trunc_mult = a.sdf_trunc / a.voxel

kept_total = 0
_order = os.environ.get("VIEW_ORDER", "")
if _order == "rev": pair_data = list(reversed(pair_data))
elif _order.startswith("first:"):
    _f = int(_order.split(":")[1]); pair_data = [t for t in pair_data if t[0] == _f] + [t for t in pair_data if t[0] != _f]
for ref_view, src_views in pair_data:
    if os.environ.get("ONLY_VIEW") and ref_view != int(os.environ["ONLY_VIEW"]): continue
    if os.environ.get("SKIP_VIEW") and ref_view == int(os.environ["SKIP_VIEW"]): print(f"  view {ref_view}: SKIPPED by env", flush=True); continue
    ref_intr, ref_extr, depth_max, depth_min = read_camera_parameters(
        os.path.join(of, "cams/{:0>8}_cam.txt".format(ref_view)))
    ref_img = read_img(os.path.join(of, "images/{:0>8}.jpg".format(ref_view)))
    ref_depth = read_pfm(os.path.join(of, "depth_est/{:0>8}.pfm".format(ref_view)))[0]

    c0 = read_pfm(os.path.join(of, "conf0/{:0>8}.pfm".format(ref_view)))[0]
    c1 = read_pfm(os.path.join(of, "conf1/{:0>8}.pfm".format(ref_view)))[0]
    c2 = read_pfm(os.path.join(of, "conf2/{:0>8}.pfm".format(ref_view)))[0]
    photo_mask = (c0 > a.photo_thres[0]) & (c1 > a.photo_thres[1]) & (c2 > a.photo_thres[2])

    acc, gsum = [], 0
    for src_view in src_views:
        src_intr, src_extr, _, _ = read_camera_parameters(
            os.path.join(of, "cams/{:0>8}_cam.txt".format(src_view)))
        src_depth = read_pfm(os.path.join(of, "depth_est/{:0>8}.pfm".format(src_view)))[0]
        geo_mask, depth_reproj, _, _ = check_geometric_consistency(
            ref_depth, ref_intr, ref_extr, src_depth, src_intr, src_extr,
            depth_max, depth_min, a.geo_pixel_thres, a.geo_depth_thres)
        gsum = gsum + geo_mask.astype(np.int32)
        acc.append(depth_reproj)
    depth_avg = (sum(acc) + ref_depth) / (gsum + 1)
    final_mask = np.logical_and(photo_mask, gsum >= a.geo_mask_thres)
    kept_total += int(final_mask.sum())

    if int(final_mask.sum()) == 0:
        print(f"  view {ref_view}: no pixel survives the gate, skipped", flush=True)
        continue
    d = np.where(final_mask, depth_avg, 0.0).astype(np.float64)
    d = np.where(d > a.depth_max, 0.0, d)
    d16 = np.round(d * a.depth_scale).astype(np.uint16)
    col = ref_img
    if col.dtype != np.uint8:
        col = np.clip(col * 255.0, 0, 255).astype(np.uint8)
    if col.shape[:2] != d16.shape:
        import cv2
        col = cv2.resize(col, (d16.shape[1], d16.shape[0]), interpolation=cv2.INTER_AREA)
    nz=d16[d16>0]; print(f"  view {ref_view}: d16 n={nz.size} min={nz.min() if nz.size else -1} max={nz.max() if nz.size else -1} shape={d16.shape} col={col.shape} {col.dtype}", flush=True)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)).to(device)
    cimg = o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(col))).to(device)
    intr = o3c.Tensor(np.asarray(ref_intr, dtype=np.float64), o3c.float64)
    extr = o3c.Tensor(np.asarray(ref_extr, dtype=np.float64), o3c.float64)   # cams store world->camera
    coords = vbg.compute_unique_block_coordinates(dimg, intr, extr, a.depth_scale, a.depth_max, trunc_mult); print(f"  coords {coords.shape}", flush=True)
    if os.environ.get("NO_COLOR"): vbg.integrate(coords, dimg, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    else: vbg.integrate(coords, dimg, cimg, intr, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    print("  integrated", flush=True)
    if True:
        print(f"  view {ref_view}: kept {int(final_mask.sum())}  running {kept_total:,}  blocks {vbg.hashmap().size()}", flush=True)

print(f"\nreplayed valid pixels: {kept_total:,}", flush=True)
if a.expect_points is not None:
    if kept_total != a.expect_points:
        raise SystemExit(f"ABORT: replay kept {kept_total} pixels but pc.ply has {a.expect_points}; "
                         "the inputs are not the ones that produced pc.ply")
    print(f"self-check OK: identical to pc.ply ({a.expect_points:,} vertices)", flush=True)

pcd = vbg.extract_point_cloud(weight_threshold=1.0, estimated_point_number=-1).to_legacy()
ply = out / f"tsdf_casdiffmvs_{a.tag}_v{a.voxel:g}_t{a.sdf_trunc:g}.ply"
o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"purpose": "TSDF fusion of the official CasDiffMVS depth_est_averaged + final_mask (the exact inputs of pc.ply)",
       "out_folder": of, "views": len(pair_data), "voxel": a.voxel, "sdf_trunc": a.sdf_trunc,
       "geo_mask_thres": a.geo_mask_thres, "geo_pixel_thres": a.geo_pixel_thres,
       "geo_depth_thres": a.geo_depth_thres, "photo_thres": a.photo_thres,
       "replayed_valid_pixels": kept_total, "expect_points": a.expect_points,
       "active_blocks": int(vbg.hashmap().size()), "points": len(pcd.points),
       "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
       "seconds": time.time() - t0}
(out / f"result_{a.tag}.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps(res, indent=2))
