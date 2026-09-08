#!/usr/bin/env python3
"""(2)' MapAnything anchored to CasDiffMVS -- rebuilt on this box.

The original chain's intermediates died with the old machine, so the two steps are reconstructed
from their archived description:
  step 1  map MapAnything's depth into the CasDiffMVS camera. MapAnything follows the fed POSE but
          not the fed K (it self-predicts a shorter focal), so the two cameras are co-located with
          the same rotation and differ only in intrinsics => this is a pure resample, no parallax,
          no z-buffer holes.
  step 2  per-view robust affine (documented as "per-view affine already applied"), then the
          Laplacian-regularised offset field in log-depth, copied verbatim from
          scripts/anchor_mapanything_to_casdiff.py (lam=4.0, solve_scale=0.5, 2 IRLS Huber passes).
Then the official CasDiffMVS gate, same as every other engine on the page.
"""
import sys, os, glob, json, time
import numpy as np, cv2, torch
import torch.nn.functional as F
import scipy.sparse as sp
import scipy.sparse.linalg as spla
sys.path.insert(0, "/root/diffmvs")
from filter import read_pfm, read_camera_parameters, check_geometric_consistency, read_pair_file

MA   = "/root/regionmerge/ma_full"
CAS  = "/root/out_official"
GATED= "/root/regionmerge/gated_casdiff"          # final mask = depth > 0
OUT  = sys.argv[1]
LAM, SOLVE_SCALE, ITERS = 4.0, 0.5, 2
for s in ("depth", "color", "cam"): os.makedirs(f"{OUT}/{s}", exist_ok=True)


