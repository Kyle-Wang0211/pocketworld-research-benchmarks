"""expAV: DPSR (Shape-As-Points, MIT) on the 12-window oriented cloud,
to compare against the screened-Poisson new12 mesh (expAH) for the
"smooth + geometrically correct" goal.

Same input cloud as expAH (12 conf>=6 ellipsoid windows, FixB-scaled,
depth-normal + photo RGB). Geometry via vendored DPSR (FFT Poisson);
color transferred from the cloud by nearest neighbour. Output PLY sits
next to colored_mesh_new12.ply so a side-by-side viewer can A/B them.

Tunables (argv): RES  SIG  VOXEL  CONF_BAR  OUT_TAG
"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np
import cv2
from scipy.spatial import cKDTree
from skimage import measure
warnings.filterwarnings("ignore")
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb
from dpsr_sap import DPSR

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DELIVER / "poisson"; OUT.mkdir(exist_ok=True)
CONF_PCT = 40.0
STRIDE = 2
RES      = int(sys.argv[1])   if len(sys.argv) > 1 else 384
SIG      = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
VOXEL    = float(sys.argv[3]) if len(sys.argv) > 3 else 0.004
CONF_BAR = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0
OUT_TAG  = sys.argv[5]        if len(sys.argv) > 5 else "dpsr12"
PAD = 0.08


def log(m): print(f"[expAV {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def depth_normals(depth, K):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu + 0.5 - K[0, 2]) / K[0, 0] * depth
    y = (vv + 0.5 - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    n = np.cross(du, dv); ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    n[(np.sum(n * P, -1) > 0)] *= -1
    return n


def load_new12():
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    sc = [r for r in rows if r["kind"] == "scales"][0]
    ws = []
    for w in range(len(sc["s_B"])):
        if sc["conf_medians"][w] < CONF_BAR: continue
        z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        ws.append((z["depth"].astype(np.float32), z["conf"].astype(np.float32),
                   z["K"].astype(np.float64), w2c4(z["w2c"]), list(wdef[w]["frame_idx"]),
                   sc["s_B"][w]))
    return ws


ws = load_new12()
log(f"{len(ws)} windows (conf>={CONF_BAR}) | DPSR res {RES} sig {SIG} voxel {VOXEL*1000:.0f}mm")

# build oriented colored cloud (same recipe as expAH)
P, N, C = [], [], []
for depth, conf, K, w2c, fidx, s in ws:
    n_, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for k in range(n_):
        dk = depth[k] * s
        nrm = depth_normals(dk, K[k])
        m = (conf[k] >= fl) & (dk > 1e-3)
        vs, us = np.where(m); sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs): continue
        dd = dk[vs, us].astype(np.float64)
        x = (us + 0.5 - K[k][0, 2]) / K[k][0, 0] * dd
        y = (vs + 0.5 - K[k][1, 2]) / K[k][1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        c2w = np.linalg.inv(w2c[k])
        P.append((c2w @ cam)[:3].T)
        nw = (c2w[:3, :3] @ nrm[vs, us].T).T
        nw = nw / np.clip(np.linalg.norm(nw, axis=1, keepdims=True), 1e-9, None)
        N.append(nw)
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[k]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        C.append(img[vs, us][:, ::-1].astype(np.float64) / 255.0)
P = np.concatenate(P); N = np.concatenate(N); C = np.concatenate(C)
log(f"cloud {len(P):,} pts")

# voxel downsample (keep one point per voxel; average normal)
key = np.floor((P - P.min(0)) / VOXEL).astype(np.int64)
_, idx = np.unique(key[:, 0] * 73856093 ^ key[:, 1] * 19349663 ^ key[:, 2] * 83492791,
                   return_index=True)
P, N, C = P[idx], N[idx], C[idx]
log(f"after {VOXEL*1000:.0f}mm downsample: {len(P):,} pts")

# normalize into [PAD, 1-PAD] cube (aspect preserved)
lo = P.min(0); span = (P.max(0) - lo).max()
Pn = (P - lo) / span * (1 - 2 * PAD) + PAD
V = torch.from_numpy(Pn[None]).float()
Nt = torch.from_numpy(N[None]).float()

log("running DPSR FFT Poisson solve …")
t0 = time.time()
dpsr = DPSR(res=(RES, RES, RES), sig=SIG)
with torch.no_grad():
    phi = dpsr(V, Nt)[0].numpy()
log(f"DPSR solved in {time.time()-t0:.0f}s | phi range [{phi.min():.2f},{phi.max():.2f}]")

verts, faces, _, _ = measure.marching_cubes(phi, level=0.0)
vc = verts / RES                                  # grid index -> [0,1)
Vw = (vc - PAD) / (1 - 2 * PAD) * span + lo        # -> world
log(f"raw mesh {len(Vw):,} verts {len(faces):,} faces")

import open3d as o3d
mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(Vw),
                                 o3d.utility.Vector3iVector(faces[:, ::-1]))
# DPSR on an OPEN scene wraps a balloon shell far from the points -> trim by
# distance to the input cloud (the screened-Poisson analogue is density trim)
dist, nn = cKDTree(P).query(Vw.astype(np.float32), workers=-1)
mesh.vertex_colors = o3d.utility.Vector3dVector(C[nn])
TRIM = max(0.012, 3.0 * span / RES)
mesh.remove_vertices_by_mask(dist > TRIM)
mesh.remove_unreferenced_vertices()
log(f"after {TRIM*1000:.0f}mm distance-trim: {len(mesh.vertices):,} verts")
# drop tiny floaters
tri_ids, n_tri, _ = mesh.cluster_connected_triangles()
tri_ids = np.asarray(tri_ids); n_tri = np.asarray(n_tri)
mesh.remove_triangles_by_mask(n_tri[tri_ids] < max(200, int(0.001 * len(mesh.triangles))))
mesh.remove_unreferenced_vertices(); mesh.compute_vertex_normals()
out = OUT / f"colored_mesh_{OUT_TAG}.ply"
o3d.io.write_triangle_mesh(str(out), mesh)
log(f"{out.name}: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris; EXPAV-DONE")
