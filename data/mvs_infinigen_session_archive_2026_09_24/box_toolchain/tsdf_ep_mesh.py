#!/usr/bin/env python3
# [2026-09-17] Mesh variant of tsdf_ep_3mm.py (user: 看看 "Open3D 自己的 marching cubes、连通块过滤、补洞、Taubin 平滑,全是它的现成函数,
# 不自定阈值" 的版本). Same official-gate replay and the same VoxelBlockGrid integration; then, instead of extract_point_cloud:
#   1. vbg.extract_triangle_mesh(weight_threshold=1.0)                     (Open3D marching cubes; 1.0 = the same threshold as the
#      point pane / 09-08 recipe so the only variable is points-vs-mesh; Open3D's own default is 3.0)
#   2. cluster_connected_triangles + remove clusters with < 100 triangles   (Open3D tutorial geometry/mesh.html cell [23], verbatim constant)
#   3. o3d.t.geometry.TriangleMesh.fill_holes()                             (tensor API, default hole_size=1e6, as the docs example)
#   4. filter_smooth_taubin(number_of_iterations=10) + compute_vertex_normals (tutorial cell [11], verbatim constant)
# Each stage's vertex/triangle count is printed; both the no-fill and the filled variants are written so the fill step can be judged.
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
ap.add_argument("--int64_kernel", action="store_true", help="running on the int64-patched Open3D build (VoxelBlockGridImpl.h products widened): skip the int32 cap guard, record it in the json")
ap.add_argument("--block_res", type=int, default=16, help="VoxelBlockGrid block_resolution (09-08 recipe: 16; 4 keeps block_idx*res^3*3 < 2^31 on CPU, see guard below)")
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
    attr_dtypes=(o3c.float32, o3c.uint16, o3c.uint16),
    attr_channels=((1), (1), (3)),
    voxel_size=a.voxel, block_resolution=a.block_res, block_count=a.block_count, device=device)
trunc_mult = a.sdf_trunc / a.voxel

kept_total = 0
for ref_view, src_views in pair_data:
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
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)).to(device)
    cimg = o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(col))).to(device)
    intr = o3c.Tensor(np.asarray(ref_intr, dtype=np.float64), o3c.float64)
    extr = o3c.Tensor(np.asarray(ref_extr, dtype=np.float64), o3c.float64)   # cams store world->camera
    coords = vbg.compute_unique_block_coordinates(dimg, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    vbg.integrate(coords, dimg, cimg, intr, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    # Open3D kernel/VoxelBlockGridImpl.h:40 `using index_t = int;` and :269 `linear_idx = block_idx * resolution3 + voxel_idx`
    # (x3 colour channels): the CPU backend segfaults once active_blocks * res^3 * 3 >= 2^31 (measured 2026-09-17: res 16 dies
    # at 174,762 blocks, exactly 2^31/(4096*3)). Fail loudly instead of trusting a wrapped index.
    if not a.int64_kernel and vbg.hashmap().size() * (a.block_res ** 3) * 3 >= 2 ** 31:
        raise SystemExit(f"int32 index cap: {vbg.hashmap().size()} blocks x {a.block_res}^3 x 3 >= 2^31 (view {ref_view}); use a smaller --block_res")
    if ref_view % 20 == 0:
        print(f"  view {ref_view}: kept {int(final_mask.sum())}  running {kept_total:,}  blocks {vbg.hashmap().size()}", flush=True)

print(f"\nreplayed valid pixels: {kept_total:,}", flush=True)
if a.expect_points is not None:
    if kept_total != a.expect_points:
        raise SystemExit(f"ABORT: replay kept {kept_total} pixels but pc.ply has {a.expect_points}; "
                         "the inputs are not the ones that produced pc.ply")
    print(f"self-check OK: identical to pc.ply ({a.expect_points:,} vertices)", flush=True)

import time
def counts(m): return f"{len(m.vertices):,} v / {len(m.triangles):,} t"
t0 = time.time()
mesh = vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy()
print(f"[mc] marching cubes: {counts(mesh)}  colours={mesh.has_vertex_colors()}  {time.time()-t0:.0f}s", flush=True)
t0 = time.time()
triangle_clusters, cluster_n_triangles, cluster_area = mesh.cluster_connected_triangles()
triangle_clusters = np.asarray(triangle_clusters); cluster_n_triangles = np.asarray(cluster_n_triangles)
triangles_to_remove = cluster_n_triangles[triangle_clusters] < 100      # tutorial cell [23]
mesh.remove_triangles_by_mask(triangles_to_remove)                       # tutorial stops here; no extra remove_unreferenced_vertices
print(f"[cc] clusters={len(cluster_n_triangles):,} largest={cluster_n_triangles.max():,} removed tris={int(triangles_to_remove.sum()):,} -> {counts(mesh)}  {time.time()-t0:.0f}s", flush=True)
stages = {}
def finish(m, name):
    t = time.time()
    m = m.filter_smooth_taubin(number_of_iterations=10)                # tutorial cell [11]
    m.compute_vertex_normals()
    print(f"[taubin10+normals] {name}: {counts(m)}  {time.time()-t:.0f}s", flush=True)
    ply = out / f"tsdf_mesh_{a.tag}_v{a.voxel:g}_t{a.sdf_trunc:g}_{name}.ply"
    o3d.io.write_triangle_mesh(str(ply), m, write_ascii=False, compressed=False, write_vertex_normals=True, write_vertex_colors=True)
    stages[name] = {"vertices": len(m.vertices), "triangles": len(m.triangles), "ply": str(ply), "bytes": ply.stat().st_size}
    return m
m_nofill = finish(mesh, "nofill")
t0 = time.time()
tm = o3d.t.geometry.TriangleMesh.from_legacy(mesh)
tm_filled = tm.fill_holes()                                             # docs example: default hole_size
mesh_filled = tm_filled.to_legacy()
print(f"[fill_holes default] {counts(mesh)} -> {counts(mesh_filled)}  colours={mesh_filled.has_vertex_colors()}  {time.time()-t0:.0f}s", flush=True)
if not mesh_filled.has_vertex_colors():
    # fill_holes returned no colours: carry the original vertex colours over ONLY if the original vertices come back
    # unchanged and in order (verified, not assumed); hole vertices stay uncoloured (black). Otherwise leave it uncoloured.
    nv0 = len(mesh.vertices); nv1 = len(mesh_filled.vertices)
    same = nv1 >= nv0 and np.array_equal(np.asarray(mesh_filled.vertices)[:nv0], np.asarray(mesh.vertices))
    print(f"[fill_holes] colours dropped by the tensor API; original {nv0:,} vertices preserved in order: {same}; new vertices: {nv1-nv0:,}", flush=True)
    if same:
        cols = np.zeros((nv1, 3)); cols[:nv0] = np.asarray(mesh.vertex_colors)
        mesh_filled.vertex_colors = o3d.utility.Vector3dVector(cols)
m_filled = finish(mesh_filled, "filled")
res = {"purpose": "TSDF -> Open3D marching cubes -> tutorial cleaning (cluster<100, fill_holes default, taubin 10)",
       "out_folder": of, "views": len(pair_data), "voxel": a.voxel, "sdf_trunc": a.sdf_trunc, "block_res": a.block_res, "device": a.device, "int64_kernel": bool(a.int64_kernel), "open3d": o3d.__version__,
       "replayed_valid_pixels": kept_total, "expect_points": a.expect_points, "active_blocks": int(vbg.hashmap().size()), "stages": stages}
(out / f"result_mesh_{a.tag}.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
