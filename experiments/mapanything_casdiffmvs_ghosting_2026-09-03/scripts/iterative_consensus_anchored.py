#!/usr/bin/env python3
"""Strengthen geometric consistency by iterating cross-view consensus over ALL
pixels with a CasDiffMVS anchor pull -- a Jacobi solver for
    min  Σ_ij (z_i - z_implied_by_j)^2  +  w_a Σ_anchors (z_i - z_mvs)^2
so anchor-free regions (white walls, periphery) are pulled into agreement with
each other while textured regions stay pinned to the multi-view-verified MVS
depths.

Presentation stays MapAnything: native 392x518 grid, every official-mask pixel,
original colours, production COLMAP cameras. Starting point is the anchored
cloud the user judged best so far. Nothing deleted, no model changed, official
2%/2% consistency thresholds and the official (Σ+ref)/(n+1) averaging form.
The official metric is reported every eval_every iterations so convergence and
any degradation are visible, and the per-iteration displacement bounds how far
MapAnything's shape moved."""

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
from einops import einsum
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse, depthmap_to_camera_frame  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.multiview_confidence import (  # noqa: E402
    _compute_frustum_intersection_matrix,
    _in_image,
    _project_pts3d_to_image_with_depth,
    compute_multiview_depth_confidence,
)
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pfm  # noqa: E402


