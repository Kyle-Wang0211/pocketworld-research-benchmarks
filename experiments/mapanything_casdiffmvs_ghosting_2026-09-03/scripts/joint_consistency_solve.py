#!/usr/bin/env python3
"""Strengthen geometric consistency of the MapAnything cloud by a JOINT solve
over all 132 views, directly minimising cross-view depth disagreement.

Presentation stays MapAnything: native 392x518 grid, every official-mask pixel,
original colours, production COLMAP cameras. CasDiffMVS only supplies anchors
(gauge + local truth), per the user's role split.

Model (physically motivated by the measured root cause: the model's predicted
intrinsics are ~23% too wide, which is a smooth RADIAL depth distortion, plus a
per-view scale):
    z_i(p) = z_i^aff(p) * exp( phi(p) . c_i ),  phi = [1, r^2, r^4, u, v, u*v]
so the correction is smooth by construction and cannot damage MapAnything's
fine shape, while it can absorb per-view scale + radial + tilt error.

Objective (Gauss-Newton, Huber IRLS, outer iterations re-project):
  cross-view : for sampled pixel p in view i and partner j,
               r = log z_j(q) - log z_exp(p)          (0 when surfaces agree)
               dr/dc_j = phi(q),  dr/dc_i = -c_ij phi(p),
               c_ij = (z_exp - t_z) / z_exp   (exact derivative of log z_exp
               w.r.t. log z_i along the ray)
  anchor     : r = log z_i(p) - log z_mvs(p) on CasDiffMVS fusion-kept pixels
  ridge      : small, keeps the solve bounded

Normal equations are assembled per view pair as K x K blocks, so the system is
(V*K) x (V*K) = 792 x 792 and solves exactly.
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
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.multiview_confidence import compute_multiview_depth_confidence  # noqa: E402
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


def basis(u, v, K):
    """u,v normalised to [-1,1]; returns (N,K)."""
    r2 = u * u + v * v
    cols = [torch.ones_like(u), r2, r2 * r2, u, v, u * v]
    return torch.stack(cols[:K], -1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
    ap.add_argument("--prior_dir", default="/root/casdiffmvs_prior_20260903/priors_blendmvg")
    ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--K", type=int, default=6)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--partners", type=int, default=32)
    ap.add_argument("--outer", type=int, default=4)
    ap.add_argument("--gate", type=float, default=0.15, help="initial |log| gate for cross-view residuals")
    ap.add_argument("--anchor_weight", type=float, default=1.0)
    ap.add_argument("--ridge", type=float, default=1e-4)
    ap.add_argument("--no_export", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"
    K = args.K

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

    # cameras on the native grid
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
    Kc = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
    Pc = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])

    # native-grid sampler for the 768x576 CasDiffMVS maps
    s_m = W / 1500.0
    off_v = (2000.0 * s_m - H) / 2.0
    vm, um = np.meshgrid(np.arange(H, dtype=np.float64), np.arange(W, dtype=np.float64), indexing="ij")
    x15 = (um + 0.5) / s_m - 0.5
    y15 = (vm + 0.5 + off_v) / s_m - 0.5
    x_l = y15
    y_l = 1500.0 - 1.0 - x15
    x768 = (x_l + 0.5) * (768.0 / 2000.0) - 0.5
    y576 = (y_l + 0.5) * (576.0 / 1500.0) - 0.5
    gridN = torch.from_numpy(np.stack([2 * x768 / 767.0 - 1, 2 * y576 / 575.0 - 1], -1).astype(np.float32))[None]

    # base depth = per-view affine-aligned MapAnything depth (COLMAP scale); anchors from CasDiffMVS
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

    zb = torch.from_numpy(z_base).to(dev)
    zm = torch.from_numpy(z_mvs).to(dev)
    validt = torch.from_numpy(valid).to(dev)
    anchort = torch.from_numpy(anchor).to(dev)
    Kt = torch.from_numpy(Kc).to(dev)
    Pt = torch.from_numpy(Pc).to(dev)
    W2C = closed_form_pose_inverse(Pt.float()).double()

    # sample grid (strided) per view
    vs = torch.arange(0, H, args.stride, device=dev)
    us = torch.arange(0, W, args.stride, device=dev)
    vv, uu = torch.meshgrid(vs, us, indexing="ij")
    uu = uu.reshape(-1).double(); vv = vv.reshape(-1).double()
    un = (uu / (W - 1)) * 2 - 1
    vn = (vv / (H - 1)) * 2 - 1
    PHI = basis(un, vn, K)  # (M,K)
    M = PHI.shape[0]

    def dirs(i):
        return torch.stack([(uu - Kt[i][0, 2]) / Kt[i][0, 0], (vv - Kt[i][1, 2]) / Kt[i][1, 1], torch.ones_like(uu)], -1)

    def h_of(i, c, phi):
        return phi @ c[i]

    # choose partners by actual overlap using the base depths
    def overlap_counts():
        cnt = torch.zeros(V, V, device=dev)
        for i in range(V):
            di = dirs(i)
            zi = zb[i][vv.long(), uu.long()]
            ok_i = validt[i][vv.long(), uu.long()] & (zi > 0)
            Xi = (Pt[i][:3, :3] @ (zi[:, None] * di).T).T + Pt[i][:3, 3]
            for j in range(V):
                if j == i:
                    continue
                Xj = (W2C[j][:3, :3] @ Xi.T).T + W2C[j][:3, 3]
                zc = Xj[:, 2]
                x = Kt[j][0, 0] * Xj[:, 0] / zc.clamp_min(1e-6) + Kt[j][0, 2]
                y = Kt[j][1, 1] * Xj[:, 1] / zc.clamp_min(1e-6) + Kt[j][1, 2]
                ok = ok_i & (zc > 0.04) & (x >= 0) & (x <= W - 1) & (y >= 0) & (y <= H - 1)
                cnt[i, j] = ok.float().sum()
        return cnt
    cnt = overlap_counts()
    part = [torch.topk(cnt[i], min(args.partners, V - 1)).indices.tolist() for i in range(V)]
    print("partner overlap frac p50:", float(torch.median(cnt / M)), flush=True)

    c = torch.zeros(V, K, device=dev, dtype=torch.float64)
    gate = args.gate
    hist = []
    for it in range(args.outer):
        A = torch.zeros(V * K, V * K, device=dev, dtype=torch.float64)
        g = torch.zeros(V * K, device=dev, dtype=torch.float64)
        n_res = 0
        res_all = []
        for i in range(V):
            di = dirs(i)
            zi_raw = zb[i][vv.long(), uu.long()]
            hi = h_of(i, c, PHI)
            zi = zi_raw * torch.exp(hi)
            ok_i = validt[i][vv.long(), uu.long()] & (zi_raw > 0)
            Xi = (Pt[i][:3, :3] @ (zi[:, None] * di).T).T + Pt[i][:3, 3]
            for j in part[i]:
                Xj = (W2C[j][:3, :3] @ Xi.T).T + W2C[j][:3, 3]
                z_exp = Xj[:, 2]
                x = Kt[j][0, 0] * Xj[:, 0] / z_exp.clamp_min(1e-6) + Kt[j][0, 2]
                y = Kt[j][1, 1] * Xj[:, 1] / z_exp.clamp_min(1e-6) + Kt[j][1, 2]
                ok = ok_i & (z_exp > 0.04) & (x >= 0) & (x <= W - 1) & (y >= 0) & (y <= H - 1)
                if ok.sum() < 32:
                    continue
                gx = (2 * x / (W - 1) - 1).clamp(-1, 1)
                gy = (2 * y / (H - 1) - 1).clamp(-1, 1)
                gr = torch.stack([gx, gy], -1)[None, None].float()
                zj_raw = F.grid_sample(zb[j][None, None], gr, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0, 0].double()
                vj = F.grid_sample(validt[j][None, None].float(), gr, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0, 0] > 0.5
                ok = ok & vj & (zj_raw > 0)
                if ok.sum() < 32:
                    continue
                # basis at the projected location in j
                phij = basis((2 * x / (W - 1) - 1), (2 * y / (H - 1) - 1), K)
                hj = phij @ c[j]
                zj = zj_raw * torch.exp(hj)
                r = torch.log(zj.clamp_min(1e-6)) - torch.log(z_exp.clamp_min(1e-6))
                cij = (z_exp - W2C[j][2, 3]) / z_exp.clamp_min(1e-6)
                keep = ok & (r.abs() < gate) & cij.isfinite() & (cij.abs() < 4)
                if keep.sum() < 32:
                    continue
                rk = r[keep]
                s_mad = 1.4826 * torch.median((rk - torch.median(rk)).abs()) + 1e-6
                kk = 1.345 * s_mad
                wgt = torch.where(rk.abs() <= kk, torch.ones_like(rk), kk / rk.abs())
                Ji = -(cij[keep][:, None] * PHI[keep])
                Jj = phij[keep]
                wJi = wgt[:, None] * Ji
                wJj = wgt[:, None] * Jj
                bi, bj = i * K, j * K
                A[bi:bi + K, bi:bi + K] += Ji.T @ wJi
                A[bj:bj + K, bj:bj + K] += Jj.T @ wJj
                A[bi:bi + K, bj:bj + K] += Ji.T @ wJj
                A[bj:bj + K, bi:bi + K] += Jj.T @ wJi
                g[bi:bi + K] -= Ji.T @ (wgt * rk)
                g[bj:bj + K] -= Jj.T @ (wgt * rk)
                n_res += int(keep.sum())
                res_all.append(rk.abs().detach())
            # anchor residuals
            am = anchort[i][vv.long(), uu.long()] & ok_i
            if am.sum() > 16:
                zmv = zm[i][vv.long(), uu.long()][am]
                ra = (torch.log((zi_raw[am] * torch.exp(hi[am])).clamp_min(1e-6)) - torch.log(zmv.clamp_min(1e-6)))
                s_mad = 1.4826 * torch.median((ra - torch.median(ra)).abs()) + 1e-6
                kk = 1.345 * s_mad
                wa = args.anchor_weight * torch.where(ra.abs() <= kk, torch.ones_like(ra), kk / ra.abs())
                Ja = PHI[am]
                bi = i * K
                A[bi:bi + K, bi:bi + K] += Ja.T @ (wa[:, None] * Ja)
                g[bi:bi + K] -= Ja.T @ (wa * ra)
        A += args.ridge * torch.eye(V * K, device=dev, dtype=torch.float64)
        dc = torch.linalg.solve(A, g).reshape(V, K)
        c = c + dc
        rr = torch.cat(res_all)
        hist.append({"outer": it, "gate": gate, "residuals": n_res, "cross_view_abs_log_p50": float(rr.median()), "cross_view_abs_log_p95": float(torch.quantile(rr[::7].float(), 0.95)), "step_norm": float(dc.norm()), "c_norm": float(c.norm())})
        print("outer", it, hist[-1], flush=True)
        gate = max(gate * 0.6, 0.03)

    # apply the parametric correction on the FULL native grid
    va, ua = torch.meshgrid(torch.arange(H, device=dev, dtype=torch.float64), torch.arange(W, device=dev, dtype=torch.float64), indexing="ij")
    PHI_full = basis((ua / (W - 1)) * 2 - 1, (va / (H - 1)) * 2 - 1, K).reshape(-1, K)
    depth_out = np.zeros_like(depth_raw)
    hstat = []
    for i in range(V):
        h = (PHI_full @ c[i]).reshape(H, W)
        z = zb[i] * torch.exp(h)
        z = torch.where(validt[i], z, torch.zeros_like(z))
        depth_out[i] = z.float().cpu().numpy()
        hv = h[validt[i]]
        hstat.append({"view": i, "h_p05": float(torch.quantile(hv.float(), 0.05)), "h_p50": float(hv.median()), "h_p95": float(torch.quantile(hv.float(), 0.95))})

    def mv(d):
        dz = [torch.from_numpy(d[i]).to(dev)[None, ..., None] for i in range(V)]
        Ks = [Kt[i].float()[None] for i in range(V)]
        Ps = [Pt[i].float()[None] for i in range(V)]
        Ms = [validt[i][None] for i in range(V)]
        conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
        fb = [float((cc[Ms[i]] < 0.5).float().mean()) for i, cc in enumerate(conf)]
        fbf = [float((conf[i][(validt[i] & ~anchort[i])[None]] < 0.5).float().mean()) for i in range(V)]
        mean = [float(cc[Ms[i]].mean()) for i, cc in enumerate(conf)]
        del conf; torch.cuda.empty_cache()
        return {"frac_below_0_50": q_(fb), "frac_below_0_50_anchorfree_only": q_(fbf), "mean": q_(mean)}
    before = mv(z_base)
    after = mv(depth_out)

    result = {
        "purpose": "joint 132-view solve of a smooth per-view radial+tilt log-depth correction minimising cross-view disagreement, anchored by CasDiffMVS; MapAnything native grid, all pixels, original colours",
        "K": K, "basis": ["1", "r2", "r4", "u", "v", "uv"][:K], "stride": args.stride, "partners": args.partners,
        "outer": args.outer, "gate0": args.gate, "anchor_weight": args.anchor_weight, "ridge": args.ridge,
        "iterations": hist,
        "h_spread_p95_minus_p05": q_([t["h_p95"] - t["h_p05"] for t in hstat]),
        "h_p50": q_([t["h_p50"] for t in hstat]),
        "anchor_frac_of_valid": q_([float(anchor[i].sum() / max(valid[i].sum(), 1)) for i in range(V)]),
        "official_mvconf_before_affine_only": before, "official_mvconf_after_joint": after,
        "seconds_compute": time.time() - t0,
    }
    if not args.no_export:
        xyz_all, rgb_all = [], []
        for f in range(V):
            vvv, uuu = np.nonzero(valid[f])
            z = depth_out[f][vvv, uuu].astype(np.float64)
            x = (uuu - Kc[f][0, 2]) / Kc[f][0, 0] * z
            y = (vvv - Kc[f][1, 2]) / Kc[f][1, 1] * z
            pc = np.stack([x, y, z, np.ones_like(z)], 1)
            xyz_all.append((Pc[f] @ pc.T).T[:, :3].astype(np.float32))
            rgb_all.append(rgb[f][valid[f]])
        xyz = np.concatenate(xyz_all); col = np.concatenate(rgb_all)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64) / 255.0)
        ply = out / "mapanything_joint_consistency.ply"
        o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
        np.save(out / "depth_native_joint.npy", depth_out)
        np.save(out / "coeffs.npy", c.cpu().numpy())
        result["points"] = int(xyz.shape[0])
        result["ply"] = {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}
    result["seconds_total"] = time.time() - t0
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "iterations"}, indent=2))


if __name__ == "__main__":
    main()
