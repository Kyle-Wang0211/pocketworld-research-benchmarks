#!/usr/bin/env python3
"""Does the Apache MapAnything checkpoint follow a supplied calibration on this
scene? Small diagnostic (8 views) using only official infer() options.

Runs (all with the official demo's amp/mask/edge settings):
  R1 image-only, 8 upright views
  R2 K given (ignore_pose_inputs=True), 8 upright views
  R3 K + pose given (non-metric, ignore_*_scale_inputs=True), 8 upright views
  R4 single-view image-only, each of the 8 upright views
  R5 single-view image-only, each of the 8 *sideways* (landscape-stored) views
  R6 image-only, 8 sideways views
Reports predicted fx / reference fx, ray angular error vs reference rays,
pose error vs input pose (R3), and official multi-view consistency (R1-R3).
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

from mapanything.models import MapAnything  # noqa: E402
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse, get_rays_in_camera_frame  # noqa: E402
from mapanything.utils.image import load_images, preprocess_inputs  # noqa: E402
from mapanything.utils.metrics import l2_distance_of_unit_ray_directions_to_angular_error  # noqa: E402
from mapanything.utils.multiview_confidence import compute_multiview_depth_confidence  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera, self_test  # noqa: E402

COMMON = dict(memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)


def q(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    return {"n": int(v.size), "p50": float(np.median(v)), "min": float(v.min()), "max": float(v.max())}


def ref_views_from_colmap(names, cams, by_name, images_dir, upright: bool):
    """Build reference views (img + intrinsics + c2w) at the *stored* image size."""
    views = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        pil = PILImage.open(Path(images_dir) / n).convert("RGB")
        if upright:
            _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
            s = pil.size[0] / cam.height  # stored width / 3024
            K = np.array([[fxu * s, 0, cxu * s], [0, fyu * s, cyu * s], [0, 0, 1]])
            R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        else:
            s = pil.size[0] / cam.width  # stored width / 4032
            K = np.array([[fx * s, 0, cx * s], [0, fy * s, cy * s], [0, 0, 1]])
            R, t = qvec2rotmat(im.qvec), im.tvec
        w2c = np.eye(4)
        w2c[:3, :3] = R
        w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0]
        views.append(
            {
                "img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)),
                "intrinsics": torch.from_numpy(K.astype(np.float32)),
                "camera_poses": torch.from_numpy(c2w.astype(np.float32)),
                "is_metric_scale": torch.tensor([False]),
            }
        )
    return views


def strip(views, keep):
    out = []
    for v in views:
        d = {k: v[k] for k in ("img", "data_norm_type", "true_shape", "idx", "instance") if k in v}
        for k in keep:
            d[k] = v[k]
        out.append(d)
    return out


def eval_outputs(outputs, ref_proc, device, label, want_pose=False):
    rows = []
    for i, (pred, ref) in enumerate(zip(outputs, ref_proc)):
        refK = ref["intrinsics"][0].float().to(device)
        H, W = pred["depth_z"].shape[1:3]
        _, ref_rays = get_rays_in_camera_frame(refK, H, W, True)
        pr = pred["ray_directions"][0].float()
        pr = pr / pr.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        ang = l2_distance_of_unit_ray_directions_to_angular_error((pr - ref_rays).norm(dim=-1).clamp(max=2.0))
        m = pred["mask"][0].squeeze(-1).bool()
        row = {
            "view": i,
            "pred_fx": float(pred["intrinsics"][0, 0, 0]),
            "ref_fx": float(refK[0, 0]),
            "fx_ratio": float(pred["intrinsics"][0, 0, 0] / refK[0, 0]),
            "ray_err_deg_p50": float(ang[m].median()),
        }
        if want_pose:
            P = pred["camera_poses"][0].float().cpu().numpy()
            Q = ref["camera_poses"][0].float().cpu().numpy()
            # relative to view 0 in both (model world = view 0)
            row["pose_available"] = True
            rows.append((row, P, Q))
        else:
            rows.append((row, None, None))
    result = {"label": label, "fx_ratio": q([r[0]["fx_ratio"] for r in rows]), "ray_err_deg_p50": q([r[0]["ray_err_deg_p50"] for r in rows]), "per_view": [r[0] for r in rows]}
    if want_pose:
        P0, Q0 = rows[0][1], rows[0][2]
        rel_rot, rel_dir = [], []
        for row, P, Q in rows[1:]:
            Pr = np.linalg.inv(P0) @ P
            Qr = np.linalg.inv(Q0) @ Q
            cosang = (np.trace(Pr[:3, :3].T @ Qr[:3, :3]) - 1) / 2
            rel_rot.append(float(np.degrees(np.arccos(np.clip(cosang, -1, 1)))))
            a, b = Pr[:3, 3], Qr[:3, 3]
            cosd = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
            rel_dir.append(float(np.degrees(np.arccos(np.clip(cosd, -1, 1)))))
        result["pose_vs_input_rel_rot_deg"] = q(rel_rot)
        result["pose_vs_input_rel_trans_dir_deg"] = q(rel_dir)
    return result


def mvconf(outputs, device):
    dz = [p["depth_z"].to(device) for p in outputs]
    Ks = [p["intrinsics"].to(device) for p in outputs]
    Ps = [p["camera_poses"].to(device) for p in outputs]
    Ms = [(p["non_ambiguous_mask"].bool() & p["mask"].squeeze(-1).bool() & (p["depth_z"].squeeze(-1) > 0)).to(device) for p in outputs]
    conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
    fb = [float((c[Ms[i]] < 0.5).float().mean()) for i, c in enumerate(conf)]
    return {"frac_below_0_50_per_view": [round(x, 4) for x in fb], "frac_below_0_50_p50": float(np.median(fb))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upright_images", required=True)
    ap.add_argument("--sideways_images", required=True)
    ap.add_argument("--colmap_sparse", required=True)
    ap.add_argument("--frames", default="0,1,2,3,4,5,6,7")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    self_test(rotate_pinhole_90degcw)
    idx = [int(x) for x in args.frames.split(",")]
    names = [f"frame_{i:06d}.jpg" for i in idx]
    device = "cuda"
    cams, imgs, _ = read_model(args.colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    model = MapAnything.from_pretrained("facebook/map-anything-apache").to(device)

    up_ref = preprocess_inputs(ref_views_from_colmap(names, cams, by_name, args.upright_images, upright=True))
    side_ref = preprocess_inputs(ref_views_from_colmap(names, cams, by_name, args.sideways_images, upright=False))
    up_img = load_images([str(Path(args.upright_images) / n) for n in names])
    side_img = load_images([str(Path(args.sideways_images) / n) for n in names])
    # sanity: official preprocess and load_images agree on pixels
    for a, b in zip(up_ref, up_img):
        assert float((a["img"].float() - b["img"].float()).abs().max()) < 1e-5, "preprocess mismatch"

    report = {"frames": names}
    with torch.no_grad():
        o = model.infer(up_img, **COMMON)
        report["R1_imageonly_upright"] = eval_outputs(o, up_ref, device, "R1")
        report["R1_imageonly_upright"]["mvconf"] = mvconf(o, device)
        del o

        o = model.infer(strip(up_ref, ["intrinsics"]), ignore_pose_inputs=True, ignore_depth_inputs=True, ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=True, **COMMON)
        report["R2_K_given_upright"] = eval_outputs(o, up_ref, device, "R2")
        report["R2_K_given_upright"]["mvconf"] = mvconf(o, device)
        del o

        o = model.infer(strip(up_ref, ["intrinsics", "camera_poses", "is_metric_scale"]), ignore_depth_inputs=True, ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=True, **COMMON)
        report["R3_K_pose_given_upright"] = eval_outputs(o, up_ref, device, "R3", want_pose=True)
        report["R3_K_pose_given_upright"]["mvconf"] = mvconf(o, device)
        del o

        single_up, single_side = [], []
        for i in range(len(names)):
            o = model.infer([up_img[i]], **COMMON)
            single_up.append(eval_outputs(o, [up_ref[i]], device, "R4")["per_view"][0])
            o = model.infer([side_img[i]], **COMMON)
            single_side.append(eval_outputs(o, [side_ref[i]], device, "R5")["per_view"][0])
        report["R4_singleview_upright"] = {"fx_ratio": q([r["fx_ratio"] for r in single_up]), "ray_err_deg_p50": q([r["ray_err_deg_p50"] for r in single_up]), "per_view": single_up}
        report["R5_singleview_sideways"] = {"fx_ratio": q([r["fx_ratio"] for r in single_side]), "ray_err_deg_p50": q([r["ray_err_deg_p50"] for r in single_side]), "per_view": single_side}

        o = model.infer(side_img, **COMMON)
        report["R6_imageonly_sideways"] = eval_outputs(o, side_ref, device, "R6")
        report["R6_imageonly_sideways"]["mvconf"] = mvconf(o, device)
        del o

    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    brief = {}
    for k, v in report.items():
        if k == "frames":
            continue
        brief[k] = {kk: vv for kk, vv in v.items() if kk in ("fx_ratio", "ray_err_deg_p50", "pose_vs_input_rel_rot_deg", "pose_vs_input_rel_trans_dir_deg")}
        if "mvconf" in v:
            brief[k]["mvconf_frac_below_0_50_p50"] = v["mvconf"]["frac_below_0_50_p50"]
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
