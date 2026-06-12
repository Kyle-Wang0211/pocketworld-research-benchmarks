#!/usr/bin/env python3
"""expF: FULL 414-frame K18 sliding-window sweep -> three complete
point clouds for eyeball inspection (no decimation, stride 1, conf40):

  full_pre.ply    official per-window umeyama only   (the ghosted original)
  full_postA.ply  + Fix A: overlap-chained per-window scalar (44 adjacent fits)
  full_postB.ply  + Fix B: sparse-anchor per-window scalar (independent)

Windows: w = 0..44, frames man[w*9 : w*9+18] (spatial order, stride 9).
Inference resumes from per-window npz caches; win 25/26/28 migrate from
expE's cache. PLYs are written STREAMING straight into the Desktop
delivery folder (header vertex count patched at the end).

Expected: ~42 windows x ~5 min MPS inference ≈ 3.5-4 h, then ~30 min
anchors + fits + PLY writes. Run under caffeinate.
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
OUT_DIR = Path("data/expF_full_sweep_2026_06_12")
WIN_DIR = OUT_DIR / "windows"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WIN_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expF_results.jsonl"
EXPE_CACHE = Path("data/expE_sparse_anchor_414_2026_06_12/window_depths.npz")
DELIVER = Path.home() / "Desktop/expF_full_clouds_2026_06_12"
DELIVER.mkdir(parents=True, exist_ok=True)

N_WIN = 45
CONF_PCT = 40.0
GATE_LOG_RATIO = np.log(2.0)
DETECT_LONG_SIDE = 1536.0
PAIR_SPAN = 6
SAMPSON_PX = 3.0
MIN_TRACK_VIEWS = 3
MIN_PARALLAX_DEG = 1.5
MAX_REPROJ_PX = 2.5
MIN_ANCHOR_OBS = 500
MEAS_STRIDE = 3


def log(m):
    print(f"[expF {time.strftime('%H:%M:%S')}] {m}", flush=True)


def append_row(row: dict) -> None:
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
assert len(man) >= N_WIN * 9 + 9, f"manifest too short: {len(man)}"


def win_rows(w: int) -> list:
    return man[w * 9: w * 9 + 18]


def win_path(w: int) -> Path:
    return WIN_DIR / f"win_{w:02d}.npz"


# ---------------------------------------------------------------- stage 1
def migrate_expe_cache() -> None:
    if not EXPE_CACHE.exists():
        return
    z = np.load(EXPE_CACHE)
    for w in (25, 26, 28):
        if win_path(w).exists() or f"depth_{w}" not in z.files:
            continue
        np.savez_compressed(
            win_path(w),
            depth=z[f"depth_{w}"].astype(np.float32),
            conf=z[f"conf_{w}"].astype(np.float16),
            K=z[f"K_{w}"].astype(np.float32),
            w2c=z[f"w2c_{w}"].astype(np.float32),
        )
        log(f"migrated win{w} from expE cache")


def run_all_windows() -> None:
    todo = [w for w in range(N_WIN) if not win_path(w).exists()]
    if not todo:
        log("all windows cached")
        return
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
    log(f"loading DA3-BASE for {len(todo)} windows …")
    model = DepthAnything3.from_pretrained(
        "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
    ).to(device=torch.device("mps"))
    model.model.eval()

    for idx, w in enumerate(todo):
        rows = win_rows(w)
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
        np.savez_compressed(
            win_path(w),
            depth=np.asarray(pred.depth, np.float32),
            conf=np.asarray(pred.conf, np.float16),
            K=np.asarray(pred.intrinsics, np.float32),
            w2c=ext,
        )
        cm = float(np.median(np.asarray(pred.conf)))
        log(f"win{w:02d} inferred ({idx+1}/{len(todo)}) in {time.time()-t0:.0f}s, "
            f"umeyama={last['v']:.4f}, conf_med={cm:.2f}")
        append_row({"kind": "window", "win": w, "umeyama_scale": last["v"],
                    "conf_median": cm, "infer_s": time.time() - t0})


def load_win(w: int) -> dict:
    z = np.load(win_path(w))
    return {"depth": z["depth"].astype(np.float32),
            "conf": z["conf"].astype(np.float32),
            "K": z["K"].astype(np.float64),
            "w2c": z["w2c"].astype(np.float64)}


# ---------------------------------------------------------------- stage 2
def build_sparse_cloud() -> np.ndarray:
    cache = OUT_DIR / "anchors_414.npy"
    if cache.exists():
        pts = np.load(cache)
        log(f"loaded {len(pts)} cached anchors")
        return pts
    sift = cv2.SIFT_create(nfeatures=6000)
    kps, descs, Ks, w2cs = [], [], [], []
    t0 = time.time()
    for r in man[: N_WIN * 9 + 9]:
        img = cv2.imread(str(D / "capture_seq_k35_strict" / r["jpegPath"]), cv2.IMREAD_GRAYSCALE)
        s = DETECT_LONG_SIDE / max(img.shape)
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        kp, de = sift.detectAndCompute(img, None)
        kps.append(np.array([k.pt for k in kp], dtype=np.float64))
        descs.append(de)
        fx, fy, cx, cy = r["cameraIntrinsicFxFyCxCy"]
        Ks.append(np.array([[fx * s, 0, cx * s], [0, fy * s, cy * s], [0, 0, 1]]))
        w2cs.append(np.asarray(r["cameraExtrinsic4x4"], np.float64).reshape(4, 4))
    n_img = len(kps)
    log(f"SIFT on {n_img} frames in {time.time()-t0:.0f}s")

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

    t0 = time.time()
    n_match = 0
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
                    n_match += 1
    log(f"matching done in {time.time()-t0:.0f}s, {n_match} gated matches")

    tracks: dict = {}
    for node in list(parent.keys()):
        tracks.setdefault(find(node), []).append(node)

    pts = []
    t0 = time.time()
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
            d = X - c2w[:3, 3]
            rays.append(d / max(np.linalg.norm(d), 1e-9))
        if not ok:
            continue
        rays = np.asarray(rays)
        cosmin = np.clip((rays @ rays.T).min(), -1, 1)
        if np.degrees(np.arccos(cosmin)) < MIN_PARALLAX_DEG:
            continue
        pts.append(X)
    pts = np.asarray(pts, dtype=np.float64)
    log(f"triangulated {len(pts)} anchors in {time.time()-t0:.0f}s")
    append_row({"kind": "sparse_cloud", "n_anchors": int(len(pts))})
    np.save(OUT_DIR / "anchors_414.npy", pts)
    return pts


# ---------------------------------------------------------------- stage 3
def fit_window_scale_B(win: dict, pts: np.ndarray):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    ratios = []
    for i in range(n):
        w2c = w2cs[i]
        cam = (w2c[:3, :3] @ pts.T + w2c[:3, 3:4])
        zc = cam[2]
        front = zc > 1e-3
        K = Ks[i]
        u = cam[0] / zc * K[0, 0] + K[0, 2] - 0.5
        v = cam[1] / zc * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zp = depth[i][vi[ok], ui[ok]].astype(np.float64)
        cp = conf[i][vi[ok], ui[ok]]
        good = (cp >= floor) & (zp > 1e-3)
        r = np.log(zc[ok][good] / zp[good])
        ratios.append(r[np.abs(r) <= GATE_LOG_RATIO])
    if not ratios:
        return None, 0
    r = np.concatenate(ratios)
    if len(r) < MIN_ANCHOR_OBS:
        return None, int(len(r))
    return float(np.exp(np.median(r))), int(len(r))


def backproject_meas(win, s):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    pts = []
    for i in range(n):
        z = depth[i] * s
        m = (conf[i] >= floor) & (z > 1e-3)
        vs, us = np.where(m)
        sel = (vs % MEAS_STRIDE == 0) & (us % MEAS_STRIDE == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        K = Ks[i]
        zz = z[vs, us].astype(np.float64)
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2cs[i])
        pts.append((c2w @ cam)[:3].T)
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def ratio_into(pts, dst) -> float | None:
    depth, conf, Ks, w2cs = dst["depth"], dst["conf"], dst["K"], dst["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    ratios = []
    for i in range(n):
        w2c = w2cs[i]
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
        zd = depth[i][vi[ok], ui[ok]].astype(np.float64)
        cd = conf[i][vi[ok], ui[ok]]
        zp = z[ok]
        good = (cd >= floor) & (zd > 1e-3)
        r = np.log(zd[good] / zp[good])
        ratios.append(r[np.abs(r) <= GATE_LOG_RATIO])
    if not ratios:
        return None
    r = np.concatenate(ratios)
    if len(r) < 50_000:
        return None
    return float(np.exp(np.median(r)))


def fit_chain_A() -> list:
    s_A = [1.0]
    prev = load_win(0)
    prev_pts = backproject_meas(prev, 1.0)
    for w in range(1, N_WIN):
        cur = load_win(w)
        r_ab = ratio_into(prev_pts, cur)          # prev pts into cur depth
        cur_pts = backproject_meas(cur, 1.0)
        r_ba = ratio_into(cur_pts, prev)
        if r_ab is None or r_ba is None:
            rel = 1.0
            log(f"A-chain win{w}: thin overlap, rel=1.0")
        else:
            rel = 1.0 / np.sqrt(r_ab / r_ba)
        s_A.append(s_A[-1] * rel)
        append_row({"kind": "fixA_chain", "win": w, "rel": rel, "s_A": s_A[-1]})
        prev, prev_pts = cur, cur_pts
    log(f"A-chain done: min {min(s_A):.4f} max {max(s_A):.4f}")
    return s_A


# ---------------------------------------------------------------- stage 4
class PlyStream:
    def __init__(self, path: Path):
        self.path = path
        self.fh = open(path, "wb")
        self.count = 0
        header = ("ply\nformat binary_little_endian 1.0\n"
                  "element vertex 000000000000\n"
                  "property float x\nproperty float y\nproperty float z\n"
                  "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                  "end_header\n")
        self.fh.write(header.encode("ascii"))

    def add(self, pts: np.ndarray, cols: np.ndarray):
        rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
        rec["xyz"], rec["rgb"] = pts.astype(np.float32), cols
        self.fh.write(rec.tobytes())
        self.count += len(pts)

    def close(self):
        self.fh.close()
        with open(self.path, "r+b") as fh:
            data = fh.read(200)
            idx = data.find(b"000000000000")
            fh.seek(idx)
            fh.write(f"{self.count:012d}".encode("ascii"))


def write_clouds(s_A: list, s_B: list) -> None:
    streams = {
        "pre": PlyStream(DELIVER / "full_pre.ply"),
        "postA": PlyStream(DELIVER / "full_postA.ply"),
        "postB": PlyStream(DELIVER / "full_postB.ply"),
    }
    t0 = time.time()
    for w in range(N_WIN):
        win = load_win(w)
        rows = win_rows(w)
        depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for i in range(n):
            z0 = depth[i]
            m = (conf[i] >= floor) & (z0 > 1e-3)
            vs, us = np.where(m)
            if not len(vs):
                continue
            img = cv2.imread(str(D / "capture_seq_k35_strict" / rows[i]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            cols = img[vs, us][:, ::-1]
            K = Ks[i]
            c2w = np.linalg.inv(w2cs[i])
            zz = z0[vs, us].astype(np.float64)
            x = (us + 0.5 - K[0, 2]) / K[0, 0]
            y = (vs + 0.5 - K[1, 2]) / K[1, 1]
            for tag, s in (("pre", 1.0), ("postA", s_A[w]), ("postB", s_B[w])):
                zs = zz * s
                cam = np.stack([x * zs, y * zs, zs, np.ones_like(zs)])
                streams[tag].add((c2w @ cam)[:3].T, cols)
        if w % 5 == 0:
            log(f"PLY write: win{w:02d}/{N_WIN} done, "
                f"{streams['pre'].count/1e6:.0f}M pts so far, {time.time()-t0:.0f}s")
    for tag, st in streams.items():
        st.close()
        sz = st.path.stat().st_size / 1e9
        log(f"{st.path.name}: {st.count:,} pts, {sz:.2f} GB")
        append_row({"kind": "ply", "file": st.path.name, "pts": st.count, "gb": sz})


def main() -> int:
    migrate_expe_cache()
    run_all_windows()
    pts = build_sparse_cloud()
    s_B, n_fallback = [], 0
    for w in range(N_WIN):
        s, n_obs = fit_window_scale_B(load_win(w), pts)
        if s is None:
            s, n_fallback = 1.0, n_fallback + 1
            log(f"win{w:02d}: s_B fallback 1.0 (obs {n_obs})")
        s_B.append(s)
        append_row({"kind": "fixB_scale", "win": w, "s_B": s, "n_obs": n_obs})
    log(f"s_B done: min {min(s_B):.4f} max {max(s_B):.4f}, fallbacks {n_fallback}")
    s_A = fit_chain_A()
    # A vs B per-window comparison (chain drift visibility)
    diff = [abs(a / b - 1) * 100 for a, b in zip(s_A, s_B)]
    log(f"A-vs-B per-window |scale diff|: median {np.median(diff):.2f}% max {max(diff):.2f}% "
        f"(A is chain-relative to win0; common global factor expected)")
    append_row({"kind": "A_vs_B", "diff_pct_median": float(np.median(diff)),
                "diff_pct_max": float(max(diff))})
    write_clouds(s_A, s_B)
    log("EXPF-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
