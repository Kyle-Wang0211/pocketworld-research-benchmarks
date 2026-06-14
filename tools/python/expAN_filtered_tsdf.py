"""expAN: STEP 4+5 done right — consistency filter THEN TSDF on the
SAME pixels. Fixes expAM (which fed raw conf-gated depth, skipping the
consistency filter). Pipeline order honored:
  FixB depth → cross-window consistency filter (per-point provenance)
  → per-(window,frame) keep-mask → TSDF integrate ONLY kept pixels.

TSDF needs depth IMAGES (ray-cast), but the filter outputs POINTS — so
we tag every point with (window, frame, v, u), run the same KDTree
cross-window filter (>=K_MIN other windows within TAU), then rebuild a
per-frame keep-mask and zero out non-kept depth before integrate.
Double gate = conf(P40) ∧ consistency.
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
CONF_BAR, CONF_PCT = 6.0, 40.0
TAU, K_MIN = 0.005, 2
STRIDE = 2                 # filter candidate sampling (= keep-mask grid)
VOXEL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.006
SDF_TRUNC = VOXEL * 4
DEPTH_TRUNC = 12.0


def log(m):
    print(f"[expAN {time.strftime('%H:%M:%S')}] {m}", flush=True)


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


def main():
    ws = load_windows()
    log(f"{len(ws)} conf>=6 windows")
    # ---- collect points with provenance (wid, frame-local, v, u) ----
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
    log(f"{len(P):,} candidate pts (stride {STRIDE})")
    # ---- cross-window consistency filter ----
    tree = cKDTree(P)
    keep = np.zeros(len(P), bool)
    for a in range(0, len(P), 200000):
        b = min(a + 200000, len(P))
        for li, nb in enumerate(tree.query_ball_point(P[a:b], TAU, workers=-1)):
            others = WID[nb]
            keep[a + li] = np.unique(others[others != WID[a + li]]).size >= K_MIN
    log(f"consistency keep {keep.mean()*100:.1f}% ({keep.sum():,}/{len(P):,})")
    # ---- rebuild per-(window,frame) keep-mask ----
    masks = {}
    ki = np.where(keep)[0]
    for idx in ki:
        masks.setdefault((int(WID[idx]), int(FL[idx])), []).append((int(VV[idx]), int(UU[idx])))

    # ---- TSDF integrate ONLY kept pixels ----
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    n_int = 0
    t0 = time.time()
    for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
        n, H, W = depth.shape
        for i in range(n):
            vu = masks.get((wid, i))
            if not vu:
                continue
            dk = (depth[i] * s).astype(np.float32)
            mask = np.zeros((H, W), bool)
            vu = np.array(vu)
            mask[vu[:, 0], vu[:, 1]] = True
            dk[~mask] = 0.0
            img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1]
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(img)), o3d.geometry.Image(dk),
                depth_scale=1.0, depth_trunc=DEPTH_TRUNC, convert_rgb_to_intensity=False)
            intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[i][0, 0], K[i][1, 1], K[i][0, 2], K[i][1, 2])
            vol.integrate(rgbd, intr, w2c[i]); n_int += 1
    log(f"integrated {n_int} frames (consistency-gated) in {time.time()-t0:.0f}s")
    mesh = vol.extract_triangle_mesh(); mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(OUT / "tsdf_filtered_mesh.ply"), mesh)
    log(f"tsdf_filtered_mesh.ply: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    V = np.asarray(mesh.vertices)
    raw = None
    rp = OUT / "tsdf_mesh.ply"   # expAM unfiltered TSDF for A/B
    if rp.exists():
        rm = o3d.io.read_triangle_mesh(str(rp)); raw = np.asarray(rm.vertices)
    xmid = np.median(V[:, 0])
    panels = [("TSDF (filter+gate)", V)] + ([("TSDF (no filter)", raw)] if raw is not None else [])
    fig, ax = plt.subplots(1, len(panels), figsize=(8*len(panels), 8))
    if len(panels) == 1: ax = [ax]
    for a, (tag, p) in zip(ax, panels):
        slab = p[np.abs(p[:, 0] - xmid) < 0.03]
        a.scatter(slab[:, 2], slab[:, 1], s=0.6, c="#3a3", alpha=0.5, linewidths=0)
        a.set_title(f"{tag}  slab|x-{xmid:.2f}|<3cm"); a.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "tsdf_filtered_vs_raw_slab.png", dpi=110)
    log("saved tsdf_filtered_vs_raw_slab.png; tsdf_filtered_mesh.ply")
    log("EXPAN-DONE")


if __name__ == "__main__":
    main()
