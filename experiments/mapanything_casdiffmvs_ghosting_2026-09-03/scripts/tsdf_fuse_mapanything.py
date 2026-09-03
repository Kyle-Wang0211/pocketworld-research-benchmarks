#!/usr/bin/env python3
"""TSDF fusion of the saved official MapAnything per-view outputs, in the
model's own frame (predicted K, predicted cam2world, predicted depth_z, official
mask). Implementation = Open3D ScalableTSDFVolume (MIT), call pattern mirrors
Depth-Anything-3 bench utils (Apache-2.0): integrate RGBD per view, then
extract. Nothing is filtered beyond the official per-view mask; no downsampling
of the extracted surface points."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import open3d as o3d


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
    ap.add_argument("--voxel", type=float, required=True, help="voxel length in model units (model claims metric)")
    ap.add_argument("--sdf_trunc", type=float, required=True)
    ap.add_argument("--depth_trunc", type=float, default=50.0)
    ap.add_argument("--no_mesh", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    saved = Path(args.saved)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = json.load(open(saved / "info.json"))

    depth = np.load(saved / "depth_z.npy")[..., 0].astype(np.float32)  # (V,H,W)
    rgb = np.load(saved / "img_no_norm.npy")  # (V,H,W,3) uint8
    K = np.load(saved / "intrinsics.npy").astype(np.float64)
    c2w = np.load(saved / "camera_poses.npy").astype(np.float64)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    valid = mask & nam & (depth > 0)
    V, H, W = depth.shape

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=args.voxel,
        sdf_trunc=args.sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    integrated_px = 0
    for i in range(V):
        d = np.where(valid[i], depth[i], 0.0).astype(np.float32)
        integrated_px += int((d > 0).sum())
        color = o3d.geometry.Image(np.ascontiguousarray(rgb[i]))
        dimg = o3d.geometry.Image(np.ascontiguousarray(d))
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color, dimg, depth_scale=1.0, depth_trunc=args.depth_trunc, convert_rgb_to_intensity=False
        )
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[i, 0, 0], K[i, 1, 1], K[i, 0, 2], K[i, 1, 2])
        extr = np.linalg.inv(c2w[i])  # world -> camera
        volume.integrate(rgbd, intr, extr)
        if i % 20 == 0:
            print(f"integrated {i + 1}/{V}", flush=True)
    t_int = time.time() - t0

    pcd = volume.extract_point_cloud()
    n_pts = len(pcd.points)
    pcd_path = out / f"tsdf_points_v{args.voxel:g}_t{args.sdf_trunc:g}.ply"
    o3d.io.write_point_cloud(str(pcd_path), pcd, write_ascii=False, compressed=False)
    result = {
        "purpose": "TSDF fusion of official MapAnything per-view outputs in the model's own frame; diagnostic candidate",
        "saved_dir": str(saved),
        "saved_info_manifest_sha256": info.get("ordered_image_manifest_sha256"),
        "repo_revision": info.get("repo_revision"),
        "num_views": V,
        "voxel": args.voxel,
        "sdf_trunc": args.sdf_trunc,
        "depth_trunc": args.depth_trunc,
        "mask_used": "official mask (non_ambiguous & edge & valid depth)",
        "integrated_valid_pixels": integrated_px,
        "raw_masked_points_reference": int(valid.sum()),
        "point_cloud": {"path": str(pcd_path), "points": n_pts, "bytes": pcd_path.stat().st_size, "sha256": sha256_file(pcd_path)},
        "integrate_seconds": t_int,
        "open3d": o3d.__version__,
    }
    if not args.no_mesh:
        mesh = volume.extract_triangle_mesh()
        mesh.compute_vertex_normals()
        mesh_path = out / f"tsdf_mesh_v{args.voxel:g}_t{args.sdf_trunc:g}.ply"
        o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)
        result["mesh"] = {"path": str(mesh_path), "vertices": len(mesh.vertices), "triangles": len(mesh.triangles), "bytes": mesh_path.stat().st_size, "sha256": sha256_file(mesh_path)}
    result["total_seconds"] = time.time() - t0
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (out / f"result_v{args.voxel:g}_t{args.sdf_trunc:g}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
