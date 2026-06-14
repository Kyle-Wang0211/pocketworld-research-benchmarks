#!/usr/bin/env python3
"""expG2: Fix-B upgrade ladder — does +shift or +SE3 buy anything?

Ladder (each fitted from the SAME 29k anchors / 143k obs, evaluated
with the SAME cross-window depth-reprojection metric on easy pairs):

  L1  scale-only median            (current production Fix B)
  L2  scale+shift robust IRLS      (DA3-paper / MiDaS standard)
  L3  L1 scale + per-window SE3    (DA3-Streaming scale+se3, anchor-built
                                    Kabsch instead of overlap)

Guards: L2 |shift| flagged if > 5 cm (clustered-anchor overfit risk per
VIMD-2025 practice); L3 |rot| and |t| logged. Golden: L1 must keep
win25/26 within the locked tolerances.
"""

import json
import time
from pathlib import Path

import numpy as np

O = Path("data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10")
Q = O / "expQ_spatial_windows"
CACHE = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
OUT_DIR = Path("data/expG2_fixb_upgrade_2026_06_13")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expG2_results.jsonl"

EASY = [0, 10, 11, 14, 24, 25, 26, 27, 40, 41, 42]
PAIRS = [(24, 25), (25, 26), (26, 27), (40, 41), (41, 42), (10, 11)]
DETECT_LONG_SIDE = 1536.0
STAGE1_GATE = np.log(1.15)
STAGE2_GATE = np.log(1.05)
CONF_PCT = 40.0
MEAS_STRIDE = 3
GATE_LOG_RATIO = np.log(2.0)


def log(m):
    print(f"[expG2 {time.strftime('%H:%M:%S')}] {m}", flush=True)


def append_row(row):
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


z = np.load(CACHE)
A_pts, A_frame, A_uv, A_aidx = z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"]
log(f"anchors {len(A_pts)}, obs {len(A_frame)}")


def load_win(w):
    d = Q / f"window_{w:03d}"
    depth = np.load(d / "pytorch_depth.npy").astype(np.float32)
    conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
    ext34 = np.load(d / "pytorch_extrinsics.npy").astype(np.float64)
    w2c = np.tile(np.eye(4), (len(ext34), 1, 1))
    w2c[:, :3, :] = ext34
    K = np.load(d / "pytorch_intrinsics.npy").astype(np.float64)
    return {"depth": depth, "conf": conf, "K": K, "w2c": w2c}


def window_obs(win, w):
    """Collect (z_pred, z_anchor_cam, P_pred_world, X_anchor) at observed
    pixels of this window's frames, conf/p40 + stage1 gated."""
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    sc = W / DETECT_LONG_SIDE
    zp_all, zc_all, Pp_all, Xa_all, C_all = [], [], [], [], []
    for i, fi in enumerate(range(w * 9, w * 9 + 18)):
        sel = A_frame == fi
        if not sel.any():
            continue
        uv = A_uv[sel]
        aidx = A_aidx[sel]
        ud = np.round((uv[:, 0] + 0.5) * sc - 0.5).astype(int)
        vd = np.round((uv[:, 1] + 0.5) * sc - 0.5).astype(int)
        ok = (ud >= 0) & (ud < W) & (vd >= 0) & (vd < H)
        ud, vd, aidx = ud[ok], vd[ok], aidx[ok]
        zp = depth[i][vd, ud].astype(np.float64)
        cp = conf[i][vd, ud]
        X = A_pts[aidx]
        w2c = w2cs[i]
        cam = (w2c[:3, :3] @ X.T + w2c[:3, 3:4])
        zc = cam[2]
        good = (cp >= floor) & (zp > 1e-3) & (zc > 1e-3)
        r = np.log(zc[good] / zp[good])
        keep = np.abs(r) <= STAGE1_GATE
        idx = np.where(good)[0][keep]
        if not len(idx):
            continue
        K = Ks[i]
        zz = zp[idx]
        x = (ud[idx] + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vd[idx] + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam_p = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2c)
        Pp_all.append((c2w @ cam_p)[:3].T)
        Xa_all.append(X[idx])
        zp_all.append(zz)
        zc_all.append(zc[idx])
        C_all.append(np.tile(c2w[:3, 3], (len(idx), 1)))
    return (np.concatenate(zp_all), np.concatenate(zc_all),
            np.concatenate(Pp_all), np.concatenate(Xa_all),
            np.concatenate(C_all))


def fit_L1(zp, zc):
    r = np.log(zc / zp)
    m1 = np.median(r)
    r2 = r[np.abs(r - m1) <= STAGE2_GATE]
    return float(np.exp(np.median(r2)))


def fit_L2(zp, zc):
    """z_anchor ~ s*z_pred + t, Huber IRLS (3 rounds), init L1."""
    s, t = fit_L1(zp, zc), 0.0
    for _ in range(3):
        res = zc - (s * zp + t)
        sigma = max(np.median(np.abs(res)) * 1.4826, 1e-6)
        wgt = np.clip(1.345 * sigma / np.maximum(np.abs(res), 1e-9), 0, 1)
        Wm = wgt
        A = np.stack([zp, np.ones_like(zp)], axis=1)
        AtW = A.T * Wm
        sol = np.linalg.solve(AtW @ A, AtW @ zc)
        s, t = float(sol[0]), float(sol[1])
    return s, t


