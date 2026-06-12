#!/usr/bin/env python3
"""expE: Fix-B validation — anchor per-window DA3 depth scale to a
sparse point cloud triangulated from KNOWN ARKit poses (414 set).

Fix A (expD2, validated): cross-window overlap scalar -> 0.5-0.8%
median residual (5.5mm @1m, conf75). Chain-dependent (needs a
reference window).

Fix B (this experiment): triangulate sparse metric points from
features + known poses (the v1 incremental-triangulator prototype,
pure classical geometry, zero learned components), then fit ONE
scalar per window so DA3 depth agrees with the sparse anchors seen
in that window. Window-independent: every window anchors directly
to the one metric frame; no chaining.

Validation criteria:
  V1  anchor yield: >= ~100 anchor observations per window
  V2  POST-B cross-window residual median <= ~1% (parity with Fix A)
  V3  s_B ratios reproduce Fix A's overlap scalars
      (A@conf75: win26/win25 = 0.9696, win28/win25 = 0.9687)

Windows are the same production-shape spatial windows as expD2:
w in {25, 26, 28}, frames man[w*9 : w*9+18], union = man[225:270].
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
OUT_DIR = Path("data/expE_sparse_anchor_414_2026_06_12")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expE_results.jsonl"
DEPTH_CACHE = OUT_DIR / "window_depths.npz"

WINDOW_IDS = [25, 26, 28]
UNION_LO, UNION_HI = 25 * 9, 28 * 9 + 18      # man[225:270], 45 frames
DETECT_LONG_SIDE = 1536.0
PAIR_SPAN = 6                                  # match frame i with i+1..i+6
SAMPSON_PX = 3.0
MIN_TRACK_VIEWS = 3
MIN_PARALLAX_DEG = 1.5
MAX_REPROJ_PX = 2.5
GATE_LOG_RATIO = np.log(2.0)
MEAS_STRIDE = 3


def log(msg: str) -> None:
    print(f"[expE {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def append_row(row: dict) -> None:
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
union_rows = man[UNION_LO:UNION_HI]
log(f"union frames: {len(union_rows)} (man[{UNION_LO}:{UNION_HI}])")


def frame_K(r: dict, scale: float) -> np.ndarray:
    fx, fy, cx, cy = r["cameraIntrinsicFxFyCxCy"]
    return np.array(
        [[fx * scale, 0, cx * scale], [0, fy * scale, cy * scale], [0, 0, 1]],
        dtype=np.float64,
    )


def frame_w2c(r: dict) -> np.ndarray:
    return np.asarray(r["cameraExtrinsic4x4"], dtype=np.float64).reshape(4, 4)


# ---------------------------------------------------------------- part 1
# Sparse anchor cloud: SIFT + known-pose epipolar gating + union-find
# tracks + multi-view DLT + reprojection/parallax gates. This is the
# v1 triangulator prototype (batch form).

def build_sparse_cloud() -> tuple[np.ndarray, list]:
    sift = cv2.SIFT_create(nfeatures=6000)
    kps, descs, Ks, w2cs, scales = [], [], [], [], []
    t0 = time.time()
    for r in union_rows:
        img = cv2.imread(str(D / "capture_seq_k35_strict" / r["jpegPath"]), cv2.IMREAD_GRAYSCALE)
        s = DETECT_LONG_SIDE / max(img.shape)
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        kp, de = sift.detectAndCompute(img, None)
        kps.append(np.array([k.pt for k in kp], dtype=np.float64))
        descs.append(de)
        Ks.append(frame_K(r, s))
        w2cs.append(frame_w2c(r))
        scales.append(s)
    log(f"SIFT on {len(union_rows)} frames in {time.time()-t0:.0f}s, "
        f"mean kp {np.mean([len(k) for k in kps]):.0f}")

    def fundamental(i: int, j: int) -> np.ndarray:
        rel = w2cs[j] @ np.linalg.inv(w2cs[i])
        R, t = rel[:3, :3], rel[:3, 3]
        tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
        E = tx @ R
        return np.linalg.inv(Ks[j]).T @ E @ np.linalg.inv(Ks[i])

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

    n_pairs, n_match = 0, 0
    t0 = time.time()
    for i in range(len(union_rows)):
        for j in range(i + 1, min(i + 1 + PAIR_SPAN, len(union_rows))):
            mm = matcher.knnMatch(descs[i], descs[j], k=2)
            good = [m for m, n in mm if m.distance < 0.8 * n.distance]
            if not good:
                continue
            F = fundamental(i, j)
            p1 = kps[i][[m.queryIdx for m in good]]
            p2 = kps[j][[m.trainIdx for m in good]]
            h1 = np.column_stack([p1, np.ones(len(p1))])
            h2 = np.column_stack([p2, np.ones(len(p2))])
            Fx1 = h1 @ F.T
            Ftx2 = h2 @ F
            s2 = np.sum(h2 * Fx1, axis=1) ** 2
            denom = Fx1[:, 0] ** 2 + Fx1[:, 1] ** 2 + Ftx2[:, 0] ** 2 + Ftx2[:, 1] ** 2
            samp = s2 / np.maximum(denom, 1e-12)
            keep = samp < SAMPSON_PX ** 2
            for m, ok in zip(good, keep):
                if ok:
                    union((i, m.queryIdx), (j, m.trainIdx))
                    n_match += 1
            n_pairs += 1
    log(f"matched {n_pairs} pairs, {n_match} epipolar-gated matches in {time.time()-t0:.0f}s")

    tracks: dict = {}
    for node in list(parent.keys()):
        tracks.setdefault(find(node), []).append(node)

    def triangulate(obs: list) -> np.ndarray | None:
        A = []
        for (fi, ki) in obs:
            P = Ks[fi] @ w2cs[fi][:3]
            u, v = kps[fi][ki]
            A.append(u * P[2] - P[0])
            A.append(v * P[2] - P[1])
        _, _, vt = np.linalg.svd(np.asarray(A))
        X = vt[-1]
        if abs(X[3]) < 1e-12:
            return None
        return X[:3] / X[3]

    pts, obs_per_pt = [], []
    n_reject = {"views": 0, "cheir": 0, "reproj": 0, "parallax": 0}
    for nodes in tracks.values():
        by_frame = {}
        for (fi, ki) in nodes:
            by_frame.setdefault(fi, ki)          # one obs per frame
        obs = sorted(by_frame.items())
        if len(obs) < MIN_TRACK_VIEWS:
            n_reject["views"] += 1
            continue
        X = triangulate(obs)
        if X is None:
            continue
        Xh = np.append(X, 1.0)
        ok, rays = True, []
        for (fi, ki) in obs:
            cam = w2cs[fi] @ Xh
            if cam[2] <= 1e-3:
                ok = False
                n_reject["cheir"] += 1
                break
            uv = Ks[fi] @ cam[:3]
            uv = uv[:2] / uv[2]
            if np.linalg.norm(uv - kps[fi][ki]) > MAX_REPROJ_PX:
                ok = False
                n_reject["reproj"] += 1
                break
            c2w = np.linalg.inv(w2cs[fi])
            rays.append((X - c2w[:3, 3]) / max(np.linalg.norm(X - c2w[:3, 3]), 1e-9))
        if not ok:
            continue
        rays = np.asarray(rays)
        cosmin = np.clip((rays @ rays.T).min(), -1, 1)
        if np.degrees(np.arccos(cosmin)) < MIN_PARALLAX_DEG:
            n_reject["parallax"] += 1
            continue
        pts.append(X)
        obs_per_pt.append(len(obs))
    pts = np.asarray(pts)
    log(f"tracks {len(tracks)} -> anchors {len(pts)} "
        f"(rejects {n_reject}), views/pt median {np.median(obs_per_pt) if len(pts) else 0:.0f}")
    append_row({"kind": "sparse_cloud", "n_tracks": len(tracks), "n_anchors": int(len(pts)),
                "rejects": n_reject,
                "views_per_pt_median": float(np.median(obs_per_pt)) if len(pts) else None})
    return pts, w2cs


# ---------------------------------------------------------------- part 2
# DA3 windows (official path, persisted to npz so iteration is cheap).

def run_windows() -> dict:
    if DEPTH_CACHE.exists():
        log("loading cached window depths")
        z = np.load(DEPTH_CACHE)
        return {k: z[k] for k in z.files}
    import torch
    from da3base_official_streaming_oracle import install_mps_chunked_sdpa
    install_mps_chunked_sdpa(torch, 256, 4.0)
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    last = {"v": None}

    def _align(self, extrinsics, intrinsics, prediction,
               align_to_input_ext_scale=True, ransac_view_thresh=10):
        if extrinsics is None:
            return prediction
        prediction.intrinsics = intrinsics.numpy()
        _, _, scale, aligned = align_poses_umeyama(
            prediction.extrinsics, extrinsics.numpy(),
            ransac=len(extrinsics) >= ransac_view_thresh,
            return_aligned=True, random_state=42)
        last["v"] = float(scale)
        if align_to_input_ext_scale:
            prediction.extrinsics = extrinsics[..., :3, :].numpy()
            prediction.depth /= scale
        else:
            prediction.extrinsics = aligned
        return prediction

    DepthAnything3._align_to_input_extrinsics_intrinsics = _align
    log("loading DA3-BASE …")
    model = DepthAnything3.from_pretrained(
        "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
    ).to(device=torch.device("mps"))
    model.model.eval()

    out = {}
    for w in WINDOW_IDS:
        rows = man[w * 9: w * 9 + 18]
        paths = [str(D / "capture_seq_k35_strict" / r["jpegPath"]) for r in rows]
        ext = np.stack([np.asarray(r["cameraExtrinsic4x4"], np.float32).reshape(4, 4) for r in rows])
        ixt = np.stack([np.asarray(
            [[r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
             [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
             [0, 0, 1]], np.float32) for r in rows])
        t0 = time.time()
        pred = model.inference(paths, extrinsics=ext, intrinsics=ixt,
                               align_to_input_ext_scale=True,
                               process_res=896, process_res_method="upper_bound_resize")
        log(f"win{w}: inferred in {time.time()-t0:.0f}s, umeyama={last['v']:.4f}, "
            f"conf_med={float(np.median(pred.conf)):.2f}")
        append_row({"kind": "window", "win": w, "umeyama_scale": last["v"],
                    "conf_median": float(np.median(pred.conf))})
        out[f"depth_{w}"] = np.asarray(pred.depth, np.float32)
        out[f"conf_{w}"] = np.asarray(pred.conf, np.float32)
        out[f"K_{w}"] = np.asarray(pred.intrinsics, np.float32)
        out[f"w2c_{w}"] = ext
    np.savez_compressed(DEPTH_CACHE, **out)
    log(f"depths cached -> {DEPTH_CACHE}")
    return out


# ---------------------------------------------------------------- part 3
# Fix B: per-window scalar from sparse anchors (median ratio).

def fit_window_scale(win: dict, pts: np.ndarray, conf_pct: float = 40.0):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, conf_pct)
    ratios = []
    for i in range(n):
        w2c = w2cs[i].astype(np.float64)
        cam = (w2c[:3, :3] @ pts.T + w2c[:3, 3:4])
        z = cam[2]
        front = z > 1e-3
        K = Ks[i]
        u = cam[0] / z * K[0, 0] + K[0, 2] - 0.5
        v = cam[1] / z * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zp = depth[i][vi[ok], ui[ok]].astype(np.float64)
        cp = conf[i][vi[ok], ui[ok]]
        good = (cp >= floor) & (zp > 1e-3)
        r = np.log(z[ok][good] / zp[good])
        keep = np.abs(r) <= GATE_LOG_RATIO
        ratios.append(r[keep])
    if not ratios:
        return None, 0, None
    r = np.concatenate(ratios)
    s = float(np.exp(np.median(r)))
    iqr = float(np.exp(np.percentile(r, 75)) / np.exp(np.percentile(r, 25)) - 1)
    return s, int(len(r)), iqr


# ---------------------------------------------------------------- part 4
# Same cross-window residual metric as expD2 (depth-reprojection).

def backproject(win, stride, s, conf_pct=40.0):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, conf_pct)
    pts = []
    for i in range(n):
        z = depth[i] * s
        m = (conf[i] >= floor) & (z > 1e-3)
        vs, us = np.where(m)
        sel = (vs % stride == 0) & (us % stride == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        K = Ks[i]
        zz = z[vs, us]
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2cs[i].astype(np.float64))
        pts.append((c2w @ cam)[:3].T.astype(np.float32))
    return np.concatenate(pts) if pts else np.zeros((0, 3), np.float32)


def pair_residual(src, dst, s_src, s_dst, conf_pct=75.0):
    pts = backproject(src, MEAS_STRIDE, s_src, 40.0)
    depth, conf, Ks, w2cs = dst["depth"], dst["conf"], dst["K"], dst["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, conf_pct)
    ratios, absd = [], []
    for i in range(n):
        w2c = w2cs[i].astype(np.float64)
        cam = (w2c[:3, :3] @ pts.T + w2c[:3, 3:4])
        z = cam[2]
        front = z > 1e-3
        K = Ks[i]
        u = cam[0] / z * K[0, 0] + K[0, 2] - 0.5
        v = cam[1] / z * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zd = depth[i][vi[ok], ui[ok]].astype(np.float64) * s_dst
        cd = conf[i][vi[ok], ui[ok]]
        zp = z[ok]
        good = (cd >= floor) & (zd > 1e-3)
        r = np.log(zd[good] / zp[good])
        keep = np.abs(r) <= GATE_LOG_RATIO
        ratios.append(r[keep])
        absd.append(np.abs(zd[good][keep] - zp[good][keep]))
    if not ratios:
        return {"n": 0}
    r = np.concatenate(ratios)
    a = np.concatenate(absd)
    return {"n": int(len(r)),
            "abs_rel_median_pct": float(np.median(np.abs(np.expm1(r))) * 100),
            "abs_rel_p90_pct": float(np.percentile(np.abs(np.expm1(r)), 90) * 100),
            "abs_cm_median": float(np.median(a) * 100),
            "abs_cm_p90": float(np.percentile(a, 90) * 100)}


def main() -> int:
    pts, _ = build_sparse_cloud()
    if len(pts) < 200:
        log(f"FATAL: only {len(pts)} anchors — triangulation too thin")
        return 1
    wins = run_windows()
    windows = {w: {"depth": wins[f"depth_{w}"], "conf": wins[f"conf_{w}"],
                   "K": wins[f"K_{w}"], "w2c": wins[f"w2c_{w}"]} for w in WINDOW_IDS}

    s_B = {}
    for w in WINDOW_IDS:
        s, n_obs, iqr = fit_window_scale(windows[w], pts)
        s_B[w] = s
        log(f"win{w}: s_B={s:.4f} from {n_obs} anchor obs (ratio IQR {iqr:.3f})")
        append_row({"kind": "fixB_scale", "win": w, "s_B": s, "n_obs": n_obs, "iqr": iqr})

    r26 = s_B[26] / s_B[25]
    r28 = s_B[28] / s_B[25]
    log(f"V3 check: s_B ratios win26/win25={r26:.4f} (A: 0.9696), "
        f"win28/win25={r28:.4f} (A: 0.9687)")
    append_row({"kind": "fixB_vs_fixA", "ratio_26_25": r26, "ratio_28_25": r28,
                "fixA_conf75": {"26_25": 0.9696, "28_25": 0.9687}})

    for tag, scales in [("pre", {w: 1.0 for w in WINDOW_IDS}), ("postB", s_B)]:
        for a in WINDOW_IDS:
            for b in WINDOW_IDS:
                if a >= b:
                    continue
                ab = pair_residual(windows[a], windows[b], scales[a], scales[b])
                ba = pair_residual(windows[b], windows[a], scales[b], scales[a])
                log(f"{tag.upper()} {a}->{b}: {ab}")
                log(f"{tag.upper()} {b}->{a}: {ba}")
                append_row({"kind": f"pair_{tag}", "pair": [a, b],
                            "a_into_b": ab, "b_into_a": ba})

    log("EXPE-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
