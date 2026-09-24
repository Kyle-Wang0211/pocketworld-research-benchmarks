#!/usr/bin/env python3
"""Fix B — production per-window depth-scale anchoring for DA3 K-window
reconstruction. LOCKED as the production recipe 2026-06-12 (user 拍板).

Problem
-------
Pose-conditioned DA3 windows share ONE ARKit pose system, but each
window's depth comes back in "network units" and the official
umeyama re-calibration carries a per-window error (measured: 3-6%
typical, 28.5% worst on the 414 daylight sweep) -> double surfaces
("ghosting") when windows are fused.

Recipe (every gate below was validated on real captures)
--------------------------------------------------------
1. Triangulate sparse metric anchors from the capture's own frames
   with KNOWN poses (SIFT @1536 long side, span-6 epipolar-gated
   matching, union-find tracks, multi-view DLT, cheirality +
   reproj<=2.5px + parallax>=1.5deg). Pure CPU, seconds per capture.
2. Per window, fit ONE scalar via OBSERVATION ASSOCIATION ONLY:
   an anchor votes only through frames that actually matched it
   (visibility comes from the feature tracks, NOT geometric
   projection — projecting all anchors lets occluded ones land on
   foreground pixels and drags the median up; that bug shredded the
   first full-sweep clouds).
   Two-stage robust fit: |log r|<=log(1.15), then median +/- log(1.05).
3. AUTHORIZATION: anchor scale applies only to windows with
   conf_median >= conf_bar (6.0). Low-conf windows have REGIONAL
   depth error (no single true scalar exists — win28: anchor fit and
   bulk-surface fit legitimately disagree 4.7%); they take the
   nearest authorized window's scale and rely on conf gating at
   fusion.

Validation chain (2026-06-12)
-----------------------------
- expD2: overlap-chained scalar (Fix A) collapses high-conf window
  pairs 3.3cm -> 5.5mm @1m (conf75).
- expE: anchor scalars independently reproduce Fix A's ratios to
  0.1-0.4% AND pass the eyeball test (window-colored clouds fuse).
- expF2/F3: occlusion bug found by eyeball, fixed by observation
  association; goldens win25/26 reproduce expE within 1.2%.

Self-test: python3 da3_window_scale_fixb.py --self-test
(needs the expQ 414 caches; asserts the goldens).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# ----------------------------------------------------------- contract
DETECT_LONG_SIDE = 1536.0
PAIR_SPAN = 6
SAMPSON_PX = 3.0
MIN_TRACK_VIEWS = 3
MIN_PARALLAX_DEG = 1.5
MAX_REPROJ_PX = 2.5
STAGE1_GATE = np.log(1.15)
STAGE2_GATE = np.log(1.05)
MIN_OBS = 300
CONF_PCT = 40.0
CONF_BAR_AUTHORIZED = 6.0


@dataclass
class AnchorSet:
    pts: np.ndarray        # (N,3) world, metric (pose units)
    obs_frame: np.ndarray  # (M,) global frame index
    obs_uv: np.ndarray     # (M,2) keypoint px at DETECT_LONG_SIDE scale
    obs_aidx: np.ndarray   # (M,) -> pts row


def triangulate_anchors(frames: list[dict]) -> AnchorSet:
    """frames[i]: {jpeg_path, fxfycxcy (4,), w2c (4,4 row-major)}.
    Returns sparse metric anchors + their observation lists."""
    sift = cv2.SIFT_create(nfeatures=6000)
    kps, descs, Ks, w2cs = [], [], [], []
    for fr in frames:
        img = cv2.imread(str(fr["jpeg_path"]), cv2.IMREAD_GRAYSCALE)
        s = DETECT_LONG_SIDE / max(img.shape)
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        kp, de = sift.detectAndCompute(img, None)
        kps.append(np.array([k.pt for k in kp], dtype=np.float64))
        descs.append(de)
        fx, fy, cx, cy = fr["fxfycxcy"]
        Ks.append(np.array([[fx * s, 0, cx * s], [0, fy * s, cy * s], [0, 0, 1]]))
        w2cs.append(np.asarray(fr["w2c"], dtype=np.float64).reshape(4, 4))

    matcher = cv2.BFMatcher(cv2.NORM_L2)
    parent: dict = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    n_img = len(frames)
    for i in range(n_img):
        for j in range(i + 1, min(i + 1 + PAIR_SPAN, n_img)):
            mm = matcher.knnMatch(descs[i], descs[j], k=2)
            good = [m for m, n in mm if m.distance < 0.8 * n.distance]
            if not good:
                continue
            rel = w2cs[j] @ np.linalg.inv(w2cs[i])
            R, t = rel[:3, :3], rel[:3, 3]
            tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
            F = np.linalg.inv(Ks[j]).T @ (tx @ R) @ np.linalg.inv(Ks[i])
            p1 = kps[i][[m.queryIdx for m in good]]
            p2 = kps[j][[m.trainIdx for m in good]]
            h1 = np.column_stack([p1, np.ones(len(p1))])
            h2 = np.column_stack([p2, np.ones(len(p2))])
            Fx1 = h1 @ F.T
            Ftx2 = h2 @ F
            s2 = np.sum(h2 * Fx1, axis=1) ** 2
            denom = Fx1[:, 0] ** 2 + Fx1[:, 1] ** 2 + Ftx2[:, 0] ** 2 + Ftx2[:, 1] ** 2
            samp = s2 / np.maximum(denom, 1e-12)
            for m, ok in zip(good, samp < SAMPSON_PX ** 2):
                if ok:
                    union((i, m.queryIdx), (j, m.trainIdx))

    tracks: dict = {}
    for node in list(parent.keys()):
        tracks.setdefault(find(node), []).append(node)

    pts, obs_frame, obs_uv, obs_aidx = [], [], [], []
    for nodes in tracks.values():
        by_frame = {}
        for (fi, ki) in nodes:
            by_frame.setdefault(fi, ki)
        obs = sorted(by_frame.items())
        if len(obs) < MIN_TRACK_VIEWS:
            continue
        A = []
        for (fi, ki) in obs:
            P = Ks[fi] @ w2cs[fi][:3]
            u, v = kps[fi][ki]
            A.append(u * P[2] - P[0])
            A.append(v * P[2] - P[1])
        _, _, vt = np.linalg.svd(np.asarray(A))
        X = vt[-1]
        if abs(X[3]) < 1e-12:
            continue
        X = X[:3] / X[3]
        Xh = np.append(X, 1.0)
        ok, rays = True, []
        for (fi, ki) in obs:
            cam = w2cs[fi] @ Xh
            if cam[2] <= 1e-3:
                ok = False
                break
            uv = Ks[fi] @ cam[:3]
            uv = uv[:2] / uv[2]
            if np.linalg.norm(uv - kps[fi][ki]) > MAX_REPROJ_PX:
                ok = False
                break
            c2w = np.linalg.inv(w2cs[fi])
            dd = X - c2w[:3, 3]
            rays.append(dd / max(np.linalg.norm(dd), 1e-9))
        if not ok:
            continue
        rays = np.asarray(rays)
        cosmin = np.clip((rays @ rays.T).min(), -1, 1)
        if np.degrees(np.arccos(cosmin)) < MIN_PARALLAX_DEG:
            continue
        aidx = len(pts)
        pts.append(X)
        for (fi, ki) in obs:
            obs_frame.append(fi)
            obs_uv.append(kps[fi][ki])
            obs_aidx.append(aidx)
    return AnchorSet(
        np.asarray(pts, dtype=np.float64),
        np.asarray(obs_frame, dtype=np.int32),
        np.asarray(obs_uv, dtype=np.float64),
        np.asarray(obs_aidx, dtype=np.int32),
    )


def fit_window_scale(anchors: AnchorSet, depth: np.ndarray, conf: np.ndarray,
                     w2c: np.ndarray, frame_indices: list[int]):
    """One scalar for one window. depth/conf: (K,H,W) post-official-
    alignment. w2c: (K,4,4). frame_indices: global frame ids of the
    window's K frames (to look up anchor observations)."""
    K_, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    sc = W / DETECT_LONG_SIDE
    ratios = []
    for i, fi in enumerate(frame_indices):
        sel = anchors.obs_frame == fi
        if not sel.any():
            continue
        uv = anchors.obs_uv[sel]
        aidx = anchors.obs_aidx[sel]
        ud = np.round((uv[:, 0] + 0.5) * sc - 0.5).astype(int)
        vd = np.round((uv[:, 1] + 0.5) * sc - 0.5).astype(int)
        ok = (ud >= 0) & (ud < W) & (vd >= 0) & (vd < H)
        if not ok.any():
            continue
        ud, vd, aidx = ud[ok], vd[ok], aidx[ok]
        zp = depth[i][vd, ud].astype(np.float64)
        cp = conf[i][vd, ud]
        X = anchors.pts[aidx]
        cam = (w2c[i][:3, :3] @ X.T + w2c[i][:3, 3:4])
        zc = cam[2]
        good = (cp >= floor) & (zp > 1e-3) & (zc > 1e-3)
        r = np.log(zc[good] / zp[good])
        ratios.append(r[np.abs(r) <= STAGE1_GATE])
    if not ratios:
        return None, 0
    r = np.concatenate(ratios)
    if len(r) < MIN_OBS:
        return None, int(len(r))
    m1 = np.median(r)
    r2 = r[np.abs(r - m1) <= STAGE2_GATE]
    if len(r2) < MIN_OBS:
        return None, int(len(r2))
    return float(np.exp(np.median(r2))), int(len(r2))


