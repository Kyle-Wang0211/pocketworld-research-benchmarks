#!/usr/bin/env python3
"""MapAnything-only candidate: fix the model's OWN per-view depths using its OWN
cross-view geometry (predicted K + predicted poses), then re-unproject.

Stage A  per-frame depth scale alignment (132 scalars) by linear least squares on
         forward-projected correspondences; poses fixed, so scales are absolute.
Stage B  consensus depth: for every pixel, average its depth with the depths the
         other views imply along the same ray, using the official multi-view
         consistency thresholds (abs 0.02 + rel 0.02); the averaging formula is
         the same (sum of consistent reprojected depths + ref)/(n+1) that
         COLMAP-style fusion and DiffMVS filter.py use. Pixels with no consistent
         partner are left untouched. Nothing is deleted; colours are the original
         per-pixel image colours; the official mask is kept as is.

Projection / sampling mirror mapanything.utils.multiview_confidence exactly
(nearest grid_sample, align_corners=True, (W-1,H-1) normalisation, min depth 0.04).
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
import torch
import torch.nn.functional as F
from einops import einsum

sys.path.insert(0, os.getcwd())
from mapanything.utils.geometry import closed_form_pose_inverse, depthmap_to_camera_frame  # noqa: E402
from mapanything.utils.multiview_confidence import (  # noqa: E402
    _compute_frustum_intersection_matrix,
    _in_image,
    _project_pts3d_to_image_with_depth,
    compute_multiview_depth_confidence,
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def q(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    return {"n": int(v.size), "p05": float(np.percentile(v, 5)), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max())}


def sample_nearest(depth_map, xy, H, W):
    """depth_map (H,W); xy (N,2) pixel coords -> (N,) nearest-sampled depth, official normalisation."""
    grid = 2.0 * xy / torch.tensor([W - 1, H - 1], device=xy.device, dtype=xy.dtype) - 1.0
    grid = grid.clamp(-1.0, 1.0)[None, None]  # (1,1,N,2)
    return F.grid_sample(depth_map[None, None], grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0, 0]


def mvconf_frac(depth, K, P, masks, device):
    dz = [torch.from_numpy(depth[i]).to(device)[None, ..., None] for i in range(len(depth))]
    Ks = [torch.from_numpy(K[i]).to(device)[None] for i in range(len(K))]
    Ps = [torch.from_numpy(P[i]).to(device)[None] for i in range(len(P))]
    Ms = [torch.from_numpy(masks[i]).to(device)[None] for i in range(len(masks))]
    conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
    fb = [float((c[Ms[i]] < 0.5).float().mean()) for i, c in enumerate(conf)]
    mean = [float(c[Ms[i]].mean()) for i, c in enumerate(conf)]
    del conf
    torch.cuda.empty_cache()
    return {"frac_below_0_50": q(fb), "mean": q(mean)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--abs_thresh", type=float, default=0.02)
    ap.add_argument("--rel_thresh", type=float, default=0.02)
    ap.add_argument("--scale_gate", type=float, default=0.25, help="initial |log ratio| gate for stage A")
    ap.add_argument("--scale_iters", type=int, default=3)
    ap.add_argument("--consensus_iters", type=int, default=2)
    ap.add_argument("--min_depth", type=float, default=0.04)
    ap.add_argument("--skip_scale", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    device = "cuda"

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    depth0 = np.load(saved / "depth_z.npy")[..., 0].astype(np.float32)
    K = np.load(saved / "intrinsics.npy").astype(np.float32)
    P = np.load(saved / "camera_poses.npy").astype(np.float32)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    rgb = np.load(saved / "img_no_norm.npy")
    V, H, W = depth0.shape
    valid = mask & nam & (depth0 > 0)

    Kt = torch.from_numpy(K).to(device)
    Pt = torch.from_numpy(P).to(device)
    W2C = closed_form_pose_inverse(Pt)  # (V,4,4)
    cam_centres = Pt[:, :3, 3]
    validt = torch.from_numpy(valid).to(device)
    depth = torch.from_numpy(depth0).to(device)

    # overlap graph (official frustum test)
    dz_list = [depth[i][None, ..., None] for i in range(V)]
    frustum = _compute_frustum_intersection_matrix([Kt[i][None] for i in range(V)], [Pt[i][None] for i in range(V)], dz_list, 50, device)
    partners = [[int(j) for j in frustum[i].nonzero(as_tuple=True)[0].tolist() if j != i] for i in range(V)]
    n_partners = [len(p) for p in partners]

    def cam_points(i, d):
        pts_cam, _ = depthmap_to_camera_frame(d[i][None], Kt[i][None])  # (1,H,W,3)
        return pts_cam[0]

    def to_world(i, pts_cam):
        homo = torch.cat([pts_cam, torch.ones_like(pts_cam[..., :1])], -1)
        return einsum(Pt[i], homo, "i k, ... k -> ... i")[..., :3]

    def to_cam(j, pts_world):
        homo = torch.cat([pts_world, torch.ones_like(pts_world[..., :1])], -1)
        return einsum(W2C[j], homo, "i k, ... k -> ... i")[..., :3]

    # ---------- Stage A: per-frame scale ----------
    scales = torch.ones(V, device=device, dtype=torch.float64)
    stageA = {"skipped": bool(args.skip_scale), "iters": []}
    if not args.skip_scale:
        gate = args.scale_gate
        for it in range(args.scale_iters):
            A = torch.zeros(V, V, device=device, dtype=torch.float64)
            b = torch.zeros(V, device=device, dtype=torch.float64)
            n_corr = 0
            for i in range(V):
                d_i = depth[i] * scales[i].float()
                pc_i = cam_points(i, depth * 1.0) if False else None  # placeholder to keep structure simple
                pts_cam_i, _ = depthmap_to_camera_frame(d_i[None], Kt[i][None])
                pts_cam_i = pts_cam_i[0]
                Xi = to_world(i, pts_cam_i)  # (H,W,3) already scaled
                a_vec = (Xi - cam_centres[i]) / scales[i].float()  # direction*unscaled length: X_i(s)=c_i+s*a
                for j in partners[i]:
                    Xij = to_cam(j, Xi)
                    proj = _project_pts3d_to_image_with_depth(Xij[None], Kt[j][None])[0]  # (H,W,3)
                    ok = _in_image(proj, H, W, min_depth=args.min_depth) & validt[i]
                    if ok.sum() < 50:
                        continue
                    xy = proj[..., :2][ok]
                    z_exp = proj[..., 2][ok]
                    z_j = sample_nearest(depth[j] * scales[j].float(), xy, H, W)
                    good = (z_j > 0) & (torch.abs(torch.log(z_j / z_exp)) < gate)
                    if good.sum() < 50:
                        continue
                    xy_g, z_g = xy[good], z_j[good]
                    # partner 3D point from j's own depth at the sampled pixel (nearest pixel centre)
                    u = torch.round(xy_g[:, 0]).clamp(0, W - 1)
                    v = torch.round(xy_g[:, 1]).clamp(0, H - 1)
                    xj = (u - Kt[j][0, 2]) / Kt[j][0, 0] * z_g
                    yj = (v - Kt[j][1, 2]) / Kt[j][1, 1] * z_g
                    pj_cam = torch.stack([xj, yj, z_g], -1)
                    Xj = to_world(j, pj_cam)
                    b_vec = (Xj - cam_centres[j]) / scales[j].float()
                    a_k = a_vec[ok][good].double()
                    b_k = b_vec.double()
                    d_k = (cam_centres[i] - cam_centres[j]).double()
                    # residual r = d + s_i a - s_j b ; accumulate normal equations
                    A[i, i] += (a_k * a_k).sum()
                    A[j, j] += (b_k * b_k).sum()
                    A[i, j] -= (a_k * b_k).sum()
                    A[j, i] -= (a_k * b_k).sum()
                    b[i] -= (a_k * d_k).sum()
                    b[j] += (b_k * d_k).sum()
                    n_corr += int(good.sum())
            new_scales = torch.linalg.solve(A + 1e-9 * torch.eye(V, device=device, dtype=torch.float64), b)
            stageA["iters"].append({"gate_logratio": gate, "correspondences": n_corr, "scales": q(new_scales.cpu().numpy()), "scales_over_prev": q((new_scales / scales).cpu().numpy())})
            print(f"stage A iter {it}: gate {gate:.3f} corr {n_corr} scales p05/p50/p95 {np.percentile(new_scales.cpu().numpy(), [5, 50, 95])}", flush=True)
            scales = new_scales
            gate = max(gate / 2.0, 0.05)
        depth = depth * scales.float()[:, None, None]

    # ---------- Stage B: consensus depth ----------
    stageB = []
    for it in range(args.consensus_iters):
        new_depth = depth.clone()
        n_cons_total = torch.zeros(V, H, W, device=device, dtype=torch.int32)
        for i in range(V):
            pts_cam_i, _ = depthmap_to_camera_frame(depth[i][None], Kt[i][None])
            Xi = to_world(i, pts_cam_i[0])
            acc = torch.zeros(H, W, device=device)
            cnt = torch.zeros(H, W, device=device)
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
                # depth implied along i's ray by j's surface: intersect i's ray with j's depth plane approx
                # = scale i's own depth by z_j/z_exp (first-order, exact for fronto-parallel local surface)
                idx = ok.nonzero(as_tuple=True)
                z_i_own = depth[i][idx]
                implied = z_i_own * (z_j / z_exp)
                acc[idx[0][cons], idx[1][cons]] += implied[cons]
                cnt[idx[0][cons], idx[1][cons]] += 1
            upd = cnt > 0
            new_depth[i][upd] = (acc[upd] + depth[i][upd]) / (cnt[upd] + 1)
            n_cons_total[i] = cnt.int()
            if i % 20 == 0:
                print(f"stage B iter {it}: view {i} consistent-partner px {float((cnt > 0)[validt[i]].float().mean()):.3f}", flush=True)
        frac_with_partner = [float((n_cons_total[i] > 0)[validt[i]].float().mean()) for i in range(V)]
        mean_partners = [float(n_cons_total[i][validt[i]].float().mean()) for i in range(V)]
        change = torch.abs(new_depth - depth) / depth.clamp_min(1e-6)
        stageB.append({"iter": it, "frac_px_with_consistent_partner": q(frac_with_partner), "mean_consistent_partners": q(mean_partners), "relative_depth_change_p50": float(change[validt].median()), "relative_depth_change_p95": float(torch.quantile(change[validt].flatten()[::37], 0.95))})
        depth = new_depth

    depth_np = depth.cpu().numpy()
    masks_np = valid
    before = mvconf_frac(depth0, K, P, masks_np, device)
    after = mvconf_frac(depth_np, K, P, masks_np, device)

    # ---------- export: every official-mask pixel, original colour ----------
    xyz_all, rgb_all = [], []
    for i in range(V):
        pts_cam_i, _ = depthmap_to_camera_frame(depth[i][None], Kt[i][None])
        Xi = to_world(i, pts_cam_i[0])
        m = validt[i]
        xyz_all.append(Xi[m].cpu().numpy().astype(np.float32))
        rgb_all.append(rgb[i][valid[i]])
    xyz = np.concatenate(xyz_all)
    col = np.concatenate(rgb_all)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
    ply = out / "mapanything_consensus_depth.ply"
    o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
    np.save(out / "depth_consensus.npy", depth_np)
    np.save(out / "scales.npy", scales.cpu().numpy())
    result = {
        "purpose": "MapAnything-only: per-frame scale alignment + consensus depth on the official per-view outputs; no deletion, no model change, original colours",
        "saved_dir": str(saved),
        "saved_manifest_sha256": info.get("ordered_image_manifest_sha256"),
        "repo_revision": info.get("repo_revision"),
        "num_views": V,
        "partners_per_view": q(n_partners),
        "thresholds": {"abs": args.abs_thresh, "rel": args.rel_thresh, "scale_gate_initial": args.scale_gate, "min_depth": args.min_depth},
        "stage_A": stageA,
        "stage_B": stageB,
        "official_mvconf_before": before,
        "official_mvconf_after": after,
        "points": int(xyz.shape[0]),
        "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
        "seconds": time.time() - t0,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("stage_A",)}, indent=2))
    print("stage A:", json.dumps(stageA, indent=1)[:1500])


if __name__ == "__main__":
    main()
