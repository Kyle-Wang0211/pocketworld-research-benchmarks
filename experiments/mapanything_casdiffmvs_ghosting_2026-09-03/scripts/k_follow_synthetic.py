#!/usr/bin/env python3
"""Does the output ray field track the *supplied* calibration at all?
4 upright views; supply intrinsics with fx scaled by a factor relative to the
COLMAP reference; report output fx / reference fx. Also try passing
ray_directions instead of intrinsics, and pose+K together."""

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
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402

COMMON = dict(memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
names = [f"frame_{i:06d}.jpg" for i in (0, 1, 2, 3)]
cams, imgs, _ = read_model("/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse", ext=".bin")
by_name = {im.name: im for im in imgs.values()}


def views_with_scale(fscale):
    vs = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        pil = PILImage.open(f"/root/imgs132_up/{n}").convert("RGB")
        s = pil.size[0] / cam.height
        K = np.array([[fxu * s * fscale, 0, cxu * s], [0, fyu * s * fscale, cyu * s], [0, 0, 1]], dtype=np.float32)
        R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4)
        w2c[:3, :3] = R
        w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
        vs.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)), "intrinsics": torch.from_numpy(K), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
    return preprocess_inputs(vs)


def keep(views, keys):
    return [{k: v[k] for k in ("img", "data_norm_type", "true_shape", "idx", "instance", *keys) if k in v} for v in views]


model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")
ref = views_with_scale(1.0)
ref_fx = [float(v["intrinsics"][0, 0, 0]) for v in ref]
rows = []
with torch.no_grad():
    for fscale in (0.5, 0.77, 1.0, 1.3, 1.6):
        vs = views_with_scale(fscale)
        o = model.infer(keep(vs, ["intrinsics"]), ignore_pose_inputs=True, ignore_depth_inputs=True, ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=True, **COMMON)
        out = [float(p["intrinsics"][0, 0, 0]) / r for p, r in zip(o, ref_fx)]
        rows.append({"mode": "intrinsics", "input_fx_over_ref": fscale, "output_fx_over_ref": [round(x, 3) for x in out]})
        print(rows[-1], flush=True)
    # ray_directions instead of intrinsics (true K)
    vs = views_with_scale(1.0)
    rv = []
    for v in vs:
        H, W = v["img"].shape[-2:]
        _, rays = get_rays_in_camera_frame(v["intrinsics"][0], H, W, True)
        d = {k: v[k] for k in ("img", "data_norm_type", "true_shape", "idx", "instance") if k in v}
        d["ray_directions"] = rays[None].cpu()
        rv.append(d)
    o = model.infer(rv, ignore_pose_inputs=True, ignore_depth_inputs=True, ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=True, **COMMON)
    rows.append({"mode": "ray_directions(true)", "input_fx_over_ref": 1.0, "output_fx_over_ref": [round(float(p["intrinsics"][0, 0, 0]) / r, 3) for p, r in zip(o, ref_fx)]})
    print(rows[-1], flush=True)
    # K + pose, metric flag True vs False
    for metric in (False, True):
        vs = views_with_scale(1.0)
        for v in vs:
            v["is_metric_scale"] = torch.tensor([metric])
        o = model.infer(keep(vs, ["intrinsics", "camera_poses", "is_metric_scale"]), ignore_depth_inputs=True, ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=not metric, **COMMON)
        rows.append({"mode": f"K+pose is_metric={metric}", "input_fx_over_ref": 1.0, "output_fx_over_ref": [round(float(p["intrinsics"][0, 0, 0]) / r, 3) for p, r in zip(o, ref_fx)]})
        print(rows[-1], flush=True)
Path("/root/mapanything_k_follow_synthetic_20260903.json").write_text(json.dumps(rows, indent=2) + "\n")
