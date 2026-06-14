"""expAL: cross-window CONSISTENCY filter (user idea: delete high-freq
noise + hard regions, keep only good regions). One filter does all three:
a point survives only if >= K_MIN OTHER windows have a point within TAU
in 3D. Hard regions (windows disagree) -> dropped; isolated scatter ->
dropped; good regions (multi-window agreement) -> kept.

Input = 23 conf>=6 windows (old11 + new12), FixB-scaled, photo-colored.
Per-point window-id tag. KDTree cross-window neighbor count.
Output: filtered PLY + slab(filtered vs raw) + retention %.
"""
import json
import sys
import time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DELIVER / "consistency"
OUT.mkdir(exist_ok=True)
CONF_BAR, CONF_PCT = 6.0, 40.0
TAU = float(sys.argv[1]) if len(sys.argv) > 1 else 0.005   # 5mm
K_MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 2       # >=2 other windows
PLY_STRIDE = int(sys.argv[3]) if len(sys.argv) > 3 else 2


def log(m):
    print(f"[expAL {time.strftime('%H:%M:%S')}] {m}", flush=True)


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


def collect():
    """all 23 conf>=6 windows -> points + colors + window-id."""
    P, C, Wid = [], [], []
    wid = 0
    # OLD 11
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
        _emit(P, C, Wid, wid, depth, conf, K, w2c, fidx, s if s else 1.0)
        wid += 1
    # NEW 12
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    scales = [r for r in rows if r["kind"] == "scales"][0]
    for w in range(len(scales["s_B"])):
        if scales["conf_medians"][w] < CONF_BAR:
            continue
        z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        _emit(P, C, Wid, wid, z["depth"].astype(np.float32), z["conf"].astype(np.float32),
              z["K"].astype(np.float64), w2c4(z["w2c"]), list(wdef[w]["frame_idx"]),
              scales["s_B"][w])
        wid += 1
    return (np.concatenate(P), np.concatenate(C), np.concatenate(Wid), wid)


def _emit(P, C, Wid, wid, depth, conf, K, w2c, fidx, s):
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = depth[i] * s
        m = (conf[i] >= floor) & (dk > 1e-3)
        vs, us = np.where(m)
        sel = (vs % PLY_STRIDE == 0) & (us % PLY_STRIDE == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        dd = dk[vs, us].astype(np.float64)
        x = (us + 0.5 - K[i][0, 2]) / K[i][0, 0] * dd
        y = (vs + 0.5 - K[i][1, 2]) / K[i][1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        P.append((np.linalg.inv(w2c[i]) @ cam)[:3].T.astype(np.float32))
        C.append(img[vs, us][:, ::-1])
        Wid.append(np.full(len(vs), wid, np.int16))


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


def main():
    t0 = time.time()
    P, C, Wid, nwin = collect()
    log(f"{nwin} windows, {len(P):,} pts (stride {PLY_STRIDE}) in {time.time()-t0:.0f}s")
    tree = cKDTree(P)
    # for each point: neighbors within TAU; count DISTINCT other windows
    log(f"KDTree query r={TAU*1000:.0f}mm …")
    keep = np.zeros(len(P), bool)
    CHUNK = 200000
    for a in range(0, len(P), CHUNK):
        b = min(a + CHUNK, len(P))
        nbrs = tree.query_ball_point(P[a:b], TAU, workers=-1)
        for li, nb in enumerate(nbrs):
            wself = Wid[a + li]
            others = Wid[nb]
            keep[a + li] = (np.unique(others[others != wself]).size >= K_MIN)
    ret = keep.mean()
    log(f"retention {ret*100:.1f}% ({keep.sum():,}/{len(P):,}); "
        f"tau {TAU*1000:.0f}mm K_min {K_MIN}")
    write_ply(OUT / "filtered.ply", P[keep], C[keep])
    write_ply(OUT / "raw.ply", P, C)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    xmid = np.median(P[:, 0])
    fig, ax = plt.subplots(1, 2, figsize=(16, 8))
    for a, (tag, mask) in zip(ax, [("raw 23窗", np.ones(len(P), bool)), ("filtered 一致性", keep)]):
        p = P[mask]; slab = p[np.abs(p[:, 0] - xmid) < 0.03]
        ax_ = a
        ax_.scatter(slab[:, 2], slab[:, 1], s=0.5, c="#39f", alpha=0.4, linewidths=0)
        ax_.set_title(f"{tag}  slab|x-{xmid:.2f}|<3cm"); ax_.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "raw_vs_filtered_slab.png", dpi=110)
    log("saved raw_vs_filtered_slab.png; filtered.ply + raw.ply")
    log("EXPAL-DONE")


if __name__ == "__main__":
    main()
