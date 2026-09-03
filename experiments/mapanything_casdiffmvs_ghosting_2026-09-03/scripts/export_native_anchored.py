#!/usr/bin/env python3
"""Export the CasDiffMVS-anchored MapAnything cloud on MapAnything's NATIVE pixel
grid (392x518 upright, one point per official-mask pixel, original colours), so
the point set is identical to the raw MapAnything cloud and only depth changes.

Per frame f (source s = frame_to_source[f]):
  z_native_final = (a_s * z_native + b_s) * exp(h_s sampled at the native pixel)
where (a_s, b_s) is the per-view affine from make_prior_maps and h_s is the
smooth log-depth offset field solved by anchor_mapanything_to_casdiff
(recovered as log(depth_final) - log(prior)). Camera = production COLMAP K/pose
rotated upright and passed through the official preprocess (same as
layer_attribution.py), so every frame lands in the common COLMAP world frame.
Also reports the official multi-view consistency on the native grid before
(affine only) and after (anchored)."""

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
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.multiview_confidence import compute_multiview_depth_confidence  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402


def q(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    return {"n": int(v.size), "p05": float(np.percentile(v, 5)), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max())}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
    ap.add_argument("--prior_dir", default="/root/casdiffmvs_prior_20260903/priors_blendmvg")
    ap.add_argument("--anchored_dir", default="/root/mapanything_anchored_20260903")
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    names = [m["name"] for m in info["image_manifest"]]
    depth = np.load(saved / "depth_z.npy")[..., 0].astype(np.float32)  # (V,518,392)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    rgb = np.load(saved / "img_no_norm.npy")
    V, Hm, Wm = depth.shape
    valid = mask & nam & (depth > 0)
    s2f = json.load(open(args.mapping))
    f2s = {int(f): s for s, f in enumerate(s2f)}
    pstats = {t["src"]: t for t in json.load(open(Path(args.prior_dir) / "prior_stats.json"))["per_view"]}

    # reference cameras at native grid (same recipe as layer_attribution.py)
    cams, imgs, _ = read_model(args.colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    ref_views = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        s = 1500.0 / 3024.0
        K15 = np.array([[fxu * s, 0, cxu * s], [0, fyu * s, cyu * s], [0, 0, 1]], dtype=np.float32)
        R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4)
        w2c[:3, :3] = R
        w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
        pil = PILImage.open(Path(args.images) / n).convert("RGB")
        ref_views.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)), "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
    proc = preprocess_inputs(ref_views)
    refK = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
    refP = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])

    # native pixel -> landscape 768x576 coordinates (inverse of make_prior_maps chain)
    s_m = Wm / 1500.0
    off_v = (2000.0 * s_m - Hm) / 2.0
    vm, um = np.meshgrid(np.arange(Hm, dtype=np.float64), np.arange(Wm, dtype=np.float64), indexing="ij")
    x15 = (um + 0.5) / s_m - 0.5
    y15 = (vm + 0.5 + off_v) / s_m - 0.5
    # upright (x', y') from landscape (x, y): x' = H_l-1-y, y' = x  (H_l = 1500) -> inverse
    x_l = y15
    y_l = 1500.0 - 1.0 - x15
    x768 = (x_l + 0.5) * (768.0 / 2000.0) - 0.5
    y576 = (y_l + 0.5) * (576.0 / 1500.0) - 0.5
    grid = torch.from_numpy(np.stack([2 * x768 / (768 - 1) - 1, 2 * y576 / (576 - 1) - 1], -1).astype(np.float32))[None]

    depth_aff, depth_fin = np.zeros_like(depth), np.zeros_like(depth)
    xyz_all, rgb_all, hstats = [], [], []
    for f in range(V):
        s = f2s[f]
        st = pstats[s]
        a, b = float(st["a"]), float(st["b"])
        prior = np.load(Path(args.prior_dir) / "prior_depth" / f"{s:08d}.npy").astype(np.float64)
        fin = np.load(Path(args.anchored_dir) / "depth_final" / f"{s:08d}.npy").astype(np.float64)
        h = np.where((prior > 0) & (fin > 0), np.log(np.maximum(fin, 1e-6)) - np.log(np.maximum(prior, 1e-6)), 0.0).astype(np.float32)
        h_native = F.grid_sample(torch.from_numpy(h)[None, None], grid, mode="bilinear", align_corners=True, padding_mode="border")[0, 0].numpy()
        z_aff = a * depth[f] + b
        z_fin = z_aff * np.exp(h_native)
        depth_aff[f] = np.where(valid[f], z_aff, 0).astype(np.float32)
        depth_fin[f] = np.where(valid[f], z_fin, 0).astype(np.float32)
        hstats.append({"frame": f, "src": s, "h_p05": float(np.percentile(h_native[valid[f]], 5)), "h_p50": float(np.median(h_native[valid[f]])), "h_p95": float(np.percentile(h_native[valid[f]], 95))})
        vv, uu = np.nonzero(valid[f])
        z = depth_fin[f][vv, uu].astype(np.float64)
        K = refK[f]
        x = (uu - K[0, 2]) / K[0, 0] * z
        y = (vv - K[1, 2]) / K[1, 1] * z
        pc = np.stack([x, y, z, np.ones_like(z)], 1)
        pw = (refP[f] @ pc.T).T[:, :3].astype(np.float32)
        xyz_all.append(pw)
        rgb_all.append(rgb[f][valid[f]])
        if f % 20 == 0:
            print(f"frame {f} (src {s}) a={a:.3f} b={b:.3f} h p05/p50/p95 {hstats[-1]['h_p05']:.4f}/{hstats[-1]['h_p50']:.4f}/{hstats[-1]['h_p95']:.4f}", flush=True)

    xyz = np.concatenate(xyz_all)
    col = np.concatenate(rgb_all)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
    ply = out / "mapanything_native_anchored.ply"
    o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
    np.save(out / "depth_native_final.npy", depth_fin)

    def mv(d):
        dz = [torch.from_numpy(d[i]).to(dev)[None, ..., None] for i in range(V)]
        Ks = [torch.from_numpy(refK[i].astype(np.float32)).to(dev)[None] for i in range(V)]
        Ps = [torch.from_numpy(refP[i].astype(np.float32)).to(dev)[None] for i in range(V)]
        Ms = [torch.from_numpy(valid[i]).to(dev)[None] for i in range(V)]
        conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
        fb = [float((c[Ms[i]] < 0.5).float().mean()) for i, c in enumerate(conf)]
        mean = [float(c[Ms[i]].mean()) for i, c in enumerate(conf)]
        del conf
        torch.cuda.empty_cache()
        return {"frac_below_0_50": q(fb), "mean": q(mean)}
    before = mv(depth_aff)
    after = mv(depth_fin)
    result = {
        "purpose": "MapAnything native-grid cloud (identical point set to raw) with depths anchored to CasDiffMVS via per-view affine + smooth offset field; COLMAP world frame",
        "num_views": V, "native_HxW": [Hm, Wm], "points": int(xyz.shape[0]),
        "h_spread_p95_minus_p05": q([t["h_p95"] - t["h_p05"] for t in hstats]),
        "official_mvconf_native_before_affine_only": before, "official_mvconf_native_after_anchoring": after,
        "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0, "per_frame_h": hstats,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "per_frame_h"}, indent=2))


if __name__ == "__main__":
    main()
