#!/usr/bin/env python3
"""Three rulers, each guarding against a failure the others cannot see.
Calibrated on the user's verdicts: the version they rejected must score badly
on at least one ruler, and the version they preferred must not.

  1. SEAM      cross-boundary / within-region adjacent depth jump along the
               CasDiffMVS anchor-mask boundary. Catches treatments applied to a
               hard subset of pixels (validated: the rejected version scores
               3.65 here, the preferred one 1.29).
  2. LAYERS    fraction of pixels where partner views deposit a second surface
               separated by more than max(2 cm, 1% z) carrying >=15% of the
               samples. This is ghosting proper.
  3. DETAIL    high-frequency content relative to the raw MapAnything depth
               (median |z - blur(z)|/z ratio). Guards against buying ruler 2
               with blur, which is how the self-consistency metric was gamed.

A candidate is only worth the user's eyes if it improves LAYERS while keeping
SEAM near 1 and DETAIL near 1."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from einops import einsum
from PIL import Image as PILImage

sys.path.insert(0, "/root/map-anything-official-exact-src-20260902")
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse, depthmap_to_camera_frame  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.multiview_confidence import _in_image, _project_pts3d_to_image_with_depth  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402


def hf(z, v):
    x = z[None, None]
    m = v[None, None].to(x.dtype)
    k = torch.ones(1, 1, 5, 5, device=z.device, dtype=x.dtype) / 25.0
    blur = F.conv2d(x * m, k, padding=2) / F.conv2d(m, k, padding=2).clamp_min(1e-6)
    r = (torch.abs(x - blur) / x.clamp_min(1e-6))[m > 0.5]
    return float(r.median())


ap = argparse.ArgumentParser()
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--images", default="/root/imgs132_up")
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
ap.add_argument("--reference", required=True, help="name=path for the raw/base depth used as the DETAIL reference")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--views", type=int, default=16)
ap.add_argument("--partners", type=int, default=16)
ap.add_argument("--abs_gap", type=float, default=0.02)
ap.add_argument("--rel_gap", type=float, default=0.01)
ap.add_argument("--min_mass", type=float, default=0.15)
ap.add_argument("--out", required=True)
a = ap.parse_args()
t0 = time.time()
dev = "cuda"

saved = Path(a.saved)
info = json.load(open(saved / "info.json"))
names = [m["name"] for m in info["image_manifest"]]
mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4:
    nam = nam[..., 0]
V, H, W = mask.shape
s2f = json.load(open(a.mapping))
f2s = {int(f): s for s, f in enumerate(s2f)}

cams, imgs, _ = read_model(a.colmap_sparse, ext=".bin")
by_name = {im.name: im for im in imgs.values()}
rv = []
for n in names:
    im = by_name[n]; cam = cams[im.camera_id]
    fx, fy, cx, cy = cam.params
    _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
    sc = 1500.0 / 3024.0
    K15 = np.array([[fxu * sc, 0, cxu * sc], [0, fyu * sc, cyu * sc], [0, 0, 1]], dtype=np.float32)
    R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
    w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = t
    c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
    pil = PILImage.open(Path(a.images) / n).convert("RGB")
    rv.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8).copy()), "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
proc = preprocess_inputs(rv)
Kt = torch.stack([v["intrinsics"][0] for v in proc]).to(dev)
Pt = torch.stack([v["camera_poses"][0] for v in proc]).to(dev)
W2C = closed_form_pose_inverse(Pt)

s_m = W / 1500.0
off_v = (2000.0 * s_m - H) / 2.0
vm, um = np.meshgrid(np.arange(H, dtype=np.float64), np.arange(W, dtype=np.float64), indexing="ij")
x15 = (um + 0.5) / s_m - 0.5
y15 = (vm + 0.5 + off_v) / s_m - 0.5
x768 = (y15 + 0.5) * (768.0 / 2000.0) - 0.5
y576 = ((1500.0 - 1.0 - x15) + 0.5) * (576.0 / 1500.0) - 0.5
gridN = torch.from_numpy(np.stack([2 * x768 / 767.0 - 1, 2 * y576 / 575.0 - 1], -1).astype(np.float32))[None]

probe = list(range(0, V, max(1, V // a.views)))[: a.views]
anchor = {}
for f in probe:
    s = f2s[f]
    fin = (np.asarray(PILImage.open(Path(a.cas_out) / "mask" / f"{s:08d}_final.png")) > 0).astype(np.float32)
    anchor[f] = torch.from_numpy((F.grid_sample(torch.from_numpy(fin)[None, None], gridN, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0].numpy() > 0.5) & mask[f] & nam[f]).to(dev)

ref_name, ref_path = a.reference.split("=", 1)
ref = np.load(ref_path).astype(np.float32)
hf_ref = {}
for f in probe:
    z = torch.from_numpy(ref[f]).to(dev)
    v = torch.from_numpy(mask[f] & nam[f]).to(dev) & (z > 0)
    hf_ref[f] = hf(z, v)

report = {"reference": ref_name, "rulers": {}}
for spec in [a.reference] + a.sets:
    name, path = spec.split("=", 1)
    d = np.load(path).astype(np.float32)
    seam, layers, det = [], [], []
    for f in probe:
        z = torch.from_numpy(d[f]).to(dev)
        v = torch.from_numpy(mask[f] & nam[f]).to(dev) & (z > 0)
        am = anchor[f]
        cr, ins, fr = [], [], []
        for axis in (0, 1):
            if axis == 0:
                dz = (z[1:] - z[:-1]).abs() / z[:-1].clamp_min(1e-6); vv = v[1:] & v[:-1]; a1, a2 = am[1:], am[:-1]
            else:
                dz = (z[:, 1:] - z[:, :-1]).abs() / z[:, :-1].clamp_min(1e-6); vv = v[:, 1:] & v[:, :-1]; a1, a2 = am[:, 1:], am[:, :-1]
            cr.append(dz[vv & (a1 != a2)]); ins.append(dz[vv & a1 & a2]); fr.append(dz[vv & ~a1 & ~a2])
        c_ = float(torch.cat(cr).median()); i_ = float(torch.cat(ins).median()); f_ = float(torch.cat(fr).median())
        seam.append(c_ / max(i_, f_))
        det.append(hf(z, v) / max(hf_ref[f], 1e-9))
        # layers
        first = torch.full((H, W), float("inf"), device=dev)
        near = torch.zeros(H, W, device=dev); far = torch.zeros(H, W, device=dev)
        js = [j for j in range(V) if j != f]
        js = js[:: max(1, len(js) // a.partners)][: a.partners]
        for rep in range(2):
            for j in js:
                pc, _ = depthmap_to_camera_frame(torch.from_numpy(d[j]).to(dev)[None], Kt[j][None])
                homo = torch.cat([pc[0], torch.ones_like(pc[0][..., :1])], -1)
                Xw = einsum(Pt[j], homo, "p q, ... q -> ... p")[..., :3]
                h2 = torch.cat([Xw, torch.ones_like(Xw[..., :1])], -1)
                Xi = einsum(W2C[f], h2, "p q, ... q -> ... p")[..., :3]
                proj = _project_pts3d_to_image_with_depth(Xi[None], Kt[f][None])[0]
                vj = torch.from_numpy(mask[j] & nam[j]).to(dev) & (torch.from_numpy(d[j]).to(dev) > 0)
                ok = _in_image(proj, H, W, min_depth=0.04) & vj
                if not ok.any():
                    continue
                xy = proj[..., :2][ok].round().long()
                zz = proj[..., 2][ok]
                lin = xy[:, 1].clamp(0, H - 1) * W + xy[:, 0].clamp(0, W - 1)
                if rep == 0:
                    first.reshape(-1).scatter_reduce_(0, lin, zz, reduce="amin")
                else:
                    fz = first.reshape(-1)[lin]
                    thr = fz + torch.maximum(torch.full_like(fz, a.abs_gap), a.rel_gap * fz)
                    nn = zz <= thr
                    near.reshape(-1).scatter_add_(0, lin[nn], torch.ones_like(zz[nn]))
                    far.reshape(-1).scatter_add_(0, lin[~nn], torch.ones_like(zz[~nn]))
        tot = near + far
        has = (tot >= 4) & v
        layers.append(float(((far[has] / tot[has]) >= a.min_mass).float().mean()) if has.any() else float("nan"))
    report["rulers"][name] = {
        "SEAM_cross_over_within_p50": float(np.median(seam)),
        "LAYERS_second_surface_frac_p50": float(np.nanmedian(layers)),
        "DETAIL_hf_ratio_vs_reference_p50": float(np.median(det)),
        "path": path,
    }
    r = report["rulers"][name]
    print(f"{name:26s} SEAM {r['SEAM_cross_over_within_p50']:.3f}   LAYERS {r['LAYERS_second_surface_frac_p50']:.4f}   DETAIL {r['DETAIL_hf_ratio_vs_reference_p50']:.4f}", flush=True)

report["seconds"] = time.time() - t0
Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
