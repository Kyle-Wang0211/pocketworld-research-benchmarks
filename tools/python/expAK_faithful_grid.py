"""expAK: FAITHFUL 360MonoDepth grid alignment — dense overlap-consistency
data term + JOINT solve over all window/frame grids. Fixes expAJ's overfit
(which fit each frame's grid in isolation to only ~133 sparse anchors).

Official data term (depthmap_stitcher_group.cpp ReprojectionResidual):
  temp = (depth_tar·scale_tar + offset_tar) − (depth_src·scale_src + offset_src)
where scale/offset are bilinear-interpolated from per-map grids, optimized
JOINTLY. We copy that, with the cleanest possible overlap correspondence:

  adjacent windows (stride 9) SHARE 9 physical frames. The same frame in
  window P and window Q has two depth maps; at the SAME pixel (same camera,
  same ray) the two adjusted depths must be EQUAL. → dense per-pixel
  cross-window constraint, no reprojection needed.

Terms (all linear in scale/offset → one big sparse LSQR, like the linear
core of the official Ceres problem):
  1. shared-frame consistency  (dense, couples windows)         w=1.0
  2. metric anchor grounding   (each obs adjusted-depth ≈ X_z)  w=anchor
  3. smoothness ‖∇·‖² per grid (official, scale & offset)       w=1e-3·N
  4. scale-reg (s→s_fixB, o→0)                                  w=1e-2·N
Unit = (window, frame). Grid = 8×5 scale + 8×5 offset per unit.
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
CONF_BAR, CONF_PCT = 6.0, 40.0
GH, GW = 8, 5
W_SHARE = 1.0
W_ANCHOR = 1.0
W_SMOOTH = 0.3
W_SCALE = 0.05
SHARE_STRIDE = 8
GATE_LOG = np.log(2.0)
PLY_STRIDE = 3
DETECT_LONG = 1536.0


def log(m):
    print(f"[expAK {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def bw(u01, v01):
    """(idx[...,4], w[...,4]) bilinear into flattened GH*GW grid."""
    fx = np.clip(u01, 0, 1) * (GW - 1); fy = np.clip(v01, 0, 1) * (GH - 1)
    x0 = np.clip(np.floor(fx).astype(int), 0, GW - 2)
    y0 = np.clip(np.floor(fy).astype(int), 0, GH - 2)
    ax = fx - x0; ay = fy - y0
    idx = np.stack([y0*GW+x0, y0*GW+x0+1, (y0+1)*GW+x0, (y0+1)*GW+x0+1], -1)
    w = np.stack([(1-ax)*(1-ay), ax*(1-ay), (1-ax)*ay, ax*ay], -1)
    return idx, w


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
        ws.append({"win": w, "depth": depth, "conf": conf, "K": K, "w2c": w2c,
                   "fidx": fidx, "s_fixB": s if s else 1.0})
    return ws


def main():
    ws = load_windows()
    log(f"{len(ws)} windows")
    # units = (window i, local frame j); param block per unit = 2*GH*GW (scale|offset)
    NB = GH * GW
    units = [(i, j) for i in range(len(ws)) for j in range(18)]
    uindex = {(i, j): k for k, (i, j) in enumerate(units)}
    NU = len(units)
    P = NU * 2 * NB                                   # total unknowns
    log(f"units {NU}, unknowns {P}")

    def sblk(k):    # scale param base index of unit k
        return k * 2 * NB

    def oblk(k):    # offset param base index
        return k * 2 * NB + NB

    rows_i, rows_j, rows_v, rhs = [], [], [], []
    nrow = [0]

    def add_row(cols, vals, b):
        r = nrow[0]
        for c, v in zip(cols, vals):
            rows_i.append(r); rows_j.append(c); rows_v.append(v)
        rhs.append(b); nrow[0] += 1

    # ---- 1. shared-frame dense consistency ----
    # group units by physical frame id
    by_fid = {}
    for k, (i, j) in enumerate(units):
        by_fid.setdefault(ws[i]["fidx"][j], []).append(k)
    n_share = 0
    for fid, ks in by_fid.items():
        if len(ks) < 2:
            continue
        # all pairs of windows sharing this physical frame
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                ka, kb = ks[a], ks[b]
                ia, ja = units[ka]; ib, jb = units[kb]
                da = ws[ia]["depth"][ja]; db = ws[ib]["depth"][jb]
                ca = ws[ia]["conf"][ja]; cb = ws[ib]["conf"][jb]
                H, Wd = da.shape
                fa = np.percentile(ws[ia]["conf"], CONF_PCT)
                fb = np.percentile(ws[ib]["conf"], CONF_PCT)
                vv, uu = np.mgrid[0:H:SHARE_STRIDE, 0:Wd:SHARE_STRIDE]
                vv = vv.ravel(); uu = uu.ravel()
                dav = da[vv, uu]; dbv = db[vv, uu]
                g = (ca[vv, uu] >= fa) & (cb[vv, uu] >= fb) & (dav > 1e-3) & (dbv > 1e-3)
                g &= np.abs(np.log(np.maximum(dav, 1e-6) / np.maximum(dbv, 1e-6))) < GATE_LOG
                if g.sum() == 0:
                    continue
                u01 = uu[g] / (Wd - 1); v01 = vv[g] / (H - 1)
                idx, wt = bw(u01, v01)
                sw = W_SHARE
                for m in range(g.sum()):
                    cols, vals = [], []
                    for t in range(4):
                        cols.append(sblk(ka) + idx[m, t]); vals.append(wt[m, t] * dav[g][m] * sw)
                        cols.append(oblk(ka) + idx[m, t]); vals.append(wt[m, t] * sw)
                        cols.append(sblk(kb) + idx[m, t]); vals.append(-wt[m, t] * dbv[g][m] * sw)
                        cols.append(oblk(kb) + idx[m, t]); vals.append(-wt[m, t] * sw)
                    add_row(cols, vals, 0.0)
                    n_share += 1
    log(f"shared-frame rows {n_share}")

    # ---- 2. metric anchor grounding ----
    n_anch = 0
    for k, (i, j) in enumerate(units):
        fid = ws[i]["fidx"][j]
        sel = anchors.obs_frame == fid
        if not sel.any():
            continue
        depth = ws[i]["depth"][j]; conf = ws[i]["conf"][j]
        H, Wd = depth.shape; scd = Wd / DETECT_LONG
        fl = np.percentile(ws[i]["conf"], CONF_PCT)
        uv = anchors.obs_uv[sel]; aidx = anchors.obs_aidx[sel]
        ud = np.round((uv[:, 0] + 0.5) * scd - 0.5).astype(int)
        vd = np.round((uv[:, 1] + 0.5) * scd - 0.5).astype(int)
        ok = (ud >= 0) & (ud < Wd) & (vd >= 0) & (vd < H)
        ud, vd, aidx = ud[ok], vd[ok], aidx[ok]
        zp = depth[vd, ud].astype(np.float64); cp = conf[vd, ud]
        X = anchors.pts[aidx]
        zc = (ws[i]["w2c"][j][:3, :3] @ X.T + ws[i]["w2c"][j][:3, 3:4])[2]
        gg = (cp >= fl * 0.5) & (zp > 1e-3) & (zc > 1e-3)
        gg &= np.abs(np.log(zc / np.maximum(zp, 1e-6))) < GATE_LOG
        if gg.sum() == 0:
            continue
        u01 = ud[gg] / (Wd - 1); v01 = vd[gg] / (H - 1)
        idx, wt = bw(u01, v01)
        for m in range(gg.sum()):
            cols, vals = [], []
            for t in range(4):
                cols.append(sblk(k) + idx[m, t]); vals.append(wt[m, t] * zp[gg][m] * W_ANCHOR)
                cols.append(oblk(k) + idx[m, t]); vals.append(wt[m, t] * W_ANCHOR)
            add_row(cols, vals, zc[gg][m] * W_ANCHOR)
            n_anch += 1
    log(f"anchor rows {n_anch}")

    # ---- 3. smoothness (scale & offset, adjacent grid cells) ----
    sm_pairs = []
    for y in range(GH):
        for x in range(GW):
            i0 = y * GW + x
            if x + 1 < GW: sm_pairs.append((i0, i0 + 1))
            if y + 1 < GH: sm_pairs.append((i0, i0 + GW))
    for k in range(NU):
        for (p, q) in sm_pairs:
            add_row([sblk(k) + p, sblk(k) + q], [W_SMOOTH, -W_SMOOTH], 0.0)
            add_row([oblk(k) + p, oblk(k) + q], [W_SMOOTH, -W_SMOOTH], 0.0)

    # ---- 4. scale-reg (s→s_fixB, o→0) ----
    for k, (i, j) in enumerate(units):
        sf = ws[i]["s_fixB"]
        for c in range(NB):
            add_row([sblk(k) + c], [W_SCALE], sf * W_SCALE)
            add_row([oblk(k) + c], [W_SCALE], 0.0)

    A = sp.csr_matrix((rows_v, (rows_i, rows_j)), shape=(nrow[0], P))
    b = np.asarray(rhs)
    log(f"solving LSQR: {A.shape[0]} rows x {P} cols, nnz {A.nnz}")
    t0 = time.time()
    x = spla.lsqr(A, b, atol=1e-7, btol=1e-7, iter_lim=4000)[0]
    log(f"solved in {time.time()-t0:.0f}s")

    # report grid spread per unit
    sp_lo, sp_hi = [], []
    for k in range(NU):
        sc = x[sblk(k):sblk(k)+NB]
        sp_lo.append(sc.min()); sp_hi.append(sc.max())
    log(f"scale grid: per-unit min mean {np.mean(sp_lo):.3f}, max mean {np.mean(sp_hi):.3f}")

    # ---- backproject with grid ----
    def apply_unit(k, depth):
        H, Wd = depth.shape
        uu, vv = np.meshgrid(np.linspace(0, 1, Wd), np.linspace(0, 1, H))
        idx, wt = bw(uu.ravel(), vv.ravel())
        sc = x[sblk(k):sblk(k)+NB]; of = x[oblk(k):oblk(k)+NB]
        s_pix = (sc[idx] * wt).sum(1).reshape(H, Wd)
        o_pix = (of[idx] * wt).sum(1).reshape(H, Wd)
        return depth * s_pix + o_pix

    allP, allC = [], []
    for k, (i, j) in enumerate(units):
        depth, conf, K, w2c = ws[i]["depth"][j], ws[i]["conf"][j], ws[i]["K"][j], ws[i]["w2c"][j]
        fid = ws[i]["fidx"][j]
        H, Wd = depth.shape
        fl = np.percentile(ws[i]["conf"], CONF_PCT)
        dk = apply_unit(k, depth)
        m = (conf >= fl) & (dk > 1e-3)
        vs, us = np.where(m)
        ss = (vs % PLY_STRIDE == 0) & (us % PLY_STRIDE == 0)
        vs, us = vs[ss], us[ss]
        if not len(vs):
            continue
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fid]["jpegPath"]))
        img = cv2.resize(img, (Wd, H), interpolation=cv2.INTER_AREA)
        dd = dk[vs, us].astype(np.float64)
        x3 = (us + 0.5 - K[0, 2]) / K[0, 0] * dd
        y3 = (vs + 0.5 - K[1, 2]) / K[1, 1] * dd
        cam = np.stack([x3, y3, dd, np.ones_like(dd)])
        allP.append((np.linalg.inv(w2c) @ cam)[:3].T.astype(np.float32))
        allC.append(img[vs, us][:, ::-1])
    Pc = np.concatenate(allP); Cc = np.concatenate(allC)
    fh = open(OUT / "sg_faithful.ply", "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(Pc)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n").encode())
    rec = np.empty(len(Pc), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
    rec["xyz"], rec["rgb"] = Pc, Cc; fh.write(rec.tobytes()); fh.close()
    log(f"sg_faithful.ply: {len(Pc):,} pts")

    # slab vs fixB (reuse expAJ sg_fixB if present)
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fixp = None
    if (OUT / "sg_fixB.ply").exists():
        with open(OUT / "sg_fixB.ply", "rb") as f:
            h = f.read(400); he = h.find(b"end_header\n") + 11
            n = int(h[:he].decode().split("element vertex ")[1].split()[0]); f.seek(he)
            r = np.frombuffer(f.read(n*15), np.uint8).reshape(n, 15)
        fixp = r[:, :12].copy().view(np.float32).reshape(n, 3)
    xmid = np.median(Pc[:, 0])
    panels = [("faithful grid", Pc)] + ([("fixB scalar", fixp)] if fixp is not None else [])
    fig, ax = plt.subplots(1, len(panels), figsize=(8*len(panels), 8))
    if len(panels) == 1: ax = [ax]
    for a, (tag, p) in zip(ax, panels):
        slab = p[np.abs(p[:, 0] - xmid) < 0.03]
        a.scatter(slab[:, 2], slab[:, 1], s=0.6, c="#39f", alpha=0.4, linewidths=0)
        a.set_title(f"{tag}  slab|x-{xmid:.2f}|<3cm"); a.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "faithful_vs_fixB_slab.png", dpi=110)
    log("saved faithful_vs_fixB_slab.png")
    log("EXPAK-DONE")


if __name__ == "__main__":
    main()
