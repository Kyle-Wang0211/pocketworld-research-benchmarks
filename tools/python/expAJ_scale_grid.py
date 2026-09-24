"""expAJ: scale-GRID per-window deformation (360MonoDepth grid-of-scale-
handles, adapted) vs FixB single scalar. Small test on the 11 conf>=6
OLD windows.

360MonoDepth (official depthmap_stitcher.hpp): scale(+offset) coefficient
grid (default 5x8), bilinear-interpolated to pixels; energy = reprojection
data term + smoothness (w 1e-3) + scale-reg (w 1e-1); Ceres solve. We copy
the GRID parameterization + smoothness + scale-reg, but swap the data term:
instead of pairwise overlap consistency we fit to the 29k METRIC sparse
anchors (cleaner — they're absolute, not relative). Scale-only first
(the core hypothesis: spatially-varying scale beats one scalar; offset was
the expG2 overfit risk, add later only if grid wins).

Per frame: unknowns = Gh*Gw scale control points. Linear LSQ:
  min  Σ_anchors conf·(s(u,v)·z_pred − z_anchor)²
     + λ_sm·‖∇s‖²  (grid finite-diff smoothness)
     + λ_sc·(s − s_window_fixB)²   (cells w/o anchors fall back to FixB scalar)
Closed-form sparse normal equations (no Ceres needed for scale-only).
"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DELIVER / "scalegrid"
OUT.mkdir(exist_ok=True)
CONF_BAR = 6.0
CONF_PCT = 40.0
GH, GW = 8, 5                 # grid rows x cols (360MonoDepth coarse = 5w x 8h)
LAM_SMOOTH = 0.05            # ‖∇s‖² weight (relative to per-anchor data)
LAM_SCALE = 0.02            # (s − s_fixB)² pull for under-constrained cells
PLY_STRIDE = 3
GATE_LOG = np.log(2.0)


def log(m):
    print(f"[expAJ {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
frames = [r for r in man if r["jpegPath"].split("/")[-1] in azel]
z = np.load(ANCH)
anchors = fixb.AnchorSet(z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"])
DETECT_LONG = 1536.0


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def bilinear_rows(u01, v01):
    """Bilinear interpolation weights of a (GH x GW) grid at normalized
    (u01,v01)∈[0,1]. Returns (idx[4], w[4]) into flattened grid."""
    fx = u01 * (GW - 1); fy = v01 * (GH - 1)
    x0 = np.clip(np.floor(fx).astype(int), 0, GW - 2)
    y0 = np.clip(np.floor(fy).astype(int), 0, GH - 2)
    ax = fx - x0; ay = fy - y0
    i00 = y0 * GW + x0; i01 = y0 * GW + x0 + 1
    i10 = (y0 + 1) * GW + x0; i11 = (y0 + 1) * GW + x0 + 1
    w00 = (1 - ax) * (1 - ay); w01 = ax * (1 - ay)
    w10 = (1 - ax) * ay; w11 = ax * ay
    return np.stack([i00, i01, i10, i11], 1), np.stack([w00, w01, w10, w11], 1)


def smoothness_matrix():
    """Finite-diff Laplacian-ish: horizontal + vertical neighbor diffs."""
    rows = []
    for y in range(GH):
        for x in range(GW):
            i = y * GW + x
            if x + 1 < GW:
                r = np.zeros(GH * GW); r[i] = 1; r[i + 1] = -1; rows.append(r)
            if y + 1 < GH:
                r = np.zeros(GH * GW); r[i] = 1; r[i + GW] = -1; rows.append(r)
    return np.asarray(rows)


SMOOTH = smoothness_matrix()


def fit_scale_grid(u01, v01, z_pred, z_anchor, wts, s_fixB):
    """Linear LSQ for Gh*Gw scale control points."""
    N = GH * GW
    idx, w = bilinear_rows(u01, v01)            # (M,4)
    M = len(z_pred)
    # data term rows: Σ_k w_k s_k * z_pred ≈ z_anchor  (weight = sqrt(conf))
    rows = np.repeat(np.arange(M), 4)
    cols = idx.reshape(-1)
    sw = np.sqrt(wts)
    vals = (w * (z_pred * sw)[:, None]).reshape(-1)
    A_data = sp.csr_matrix((vals, (rows, cols)), shape=(M, N))
    b_data = z_anchor * sw
    # smoothness rows
    A_sm = sp.csr_matrix(SMOOTH) * np.sqrt(LAM_SMOOTH)
    b_sm = np.zeros(A_sm.shape[0])
    # scale-reg rows (pull toward s_fixB)
    A_sc = sp.identity(N, format="csr") * np.sqrt(LAM_SCALE)
    b_sc = np.full(N, s_fixB) * np.sqrt(LAM_SCALE)
    A = sp.vstack([A_data, A_sm, A_sc]).tocsr()
    b = np.concatenate([b_data, b_sm, b_sc])
    s = spla.lsqr(A, b, atol=1e-8, btol=1e-8, iter_lim=2000)[0]
    return s


def apply_grid(depth, s_grid):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
    idx, w = bilinear_rows(uu.reshape(-1), vv.reshape(-1))
    s_pix = (s_grid[idx] * w).sum(1).reshape(H, W)
    return depth * s_pix, s_pix


def load_windows():
    ws = []
    for w in range(45):
        d = Q / f"window_{w:03d}"
        if not (d / "pytorch_conf.npy").exists():
            continue
        conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
        if float(np.median(conf)) < CONF_BAR:
            continue
        depth = np.load(d / "pytorch_depth.npy").astype(np.float32)
        K = np.load(d / "pytorch_intrinsics.npy").astype(np.float64)
        w2c = w2c4(np.load(d / "pytorch_extrinsics.npy"))
        fidx = list(range(w * 9, w * 9 + 18))
        s, _ = fixb.fit_window_scale(anchors, depth, conf, w2c, fidx)
        ws.append({"depth": depth, "conf": conf, "K": K, "w2c": w2c,
                   "fidx": fidx, "s_fixB": s if s else 1.0})
    return ws


def build_cloud(ws, mode):
    """mode: 'fixB' (single scalar) or 'grid' (scale grid). Returns pts,cols."""
    allP, allC = [], []
    grid_stats = []
    for win in ws:
        depth, conf, K, w2c, fidx, s_fixB = (win["depth"], win["conf"], win["K"],
                                             win["w2c"], win["fidx"], win["s_fixB"])
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        scd = W / DETECT_LONG
        for i, fi in enumerate(fidx):
            if mode == "grid":
                sel = anchors.obs_frame == fi
                s_grid = np.full(GH * GW, s_fixB)
                if sel.sum() >= 8:
                    uv = anchors.obs_uv[sel]; aidx = anchors.obs_aidx[sel]
                    ud = np.round((uv[:, 0] + 0.5) * scd - 0.5).astype(int)
                    vd = np.round((uv[:, 1] + 0.5) * scd - 0.5).astype(int)
                    ok = (ud >= 0) & (ud < W) & (vd >= 0) & (vd < H)
                    ud, vd, aidx = ud[ok], vd[ok], aidx[ok]
                    zp = depth[i][vd, ud].astype(np.float64)
                    cp = conf[i][vd, ud].astype(np.float64)
                    X = anchors.pts[aidx]
                    zc = (w2c[i][:3, :3] @ X.T + w2c[i][:3, 3:4])[2]
                    g = (cp >= floor * 0.5) & (zp > 1e-3) & (zc > 1e-3)
                    r = np.log(zc[g] / np.maximum(zp[g], 1e-6))
                    keep = np.abs(r) <= GATE_LOG
                    if keep.sum() >= 8:
                        u01 = ud[g][keep] / (W - 1); v01 = vd[g][keep] / (H - 1)
                        s_grid = fit_scale_grid(u01, v01, zp[g][keep], zc[g][keep],
                                                cp[g][keep], s_fixB)
                        grid_stats.append((s_grid.min(), s_grid.max(), int(keep.sum())))
                dk, _ = apply_grid(depth[i], s_grid)
            else:
                dk = depth[i] * s_fixB
            m = (conf[i] >= floor) & (dk > 1e-3)
            vs, us = np.where(m)
            ssel = (vs % PLY_STRIDE == 0) & (us % PLY_STRIDE == 0)
            vs, us = vs[ssel], us[ssel]
            if not len(vs):
                continue
            img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fi]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            Ki = K[i]; dd = dk[vs, us].astype(np.float64)
            x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
            y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
            cam = np.stack([x, y, dd, np.ones_like(dd)])
            allP.append((np.linalg.inv(w2c[i]) @ cam)[:3].T.astype(np.float32))
            allC.append(img[vs, us][:, ::-1])
    P = np.concatenate(allP); C = np.concatenate(allC)
    if grid_stats:
        gs = np.array(grid_stats)
        log(f"  grid fits: {len(gs)} frames, s range per-frame "
            f"min {gs[:,0].mean():.3f} max {gs[:,1].mean():.3f} (spread within frame), "
            f"anchors/frame median {int(np.median(gs[:,2]))}")
    return P, C


def write_ply(path, P, C):
    fh = open(path, "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(P)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n").encode())
    rec = np.empty(len(P), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
    rec["xyz"], rec["rgb"] = P, C
    fh.write(rec.tobytes()); fh.close()


def slab_render(clouds):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    allp = clouds["fixB"][0]
    xmid = np.median(allp[:, 0])
    fig, ax = plt.subplots(1, 2, figsize=(16, 8))
    for a, tag in zip(ax, ["fixB", "grid"]):
        p = clouds[tag][0]
        slab = p[np.abs(p[:, 0] - xmid) < 0.03]
        a.scatter(slab[:, 2], slab[:, 1], s=0.6, c="#39f", alpha=0.4, linewidths=0)
        a.set_title(f"{tag}  slab|x-{xmid:.2f}|<3cm  (thin=good, layers=ghost)")
        a.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "fixB_vs_grid_slab.png", dpi=110)
    log("saved fixB_vs_grid_slab.png")


def main():
    ws = load_windows()
    log(f"loaded {len(ws)} conf>=6 windows, FixB scalars "
        f"{[round(w['s_fixB'],3) for w in ws]}")
    clouds = {}
    for mode in ["fixB", "grid"]:
        t0 = time.time()
        P, C = build_cloud(ws, mode)
        clouds[mode] = (P, C)
        write_ply(OUT / f"sg_{mode}.ply", P, C)
        log(f"{mode}: {len(P):,} pts in {time.time()-t0:.0f}s -> sg_{mode}.ply")
    slab_render(clouds)
    log("EXPAJ-DONE")


if __name__ == "__main__":
    main()
