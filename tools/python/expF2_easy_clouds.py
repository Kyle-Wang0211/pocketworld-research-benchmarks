#!/usr/bin/env python3
"""expF2: the user's shortcut — the original K18 spatial-window sweep
(expQ) saved every window's depth/conf/poses/colors to disk, and the
original ghosted deliverable was the 11 easy windows (conf_bar 6.0):

    easy_windows_reference_rgb.ply  (expS, pixel gate conf>=7.3265, 53.6M pts)

So: ZERO inference. Load expQ arrays, fit Fix A (adjacent-overlap chain
across all 45 windows) and Fix B (sparse-anchor per-window scalar) and
write THREE full-resolution clouds of the same 11 easy windows:

    easy_pre.ply    pixel-identical recreation of the original deliverable
    easy_postA.ply  + chained overlap scalar
    easy_postB.ply  + sparse-anchor scalar

Straight into ~/Desktop/expF2_easy_clouds_2026_06_12/.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
OUT_DIR = Path("data/expF2_easy_clouds_2026_06_12")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expF2_results.jsonl"
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
DELIVER.mkdir(parents=True, exist_ok=True)

N_WIN = 45
EASY = [0, 10, 11, 14, 24, 25, 26, 27, 40, 41, 42]   # expI easy reference
PIXEL_GATE = 7.326535224914551                        # original deliverable's gate
CONF_PCT = 40.0
GATE_LOG_RATIO = np.log(2.0)
MEAS_STRIDE = 3
DETECT_LONG_SIDE = 1536.0
PAIR_SPAN = 6
SAMPSON_PX = 3.0
MIN_TRACK_VIEWS = 3
MIN_PARALLAX_DEG = 1.5
MAX_REPROJ_PX = 2.5
MIN_ANCHOR_OBS = 500


def log(m):
    print(f"[expF2 {time.strftime('%H:%M:%S')}] {m}", flush=True)


def append_row(row):
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]


def load_win(w: int) -> dict:
    d = Q / f"window_{w:03d}"
    ext34 = np.load(d / "pytorch_extrinsics.npy").astype(np.float64)
    w2c = np.tile(np.eye(4), (len(ext34), 1, 1))
    w2c[:, :3, :] = ext34
    return {
        "depth": np.load(d / "pytorch_depth.npy").astype(np.float32),
        "conf": np.load(d / "pytorch_conf.npy").astype(np.float32),
        "K": np.load(d / "pytorch_intrinsics.npy").astype(np.float64),
        "w2c": w2c,
        "rgb": np.load(d / "processed_images_uint8.npy"),
    }


# ------------------------------------------------------------ anchors
def build_sparse_cloud() -> np.ndarray:
    cache = OUT_DIR / "anchors_414.npy"
    if cache.exists():
        pts = np.load(cache)
        log(f"loaded {len(pts)} cached anchors")
        return pts
    sift = cv2.SIFT_create(nfeatures=6000)
    kps, descs, Ks, w2cs = [], [], [], []
    t0 = time.time()
    for r in man:
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
    log(f"matching done in {time.time()-t0:.0f}s")

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
            dd = X - c2w[:3, 3]
            rays.append(dd / max(np.linalg.norm(dd), 1e-9))
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
    np.save(cache, pts)
    return pts


# ------------------------------------------------------------ fits
def fit_window_scale_B(win, pts):
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


def ratio_into(pts, dst):
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


# ------------------------------------------------------------ PLY
class PlyStream:
    def __init__(self, path):
        self.path = Path(path)
        self.fh = open(path, "wb")
        self.count = 0
        self.fh.write((
            "ply\nformat binary_little_endian 1.0\n"
            "element vertex 000000000000\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            "end_header\n").encode("ascii"))

    def add(self, pts, cols):
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


def main() -> int:
    pts = build_sparse_cloud()

    # sanity: same lineage as expE? win25<->26 raw overlap ratios
    w25, w26 = load_win(25), load_win(26)
    r_ab = ratio_into(backproject_meas(w25, 1.0), w26)
    r_ba = ratio_into(backproject_meas(w26, 1.0), w25)
    log(f"sanity 25<->26 ratios: {r_ab:.4f} / {r_ba:.4f} (expE: 1.0288 / 0.9710)")
    append_row({"kind": "sanity", "r_ab": r_ab, "r_ba": r_ba})

    s_B, n_fb = [], 0
    for w in range(N_WIN):
        s, n_obs = fit_window_scale_B(load_win(w), pts)
        if s is None:
            s, n_fb = 1.0, n_fb + 1
            log(f"win{w:02d}: s_B fallback (obs {n_obs})")
        s_B.append(s)
        append_row({"kind": "fixB_scale", "win": w, "s_B": s, "n_obs": n_obs})
    log(f"s_B: min {min(s_B):.4f} max {max(s_B):.4f} fallbacks {n_fb}")

    s_A = [1.0]
    prev = load_win(0)
    prev_pts = backproject_meas(prev, 1.0)
    for w in range(1, N_WIN):
        cur = load_win(w)
        rab = ratio_into(prev_pts, cur)
        cur_pts = backproject_meas(cur, 1.0)
        rba = ratio_into(cur_pts, prev)
        rel = 1.0 if (rab is None or rba is None) else 1.0 / np.sqrt(rab / rba)
        s_A.append(s_A[-1] * rel)
        append_row({"kind": "fixA_chain", "win": w, "rel": rel, "s_A": s_A[-1]})
        prev, prev_pts = cur, cur_pts
    # gauge A-chain to B's global scale so pre/postA/postB share one metric
    gauge = float(np.median([b / a for a, b in zip(s_A, s_B)]))
    s_A = [a * gauge for a in s_A]
    log(f"s_A chained (gauged x{gauge:.4f}): min {min(s_A):.4f} max {max(s_A):.4f}")
    diff = [abs(a / b - 1) * 100 for a, b in zip(s_A, s_B)]
    log(f"A-vs-B per-window |diff|: median {np.median(diff):.2f}% max {max(diff):.2f}%")
    append_row({"kind": "A_vs_B", "gauge": gauge,
                "diff_pct_median": float(np.median(diff)),
                "diff_pct_max": float(max(diff))})

    streams = {
        "pre": PlyStream(DELIVER / "easy_pre.ply"),
        "postA": PlyStream(DELIVER / "easy_postA.ply"),
        "postB": PlyStream(DELIVER / "easy_postB.ply"),
    }
    t0 = time.time()
    for w in EASY:
        win = load_win(w)
        depth, conf, Ks, w2cs, rgb = win["depth"], win["conf"], win["K"], win["w2c"], win["rgb"]
        n, H, W = depth.shape
        for i in range(n):
            z0 = depth[i]
            m = (conf[i] >= PIXEL_GATE) & (z0 > 1e-3)
            vs, us = np.where(m)
            if not len(vs):
                continue
            cols = rgb[i][vs, us]
            K = Ks[i]
            c2w = np.linalg.inv(w2cs[i])
            zz = z0[vs, us].astype(np.float64)
            x = (us + 0.5 - K[0, 2]) / K[0, 0]
            y = (vs + 0.5 - K[1, 2]) / K[1, 1]
            for tag, s in (("pre", 1.0), ("postA", s_A[w]), ("postB", s_B[w])):
                zs = zz * s
                cam = np.stack([x * zs, y * zs, zs, np.ones_like(zs)])
                streams[tag].add((c2w @ cam)[:3].T, cols)
        log(f"PLY: win{w:03d} done, {streams['pre'].count/1e6:.1f}M pts, {time.time()-t0:.0f}s")
    for tag, st in streams.items():
        st.close()
        log(f"{st.path.name}: {st.count:,} pts, {st.path.stat().st_size/1e9:.2f} GB")
        append_row({"kind": "ply", "file": st.path.name, "pts": st.count})
    log("EXPF2-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
