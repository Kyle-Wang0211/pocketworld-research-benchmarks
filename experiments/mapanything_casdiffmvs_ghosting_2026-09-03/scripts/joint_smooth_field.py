#!/usr/bin/env python3
"""Strengthen geometric consistency while never averaging MapAnything's pixels.

User verdict 2026-09-03: the anchored version (smooth per-view log-depth offset
field pinned to CasDiffMVS) looks best; per-pixel consensus averaging looks
worse even though it scores better on the official self-consistency metric
(that metric is gameable by smoothing). So the correction must stay a SMOOTH
per-view field -- MapAnything's high-frequency shape is then untouched by
construction -- and the way to strengthen it is to constrain the FIELD better:

  data term A (anchors)     : log z_mvs - log z_base   at CasDiffMVS fusion-kept
                              pixels (weight w_a)
  data term B (cross-view)  : log z_implied_by_partners - log z_base at pixels
                              with no anchor, where partners agree within the
                              official 2%/2% test (weight w_x)  <-- NEW: the
                              cross-view evidence enters the smooth field
                              instead of the depth map, so it fixes low-frequency
                              disagreement (whole-surface offsets = layering)
                              without touching detail
  smoothness                : lambda * |grad h|^2, solved at half resolution

Outer rounds recompute the cross-view targets from the current depths.
Presentation stays MapAnything: native 392x518 grid, every official-mask pixel,
original colours, production COLMAP cameras, nothing deleted.

Reported: the official metric (for locating, NOT for choosing a winner) plus a
DETAIL-PRESERVATION gauge -- the high-frequency content of each depth map
relative to the raw MapAnything depth. A correction that blurs detail shows up
there even when the consistency metric improves.
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
import scipy.sparse as sp
import scipy.sparse.linalg as spla
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


def laplacian(h, w):
    n = h * w
    idx = np.arange(n).reshape(h, w)
    rows, cols, vals = [], [], []
    for a, b in ((idx[:, :-1].ravel(), idx[:, 1:].ravel()), (idx[:-1, :].ravel(), idx[1:, :].ravel())):
        rows += [a, a, b, b]; cols += [a, b, a, b]
        vals += [np.ones_like(a), -np.ones_like(a), -np.ones_like(a), np.ones_like(a)]
    return sp.csr_matrix((np.concatenate(vals).astype(np.float64), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))


def sample_nearest(dmap, xy, H, W):
    grid = 2.0 * xy / torch.tensor([W - 1, H - 1], device=xy.device, dtype=xy.dtype) - 1.0
    grid = grid.clamp(-1.0, 1.0)[None, None]
    return F.grid_sample(dmap[None, None], grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0, 0]


def hf_energy(d, valid):
    """High-frequency content gauge: median |d - blur(d)| / d over valid pixels."""
    x = torch.from_numpy(d)[None, None] if isinstance(d, np.ndarray) else d[None, None]
    k = torch.ones(1, 1, 5, 5, device=x.device, dtype=x.dtype) / 25.0
    m = (torch.from_numpy(valid)[None, None].to(x.device).to(x.dtype) if isinstance(valid, np.ndarray) else valid[None, None].to(x.dtype))
    num = F.conv2d(x * m, k, padding=2)
    den = F.conv2d(m, k, padding=2).clamp_min(1e-6)
    blur = num / den
    r = (torch.abs(x - blur) / x.clamp_min(1e-6))[m > 0.5]
    return float(r.median())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
    ap.add_argument("--prior_dir", default="/root/casdiffmvs_prior_20260903/priors_blendmvg")
    ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--lam", type=float, default=4.0)
    ap.add_argument("--solve_scale", type=float, default=0.5)
    ap.add_argument("--w_anchor", type=float, default=1.0)
    ap.add_argument("--w_cross", type=float, default=0.5)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--irls", type=int, default=2)
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
    depth_raw = np.load(saved / "depth_z.npy")[..., 0].astype(np.float32)
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    rgb = np.load(saved / "img_no_norm.npy")
    V, H, W = depth_raw.shape
    valid = mask & nam & (depth_raw > 0)
    s2f = json.load(open(args.mapping))
    f2s = {int(f): s for s, f in enumerate(s2f)}
    pstats = {t["src"]: t for t in json.load(open(Path(args.prior_dir) / "prior_stats.json"))["per_view"]}

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

    s_m = W / 1500.0
    off_v = (2000.0 * s_m - H) / 2.0
    vm, um = np.meshgrid(np.arange(H, dtype=np.float64), np.arange(W, dtype=np.float64), indexing="ij")
    x15 = (um + 0.5) / s_m - 0.5
    y15 = (vm + 0.5 + off_v) / s_m - 0.5
    x768 = (y15 + 0.5) * (768.0 / 2000.0) - 0.5
    y576 = ((1500.0 - 1.0 - x15) + 0.5) * (576.0 / 1500.0) - 0.5
    gridN = torch.from_numpy(np.stack([2 * x768 / 767.0 - 1, 2 * y576 / 575.0 - 1], -1).astype(np.float32))[None]

    z_base = np.zeros_like(depth_raw)
    z_mvs = np.zeros_like(depth_raw)
    anchor = np.zeros((V, H, W), dtype=bool)
    for f in range(V):
        s = f2s[f]
        a, b = float(pstats[s]["a"]), float(pstats[s]["b"])
        z_base[f] = np.where(valid[f], a * depth_raw[f] + b, 0.0)
        dm = read_pfm(str(Path(args.cas_out) / "depth_est" / f"{s:08d}.pfm"))[0].astype(np.float32)
        fin = (np.asarray(PILImage.open(Path(args.cas_out) / "mask" / f"{s:08d}_final.png")) > 0).astype(np.float32)
        dn = F.grid_sample(torch.from_numpy(dm)[None, None], gridN, mode="bilinear", align_corners=True, padding_mode="border")[0, 0].numpy()
        an = F.grid_sample(torch.from_numpy(fin)[None, None], gridN, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0].numpy()
        z_mvs[f] = np.where(valid[f], dn, 0.0)
        anchor[f] = (an > 0.5) & valid[f] & (dn > 0)

    Kt = torch.from_numpy(Kc).to(dev)
    Pt = torch.from_numpy(Pc).to(dev)
    W2C = closed_form_pose_inverse(Pt)
    zb = torch.from_numpy(z_base).to(dev)
    zmv = torch.from_numpy(z_mvs).to(dev)
    validt = torch.from_numpy(valid).to(dev)
    anchort = torch.from_numpy(anchor).to(dev)
    logb = torch.log(zb.clamp_min(1e-6))

    depth = zb.clone()
    dz_list = [depth[i][None, ..., None] for i in range(V)]
    frustum = _compute_frustum_intersection_matrix([Kt[i][None] for i in range(V)], [Pt[i][None] for i in range(V)], dz_list, 50, dev)
    partners = [[int(j) for j in frustum[i].nonzero(as_tuple=True)[0].tolist() if j != i] for i in range(V)]

    hs, ws = int(round(H * args.solve_scale)), int(round(W * args.solve_scale))
    L = laplacian(hs, ws)
    down = lambda a: F.interpolate(a[None, None].float(), size=(hs, ws), mode="area")[0, 0]
    up = lambda a: F.interpolate(torch.from_numpy(a.reshape(hs, ws).astype(np.float32))[None, None], size=(H, W), mode="bilinear", align_corners=False)[0, 0]

    def to_world(i, pts_cam):
        homo = torch.cat([pts_cam, torch.ones_like(pts_cam[..., :1])], -1)
        return einsum(Pt[i], homo, "i k, ... k -> ... i")[..., :3]

    def to_cam(j, pts_world):
        homo = torch.cat([pts_world, torch.ones_like(pts_world[..., :1])], -1)
        return einsum(W2C[j], homo, "i k, ... k -> ... i")[..., :3]

    def mv(d):
        dz = [d[i][None, ..., None] for i in range(V)]
        conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=[Kt[i][None] for i in range(V)], camera_poses=[Pt[i][None] for i in range(V)], depth_masks=[validt[i][None] for i in range(V)])
        fb = [float((cc[validt[i][None]] < 0.5).float().mean()) for i, cc in enumerate(conf)]
        fbf = [float((conf[i][(validt[i] & ~anchort[i])[None]] < 0.5).float().mean()) for i in range(V)]
        del conf; torch.cuda.empty_cache()
        return {"frac_below_0_50_p50": float(np.median(fb)), "frac_below_0_50_p95": float(np.percentile(fb, 95)), "anchorfree_frac_below_0_50_p50": float(np.median(fbf))}

    hf_raw = float(np.median([hf_energy(zb[i], validt[i]) for i in range(0, V, 11)]))
    hist = []
    h_full = torch.zeros(V, H, W, device=dev)
    for rnd in range(args.rounds):
        for i in range(V):
            pts_cam_i, _ = depthmap_to_camera_frame(depth[i][None], Kt[i][None])
            Xi = to_world(i, pts_cam_i[0])
            acc = torch.zeros(H, W, device=dev)
            cnt = torch.zeros(H, W, device=dev)
            for j in partners[i]:
                Xij = to_cam(j, Xi)
                proj = _project_pts3d_to_image_with_depth(Xij[None], Kt[j][None])[0]
                ok = _in_image(proj, H, W, min_depth=args.min_depth) & validt[i] & ~anchort[i]
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
            # targets for the SMOOTH field only
            tgt = torch.zeros(H, W, device=dev)
            wgt = torch.zeros(H, W, device=dev)
            am = anchort[i]
            tgt[am] = torch.log(zmv[i][am].clamp_min(1e-6)) - logb[i][am]
            wgt[am] = args.w_anchor
            cm = (cnt > 0) & validt[i] & ~am
            tgt[cm] = torch.log((acc[cm] / cnt[cm]).clamp_min(1e-6)) - logb[i][cm]
            wgt[cm] = args.w_cross
            wd = down(wgt).double().cpu().numpy().ravel()
            td = (down(tgt * wgt).double() / down(wgt).double().clamp_min(1e-9)).cpu().numpy().ravel()
            hcur = np.zeros(hs * ws)
            w = wd.copy()
            for _ in range(args.irls):
                A = (sp.diags(w) + args.lam * L + 1e-9 * sp.identity(hs * ws)).tocsc()
                hcur = spla.spsolve(A, w * td)
                r = (td - hcur)[wd > 0]
                s_mad = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
                k = 1.345 * s_mad
                ww = np.where(np.abs(td - hcur) <= k, 1.0, k / np.maximum(np.abs(td - hcur), 1e-9))
                w = wd * ww
            h_full[i] = up(hcur).to(dev)
            depth[i] = torch.where(validt[i], zb[i] * torch.exp(h_full[i]), torch.zeros_like(zb[i]))
        hf_now = float(np.median([hf_energy(depth[i], validt[i]) for i in range(0, V, 11)]))
        disp = (torch.abs(depth - zb) / zb.clamp_min(1e-6))[validt]
        hist.append({"round": rnd, **mv(depth), "hf_ratio_vs_raw": hf_now / hf_raw, "h_spread_p95_p05_p50": float(np.median([float(torch.quantile(h_full[i][validt[i]].float(), 0.95) - torch.quantile(h_full[i][validt[i]].float(), 0.05)) for i in range(V)])), "rel_disp_vs_base_p50": float(disp.median())})
        print("round", rnd, hist[-1], flush=True)

    depth_np = depth.cpu().numpy()
    result = {
        "purpose": "cross-view evidence enters a SMOOTH per-view log-depth field (never the depth map), anchored by CasDiffMVS; MapAnything native grid, all pixels, original colours; detail preserved by construction",
        "lam": args.lam, "solve_scale": args.solve_scale, "w_anchor": args.w_anchor, "w_cross": args.w_cross, "rounds": args.rounds,
        "note_on_metric": "official mvconf is gameable by smoothing and is reported for locating only; hf_ratio_vs_raw near 1.0 certifies MapAnything detail is intact",
        "hf_ratio_vs_raw_final": hist[-1]["hf_ratio_vs_raw"],
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
        ply = out / "mapanything_joint_smooth_field.ply"
        o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
        np.save(out / "depth_native_final.npy", depth_np)
        result["points"] = int(xyz.shape[0])
        result["ply"] = {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}
    result["seconds_total"] = time.time() - t0
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