def laplacian(h, w):
    n = h * w; idx = np.arange(n).reshape(h, w)
    rows, cols, vals = [], [], []
    a = idx[:, :-1].ravel(); b = idx[:, 1:].ravel()
    rows += [a, a, b, b]; cols += [a, b, a, b]; vals += [np.ones_like(a), -np.ones_like(a), -np.ones_like(a), np.ones_like(a)]
    a = idx[:-1, :].ravel(); b = idx[1:, :].ravel()
    rows += [a, a, b, b]; cols += [a, b, a, b]; vals += [np.ones_like(a), -np.ones_like(a), -np.ones_like(a), np.ones_like(a)]
    return sp.csr_matrix((np.concatenate(vals).astype(np.float64),
                          (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))


def solve_offset(logmap, logmvs, anchor, lam=LAM, solve_scale=SOLVE_SCALE, iters=ITERS):
    H, W = logmap.shape
    hs, ws = int(round(H * solve_scale)), int(round(W * solve_scale))
    t = lambda a: F.interpolate(torch.from_numpy(a.astype(np.float32))[None, None], size=(hs, ws), mode="area")[0, 0].numpy().astype(np.float64)
    an = t(anchor.astype(np.float32)) > 0.5
    d = t(np.where(anchor, logmvs - logmap, 0.0)) / np.maximum(t(anchor.astype(np.float32)), 1e-6)
    L = laplacian(hs, ws)
    w = an.astype(np.float64).ravel(); rhs = d.ravel(); h = np.zeros(hs * ws)
    for _ in range(iters):
        A = (sp.diags(w) + lam * L + 1e-9 * sp.identity(hs * ws)).tocsc()
        h = spla.spsolve(A, w * rhs)
        r = (rhs - h)[an.ravel()]
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        k = 1.345 * s
        wa = np.where(np.abs(r) <= k, 1.0, k / np.abs(r))
        w = np.zeros(hs * ws); w[an.ravel()] = wa
    hf = F.interpolate(torch.from_numpy(h.reshape(hs, ws).astype(np.float32))[None, None],
                       size=(H, W), mode="bilinear", align_corners=False)[0, 0].numpy()
    return hf, float(np.median(np.abs((rhs - h)[an.ravel()])))


def robust_affine(x, y, iters=2):
    """least squares y ~ a x + b with two Huber IRLS passes"""
    w = np.ones_like(x)
    a, b = 1.0, 0.0
    for _ in range(iters):
        A = np.stack([x * w, w], 1); rhs = y * w
        sol, *_ = np.linalg.lstsq(A, rhs, rcond=None); a, b = float(sol[0]), float(sol[1])
        r = y - (a * x + b)
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        k = 1.345 * s
        w = np.where(np.abs(r) <= k, 1.0, k / np.maximum(np.abs(r), 1e-9))
    return a, b


pair = read_pair_file("/root/mvs_P16k/pair.txt", "general")
ids = [r for r, _ in pair]
t0 = time.time(); ctl = []
Zfin = {}
for ref in ids:
    z = np.load(f"{MA}/{ref:08d}.npz")
    dma, mma, Kma, Pma = z["depth_z"], z["mask"], z["K_ma"], z["pose_ma"]
    Kc, Ec, dmax, dmin = read_camera_parameters(f"{CAS}/cams/{ref:08d}_cam.txt")
    zmvs = read_pfm(f"{CAS}/depth_est/{ref:08d}.pfm")[0].astype(np.float32)
    final = np.load(f"{GATED}/depth/{ref:08d}.npy") > 0
    H, W = zmvs.shape

    # positive control 1: does MapAnything follow the fed pose?
    c2w = np.linalg.inv(Ec.astype(np.float64))
    Pm = Pma.astype(np.float64)
    if Pm.shape == (4, 4):
        Rr = c2w[:3, :3].T @ Pm[:3, :3]
        ang = float(np.degrees(np.arccos(np.clip((np.trace(Rr) - 1) / 2, -1, 1))))
        dt = float(np.linalg.norm(c2w[:3, 3] - Pm[:3, 3]))
    else:
        ang, dt = float("nan"), float("nan")

    # step 1: resample MA depth into the CasDiffMVS camera (same pose, different K)
    u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    dx = (u - Kc[0, 2]) / Kc[0, 0]; dy = (v - Kc[1, 2]) / Kc[1, 1]
    up = Kma[0, 0] * dx + Kma[0, 2]; vp = Kma[1, 1] * dy + Kma[1, 2]
    hm, wm = dma.shape
    gx = (up / (wm - 1) * 2 - 1); gy = (vp / (hm - 1) * 2 - 1)
    grid = torch.from_numpy(np.stack([gx, gy], -1))[None]
    zmap = F.grid_sample(torch.from_numpy(dma)[None, None], grid, mode="bilinear",
                         padding_mode="zeros", align_corners=True)[0, 0].numpy()
    mmap = F.grid_sample(torch.from_numpy(mma.astype(np.float32))[None, None], grid, mode="nearest",
                         padding_mode="zeros", align_corners=True)[0, 0].numpy() > 0.5
    mmap &= zmap > 0

    anchor = final & mmap & (zmvs > 0)
    if anchor.sum() < 500:
        Zfin[ref] = np.zeros_like(zmvs); ctl.append({"view": ref, "anchor": int(anchor.sum()), "skipped": True}); continue

    # step 2a: per-view robust affine
    a, b = robust_affine(zmap[anchor].astype(np.float64), zmvs[anchor].astype(np.float64))
    zmap_a = np.where(mmap, a * zmap + b, 0.0)
    zmap_a = np.where(zmap_a > 0, zmap_a, 0.0)
    mmap &= zmap_a > 0
    anchor = final & mmap & (zmvs > 0)

    # step 2b: Laplacian-regularised offset field in log depth (verbatim)
    logmap = np.log(np.where(mmap, zmap_a, 1.0))
    logmvs = np.log(np.where(zmvs > 0, zmvs, 1.0))
    h, resid = solve_offset(logmap, logmvs, anchor)
    zfin = np.where(mmap, np.exp(logmap + h), 0.0).astype(np.float32)
    Zfin[ref] = zfin

    r = zfin[anchor] / zmvs[anchor]
    ctl.append({"view": ref, "pose_ang_deg": ang, "pose_dt_m": dt,
                "K_ratio_fx": float(Kma[0, 0] / Kc[0, 0]),
                "affine_a": a, "affine_b": b, "anchor_frac": float(anchor.mean()),
                "ma_cov": float(mmap.mean()), "log_resid_p50": resid,
                "ratio_p10": float(np.percentile(r, 10)), "ratio_p50": float(np.median(r)),
                "ratio_p90": float(np.percentile(r, 90))})
    if ref % 20 == 0:
        c = ctl[-1]
        print(f"  ref {ref:3d} pose dR {ang:.3f}deg dt {dt:.4f}m  fx_ma/fx {c['K_ratio_fx']:.3f}  "
              f"affine a={a:.3f} b={b:+.3f}  cov {c['ma_cov']:.3f}  ratio p50 {c['ratio_p50']:.4f} "
              f"[{c['ratio_p10']:.4f},{c['ratio_p90']:.4f}]  {time.time()-t0:.0f}s", flush=True)

print("anchored", len(Zfin), f"{time.time()-t0:.0f}s -- now the official gate", flush=True)

# official gate, identical to every other engine on the page
for ref, srcs in pair:
    dref = Zfin[ref]
    Kr, Er, dmax, dmin = read_camera_parameters(f"{CAS}/cams/{ref:08d}_cam.txt")
    gsum = 0; rsum = 0
    for s in srcs:
        Ks, Es, _, _ = read_camera_parameters(f"{CAS}/cams/{s:08d}_cam.txt")
        gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, Zfin[s], Ks, Es, dmax, dmin, 1.0, 0.01)
        gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
    davg = (rsum + dref) / (gsum + 1)
    keep = (gsum >= 3) & (dref > 0)
    np.save(f"{OUT}/depth/{ref:08d}.npy", np.where(keep, davg, 0).astype(np.float32))
    img = cv2.imread(f"{CAS}/images/{ref:08d}.jpg")
    cv2.imwrite(f"{OUT}/color/{ref:08d}.png", img)
    np.savez(f"{OUT}/cam/{ref:08d}.npz", K=Kr.astype(np.float64), E=Er.astype(np.float64))
    if ref % 40 == 0: print(f"  gate ref {ref} keep {keep.mean():.3f}", flush=True)

json.dump(ctl, open(f"{OUT}/positive_control.json", "w"), indent=1)
ok = [c for c in ctl if "ratio_p50" in c]
print("POSITIVE CONTROL over %d views:" % len(ok), flush=True)
print("  pose dR deg   p50 %.4f  max %.4f" % (np.median([c['pose_ang_deg'] for c in ok]), max(c['pose_ang_deg'] for c in ok)), flush=True)
print("  pose dt m     p50 %.5f  max %.5f" % (np.median([c['pose_dt_m'] for c in ok]), max(c['pose_dt_m'] for c in ok)), flush=True)
print("  fx_ma/fx_true p50 %.4f" % np.median([c['K_ratio_fx'] for c in ok]), flush=True)
print("  anchored/mvs  p50 %.4f  p10 %.4f  p90 %.4f" % (
    np.median([c['ratio_p50'] for c in ok]), np.median([c['ratio_p10'] for c in ok]), np.median([c['ratio_p90'] for c in ok])), flush=True)
print("DONE", f"{time.time()-t0:.0f}s", flush=True)
