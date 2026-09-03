#!/usr/bin/env python3
"""MapAnything as the final presentation, CasDiffMVS as the geometric anchor.

Per view (CasDiffMVS working image, 768x576, production COLMAP camera):
  z_map  : MapAnything depth mapped into this camera (make_prior_maps output,
           per-view affine already applied; 0 where MapAnything masked)
  z_mvs  : CasDiffMVS refined depth, anchors = pixels kept by the official
           fusion (mask/*_final.png) of the chosen run
Solve for a smooth offset field h in log-depth:
  min  sum_anchors w (log z_map + h - log z_mvs)^2 + lam * |grad h|^2
so the result keeps MapAnything's relative shape everywhere (all pixels kept,
original colours) while being pinned to the multi-view-consistent CasDiffMVS
depths wherever they exist; h extends harmonically into anchor-free regions
(walls / periphery). Two IRLS passes (Huber) drop inconsistent anchors.
Then unproject every MapAnything pixel with the COLMAP camera into the common
COLMAP world frame and export one true-colour cloud (export stride keeps the
count in the 20-30M band). Also reports the official multi-view consistency
(mapanything.utils.multiview_confidence) before/after in the COLMAP frame."""

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
from PIL import Image

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_camera_parameters, read_pfm  # noqa: E402

sys.path.insert(0, "/root/map-anything-official-exact-src-20260902")
from mapanything.utils.multiview_confidence import compute_multiview_depth_confidence  # noqa: E402


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


def laplacian(h, w):
    n = h * w
    idx = np.arange(n).reshape(h, w)
    rows, cols, vals = [], [], []
    # horizontal and vertical first differences D; L = D^T D
    a = idx[:, :-1].ravel(); b = idx[:, 1:].ravel()
    rows += [a, a, b, b]; cols += [a, b, a, b]; vals += [np.ones_like(a), -np.ones_like(a), -np.ones_like(a), np.ones_like(a)]
    a = idx[:-1, :].ravel(); b = idx[1:, :].ravel()
    rows += [a, a, b, b]; cols += [a, b, a, b]; vals += [np.ones_like(a), -np.ones_like(a), -np.ones_like(a), np.ones_like(a)]
    return sp.csr_matrix((np.concatenate(vals).astype(np.float64), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))


