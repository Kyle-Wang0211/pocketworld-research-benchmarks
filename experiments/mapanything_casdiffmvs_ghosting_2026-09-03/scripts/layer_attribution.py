#!/usr/bin/env python3
"""Layer-by-layer attribution of cross-view geometric inconsistency for the saved
official MapAnything outputs. Diagnostic only; produces numbers, no candidate.

Reference = production COLMAP sparse model (132 PINHOLE cameras, 4032x3024,
landscape storage). Model inputs were the upright 1500x2000 JPEGs (90deg CW).

Experiments (all use the *same* saved predicted depth_z unless stated):
  V1  pred depth + pred K      + pred pose                (official raw geometry)
  V2  pred depth + COLMAP K    + pred pose
  V3  pred depth + pred K      + COLMAP pose (Sim3 -> model units)
  V4  pred depth + COLMAP K    + COLMAP pose
  V5  pred depth * per-frame COLMAP scale + COLMAP K + COLMAP pose
Consistency metric = official compute_multiview_depth_confidence (2%/2% thresholds).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")

from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import (  # noqa: E402
    closed_form_pose_inverse,
    get_rays_in_camera_frame,
)
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.metrics import (  # noqa: E402
    l2_distance_of_unit_ray_directions_to_angular_error,
)
from mapanything.utils.multiview_confidence import (  # noqa: E402
    compute_multiview_depth_confidence,
)
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import (  # noqa: E402  (prior agent's self-tested helper)
    rotate_pixels,
    rotate_world_to_camera,
    self_test,
)


def q(values, name=""):
    v = np.asarray(values, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0}
    return {
        "n": int(v.size),
        "mean": float(v.mean()),
        "p05": float(np.percentile(v, 5)),
        "p50": float(np.percentile(v, 50)),
        "p95": float(np.percentile(v, 95)),
        "min": float(v.min()),
        "max": float(v.max()),
    }


def umeyama(src: np.ndarray, dst: np.ndarray):
    """Similarity transform (s, R, t) with dst ~= s*R@src + t (Umeyama 1991)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    n = src.shape[0]
    cov = xd.T @ xs / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    var_s = (xs**2).sum() / n
    s = np.trace(np.diag(D) @ S) / var_s
    t = mu_d - s * R @ mu_s
    return s, R, t


