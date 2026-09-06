#!/usr/bin/env python3
"""TSDF fusion of the ANCHORED depths in the COLMAP world frame.

The existing TSDF cloud was fused in the model's own frame from the raw
MapAnything depths, so putting it beside the current versions would change two
things at once -- the frame and the base -- and the synced cameras would not even
line up. Fusing the anchored depths with the production COLMAP cameras leaves
exactly one variable between this and the anchored cloud: whether TSDF ran.

Fusion settings are unchanged from tsdf_fuse_gpu.py (Open3D VoxelBlockGrid on
CUDA, 3 mm voxels, 40 mm truncation, every voxel with weight >= 1 kept, no
downsampling). The anchored depth map already carries the official mask, since
export_native_anchored writes zero wherever the mask is false.

Worth being explicit about what this pane is: TSDF resamples onto a voxel grid,
so it does NOT keep the original per-pixel points, and the point count changes.
It cannot satisfy the standing requirement for native per-pixel points; it is
here to be looked at, not to be shipped.
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
import torch
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402


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
ap.add_argument("--depth", required=True)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--voxel", type=float, default=0.003)
ap.add_argument("--sdf_trunc", type=float, default=0.04)
ap.add_argument("--depth_max", type=float, default=12.0)
ap.add_argument("--depth_scale", type=float, default=5000.0)
ap.add_argument("--block_count", type=int, default=200000)
ap.add_argument("--weight_threshold", type=float, default=1.0)
a = ap.parse_args()
t0 = time.time()
out = Path(a.out_dir)
out.mkdir(parents=True, exist_ok=True)

saved = Path(a.saved)
info = json.load(open(saved / "info.json"))
names = [m["name"] for m in info["image_manifest"]]
depth = np.load(a.depth).astype(np.float32)
rgb = np.load(saved / "img_no_norm.npy")
V, H, W = depth.shape

cams, imgs, _ = read_model(a.colmap_sparse, ext=".bin")
by_name = {im.name: im for im in imgs.values()}
views = []
for n in names:
    im = by_name[n]
    cam = cams[im.camera_id]
    fx, fy, cx, cy = cam.params
    _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
    s = 1500.0 / 3024.0
    K15 = np.array([[fxu * s, 0, cxu * s], [0, fyu * s, cyu * s], [0, 0, 1]], dtype=np.float32)
    R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
    w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = t
    c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
    pil = PILImage.open(Path(a.images) / n).convert("RGB")
    views.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)),
                  "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w),
                  "is_metric_scale": torch.tensor([False])})
proc = preprocess_inputs(views)
K = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
c2w = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])
print(f"{V} views {H}x{W}; COLMAP focal {K[0,0,0]:.1f} px; depth p50 {np.median(depth[depth>0]):.3f} m", flush=True)

device = o3c.Device("CUDA:0")
vbg = o3d.t.geometry.VoxelBlockGrid(
    attr_names=("tsdf", "weight", "color"),
    attr_dtypes=(o3c.float32, o3c.uint16, o3c.uint16),
    attr_channels=((1), (1), (3)),
    voxel_size=a.voxel, block_resolution=16, block_count=a.block_count, device=device)
trunc_mult = a.sdf_trunc / a.voxel
assert float(depth.max()) * a.depth_scale < 65535, "depth exceeds uint16 range"
integrated_px = 0
for i in range(V):
    d = depth[i].astype(np.float64)          # already zero outside the official mask
    integrated_px += int((d > 0).sum())
    d16 = np.round(d * a.depth_scale).astype(np.uint16)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)).to(device)
    cimg = o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(rgb[i]))).to(device)
    intr = o3c.Tensor(K[i], o3c.float64)
    extr = o3c.Tensor(np.linalg.inv(c2w[i]), o3c.float64)
    coords = vbg.compute_unique_block_coordinates(dimg, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    vbg.integrate(coords, dimg, cimg, intr, intr, extr, a.depth_scale, a.depth_max, trunc_mult)
    if i % 20 == 0:
        print(f"integrated {i+1}/{V} active_blocks={vbg.hashmap().size()}", flush=True)

pcd = vbg.extract_point_cloud(weight_threshold=a.weight_threshold, estimated_point_number=-1).to_legacy()
n_pts = len(pcd.points)
ply = out / f"tsdf_{a.tag}_v{a.voxel:g}_t{a.sdf_trunc:g}.ply"
o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
res = {"purpose": "TSDF fusion of the anchored depths in the production COLMAP world frame",
       "depth_source": a.depth, "num_views": V, "voxel": a.voxel, "sdf_trunc": a.sdf_trunc,
       "weight_threshold": a.weight_threshold, "active_blocks": int(vbg.hashmap().size()),
       "integrated_valid_pixels": integrated_px, "points": n_pts,
       "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
       "seconds": time.time() - t0, "open3d": o3d.__version__}
(out / "result.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps(res, indent=2))