def solve_offset(logmap, logmvs, anchor, lam, solve_scale, iters=2):
    """h at reduced resolution (smooth), returned upsampled to full."""
    H, W = logmap.shape
    hs, ws = int(round(H * solve_scale)), int(round(W * solve_scale))
    t = lambda a: F.interpolate(torch.from_numpy(a.astype(np.float32))[None, None], size=(hs, ws), mode="area")[0, 0].numpy().astype(np.float64)
    an = t(anchor.astype(np.float32)) > 0.5
    d = t(np.where(anchor, logmvs - logmap, 0.0)) / np.maximum(t(anchor.astype(np.float32)), 1e-6)
    L = laplacian(hs, ws)
    w = an.astype(np.float64).ravel()
    rhs_base = d.ravel()
    h = np.zeros(hs * ws)
    for it in range(iters):
        A = (sp.diags(w) + lam * L + 1e-9 * sp.identity(hs * ws)).tocsc()
        h = spla.spsolve(A, w * rhs_base)
        info = 0
        r = (rhs_base - h)[an.ravel()]
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        k = 1.345 * s
        wa = np.where(np.abs(r) <= k, 1.0, k / np.abs(r))
        w = np.zeros(hs * ws); w[an.ravel()] = wa
    hf = F.interpolate(torch.from_numpy(h.reshape(hs, ws).astype(np.float32))[None, None], size=(H, W), mode="bilinear", align_corners=False)[0, 0].numpy()
    stats = {"anchor_frac": float(an.mean()), "h_p05": float(np.percentile(h, 5)), "h_p50": float(np.median(h)), "h_p95": float(np.percentile(h, 95)), "resid_abs_p50_after": float(np.median(np.abs((rhs_base - h)[an.ravel()]))), "cg_info": int(info)}
    return hf, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prior_dir", default="/root/casdiffmvs_prior_20260903/priors_blendmvg/prior_depth")
    ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--lam", type=float, default=4.0)
    ap.add_argument("--solve_scale", type=float, default=0.5)
    ap.add_argument("--export_scale", type=float, default=0.75)
    ap.add_argument("--views", type=int, default=132)
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)
    (out / "depth_final").mkdir(parents=True, exist_ok=True)
    cas = Path(args.cas_out)

    K_list, c2w_list, zmap_list, zfin_list, mask_list, stats = [], [], [], [], [], []
    xyz_all, rgb_all = [], []
    for s in range(args.views):
        intr, extr, dmin, dmax = read_camera_parameters(str(cas / "cams" / f"{s:08d}_cam.txt"))
        zmap = np.load(Path(args.prior_dir) / f"{s:08d}.npy").astype(np.float32)
        zmvs = read_pfm(str(cas / "depth_est" / f"{s:08d}.pfm"))[0].astype(np.float32)
        final = np.asarray(Image.open(cas / "mask" / f"{s:08d}_final.png")) > 0
        H, W = zmap.shape
        assert zmvs.shape == (H, W) and final.shape == (H, W)
        mmap = zmap > 0
        anchor = final & mmap & (zmvs > 0)
        logmap = np.log(np.where(mmap, zmap, 1.0))
        logmvs = np.log(np.where(zmvs > 0, zmvs, 1.0))
        h, st = solve_offset(logmap, logmvs, anchor, args.lam, args.solve_scale)
        zfin = np.where(mmap, np.exp(logmap + h), 0.0).astype(np.float32)
        np.save(out / "depth_final" / f"{s:08d}.npy", zfin)
        st.update({"view": s, "map_cov": float(mmap.mean()), "cas_final_cov": float(final.mean())})
        stats.append(st)
        K_list.append(intr.astype(np.float32)); c2w_list.append(np.linalg.inv(extr.astype(np.float64)).astype(np.float32))
        zmap_list.append(zmap); zfin_list.append(zfin); mask_list.append(mmap)
        # export (nearest depth, bilinear colour) at export_scale
        eh, ew = int(round(H * args.export_scale)), int(round(W * args.export_scale))
        ys = np.clip(np.round((np.arange(eh) + 0.5) / args.export_scale - 0.5).astype(int), 0, H - 1)
        xs = np.clip(np.round((np.arange(ew) + 0.5) / args.export_scale - 0.5).astype(int), 0, W - 1)
        z = zfin[ys][:, xs]; m = mmap[ys][:, xs]
        img = np.asarray(Image.open(cas / "images" / f"{s:08d}.jpg").convert("RGB"))
        col = img[ys][:, xs]
        v, u = np.nonzero(m)
        uu = xs[u].astype(np.float64); vv = ys[v].astype(np.float64)
        zz = z[v, u].astype(np.float64)
        x = (uu - intr[0, 2]) / intr[0, 0] * zz
        y = (vv - intr[1, 2]) / intr[1, 1] * zz
        pc = np.stack([x, y, zz, np.ones_like(zz)], 1)
        pw = (c2w_list[-1].astype(np.float64) @ pc.T).T[:, :3].astype(np.float32)
        xyz_all.append(pw); rgb_all.append(col[v, u])
        if s % 20 == 0:
            print(f"view {s}: anchors {st['anchor_frac']:.3f} h p05/p50/p95 {st['h_p05']:.4f}/{st['h_p50']:.4f}/{st['h_p95']:.4f} resid {st['resid_abs_p50_after']:.4f} cg {st['cg_info']}", flush=True)

    xyz = np.concatenate(xyz_all); rgb = np.concatenate(rgb_all)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(rgb.astype(np.float64) / 255.0)
    ply = out / "mapanything_anchored_to_casdiff.ply"
    o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)

    # official multi-view consistency in the COLMAP frame, before (affine-aligned MapAnything) vs after (anchored)
    dev = "cuda"
    def mv(depths):
        dz = [torch.from_numpy(d).to(dev)[None, ..., None] for d in depths]
        Ks = [torch.from_numpy(K).to(dev)[None] for K in K_list]
        Ps = [torch.from_numpy(P).to(dev)[None] for P in c2w_list]
        Ms = [torch.from_numpy(m).to(dev)[None] for m in mask_list]
        conf = compute_multiview_depth_confidence(depth_z=dz, intrinsics=Ks, camera_poses=Ps, depth_masks=Ms)
        fb = [float((c[Ms[i]] < 0.5).float().mean()) for i, c in enumerate(conf)]
        mean = [float(c[Ms[i]].mean()) for i, c in enumerate(conf)]
        del conf; torch.cuda.empty_cache()
        return {"frac_below_0_50": q(fb), "mean": q(mean)}
    before = mv(zmap_list); after = mv(zfin_list)

    result = {
        "purpose": "MapAnything presentation anchored to CasDiffMVS geometry via smooth log-depth offset field; all MapAnything pixels kept; COLMAP frame",
        "prior_dir": args.prior_dir, "cas_out": str(cas), "lam": args.lam, "solve_scale": args.solve_scale, "export_scale": args.export_scale,
        "anchor_frac": q([s["anchor_frac"] for s in stats]), "map_cov": q([s["map_cov"] for s in stats]),
        "h_p50": q([s["h_p50"] for s in stats]), "h_spread_p95_minus_p05": q([s["h_p95"] - s["h_p05"] for s in stats]),
        "anchor_resid_abs_p50_after": q([s["resid_abs_p50_after"] for s in stats]),
        "official_mvconf_before_affine_only": before, "official_mvconf_after_anchoring": after,
        "points": int(xyz.shape[0]), "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)}, "seconds": time.time() - t0,
        "per_view": stats,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "per_view"}, indent=2))


if __name__ == "__main__":
    main()