def mv_conf_stats(depth_z, K, poses, masks, device, label):
    dz = [torch.from_numpy(depth_z[i]).to(device)[None, ..., None] for i in range(len(depth_z))]
    Ks = [torch.from_numpy(K[i]).to(device)[None] for i in range(len(K))]
    Ps = [torch.from_numpy(poses[i]).to(device)[None] for i in range(len(poses))]
    Ms = [torch.from_numpy(masks[i]).to(device)[None] for i in range(len(masks))]
    conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
    per_mean, per_below = [], []
    for i, c in enumerate(conf):
        vals = c[Ms[i].to(c.device)]
        per_mean.append(float(vals.mean()))
        per_below.append(float((vals < 0.5).float().mean()))
    del conf
    torch.cuda.empty_cache()
    return {
        "label": label,
        "per_frame_mean": q(per_mean),
        "per_frame_fraction_below_0_50": q(per_below),
        "per_frame_fraction_below_0_50_list": [round(x, 4) for x in per_below],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", required=True)
    ap.add_argument("--images", required=True, help="upright 1500x2000 jpg folder fed to the model")
    ap.add_argument("--colmap_sparse", required=True, help="production sparse model (frame_XXXXXX.jpg names)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    self_test(rotate_pinhole_90degcw)

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    names = [m["name"] for m in info["image_manifest"]]
    depth_z = np.load(saved / "depth_z.npy")[..., 0]  # (V,H,W)
    predK = np.load(saved / "intrinsics.npy")  # (V,3,3)
    predP = np.load(saved / "camera_poses.npy")  # (V,4,4) cam2world
    rays = np.load(saved / "ray_directions.npy")  # (V,H,W,3)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    V, H, W = depth_z.shape
    valid = mask & (depth_z > 0)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ---- reference: production COLMAP (landscape 4032x3024) -> upright -> 1500x2000 -> model res via official preprocess
    cams, imgs, pts3d = read_model(args.colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise SystemExit(f"COLMAP model lacks {len(missing)} names, e.g. {missing[:3]}")
    xyz = {pid: p.xyz for pid, p in pts3d.items()}

    ref_views, refK_1500, w2c_up, obs = [], [], [], []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        assert cam.model == "PINHOLE" and cam.width == 4032 and cam.height == 3024, (cam.model, cam.width, cam.height)
        fx, fy, cx, cy = cam.params
        w_up, h_up, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        assert (w_up, h_up) == (3024, 4032)
        s = 1500.0 / 3024.0
        K15 = np.array([[fxu * s, 0, cxu * s], [0, fyu * s, cyu * s], [0, 0, 1]], dtype=np.float64)
        R_w2c, t_w2c = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4)
        w2c[:3, :3] = R_w2c
        w2c[:3, 3] = t_w2c
        c2w = closed_form_pose_inverse(w2c[None])[0]
        pil = PILImage.open(Path(args.images) / n).convert("RGB")
        assert pil.size == (1500, 2000), pil.size
        ref_views.append(
            {
                "img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)),
                "intrinsics": torch.from_numpy(K15.astype(np.float32)),
                "camera_poses": torch.from_numpy(c2w.astype(np.float32)),
                "is_metric_scale": torch.tensor([False]),
            }
        )
        refK_1500.append(K15)
        w2c_up.append((R_w2c, t_w2c))
        # sparse observations in original landscape pixel coords
        sel = im.point3D_ids >= 0
        xys_up = rotate_pixels(im.xys[sel].astype(np.float64), cam.height)
        obs.append((xys_up * s, np.stack([xyz[pid] for pid in im.point3D_ids[sel]]) if sel.any() else np.zeros((0, 3))))

    proc = preprocess_inputs(ref_views)
    refK = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
    refP = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])
    ph, pw = proc[0]["img"].shape[-2:]
    assert (ph, pw) == (H, W), ((ph, pw), (H, W))

    # ---- Layer K: predicted vs reference intrinsics / rays
    layerK = []
    for i in range(V):
        _, ref_rays = get_rays_in_camera_frame(torch.from_numpy(refK[i]).float().to(device), H, W, True)
        pr = torch.from_numpy(rays[i]).to(device)
        pr = pr / pr.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        ang = l2_distance_of_unit_ray_directions_to_angular_error((pr - ref_rays).norm(dim=-1).clamp(max=2.0))
        m = torch.from_numpy(valid[i]).to(device)
        layerK.append(
            {
                "frame": i,
                "name": names[i],
                "pred_fx": float(predK[i, 0, 0]),
                "pred_fy": float(predK[i, 1, 1]),
                "pred_cx": float(predK[i, 0, 2]),
                "pred_cy": float(predK[i, 1, 2]),
                "ref_fx": float(refK[i, 0, 0]),
                "ref_fy": float(refK[i, 1, 1]),
                "ref_cx": float(refK[i, 0, 2]),
                "ref_cy": float(refK[i, 1, 2]),
                "fx_ratio_pred_over_ref": float(predK[i, 0, 0] / refK[i, 0, 0]),
                "ray_angular_err_deg_p50": float(ang[m].median()),
                "ray_angular_err_deg_p95": float(torch.quantile(ang[m], 0.95)),
            }
        )

    # ---- Layer pose: Sim3 align predicted camera centres to COLMAP centres
    c_pred = predP[:, :3, 3]
    c_ref = refP[:, :3, 3]
    s_sim, R_sim, t_sim = umeyama(c_ref, c_pred)  # model ~= s R colmap + t
    c_ref_in_model = (s_sim * (R_sim @ c_ref.T)).T + t_sim
    centre_resid = np.linalg.norm(c_pred - c_ref_in_model, axis=1)
    diag_pred = np.linalg.norm(c_pred.max(0) - c_pred.min(0))
    rot_err = []
    for i in range(V):
        R_ref_m = R_sim @ refP[i, :3, :3]
        R_p = predP[i, :3, :3]
        cosang = (np.trace(R_p.T @ R_ref_m) - 1) / 2
        rot_err.append(float(np.degrees(np.arccos(np.clip(cosang, -1, 1)))))
    refP_model = np.zeros_like(refP)
    for i in range(V):
        refP_model[i] = np.eye(4)
        refP_model[i, :3, :3] = R_sim @ refP[i, :3, :3]
        refP_model[i, :3, 3] = c_ref_in_model[i]

    # ---- Layer depth: per-frame scale vs COLMAP sparse observations (in COLMAP units)
    per_frame_scale = []
    all_logratio, all_radius = [], []
    for i in range(V):
        xy15, X = obs[i]
        if X.shape[0] == 0:
            per_frame_scale.append(None)
            continue
        R_w2c, t_w2c = w2c_up[i]
        Xc = (R_w2c @ X.T).T + t_w2c
        zc = Xc[:, 2]
        a_x = refK[i, 0, 0] / refK_1500[i][0, 0]
        b_x = refK[i, 0, 2] - a_x * refK_1500[i][0, 2]
        a_y = refK[i, 1, 1] / refK_1500[i][1, 1]
        b_y = refK[i, 1, 2] - a_y * refK_1500[i][1, 2]
        u = a_x * xy15[:, 0] + b_x
        v = a_y * xy15[:, 1] + b_y
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        inb = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H) & (zc > 0)
        ok = inb.copy()
        ok[inb] &= valid[i][vi[inb], ui[inb]]
        if ok.sum() < 20:
            per_frame_scale.append(None)
            continue
        dpred = depth_z[i][vi[ok], ui[ok]]
        ratio = dpred / zc[ok]
        lr = np.log(ratio)
        med = float(np.exp(np.median(lr)))
        rad = np.sqrt(((u[ok] - refK[i, 0, 2]) / refK[i, 0, 0]) ** 2 + ((v[ok] - refK[i, 1, 2]) / refK[i, 1, 1]) ** 2)
        all_logratio.append(lr - np.median(lr))
        all_radius.append(rad)
        per_frame_scale.append(
            {
                "frame": i,
                "n_obs": int(ok.sum()),
                "median_ratio_pred_over_colmap": med,
                "iqr_logratio": float(np.percentile(lr, 75) - np.percentile(lr, 25)),
                "p05_ratio": float(np.exp(np.percentile(lr, 5))),
                "p95_ratio": float(np.exp(np.percentile(lr, 95))),
            }
        )
    scales = np.array([p["median_ratio_pred_over_colmap"] for p in per_frame_scale if p])
    frames_with_scale = [p["frame"] for p in per_frame_scale if p]
    lr_all = np.concatenate(all_logratio)
    rad_all = np.concatenate(all_radius)
    corr_radius = float(np.corrcoef(rad_all, lr_all)[0, 1])
    # binned: residual log-ratio vs normalised radius
    bins = np.percentile(rad_all, [0, 20, 40, 60, 80, 100])
    binned = []
    for b0, b1 in zip(bins[:-1], bins[1:]):
        sel = (rad_all >= b0) & (rad_all <= b1)
        binned.append({"radius_range": [float(b0), float(b1)], "median_residual_ratio": float(np.exp(np.median(lr_all[sel])))})

    # ---- Cross-view consistency experiments (official metric)
    masks_for_conf = nam & valid
    K_pred32 = predK.astype(np.float32)
    K_ref32 = refK.astype(np.float32)
    P_pred32 = predP.astype(np.float32)
    P_ref32 = refP_model.astype(np.float32)
    dz32 = depth_z.astype(np.float32)
    exps = []
    exps.append(mv_conf_stats(dz32, K_pred32, P_pred32, masks_for_conf, device, "V1 pred depth + pred K + pred pose"))
    exps.append(mv_conf_stats(dz32, K_ref32, P_pred32, masks_for_conf, device, "V2 pred depth + COLMAP K + pred pose"))
    exps.append(mv_conf_stats(dz32, K_pred32, P_ref32, masks_for_conf, device, "V3 pred depth + pred K + COLMAP pose(Sim3)"))
    exps.append(mv_conf_stats(dz32, K_ref32, P_ref32, masks_for_conf, device, "V4 pred depth + COLMAP K + COLMAP pose(Sim3)"))
    # V5: rescale each frame's depth so its median ratio vs COLMAP sparse equals the global Sim3 scale
    dz5 = dz32.copy()
    for p in per_frame_scale:
        if p:
            dz5[p["frame"]] *= float(s_sim / p["median_ratio_pred_over_colmap"])
    exps.append(mv_conf_stats(dz5, K_ref32, P_ref32, masks_for_conf, device, "V5 per-frame-rescaled depth + COLMAP K + COLMAP pose(Sim3)"))

    report = {
        "saved_dir": str(saved),
        "num_views": V,
        "input_resolution_HxW": [H, W],
        "demo_export_vertex_count": info.get("demo_export_vertex_count"),
        "layer_K": {
            "pred_fx": q([r["pred_fx"] for r in layerK]),
            "ref_fx": q([r["ref_fx"] for r in layerK]),
            "fx_ratio_pred_over_ref": q([r["fx_ratio_pred_over_ref"] for r in layerK]),
            "pred_cx": q([r["pred_cx"] for r in layerK]),
            "ref_cx": q([r["ref_cx"] for r in layerK]),
            "pred_cy": q([r["pred_cy"] for r in layerK]),
            "ref_cy": q([r["ref_cy"] for r in layerK]),
            "ray_angular_err_deg_p50_per_frame": q([r["ray_angular_err_deg_p50"] for r in layerK]),
            "per_frame": layerK,
        },
        "layer_pose": {
            "sim3_scale_model_over_colmap": float(s_sim),
            "camera_centre_residual_model_units": q(centre_resid),
            "camera_centre_residual_over_trajectory_diag": q(centre_resid / diag_pred),
            "trajectory_diag_model_units": float(diag_pred),
            "rotation_error_deg": q(rot_err),
            "per_frame_centre_residual": [round(float(x), 5) for x in centre_resid],
            "per_frame_rotation_err_deg": [round(float(x), 4) for x in rot_err],
        },
        "layer_depth_scale_vs_colmap_sparse": {
            "frames_with_enough_obs": len(frames_with_scale),
            "per_frame_median_ratio": q(scales),
            "per_frame_median_ratio_over_sim3_scale": q(scales / s_sim),
            "spread_p95_over_p05": float(np.percentile(scales, 95) / np.percentile(scales, 5)),
            "within_frame_iqr_logratio": q([p["iqr_logratio"] for p in per_frame_scale if p]),
            "corr_residual_logratio_vs_normalised_radius": corr_radius,
            "binned_residual_ratio_by_radius": binned,
            "per_frame": per_frame_scale,
        },
        "cross_view_consistency_official_mvconf": exps,
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    summary = {
        "fx_ratio_pred_over_ref": report["layer_K"]["fx_ratio_pred_over_ref"],
        "ray_angular_err_p50": report["layer_K"]["ray_angular_err_deg_p50_per_frame"],
        "sim3_scale": s_sim,
        "centre_resid_over_diag": report["layer_pose"]["camera_centre_residual_over_trajectory_diag"],
        "rot_err_deg": report["layer_pose"]["rotation_error_deg"],
        "per_frame_scale_over_sim3": report["layer_depth_scale_vs_colmap_sparse"]["per_frame_median_ratio_over_sim3_scale"],
        "scale_spread_p95_over_p05": report["layer_depth_scale_vs_colmap_sparse"]["spread_p95_over_p05"],
        "corr_logratio_vs_radius": corr_radius,
        "binned": binned,
        "mvconf": [{"label": e["label"], "mean": e["per_frame_mean"]["p50"], "frac_below_0.5_p50": e["per_frame_fraction_below_0_50"]["p50"], "frac_below_0.5_p95": e["per_frame_fraction_below_0_50"]["p95"]} for e in exps],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
