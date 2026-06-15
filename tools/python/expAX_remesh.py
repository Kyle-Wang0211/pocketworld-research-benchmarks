"""expAX: re-mesh the 12-window cloud with FixB vs BA depth, optional per-window
RGB-GUIDED depth denoising (guided filter, He 2010 — implemented with box
filters from base OpenCV, Apache, zero extra deps), via screened Poisson
(Open3D MIT) or DPSR (vendored MIT).

Goal: does denoising the intra-window depth scatter (the residual ~18mm floor
that BA can't touch) push the floor below 18mm WHILE keeping thin structures
(crossbars)? Guided filter smooths within RGB-flat regions, preserves depth
edges where RGB has edges -> denoise floor, keep crossbars (they have RGB edges).

Tunables (argv): MESHER(poisson|dpsr) USE_BA(0|1) OUT_TAG DENOISE(0|1) [GF_R GF_EPS RES SIG]
"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np
import cv2
from scipy.spatial import cKDTree
import open3d as o3d
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DELIVER / "poisson"; OUT.mkdir(exist_ok=True)
CONF_PCT = 40.0; STRIDE = 2; UP = 1
MESHER  = sys.argv[1] if len(sys.argv) > 1 else "poisson"
USE_BA  = int(sys.argv[2]) if len(sys.argv) > 2 else 0
OUT_TAG = sys.argv[3] if len(sys.argv) > 3 else "remesh"
DENOISE = int(sys.argv[4]) if len(sys.argv) > 4 else 0
GF_R    = int(sys.argv[5])   if len(sys.argv) > 5 else 6        # guided-filter radius (px)
GF_EPS  = float(sys.argv[6]) if len(sys.argv) > 6 else 1e-4     # edge threshold (guide in [0,1])
RES     = int(sys.argv[7])   if len(sys.argv) > 7 else 768
SIG     = float(sys.argv[8]) if len(sys.argv) > 8 else 1.0
CONF_BAR = 6.0; PAD = 0.08


def log(m): print(f"[expAX {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def guided_filter(guide, src, mask, r, eps):
    """RGB(gray)-guided edge-preserving filter of depth `src`, masked to valid."""
    k = (2 * r + 1, 2 * r + 1)
    box = lambda x: cv2.boxFilter(x, -1, k, normalize=True)
    m = mask.astype(np.float64); n = np.clip(box(m), 1e-6, None)
    mI = box(guide * m) / n; mp = box(src * m) / n
    mIp = box(guide * src * m) / n; mII = box(guide * guide * m) / n
    a = (mIp - mI * mp) / (mII - mI * mI + eps); b = mp - a * mI
    q = box(a * m) / n * guide + box(b * m) / n
    return np.where(mask, q, src)


def depth_normals(depth, K):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu + 0.5 - K[0, 2]) / K[0, 0] * depth; y = (vv + 0.5 - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1); du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    n = np.cross(du, dv); ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    n[(np.sum(n * P, -1) > 0)] *= -1
    return n


rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
sc = [r for r in rows if r["kind"] == "scales"][0]
ws = []
for w in range(len(sc["s_B"])):
    if sc["conf_medians"][w] < CONF_BAR: continue
    z = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
    ws.append((z["depth"].astype(np.float64), z["conf"].astype(np.float32),
               z["K"].astype(np.float64), w2c4(z["w2c"]), list(wdef[w]["frame_idx"]), float(sc["s_B"][w])))

BA_GRAN = "window"
if USE_BA:
    zz = np.load(EXPAC / "ba_scaleshift.npz"); A_ba, B_ba = zz["a"], zz["b"]
    BA_GRAN = str(zz["gran"]) if "gran" in zz else "window"
    if BA_GRAN == "window": assert len(A_ba) == len(ws), "window-BA count mismatch"
else:
    A_ba = np.ones(len(ws)); B_ba = np.zeros(len(ws))
log(f"{len(ws)} windows | mesher={MESHER} use_ba={USE_BA}({BA_GRAN}) denoise={DENOISE} (r={GF_R} eps={GF_EPS})")

P, N, C = [], [], []
gframe = 0
for wi, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
    n_, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for k in range(n_):
        ai, bi = (A_ba[gframe], B_ba[gframe]) if BA_GRAN == "frame" else (A_ba[wi], B_ba[wi])
        gframe += 1
        dk = ai * (depth[k] * s) + bi
        valid = (conf[k] >= fl) & (depth[k] > 1e-3)
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[k]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        if DENOISE:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
            dk = guided_filter(gray, dk, valid, GF_R, GF_EPS)
        nrm = depth_normals(dk, K[k])
        vs, us = np.where(valid); sel = (vs % STRIDE == 0) & (us % STRIDE == 0); vs, us = vs[sel], us[sel]
        if not len(vs): continue
        dd = dk[vs, us]
        x = (us + 0.5 - K[k][0, 2]) / K[k][0, 0] * dd; y = (vs + 0.5 - K[k][1, 2]) / K[k][1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)]); c2w = np.linalg.inv(w2c[k])
        P.append((c2w @ cam)[:3].T)
        nw = (c2w[:3, :3] @ nrm[vs, us].T).T
        N.append(nw / np.clip(np.linalg.norm(nw, axis=1, keepdims=True), 1e-9, None))
        C.append(img[vs, us][:, ::-1].astype(np.float64) / 255.0)
P = np.concatenate(P); N = np.concatenate(N); C = np.concatenate(C)
log(f"cloud {len(P):,} pts")

# floor thickness on the cloud (RANSAC, Y up)
low = P[P[:, UP] < np.percentile(P[:, UP], 45)]
pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(low))
for _ in range(4):
    if len(pc.points) < 500: break
    plane, inl = pc.segment_plane(0.05, 3, 200); nrm = np.array(plane[:3]); pts = np.asarray(pc.points)[inl]
    if abs(nrm[UP]) > 0.7:
        d = pts @ nrm + plane[3]
        log(f"floor thickness: 16-84% {1000*(np.percentile(d,84)-np.percentile(d,16)):.1f}mm  std {1000*d.std():.1f}mm ({len(inl)} inl)")
        break
    pc = pc.select_by_index(inl, invert=True)

if MESHER == "poisson":
    pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(P)
    pcd.normals = o3d.utility.Vector3dVector(N); pcd.colors = o3d.utility.Vector3dVector(C)
    pcd = pcd.voxel_down_sample(0.003)
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=10, linear_fit=True, n_threads=1)
    dens = np.asarray(dens); mesh.remove_vertices_by_mask(dens <= np.quantile(dens, 0.04)); mesh.compute_vertex_normals()
else:
    from dpsr_sap import DPSR
    import torch
    key = np.floor((P - P.min(0)) / 0.003).astype(np.int64)
    _, idx = np.unique(key[:, 0] * 73856093 ^ key[:, 1] * 19349663 ^ key[:, 2] * 83492791, return_index=True)
    Pd, Nd, Cd = P[idx], N[idx], C[idx]
    lo = Pd.min(0); span = (Pd.max(0) - lo).max(); Pn = (Pd - lo) / span * (1 - 2 * PAD) + PAD
    with torch.no_grad():
        phi = DPSR((RES, RES, RES), sig=SIG)(torch.from_numpy(Pn[None]).float(), torch.from_numpy(Nd[None]).float())[0].numpy()
    from skimage import measure
    verts, faces, _, _ = measure.marching_cubes(phi, level=0.0)
    Vw = (verts / RES - PAD) / (1 - 2 * PAD) * span + lo
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(Vw), o3d.utility.Vector3iVector(faces[:, ::-1]))
    dist, nn = cKDTree(Pd).query(Vw.astype(np.float32), workers=-1)
    mesh.vertex_colors = o3d.utility.Vector3dVector(Cd[nn])
    mesh.remove_vertices_by_mask(dist > max(0.012, 3.0 * span / RES)); mesh.remove_unreferenced_vertices()

tri_ids, n_tri, _ = mesh.cluster_connected_triangles()
tri_ids = np.asarray(tri_ids); n_tri = np.asarray(n_tri)
mesh.remove_triangles_by_mask(n_tri[tri_ids] < max(200, int(0.001 * len(mesh.triangles))))
mesh.remove_unreferenced_vertices(); mesh.compute_vertex_normals()
out = OUT / f"colored_mesh_{OUT_TAG}.ply"
o3d.io.write_triangle_mesh(str(out), mesh)
log(f"{out.name}: {len(mesh.vertices):,} verts; EXPAX-DONE")
