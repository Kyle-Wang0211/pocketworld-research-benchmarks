#!/usr/bin/env python3
"""Was mixing MapAnything's depth with COLMAP's cameras the mistake?

MapAnything predicts a focal ~23% shorter than the true one. Its depth_z is the
Z-depth in ITS OWN camera, so its own reconstruction pts3d = z * dir_predicted is
self-consistent. Unprojecting that same depth with the TRUE COLMAP intrinsics
places each point along a DIFFERENT ray:

    x = (u - cx) / fx * z      fx_pred ~= 286   vs   fx_true ~= 371

At the image edge (u-cx ~ 196 px) and z = 4 m that is 2.74 m vs 2.11 m, a 63 cm
difference, and the error grows LINEARLY with z. Each view is distorted about its
own optical axis, so the same surface lands in a different place in every view.
That is exactly the reported symptom: ghosting plus far-field warping.

Every candidate since the anchored version was built on COLMAP cameras. This
compares, from the SAME saved depth tensors and with the same ruler and the same
absolute neighbourhood radius:

  A  own    : predicted K + predicted poses      (what the official demo does)
  B  colmap : production COLMAP K + poses        (what every candidate used)
  C  own_K_colmap_pose / D colmap_K_own_pose     (which half matters)

A is brought into the same metric scale as B with a Umeyama similarity computed
from the camera centres, so the absolute-radius ruler is fair.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
from PIL import Image as PILImage

sys.path.insert(0, "/root/map-anything-official-exact-src-20260902")
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402

S = "/root/mapanything_layer_audit_A_imgs132_up_20260903"
info = json.load(open(f"{S}/info.json"))
names = [m["name"] for m in info["image_manifest"]]
depth = np.load(f"{S}/depth_z.npy")[..., 0].astype(np.float64)
Kp = np.load(f"{S}/intrinsics.npy").astype(np.float64)
Pp = np.load(f"{S}/camera_poses.npy").astype(np.float64)
mask = np.load(f"{S}/mask.npy")[..., 0].astype(bool)
nam = np.load(f"{S}/non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4:
    nam = nam[..., 0]
rgb = np.load(f"{S}/img_no_norm.npy")
# the per-view affine every candidate applies (fitted against CasDiffMVS); without it
# the COLMAP-camera arms carry MapAnything's own ~1/3.9 depth scale and the scene is
# squashed toward the cameras, which would make the comparison meaningless
_ps = {t["src"]: t for t in json.load(open("/root/casdiffmvs_prior_20260903/priors_blendmvg/prior_stats.json"))["per_view"]}
_s2f = json.load(open("/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json"))
_f2s = {int(f): sidx for sidx, f in enumerate(_s2f)}
V, H, W = depth.shape
valid = mask & nam & (depth > 0)

cams, imgs, _ = read_model("/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse", ext=".bin")
by = {im.name: im for im in imgs.values()}
rv = []
for n in names:
    im = by[n]; cam = cams[im.camera_id]
    fx, fy, cx, cy = cam.params
    _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
    sc = 1500.0 / 3024.0
    K15 = np.array([[fxu*sc, 0, cxu*sc], [0, fyu*sc, cyu*sc], [0, 0, 1]], dtype=np.float32)
    R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
    w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = t
    c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
    pil = PILImage.open(f"/root/imgs132_up/{n}").convert("RGB")
    rv.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8).copy()),
               "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w),
               "is_metric_scale": torch.tensor([False])})
proc = preprocess_inputs(rv)
Kc = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
Pc = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])

print("focal  predicted p50 %.1f   colmap p50 %.1f   ratio %.4f" % (
    np.median(Kp[:, 0, 0]), np.median(Kc[:, 0, 0]), np.median(Kp[:, 0, 0] / Kc[:, 0, 0])), flush=True)


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / src.shape[0]
    U, D, Vt = np.linalg.svd(cov)
    Sg = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        Sg[2, 2] = -1
    R = U @ Sg @ Vt
    s = np.trace(np.diag(D) @ Sg) / ((xs ** 2).sum() / src.shape[0])
    return s, R, mu_d - s * R @ mu_s


s_sim, R_sim, t_sim = umeyama(Pp[:, :3, 3], Pc[:, :3, 3])
print("Umeyama predicted->colmap: scale %.4f" % s_sim, flush=True)


def build(useKp, usePp, tag, align, affine):
    xyz, col = [], []
    for f in range(V):
        K = Kp[f] if useKp else Kc[f]
        P = Pp[f] if usePp else Pc[f]
        yy, xx = np.nonzero(valid[f])
        z = depth[f][yy, xx]
        if affine:
            st = _ps[_f2s[f]]
            z = float(st["a"]) * z + float(st["b"])
        x = (xx - K[0, 2]) / K[0, 0] * z
        y = (yy - K[1, 2]) / K[1, 1] * z
        pc = np.stack([x, y, z, np.ones_like(z)], 1)
        Xw = (P @ pc.T).T[:, :3]
        if align:
            Xw = (s_sim * (R_sim @ Xw.T)).T + t_sim
        xyz.append(Xw.astype(np.float32)); col.append(rgb[f][valid[f]])
    xyz = np.concatenate(xyz); col = np.concatenate(col)
    p = o3d.geometry.PointCloud()
    p.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    p.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
    out = f"/root/cammix_{tag}.ply"
    o3d.io.write_point_cloud(out, p, write_ascii=False, compressed=False)
    lo, hi = np.percentile(xyz, 1, 0), np.percentile(xyz, 99, 0)
    print("%-22s pts %d  diag %.2f  -> %s" % (tag, xyz.shape[0], np.linalg.norm(hi - lo), out), flush=True)
    return out


t0 = time.time()
build(True, True, "A_own_K_own_pose", align=True, affine=False)
build(False, False, "B_colmap_K_colmap_pose", align=False, affine=True)
build(True, False, "C_ownK_colmapPose", align=False, affine=True)
build(False, True, "D_colmapK_ownPose", align=True, affine=False)
print("built in %.0fs" % (time.time() - t0), flush=True)