def q_(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    return {"n": int(v.size), "p05": float(np.percentile(v, 5)), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max())}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def sample_nearest(dmap, xy, H, W):
    grid = 2.0 * xy / torch.tensor([W - 1, H - 1], device=xy.device, dtype=xy.dtype) - 1.0
    grid = grid.clamp(-1.0, 1.0)[None, None]
    return F.grid_sample(dmap[None, None], grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0, 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
    ap.add_argument("--start_depth", default="/root/mapanything_native_anchored_20260903/depth_native_final.npy")
    ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--iters", type=int, default=8)
    ap.add_argument("--eval_every", type=int, default=2)
    ap.add_argument("--anchor_weight", type=float, default=2.0)
    ap.add_argument("--abs_thresh", type=float, default=0.02)
    ap.add_argument("--rel_thresh", type=float, default=0.02)
    ap.add_argument("--min_depth", type=float, default=0.04)
    ap.add_argument("--no_export", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    names = [m["name"] for m in info["image_manifest"]]
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    rgb = np.load(saved / "img_no_norm.npy")
    depth_start = np.load(args.start_depth).astype(np.float32)
    V, H, W = depth_start.shape
    valid = mask & nam & (depth_start > 0)
    s2f = json.load(open(args.mapping))
    f2s = {int(f): s for s, f in enumerate(s2f)}

    cams, imgs, _ = read_model(args.colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    ref_views = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        sc = 1500.0 / 3024.0
        K15 = np.array([[fxu * sc, 0, cxu * sc], [0, fyu * sc, cyu * sc], [0, 0, 1]], dtype=np.float32)
        R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
        pil = PILImage.open(Path(args.images) / n).convert("RGB")
        ref_views.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)), "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
    proc = preprocess_inputs(ref_views)
    Kc = np.stack([v["intrinsics"][0].numpy().astype(np.float32) for v in proc])
    Pc = np.stack([v["camera_poses"][0].numpy().astype(np.float32) for v in proc])

    # CasDiffMVS depth + fusion mask sampled to the native grid
    s_m = W / 1500.0
    off_v = (2000.0 * s_m - H) / 2.0
    vm, um = np.meshgrid(np.arange(H, dtype=np.float64), np.arange(W, dtype=np.float64), indexing="ij")
    x15 = (um + 0.5) / s_m - 0.5
    y15 = (vm + 0.5 + off_v) / s_m - 0.5
    x768 = (y15 + 0.5) * (768.0 / 2000.0) - 0.5
    y576 = ((1500.0 - 1.0 - x15) + 0.5) * (576.0 / 1500.0) - 0.5
    gridN = torch.from_numpy(np.stack([2 * x768 / 767.0 - 1, 2 * y576 / 575.0 - 1], -1).astype(np.float32))[None]
    z_mvs = np.zeros_like(depth_start)
    anchor = np.zeros((V, H, W), dtype=bool)
    for f in range(V):
        s = f2s[f]
        dm = read_pfm(str(Path(args.cas_out) / "depth_est" / f"{s:08d}.pfm"))[0].astype(np.float32)
        fin = (np.asarray(PILImage.open(Path(args.cas_out) / "mask" / f"{s:08d}_final.png")) > 0).astype(np.float32)
        dn = F.grid_sample(torch.from_numpy(dm)[None, None], gridN, mode="bilinear", align_corners=True, padding_mode="border")[0, 0].numpy()
        an = F.grid_sample(torch.from_numpy(fin)[None, None], gridN, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0].numpy()
        z_mvs[f] = np.where(valid[f], dn, 0.0)
        anchor[f] = (an > 0.5) & valid[f] & (dn > 0)

    Kt = torch.from_numpy(Kc).to(dev)
    Pt = torch.from_numpy(Pc).to(dev)
    W2C = closed_form_pose_inverse(Pt)
    depth = torch.from_numpy(depth_start).to(dev)
    depth_init = depth.clone()
    zmv = torch.from_numpy(z_mvs).to(dev)
    validt = torch.from_numpy(valid).to(dev)
    anchort = torch.from_numpy(anchor).to(dev)
    wa = args.anchor_weight * anchort.float()

    dz_list = [depth[i][None, ..., None] for i in range(V)]
    frustum = _compute_frustum_intersection_matrix([Kt[i][None] for i in range(V)], [Pt[i][None] for i in range(V)], dz_list, 50, dev)
    partners = [[int(j) for j in frustum[i].nonzero(as_tuple=True)[0].tolist() if j != i] for i in range(V)]

    def to_world(i, pts_cam):
        homo = torch.cat([pts_cam, torch.ones_like(pts_cam[..., :1])], -1)
        return einsum(Pt[i], homo, "i k, ... k -> ... i")[..., :3]

    def to_cam(j, pts_world):
        homo = torch.cat([pts_world, torch.ones_like(pts_world[..., :1])], -1)
        return einsum(W2C[j], homo, "i k, ... k -> ... i")[..., :3]

    def mv(d):
        dz = [torch.from_numpy(d[i]).to(dev)[None, ..., None] if isinstance(d, np.ndarray) else d[i][None, ..., None] for i in range(V)]
        Ks = [Kt[i][None] for i in range(V)]
        Ps = [Pt[i][None] for i in range(V)]
        Ms = [validt[i][None] for i in range(V)]
        conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
        fb = [float((cc[Ms[i]] < 0.5).float().mean()) for i, cc in enumerate(conf)]
        fbf = [float((conf[i][(validt[i] & ~anchort[i])[None]] < 0.5).float().mean()) for i in range(V)]
        mean = [float(cc[Ms[i]].mean()) for i, cc in enumerate(conf)]
        del conf; torch.cuda.empty_cache()
        return {"frac_below_0_50_p50": float(np.median(fb)), "frac_below_0_50_p95": float(np.percentile(fb, 95)), "anchorfree_frac_below_0_50_p50": float(np.median(fbf)), "mean_p50": float(np.median(mean))}

    hist = [{"iter": 0, **mv(depth), "rel_disp_vs_start_p50": 0.0, "rel_disp_vs_start_p95": 0.0}]
    print("iter 0", hist[-1], flush=True)
    for it in range(1, args.iters + 1):
        new_depth = depth.clone()
        for i in range(V):
            pts_cam_i, _ = depthmap_to_camera_frame(depth[i][None], Kt[i][None])
            Xi = to_world(i, pts_cam_i[0])
            acc = torch.zeros(H, W, device=dev)
            cnt = torch.zeros(H, W, device=dev)
            for j in partners[i]:
                Xij = to_cam(j, Xi)
                proj = _project_pts3d_to_image_with_depth(Xij[None], Kt[j][None])[0]
                ok = _in_image(proj, H, W, min_depth=args.min_depth) & validt[i]
                if not ok.any():
                    continue
                xy = proj[..., :2][ok]
                z_exp = proj[..., 2][ok]
                z_j = sample_nearest(depth[j], xy, H, W)
                thresh = args.abs_thresh + args.rel_thresh * z_exp
                cons = (z_j > 0) & (torch.abs(z_j - z_exp) < thresh)
                if not cons.any():
                    continue
                idx = ok.nonzero(as_tuple=True)
                implied = depth[i][idx] * (z_j / z_exp)
                acc[idx[0][cons], idx[1][cons]] += implied[cons]
                cnt[idx[0][cons], idx[1][cons]] += 1
            denom = cnt + 1.0 + wa[i]
            num = acc + depth[i] + wa[i] * zmv[i]
            upd = validt[i] & (denom > 0)
            new_depth[i][upd] = (num[upd] / denom[upd])
        depth = new_depth
        if it % args.eval_every == 0 or it == args.iters:
            disp = (torch.abs(depth - depth_init) / depth_init.clamp_min(1e-6))[validt]
            hist.append({"iter": it, **mv(depth), "rel_disp_vs_start_p50": float(disp.median()), "rel_disp_vs_start_p95": float(torch.quantile(disp[::37].float(), 0.95))})
            print("iter", it, hist[-1], flush=True)

    depth_np = depth.cpu().numpy()
    result = {
        "purpose": "iterated cross-view consensus with CasDiffMVS anchor pull over all pixels; MapAnything native grid, all pixels, original colours; strengthens geometric consistency",
        "start_depth": args.start_depth, "iters": args.iters, "anchor_weight": args.anchor_weight,
        "thresholds": {"abs": args.abs_thresh, "rel": args.rel_thresh},
        "anchor_frac_of_valid": q_([float(anchor[i].sum() / max(valid[i].sum(), 1)) for i in range(V)]),
        "history": hist, "seconds_compute": time.time() - t0,
    }
    if not args.no_export:
        xyz_all, rgb_all = [], []
        for f in range(V):
            vvv, uuu = np.nonzero(valid[f])
            z = depth_np[f][vvv, uuu].astype(np.float64)
            x = (uuu - Kc[f][0, 2]) / Kc[f][0, 0] * z
            y = (vvv - Kc[f][1, 2]) / Kc[f][1, 1] * z
            pc = np.stack([x, y, z, np.ones_like(z)], 1)
            xyz_all.append((Pc[f].astype(np.float64) @ pc.T).T[:, :3].astype(np.float32))
            rgb_all.append(rgb[f][valid[f]])
        xyz = np.concatenate(xyz_all); col = np.concatenate(rgb_all)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
        ply = out / "mapanything_iterative_consensus.ply"
        o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
        np.save(out / "depth_native_final.npy", depth_np)
        result["points"] = int(xyz.shape[0])
        result["ply"] = {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}
    result["seconds_total"] = time.time() - t0
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
