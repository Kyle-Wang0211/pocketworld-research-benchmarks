#!/usr/bin/env python3
"""GPU TSDF fusion (Open3D tensor VoxelBlockGrid, CUDA) of the saved official
MapAnything per-view outputs in the model's own frame. Same inputs and same
official mask as tsdf_fuse_mapanything.py; only the TSDF backend differs so
that fine voxels fit in memory. No filtering beyond the official mask; surface
points are extracted at weight >= 1 (every observed voxel), no downsampling."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import open3d.core as o3c


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--voxel", type=float, required=True)
    ap.add_argument("--sdf_trunc", type=float, required=True)
    ap.add_argument("--depth_max", type=float, default=12.0)
    ap.add_argument("--depth_scale", type=float, default=5000.0)
    ap.add_argument("--block_count", type=int, default=200000)
    ap.add_argument("--weight_threshold", type=float, default=1.0)
    ap.add_argument("--mesh", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    saved = Path(args.saved)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = json.load(open(saved / "info.json"))

    depth = np.load(saved / "depth_z.npy")[..., 0].astype(np.float32)
    rgb = np.load(saved / "img_no_norm.npy")
    K = np.load(saved / "intrinsics.npy").astype(np.float64)
    c2w = np.load(saved / "camera_poses.npy").astype(np.float64)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    valid = mask & nam & (depth > 0)
    V, H, W = depth.shape

    device = o3c.Device("CUDA:0")
    vbg = o3d.t.geometry.VoxelBlockGrid(
        attr_names=("tsdf", "weight", "color"),
        attr_dtypes=(o3c.float32, o3c.uint16, o3c.uint16),
        attr_channels=((1), (1), (3)),
        voxel_size=args.voxel,
        block_resolution=16,
        block_count=args.block_count,
        device=device,
    )
    trunc_mult = args.sdf_trunc / args.voxel
    # Open3D's CUDA integrate kernel accepts (uint16 depth, uint8 color); quantise
    # depth at 1/depth_scale units (0.2 mm at 5000), far below the 3 mm voxel.
    depth_scale = args.depth_scale
    assert float(depth.max()) * depth_scale < 65535, "depth exceeds uint16 range at this depth_scale"
    integrated_px = 0
    for i in range(V):
        d = np.where(valid[i], depth[i], 0.0).astype(np.float64)
        integrated_px += int((d > 0).sum())
        d16 = np.round(d * depth_scale).astype(np.uint16)
        dimg = o3d.t.geometry.Image(o3c.Tensor(d16)).to(device)
        cimg = o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(rgb[i]))).to(device)
        intr = o3c.Tensor(K[i], o3c.float64)
        extr = o3c.Tensor(np.linalg.inv(c2w[i]), o3c.float64)
        coords = vbg.compute_unique_block_coordinates(dimg, intr, extr, depth_scale, args.depth_max, trunc_mult)
        vbg.integrate(coords, dimg, cimg, intr, intr, extr, depth_scale, args.depth_max, trunc_mult)
        if i % 20 == 0:
            print(f"integrated {i + 1}/{V} active_blocks={vbg.hashmap().size()}", flush=True)
    t_int = time.time() - t0
    n_blocks = int(vbg.hashmap().size())

    pcd = vbg.extract_point_cloud(weight_threshold=args.weight_threshold, estimated_point_number=-1)
    pcd_legacy = pcd.to_legacy()
    n_pts = len(pcd_legacy.points)
    pcd_path = out / f"tsdf_gpu_points_v{args.voxel:g}_t{args.sdf_trunc:g}_w{args.weight_threshold:g}.ply"
    o3d.io.write_point_cloud(str(pcd_path), pcd_legacy, write_ascii=False, compressed=False)
    result = {
        "purpose": "GPU TSDF fusion (Open3D VoxelBlockGrid) of official MapAnything per-view outputs in the model's own frame; candidate for visual review",
        "saved_dir": str(saved),
        "saved_info_manifest_sha256": info.get("ordered_image_manifest_sha256"),
        "repo_revision": info.get("repo_revision"),
        "num_views": V,
        "voxel": args.voxel,
        "sdf_trunc": args.sdf_trunc,
        "trunc_voxel_multiplier": trunc_mult,
        "depth_max": args.depth_max,
        "depth_scale_uint16": depth_scale,
        "weight_threshold": args.weight_threshold,
        "block_resolution": 16,
        "block_count_capacity": args.block_count,
        "active_blocks": n_blocks,
        "mask_used": "official mask (non_ambiguous & edge & valid depth)",
        "integrated_valid_pixels": integrated_px,
        "point_cloud": {"path": str(pcd_path), "points": n_pts, "bytes": pcd_path.stat().st_size, "sha256": sha256_file(pcd_path)},
        "integrate_seconds": t_int,
        "open3d": o3d.__version__,
    }
    if args.mesh:
        mesh = vbg.extract_triangle_mesh(weight_threshold=args.weight_threshold, estimated_vertex_number=-1).to_legacy()
        mesh_path = out / f"tsdf_gpu_mesh_v{args.voxel:g}_t{args.sdf_trunc:g}_w{args.weight_threshold:g}.ply"
        o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)
        result["mesh"] = {"path": str(mesh_path), "vertices": len(mesh.vertices), "triangles": len(mesh.triangles), "bytes": mesh_path.stat().st_size, "sha256": sha256_file(mesh_path)}
    result["total_seconds"] = time.time() - t0
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (out / f"result_gpu_v{args.voxel:g}_t{args.sdf_trunc:g}_w{args.weight_threshold:g}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
