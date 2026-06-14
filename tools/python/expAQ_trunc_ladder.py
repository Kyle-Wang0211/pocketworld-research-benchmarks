"""expAQ: NO-FILTER TSDF (100% observations = crisp texture) with a
sdf_trunc LADDER. The multi-layer floor in no-filter TSDF is because the
window-disagreement band (~5cm) > 2*sdf_trunc(24mm) -> two zero-crossings.
Widening sdf_trunc makes the truncation band span the disagreement ->
TSDF blends all layers into ONE weighted-average surface, WITHOUT removing
any observations. Find the trunc that collapses floor/cabinet to one layer
while keeping structure crisp.
"""
import json, sys, time
from pathlib import Path
import numpy as np
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
VOXEL = 0.006
TRUNCS = [0.090, 0.100]    # 4x / 6.7x / 10x voxel
DEPTH_TRUNC = 12.0


def log(m): print(f"[expAQ {time.strftime('%H:%M:%S')}] {m}", flush=True)


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
        if not (d / "pytorch_conf.npy").exists(): continue
        conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
        if float(np.median(conf)) < CONF_BAR: continue
        depth = np.load(d / "pytorch_depth.npy").astype(np.float32)
        K = np.load(d / "pytorch_intrinsics.npy").astype(np.float64)
        w2c = w2c4(np.load(d / "pytorch_extrinsics.npy"))
        fidx = list(range(w * 9, w * 9 + 18))
        s, _ = fixb.fit_window_scale(anchors, depth, conf, w2c, fidx)
        ws.append((depth, conf, K, w2c, fidx, s if s else 1.0))
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    sc = [r for r in rows if r["kind"] == "scales"][0]
    for w in range(len(sc["s_B"])):
        if sc["conf_medians"][w] < CONF_BAR: continue
        z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        ws.append((z["depth"].astype(np.float32), z["conf"].astype(np.float32),
                   z["K"].astype(np.float64), w2c4(z["w2c"]),
                   list(wdef[w]["frame_idx"]), sc["s_B"][w]))
    return ws


ws = load_windows(); log(f"{len(ws)} windows (NO filter, 100% conf-gated obs)")
# preload color images once per frame is heavy; cache depth-gated rgbd inputs reused per trunc
frames_cache = []
for depth, conf, K, w2c, fidx, s in ws:
    n, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = (depth[i] * s).astype(np.float32); dk[conf[i] < fl] = 0.0
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1]
        frames_cache.append((dk, np.ascontiguousarray(img), K[i], w2c[i], W, H))
log(f"cached {len(frames_cache)} frame inputs")


def build(trunc):
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL, sdf_trunc=trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for dk, img, K, w2c, W, H in frames_cache:
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(img), o3d.geometry.Image(dk),
            depth_scale=1.0, depth_trunc=DEPTH_TRUNC, convert_rgb_to_intensity=False)
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[0, 0], K[1, 1], K[0, 2], K[1, 2])
        vol.integrate(rgbd, intr, w2c)
    return vol.extract_triangle_mesh()


import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, len(TRUNCS), figsize=(8 * len(TRUNCS), 8))
for j, tr in enumerate(TRUNCS):
    t0 = time.time(); mesh = build(tr); mesh.compute_vertex_normals()
    V = np.asarray(mesh.vertices)
    o3d.io.write_triangle_mesh(str(OUT / f"tsdf_nofilt_trunc{int(tr*1000)}.ply"), mesh)
    import shutil; shutil.copy(OUT / f"tsdf_nofilt_trunc{int(tr*1000)}.ply",
                               DELIVER / f"poisson/colored_mesh_trunc{int(tr*1000)}.ply")
    xmid = np.median(V[:, 0]); slab = V[np.abs(V[:, 0] - xmid) < 0.03]
    ax[j].scatter(slab[:, 2], slab[:, 1], s=0.6, c="#3a3", alpha=0.5, linewidths=0)
    ax[j].set_title(f"trunc {tr*1000:.0f}mm  {len(V):,}v"); ax[j].set_aspect("equal")
    log(f"trunc {tr*1000:.0f}mm: {len(V):,} verts, {time.time()-t0:.0f}s")
fig.tight_layout(); fig.savefig(OUT / "trunc_ladder_slab.png", dpi=110)
log("saved trunc_ladder_slab.png; EXPAQ-DONE")
