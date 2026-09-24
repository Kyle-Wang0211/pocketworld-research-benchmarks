"""expAS: CONSENSUS gate at the DEPTH level -> Open3D ScalableTSDFVolume.

Why expAR/expAP looked "point-cloudy": they meshed a custom NARROW-BAND
active-voxel field with marching_cubes; where observations are sparse the
band fragments into thousands of disconnected triangle islands -> reads as
speckle, not a solid TSDF surface.

Fix: keep the consensus idea but DON'T custom-mesh. Apply consensus as a
per-pixel DEPTH MASK (drop pixels whose back-projected point has too few
distinct windows agreeing nearby = ghost / isolated scatter), then feed the
masked depth to the SAME Open3D ScalableTSDFVolume engine that produced the
clean ★40mm mesh. Result = expAL-style ghost removal + Open3D's crisp,
watertight, free-space-carved surface (no speckle, no hairy boundary).

  support(pixel) = # distinct windows with a surface point within TAU_CONS
  keep pixel iff support >= S_MIN  (>=1 other window agrees)
  trunc small (24mm) so true surface stays crisp; ghost sheet has low
  support -> its pixels dropped -> Open3D never integrates a 2nd floor.

Tunables (argv): VOXEL  S_MIN  TAU_CONS  SDF_TRUNC
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
VOXEL     = float(sys.argv[1]) if len(sys.argv) > 1 else 0.006
S_MIN     = int(sys.argv[2])   if len(sys.argv) > 2 else 2        # >= this many distinct windows
TAU_CONS  = float(sys.argv[3]) if len(sys.argv) > 3 else 0.010    # agreement radius
SDF_TRUNC = float(sys.argv[4]) if len(sys.argv) > 4 else 0.024    # smaller -> crisper detail
OUT_TAG   = sys.argv[5]        if len(sys.argv) > 5 else "consensus"
KEEP_VERT = int(sys.argv[6])   if len(sys.argv) > 6 else 0        # 1 = keep non-horizontal px regardless of support
NZ_HORIZ  = float(sys.argv[7]) if len(sys.argv) > 7 else 0.6      # |world n_z|>=this = horizontal (floor, ghost-prone)
DEPTH_TRUNC = 12.0


def log(m): print(f"[expAS {time.strftime('%H:%M:%S')}] {m}", flush=True)


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


def backproject(dk, K, w2ci, vs, us):
    dd = dk[vs, us].astype(np.float64)
    x = (us + 0.5 - K[0, 2]) / K[0, 0] * dd
    y = (vs + 0.5 - K[1, 2]) / K[1, 1] * dd
    cam = np.stack([x, y, dd, np.ones_like(dd)])
    return (np.linalg.inv(w2ci) @ cam)[:3].T


def world_nz(dk, K, w2ci, vs, us):
    """|world n_z| per pixel (1=horizontal/floor, 0=vertical/wall). Depth-space
    cross-product normal rotated to world."""
    H, W = dk.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu + 0.5 - K[0, 2]) / K[0, 0] * dk
    y = (vv + 0.5 - K[1, 2]) / K[1, 1] * dk
    P = np.stack([x, y, dk], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    n = np.cross(du, dv); ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    nworld = n[vs, us] @ w2ci[:3, :3]            # cam->world rotation (rows)
    return np.abs(nworld[:, 2])


ws = load_windows()
log(f"{len(ws)} windows | trunc {SDF_TRUNC*1000:.0f}mm  S_MIN {S_MIN}  tau {TAU_CONS*1000:.0f}mm")

# ---- pass 1: global consensus cell-hash (cell -> set of distinct windows) ----
allP, allW = [], []
for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
    n, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = depth[i] * s; m = (conf[i] >= fl) & (dk > 1e-3)
        vs, us = np.where(m); sel = (vs % 2 == 0) & (us % 2 == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs): continue
        allP.append(backproject(dk, K[i], w2c[i], vs, us).astype(np.float32))
        allW.append(np.full(len(vs), wid, np.int32))
allP = np.concatenate(allP); allW = np.concatenate(allW)
lo = np.percentile(allP, 0.5, axis=0) - 0.05
hi = np.percentile(allP, 99.5, axis=0) + 0.05
dimsC = np.ceil((hi - lo) / TAU_CONS).astype(np.int64) + 2
log(f"consensus cloud {len(allP):,} pts, cell grid {dimsC}")


def cell_lin(P):
    c = np.clip(np.floor((P - lo) / TAU_CONS).astype(np.int64), 0, dimsC - 1)
    return (c[:, 0] * dimsC[1] + c[:, 1]) * dimsC[2] + c[:, 2]


linP = cell_lin(allP)
pair = np.unique(linP * 32 + allW.astype(np.int64))          # distinct (cell, window)
cell_of_pair = pair // 32
uc, cnt = np.unique(cell_of_pair, return_counts=True)        # uc sorted; cnt = #distinct windows
log(f"{len(uc):,} occupied cells; median support {int(np.median(cnt))} windows")


def support_of(P):
    lin = cell_lin(P)
    pos = np.clip(np.searchsorted(uc, lin), 0, len(uc) - 1)
    return np.where(uc[pos] == lin, cnt[pos], 0)


# ---- pass 2: consensus-masked depth -> Open3D ScalableTSDFVolume ----
vol = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
kept_tot = drop_tot = 0
t0 = time.time()
for depth, conf, K, w2c, fidx, s in ws:
    n, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = (depth[i] * s).astype(np.float32)
        m = (conf[i] >= fl) & (dk > 1e-3)
        vs, us = np.where(m)
        if not len(vs): continue
        P = backproject(dk, K[i], w2c[i], vs, us)
        keep = support_of(P) >= S_MIN
        if KEEP_VERT:                                        # spare vertical (wall/background) px: can't form a double floor
            keep = keep | (world_nz(dk, K[i], w2c[i], vs, us) < NZ_HORIZ)
        kept_tot += int(keep.sum()); drop_tot += int((~keep).sum())
        dk2 = np.zeros_like(dk)
        kv, ku = vs[keep], us[keep]
        dk2[kv, ku] = dk[kv, ku]                              # consensus + conf gated depth
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
        img = np.ascontiguousarray(cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(img), o3d.geometry.Image(dk2),
            depth_scale=1.0, depth_trunc=DEPTH_TRUNC, convert_rgb_to_intensity=False)
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[i][0, 0], K[i][1, 1], K[i][0, 2], K[i][1, 2])
        vol.integrate(rgbd, intr, w2c[i])
log(f"integrated {len(ws)} windows in {time.time()-t0:.0f}s | "
    f"kept {kept_tot/1e6:.1f}M px, dropped {drop_tot/1e6:.1f}M ({100*drop_tot/(kept_tot+drop_tot):.0f}%)")

mesh = vol.extract_triangle_mesh(); mesh.compute_vertex_normals()
log(f"raw mesh {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")
# drop tiny floaters: keep clusters with >= 0.1% of triangles
tri_ids, n_tri, _ = mesh.cluster_connected_triangles()
tri_ids = np.asarray(tri_ids); n_tri = np.asarray(n_tri)
small = n_tri[tri_ids] < max(200, int(0.001 * len(mesh.triangles)))
mesh.remove_triangles_by_mask(small); mesh.remove_unreferenced_vertices()
log(f"after floater cull {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")

o3d.io.write_triangle_mesh(str(OUT / f"tsdf_{OUT_TAG}_o3d.ply"), mesh)
import shutil; shutil.copy(OUT / f"tsdf_{OUT_TAG}_o3d.ply", DELIVER / f"poisson/colored_mesh_{OUT_TAG}.ply")
log(f"colored_mesh_{OUT_TAG}.ply written; EXPAS-DONE")
