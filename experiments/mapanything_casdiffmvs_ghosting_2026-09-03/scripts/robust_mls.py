#!/usr/bin/env python3
"""Robust point set surface projection: lock the local plane onto the DOMINANT
layer, then pull the minority layer onto it.

Why the plain version was not enough. Measured tails, neighbourhood radius 20 cm:

    point set surface (least squares)   14.6% of neighbourhoods > 2 cm,  2.0% > 5 cm
    CasDiffMVS                           2.5%                            0.02%
    COLMAP dense                         1.5%                            0.04%

The medians already matched CasDiffMVS (5.3 vs 5.4 mm); the visible ghosting
lives entirely in that tail. A least-squares plane through a neighbourhood that
genuinely holds two layers 5 cm apart lands between them, so both layers get
pulled to the middle -- the ghost is halved, not removed.

Fix: iteratively reweighted plane fitting (Tukey biweight on the residual along
the normal). After a couple of reweights the plane sits on whichever layer holds
the most points, and projecting then moves the minority layer onto it. This is
the standard robust variant of the same method, not a new invention.

Everything else is unchanged from the plain version and from the standing
constraints: every point kept, colours untouched, plane parameters trilinearly
interpolated per point, and whatever trilinear weight is missing leaves the
point where it is, so there is no moved/unmoved boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import torch


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def smallest_eigvec_sym3(A):
    """Eigenvector of the smallest eigenvalue of a batch of symmetric 3x3
    matrices, in closed form -- cuSOLVER's batched syevd refuses large 3x3
    batches on this build."""
    a00, a01, a02 = A[:, 0, 0], A[:, 0, 1], A[:, 0, 2]
    a11, a12, a22 = A[:, 1, 1], A[:, 1, 2], A[:, 2, 2]
    p1 = a01 ** 2 + a02 ** 2 + a12 ** 2
    q = (a00 + a11 + a22) / 3.0
    p2 = (a00 - q) ** 2 + (a11 - q) ** 2 + (a22 - q) ** 2 + 2.0 * p1
    p = torch.sqrt((p2 / 6.0).clamp_min(1e-300))
    inv = 1.0 / p
    b00, b11, b22 = (a00 - q) * inv, (a11 - q) * inv, (a22 - q) * inv
    b01, b02, b12 = a01 * inv, a02 * inv, a12 * inv
    detB = (b00 * (b11 * b22 - b12 * b12) - b01 * (b01 * b22 - b12 * b02)
            + b02 * (b01 * b12 - b11 * b02))
    r = (detB / 2.0).clamp(-1.0, 1.0)
    phi = torch.acos(r) / 3.0
    e1 = q + 2.0 * p * torch.cos(phi)
    e2 = 3.0 * q - e1 - (q + 2.0 * p * torch.cos(phi + 2.0 * np.pi / 3.0))
    I = torch.eye(3, device=A.device, dtype=A.dtype)[None]
    M = (A - e1[:, None, None] * I) @ (A - e2[:, None, None] * I)
    nn = M.norm(dim=1)
    pick = nn.argmax(dim=1)
    v = M[torch.arange(M.shape[0], device=A.device), :, pick]
    v = v / v.norm(dim=1, keepdim=True).clamp_min(1e-300)
    return v, torch.isfinite(v).all(1) & (p > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--voxel", type=float, default=0.03)
    ap.add_argument("--min_pts", type=int, default=24)
    ap.add_argument("--irls", type=int, default=3, help="reweighting passes; 0 reproduces the plain least-squares version")
    ap.add_argument("--tukey_c", type=float, default=0.02, help="metres; residuals beyond this stop pulling the plane, so a minority layer cannot drag it")
    ap.add_argument("--max_move", type=float, default=0.15)
    args = ap.parse_args()
    t0 = time.time()
    dev = "cuda"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    pcd = o3d.io.read_point_cloud(args.ply)
    P0 = np.asarray(pcd.points, dtype=np.float64)
    C = np.asarray(pcd.colors)
    N = P0.shape[0]
    P = torch.from_numpy(P0).to(dev)
    print(f"loaded {N} points", flush=True)

    h = args.voxel
    origin = P.min(0).values - h
    c = (P - origin) / h
    vi = torch.floor(c).long()
    dims = vi.max(0).values + 2
    strides = torch.tensor([int(dims[1]) * int(dims[2]), int(dims[2]), 1], device=dev, dtype=torch.long)
    lin = (vi * strides).sum(1)
    uniq, inv = torch.unique(lin, return_inverse=True)
    M = uniq.numel()
    print(f"{M} occupied voxels at {h*100:.0f} cm, support {3*h*100:.0f} cm", flush=True)
    pairs = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]

    # 27-neighbour lookup, computed once
    nbr = []
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for oz in (-1, 0, 1):
                t = uniq + ox * strides[0] + oy * strides[1] + oz * strides[2]
                pos = torch.searchsorted(uniq, t).clamp(max=M - 1)
                nbr.append((pos, uniq[pos] == t))

    w_pt = torch.ones(N, device=dev, dtype=torch.float64)
    mu = nrm = ok_vox = None
    stats = []
    for it in range(args.irls + 1):
        cnt = torch.zeros(M, device=dev, dtype=torch.float64)
        cnt.scatter_add_(0, inv, w_pt)
        s1 = torch.zeros(M, 3, device=dev, dtype=torch.float64)
        for k in range(3):
            s1[:, k].scatter_add_(0, inv, P[:, k] * w_pt)
        s2 = torch.zeros(M, 6, device=dev, dtype=torch.float64)
        for q, (x_, y_) in enumerate(pairs):
            s2[:, q].scatter_add_(0, inv, P[:, x_] * P[:, y_] * w_pt)
        # box-filter the (weighted) moments over 3x3x3 -> support 3h
        cs, s1s, s2s = torch.zeros_like(cnt), torch.zeros_like(s1), torch.zeros_like(s2)
        for pos, hit in nbr:
            cs[hit] += cnt[pos[hit]]
            s1s[hit] += s1[pos[hit]]
            s2s[hit] += s2[pos[hit]]
        cnt, s1, s2 = cs, s1s, s2s
        mu = s1 / cnt[:, None].clamp_min(1e-9)
        m2 = s2 / cnt[:, None].clamp_min(1e-9)
        cov = torch.zeros(M, 3, 3, device=dev, dtype=torch.float64)
        for q, (x_, y_) in enumerate(pairs):
            cov[:, x_, y_] = m2[:, q] - mu[:, x_] * mu[:, y_]
            cov[:, y_, x_] = cov[:, x_, y_]
        ok_vox = cnt >= args.min_pts
        cov = torch.where(torch.isfinite(cov), cov, torch.zeros_like(cov))
        nrm, okv = smallest_eigvec_sym3(cov)
        ok_vox = ok_vox & okv
        del cov, s2, m2, s1, cs, s1s, s2s
        torch.cuda.empty_cache()

        # residual of every point to its own voxel's plane -> Tukey weight
        ph = inv
        d = ((P - mu[ph]) * nrm[ph]).sum(1)
        good = ok_vox[ph]
        if it < args.irls:
            u = (d.abs() / args.tukey_c).clamp(max=1.0)
            w_pt = torch.where(good, (1.0 - u ** 2) ** 2, torch.ones_like(d))
            stats.append({"pass": it, "resid_mm_p50": float(d[good].abs().median() * 1000),
                          "resid_mm_p95": float(torch.quantile(d[good].abs()[::37].float(), 0.95) * 1000),
                          "mean_weight": float(w_pt[good].mean()),
                          "frac_downweighted_below_0.5": float((w_pt[good] < 0.5).double().mean())})
            print("irls", it, stats[-1], flush=True)

    # project, with the plane trilinearly interpolated from the 8 surrounding voxels
    newP = torch.zeros_like(P)
    wsum = torch.zeros(N, device=dev, dtype=torch.float64)
    base = torch.floor(c - 0.5).long()
    frac = (c - 0.5) - base
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((1 - frac[:, 0]) if dx == 0 else frac[:, 0]) * \
                    ((1 - frac[:, 1]) if dy == 0 else frac[:, 1]) * \
                    ((1 - frac[:, 2]) if dz == 0 else frac[:, 2])
                v = base + torch.tensor([dx, dy, dz], device=dev, dtype=torch.long)
                vlin = (v.clamp_min(0) * strides).sum(1)
                pos = torch.searchsorted(uniq, vlin).clamp(max=M - 1)
                hit = (uniq[pos] == vlin) & ok_vox[pos] & (w > 0)
                if not hit.any():
                    continue
                q = pos[hit]
                proj = P[hit] - ((P[hit] - mu[q]) * nrm[q]).sum(1, keepdim=True) * nrm[q]
                newP[hit] += w[hit][:, None] * proj
                wsum[hit] += w[hit]
    cand = newP + (1.0 - wsum.clamp(max=1.0))[:, None] * P
    disp = (cand - P).norm(dim=1)
    clip = disp > args.max_move
    if clip.any():
        cand[clip] = P[clip] + (cand[clip] - P[clip]) * (args.max_move / disp[clip])[:, None]

    Pn = cand.cpu().numpy()
    o = o3d.geometry.PointCloud()
    o.points = o3d.utility.Vector3dVector(Pn)
    o.colors = o3d.utility.Vector3dVector(C)
    ply = out / f"mapanything_{args.tag}.ply"
    o3d.io.write_point_cloud(str(ply), o, write_ascii=False, compressed=False)
    tot = np.linalg.norm(Pn - P0, axis=1)
    res = {
        "tag": args.tag, "source_ply": args.ply, "voxel_m": h, "support_m": 3 * h,
        "irls": args.irls, "tukey_c_m": args.tukey_c, "points": int(N), "irls_stats": stats,
        "mean_support_weight": float(wsum.clamp(max=1.0).mean()),
        "disp_mm_p50": float(np.median(tot) * 1000), "disp_mm_p95": float(np.percentile(tot, 95) * 1000),
        "disp_mm_p99": float(np.percentile(tot, 99) * 1000),
        "frac_moved_over_2cm": float((tot > 0.02).mean()), "frac_moved_over_5cm": float((tot > 0.05).mean()),
        "clipped_frac": float(clip.double().mean().item()),
        "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
        "seconds": time.time() - t0,
    }
    (out / "result.json").write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "irls_stats"}, indent=2))


if __name__ == "__main__":
    main()