def fit_L3(zp, zc, Pp, Xa, C):
    """L1 depth scale, then rigid SE3 (Kabsch) on anchor correspondences.
    Scaled predicted anchor position is exact: P(s) = C + s*(P - C)."""
    s = fit_L1(zp, zc)
    Ps = C + s * (Pp - C)
    R, t = kabsch(Ps, Xa)
    return s, R, t


def kabsch(src, dst):
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    t = cd - R @ cs
    return R, t


def backproject(win, stride, s, shift=0.0):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    pts = []
    for i in range(n):
        zz0 = depth[i] * s + shift
        m = (conf[i] >= floor) & (zz0 > 1e-3)
        vs, us = np.where(m)
        sel = (vs % stride == 0) & (us % stride == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        K = Ks[i]
        zz = zz0[vs, us].astype(np.float64)
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2cs[i].astype(np.float64))
        pts.append((c2w @ cam)[:3].T)
    return np.concatenate(pts)


def pair_residual(src_pts_world, dst, s_dst, shift_dst=0.0, T_dst=None):
    """src points (already corrected to world) vs dst corrected surface.
    dst correction: depth' = s*z + shift, then world SE3 T (R,t).
    Comparator maps src pts through T^-1 then projects with original
    cams against depth'."""
    pts = src_pts_world
    if T_dst is not None:
        R, t = T_dst
        pts = (pts - t) @ R  # R^T @ (x - t), row-vector form
    depth, conf, Ks, w2cs = dst["depth"], dst["conf"], dst["K"], dst["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    ratios, absd = [], []
    for i in range(n):
        w2c = w2cs[i].astype(np.float64)
        cam = (w2c[:3, :3] @ pts.T + w2c[:3, 3:4])
        zw = cam[2]
        front = zw > 1e-3
        K = Ks[i]
        u = cam[0] / zw * K[0, 0] + K[0, 2] - 0.5
        v = cam[1] / zw * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zd = depth[i][vi[ok], ui[ok]].astype(np.float64) * s_dst + shift_dst
        cd = conf[i][vi[ok], ui[ok]]
        zp = zw[ok]
        good = (cd >= floor) & (zd > 1e-3)
        r = np.log(zd[good] / zp[good])
        keep = np.abs(r) <= GATE_LOG_RATIO
        ratios.append(r[keep])
        absd.append(np.abs(zd[good][keep] - zp[good][keep]))
    r = np.concatenate(ratios)
    a = np.concatenate(absd)
    return {"n": int(len(r)),
            "abs_rel_median_pct": float(np.median(np.abs(np.expm1(r))) * 100),
            "abs_rel_p90_pct": float(np.percentile(np.abs(np.expm1(r)), 90) * 100),
            "abs_cm_median": float(np.median(a) * 100)}


def main():
    wins = {w: load_win(w) for w in EASY}
    obs = {w: window_obs(wins[w], w) for w in EASY}

    fits = {}
    for w in EASY:
        zp, zc, Pp, Xa, C = obs[w]
        s1 = fit_L1(zp, zc)
        s2, t2 = fit_L2(zp, zc)
        s3, R3, t3 = fit_L3(zp, zc, Pp, Xa, C)
        rot_deg = float(np.degrees(np.arccos(np.clip((np.trace(R3) - 1) / 2, -1, 1))))
        fits[w] = {"s1": s1, "s2": s2, "t2": t2, "s3": s3,
                   "R3": R3, "t3": t3, "rot_deg": rot_deg}
        flag = " ⚠shift>5cm" if abs(t2) > 0.05 else ""
        log(f"win{w:02d}: L1 s={s1:.4f} | L2 s={s2:.4f} t={t2*100:+.1f}cm{flag} | "
            f"L3 rot={rot_deg:.3f}° t={np.linalg.norm(t3)*100:.1f}cm")
        append_row({"kind": "fits", "win": w, "s1": s1, "s2": s2, "t2": t2,
                    "s3": s3, "rot_deg": rot_deg,
                    "t3_cm": float(np.linalg.norm(t3) * 100)})

    # golden regression on L1
    for w, g in [(25, 1.0035), (26, 0.9768)]:
        d = abs(fits[w]["s1"] / g - 1) * 100
        log(f"golden win{w}: L1 {fits[w]['s1']:.4f} vs {g} -> {d:.2f}% {'OK' if d<=1.2 else 'FAIL'}")

    for tag in ["L1", "L2", "L3"]:
        meds = []
        for a, b in PAIRS:
            if tag == "L1":
                sa, ta, Ta = fits[a]["s1"], 0.0, None
                sb, tb, Tb = fits[b]["s1"], 0.0, None
            elif tag == "L2":
                sa, ta, Ta = fits[a]["s2"], fits[a]["t2"], None
                sb, tb, Tb = fits[b]["s2"], fits[b]["t2"], None
            else:
                sa, ta, Ta = fits[a]["s3"], 0.0, (fits[a]["R3"], fits[a]["t3"])
                sb, tb, Tb = fits[b]["s3"], 0.0, (fits[b]["R3"], fits[b]["t3"])
            pa = backproject(wins[a], MEAS_STRIDE, sa, ta)
            if Ta is not None:
                R, t = Ta
                pa = pa @ R.T + t
            res = pair_residual(pa, wins[b], sb, tb, T_dst=Tb)
            meds.append(res["abs_rel_median_pct"])
            log(f"{tag} {a}->{b}: {res}")
            append_row({"kind": f"pair_{tag}", "pair": [a, b], **res})
        log(f"{tag} median-of-pairs: {np.median(meds):.3f}%")
        append_row({"kind": f"summary_{tag}", "median_pct": float(np.median(meds))})
    log("EXPG2-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
