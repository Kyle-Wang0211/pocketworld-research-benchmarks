"""expAO: voxel-size ladder on the consistency-filtered TSDF. Tests the
user's "1mm for extreme detail" request empirically. Computes the filter
ONCE (cache keep-masks), then integrates at {6,3,2,1.5}mm and compares:
vert count + floor-band slab thickness + (claim) finer voxel resurrects
the double-floor and voxelizes DA3 depth noise, not real detail.
"""
import json
import sys
import time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import cv2
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DELIVER / "tsdf"; OUT.mkdir(exist_ok=True)
MASKCACHE = Path("data/expAO_keepmasks.npz")
CONF_BAR, CONF_PCT = 6.0, 40.0
TAU, K_MIN, STRIDE = 0.005, 2, 2
VOXELS = [0.007, 0.008, 0.009, 0.010]
DEPTH_TRUNC = 12.0


def log(m):
    print(f"[expAO {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


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
        ws.append([depth, conf, K, w2c, fidx, s if s else 1.0])
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    sc = [r for r in rows if r["kind"] == "scales"][0]
    for w in range(len(sc["s_B"])):
        if sc["conf_medians"][w] < CONF_BAR:
            continue
        z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        ws.append([z["depth"].astype(np.float32), z["conf"].astype(np.float32),
                   z["K"].astype(np.float64), w2c4(z["w2c"]),
                   list(wdef[w]["frame_idx"]), sc["s_B"][w]])
    return ws


ws = load_windows()
log(f"{len(ws)} windows")

# ---- filter once -> keep-mask per (wid, frame) ----
if MASKCACHE.exists():
    z = np.load(MASKCACHE, allow_pickle=True)
    masks = z["masks"].item()
    log(f"loaded cached keep-masks ({len(masks)} frames)")
else:
    P, WID, FL, VV, UU = [], [], [], [], []
    for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for i in range(n):
            dk = depth[i] * s
            m = (conf[i] >= floor) & (dk > 1e-3)
            vs, us = np.where(m)
            sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
            vs, us = vs[sel], us[sel]
            if not len(vs):
                continue
            dd = dk[vs, us].astype(np.float64)
            x = (us + 0.5 - K[i][0, 2]) / K[i][0, 0] * dd
            y = (vs + 0.5 - K[i][1, 2]) / K[i][1, 1] * dd
            cam = np.stack([x, y, dd, np.ones_like(dd)])
            P.append((np.linalg.inv(w2c[i]) @ cam)[:3].T.astype(np.float32))
            WID.append(np.full(len(vs), wid, np.int16))
            FL.append(np.full(len(vs), i, np.int16))
            VV.append(vs.astype(np.int16)); UU.append(us.astype(np.int16))
    P = np.concatenate(P); WID = np.concatenate(WID); FL = np.concatenate(FL)
    VV = np.concatenate(VV); UU = np.concatenate(UU)
    log(f"{len(P):,} candidate pts; KDTree filter…")
    tree = cKDTree(P); keep = np.zeros(len(P), bool)
    for a in range(0, len(P), 200000):
        b = min(a + 200000, len(P))
        for li, nb in enumerate(tree.query_ball_point(P[a:b], TAU, workers=-1)):
            others = WID[nb]; keep[a + li] = np.unique(others[others != WID[a + li]]).size >= K_MIN
    log(f"keep {keep.mean()*100:.1f}%")
    masks = {}
    for idx in np.where(keep)[0]:
        masks.setdefault((int(WID[idx]), int(FL[idx])), []).append((int(VV[idx]), int(UU[idx])))
    masks = {k: np.array(v) for k, v in masks.items()}
    np.savez_compressed(MASKCACHE, masks=np.array(masks, dtype=object))
    log("cached keep-masks")


def integrate(voxel):
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel, sdf_trunc=voxel * 4,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
        n, H, W = depth.shape
        for i in range(n):
            vu = masks.get((wid, i))
            if vu is None or not len(vu):
                continue
            dk = (depth[i] * s).astype(np.float32)
            mk = np.zeros((H, W), bool); mk[vu[:, 0], vu[:, 1]] = True
            dk[~mk] = 0.0
            img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1]
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(img)), o3d.geometry.Image(dk),
                depth_scale=1.0, depth_trunc=DEPTH_TRUNC, convert_rgb_to_intensity=False)
            intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[i][0, 0], K[i][1, 1], K[i][0, 2], K[i][1, 2])
            vol.integrate(rgbd, intr, w2c[i])
    return vol.extract_triangle_mesh()


import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, len(VOXELS), figsize=(7 * len(VOXELS), 7))
results = []
for j, vx in enumerate(VOXELS):
    t0 = time.time()
    try:
        mesh = integrate(vx)
    except (MemoryError, RuntimeError) as e:
        log(f"voxel {vx*1000:.1f}mm FAILED: {e}")
        ax[j].set_title(f"{vx*1000:.1f}mm OOM/FAIL"); continue
    V = np.asarray(mesh.vertices); nv = len(V)
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(OUT / f"tsdf_v{int(vx*1000*10)}.ply"), mesh)
    # floor-band thickness: points near floor (lowest 15% in Y), measure Y spread
    if len(V):
        ylo = np.percentile(V[:, 1], 2)
        floorpts = V[V[:, 1] < ylo + 0.08]
        band = float(np.percentile(floorpts[:, 1], 90) - np.percentile(floorpts[:, 1], 10)) * 1000 if len(floorpts) else 0
    else:
        band = 0
    xmid = np.median(V[:, 0])
    slab = V[np.abs(V[:, 0] - xmid) < 0.03]
    ax[j].scatter(slab[:, 2], slab[:, 1], s=0.5, c="#3a3", alpha=0.5, linewidths=0)
    ax[j].set_title(f"{vx*1000:.1f}mm  {nv:,}v  地板带{band:.0f}mm"); ax[j].set_aspect("equal")
    log(f"voxel {vx*1000:.1f}mm: {nv:,} verts, floor-band {band:.0f}mm, {time.time()-t0:.0f}s")
    results.append((vx, nv, band))
fig.tight_layout(); fig.savefig(OUT / "voxel_ladder.png", dpi=110)
log("saved voxel_ladder.png")
for vx, nv, band in results:
    log(f"  {vx*1000:.1f}mm -> {nv:,} verts, floor band {band:.0f}mm")
log("EXPAO-DONE")
