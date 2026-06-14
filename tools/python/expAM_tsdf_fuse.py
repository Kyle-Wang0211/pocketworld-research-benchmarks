"""expAM: STEP 5 — weighted TSDF fusion (Open3D ScalableTSDFVolume, MIT).
Integrate the 23 conf>=6 windows' FixB-scaled depth maps (conf-gated per
pixel) into one volumetric SDF -> single surface. Tests whether the ~1cm
good-region thickness collapses to one sheet under volumetric averaging.

First cut = UNIFORM per-observation weight (legacy API can't do per-pixel
conf*n·v). But uniform already gives the key denoising: a floor seen by N
windows gets weight N, an outlier seen by 1 gets weight 1 -> surface goes
to multi-window consensus. conf gate (P40) drops bad pixels pre-integrate.
True conf*n·v weight = tensor VoxelBlockGrid refinement, later if needed.
"""
import json
import sys
import time
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
OUT = DELIVER / "tsdf"
OUT.mkdir(exist_ok=True)
CONF_BAR, CONF_PCT = 6.0, 40.0
VOXEL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.006   # 6mm
SDF_TRUNC = VOXEL * 4
DEPTH_TRUNC = 12.0


def log(m):
    print(f"[expAM {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def windows():
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
        ws.append((depth, conf, K, w2c, fidx, s if s else 1.0))
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    sc = [r for r in rows if r["kind"] == "scales"][0]
    for w in range(len(sc["s_B"])):
        if sc["conf_medians"][w] < CONF_BAR:
            continue
        z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        ws.append((z["depth"].astype(np.float32), z["conf"].astype(np.float32),
                   z["K"].astype(np.float64), w2c4(z["w2c"]),
                   list(wdef[w]["frame_idx"]), sc["s_B"][w]))
    return ws


def main():
    ws = windows()
    log(f"{len(ws)} conf>=6 windows; voxel {VOXEL*1000:.0f}mm trunc {SDF_TRUNC*1000:.0f}mm")
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    n_int = 0
    t0 = time.time()
    for depth, conf, K, w2c, fidx, s in ws:
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for i in range(n):
            dk = (depth[i] * s).astype(np.float32)
            dk[conf[i] < floor] = 0.0                       # conf gate -> 0 = skip
            img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1]
            color = o3d.geometry.Image(np.ascontiguousarray(img))
            dep = o3d.geometry.Image(dk)
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                color, dep, depth_scale=1.0, depth_trunc=DEPTH_TRUNC,
                convert_rgb_to_intensity=False)
            intr = o3d.camera.PinholeCameraIntrinsic(
                W, H, K[i][0, 0], K[i][1, 1], K[i][0, 2], K[i][1, 2])
            vol.integrate(rgbd, intr, w2c[i])
            n_int += 1
    log(f"integrated {n_int} frames in {time.time()-t0:.0f}s")
    mesh = vol.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(OUT / "tsdf_mesh.ply"), mesh)
    log(f"tsdf_mesh.ply: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")
    pcd = vol.extract_point_cloud()
    V = np.asarray(mesh.vertices)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    # slab vs the consistency-filtered raw point cloud
    filt = None
    fp = DELIVER / "consistency/filtered.ply"
    if fp.exists():
        with open(fp, "rb") as f:
            h = f.read(400); he = h.find(b"end_header\n") + 11
            nn = int(h[:he].decode().split("element vertex ")[1].split()[0]); f.seek(he)
            r = np.frombuffer(f.read(nn * 15), np.uint8).reshape(nn, 15)
        filt = r[:, :12].copy().view(np.float32).reshape(nn, 3)
    xmid = np.median(V[:, 0])
    panels = [("TSDF mesh verts", V)] + ([("filtered points", filt)] if filt is not None else [])
    fig, ax = plt.subplots(1, len(panels), figsize=(8 * len(panels), 8))
    if len(panels) == 1:
        ax = [ax]
    for a, (tag, p) in zip(ax, panels):
        slab = p[np.abs(p[:, 0] - xmid) < 0.03]
        a.scatter(slab[:, 2], slab[:, 1], s=0.6, c="#3a3", alpha=0.5, linewidths=0)
        a.set_title(f"{tag}  slab|x-{xmid:.2f}|<3cm"); a.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "tsdf_vs_filtered_slab.png", dpi=110)
    log("saved tsdf_vs_filtered_slab.png; tsdf_mesh.ply")
    log("EXPAM-DONE")


if __name__ == "__main__":
    main()