def authorize_scales(fits: list, conf_medians: list[float],
                     conf_bar: float = CONF_BAR_AUTHORIZED) -> list[float]:
    """fits[w] = (scale|None, n_obs). Anchor scale is authorized only
    for windows with conf_median >= conf_bar AND a successful fit;
    every other window inherits the nearest authorized window's scale
    (spatial-order distance), defaulting to 1.0 if none exists.
    Low-conf windows' error is regional — fusion-level conf gating is
    their real treatment, the inherited scalar just keeps them in the
    same global frame."""
    n = len(fits)
    authorized = {
        w: fits[w][0]
        for w in range(n)
        if fits[w][0] is not None and conf_medians[w] >= conf_bar
    }
    out = []
    for w in range(n):
        if w in authorized:
            out.append(authorized[w])
        elif authorized:
            nearest = min(authorized, key=lambda a: abs(a - w))
            out.append(authorized[nearest])
        else:
            out.append(1.0)
    return out


# ----------------------------------------------------------- self-test
def _self_test() -> int:
    base = Path(__file__).resolve().parents[2]
    D = base / "data/official_da3_base_k35_strict_seq_2026_06_02"
    O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
    Q = O / "expQ_spatial_windows"
    man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
    frames = [
        {
            "jpeg_path": D / "capture_seq_k35_strict" / r["jpegPath"],
            "fxfycxcy": r["cameraIntrinsicFxFyCxCy"],
            "w2c": r["cameraExtrinsic4x4"],
        }
        for r in man
    ]
    t0 = time.time()
    anchors = triangulate_anchors(frames)
    print(f"anchors {len(anchors.pts)} / obs {len(anchors.obs_frame)} in {time.time()-t0:.0f}s")
    assert len(anchors.pts) > 20_000, "anchor yield collapsed"

    GOLDEN = {25: 1.0035, 26: 0.9768}   # expE locally-validated, high-conf
    fits, confs = [], []
    for w in range(45):
        d = Q / f"window_{w:03d}"
        depth = np.load(d / "pytorch_depth.npy").astype(np.float32)
        conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
        ext34 = np.load(d / "pytorch_extrinsics.npy").astype(np.float64)
        w2c = np.tile(np.eye(4), (len(ext34), 1, 1))
        w2c[:, :3, :] = ext34
        fits.append(fit_window_scale(anchors, depth, conf, w2c,
                                     list(range(w * 9, w * 9 + 18))))
        confs.append(float(np.median(conf)))
    scales = authorize_scales(fits, confs)
    for w, g in GOLDEN.items():
        d = abs(scales[w] / g - 1) * 100
        status = "OK" if d <= 1.2 else "FAIL"
        print(f"golden win{w}: {scales[w]:.4f} vs {g:.4f} -> {d:.2f}% {status}")
        assert d <= 1.2, f"golden regression on win{w}"
    n_auth = sum(1 for w in range(45)
                 if fits[w][0] is not None and confs[w] >= CONF_BAR_AUTHORIZED)
    print(f"authorized {n_auth}/45 windows; scales min {min(scales):.4f} max {max(scales):.4f}")
    print("SELF-TEST PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    print(__doc__)
