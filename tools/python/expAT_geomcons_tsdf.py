"""expAT: per-pixel multi-view GEOMETRIC CONSISTENCY filter (ported from
COLMAP StereoFusion, new-BSD -> commercially reusable) -> Open3D TSDF.

Replaces expAS's coarse "distinct-window count in a 12mm cell" (which let
the ghost floor back in once background was restored) with COLMAP's actual
geometric-consistency test. COLMAP fusion.cc gates (verbatim):
    depth_error  = |proj_z - measured_depth| / measured_depth  < max_depth_error (1%)
    reproj_error = ||proj_pixel - pixel||                       < max_reproj_error (2px)
    normal_error = ref_normal . normal                         < cos(max_normal_error)
A pixel is kept only if >= MIN OTHER WINDOWS confirm it (own window excluded
so same-window frames can't self-certify a ghost).

We port the two strong gates (depth 1% + forward-backward reproj 2px). The
normal gate is left off in v1: it needs all 414 world-normal maps cached
(~6.7GB) for little gain on noisy DA3 normals; depth+reproj is the core MVS
consistency and is what kills the ~5cm ghost. Surviving depths -> Open3D
ScalableTSDFVolume (small trunc) -> watertight mesh -> small-cluster cull.

Why this fixes both problems at once: a ghost-floor pixel projects into a
window that sees the TRUE floor; its depth disagrees (>1%) and its forward-
backward reprojection lands far away -> fails -> dropped, even if several
misaligned windows produced it. A real thin/object/wall surface that is
cross-window consistent passes -> kept. The criterion is "reprojects
consistently", not "co-located", so restoring background no longer revives
the double floor.

Tunables (argv): VOXEL  MIN_WIN  MAX_DEPTH_ERR  MAX_REPROJ_PX  SDF_TRUNC  N_CAND  OUT_TAG
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
CONF_PCT = 40.0
VOXEL         = float(sys.argv[1]) if len(sys.argv) > 1 else 0.005
MIN_WIN       = int(sys.argv[2])   if len(sys.argv) > 2 else 2       # >= this many OTHER windows must confirm
MAX_DEPTH_ERR = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01    # COLMAP default 1%
MAX_REPROJ_PX = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0     # COLMAP default 2px
SDF_TRUNC     = float(sys.argv[5]) if len(sys.argv) > 5 else 0.010
N_CAND        = int(sys.argv[6])   if len(sys.argv) > 6 else 40      # nearest other-window frames to test
OUT_TAG       = sys.argv[7]        if len(sys.argv) > 7 else "geomcons"
STRIDE        = int(sys.argv[8])   if len(sys.argv) > 8 else 2       # 1 = dense (clean surface), 2 = fast
WIN_SET       = sys.argv[9]        if len(sys.argv) > 9 else "all"   # all | new12 (ellipsoid 40-48°) | old11 (random 20-100°)
CONF_BAR      = float(sys.argv[10]) if len(sys.argv) > 10 else 6.0   # window median-conf bar (lower = more windows -> more overlap)
USE_BA        = int(sys.argv[11]) if len(sys.argv) > 11 else 0       # 1 = feed BA(scale+shift)-aligned depth (needs WIN_SET=new12 CONF_BAR=6)
MESHER        = sys.argv[12]      if len(sys.argv) > 12 else "tsdf"  # tsdf | poisson (滤后点云 -> screened Poisson, 保细结构)
DEPTH_TRUNC = 12.0


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
MAX_REPROJ2 = MAX_REPROJ_PX * MAX_REPROJ_PX


def log(m): print(f"[expAT {time.strftime('%H:%M:%S')}] {m}", flush=True)


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
    if WIN_SET in ("all", "old11"):                       # OLD 11: random-angle windows (20-100°)
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
    if WIN_SET in ("all", "new12"):                       # NEW 12: ellipsoid windows (40-48°), higher object fidelity
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


ws = load_windows()
if USE_BA:
    zz = np.load(EXPAC / "ba_scaleshift.npz"); A_ba, B_ba = zz["a"], zz["b"]
    assert len(A_ba) == len(ws), f"BA has {len(A_ba)} windows but loaded {len(ws)} (use WIN_SET=new12 CONF_BAR=6)"
    log(f"BA(scale+shift) applied: a[{A_ba.min():.3f},{A_ba.max():.3f}] b[{B_ba.min()*1000:.0f},{B_ba.max()*1000:.0f}]mm")
else:
    A_ba = np.ones(len(ws)); B_ba = np.zeros(len(ws))
log(f"{len(ws)} windows | voxel {VOXEL*1000:.0f}mm trunc {SDF_TRUNC*1000:.0f}mm | "
    f"MIN_WIN {MIN_WIN} depth_err {MAX_DEPTH_ERR} reproj {MAX_REPROJ_PX}px N_CAND {N_CAND}")

# ---- flatten windows -> per-frame VIEWS (each = one depth map + pose) ----
views = []
for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
    n, H, W = depth.shape
    fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = (A_ba[wid] * (depth[i] * s) + B_ba[wid]).astype(np.float32)   # FixB (a=1,b=0) or BA
        Ki = K[i].astype(np.float64); w2ci = w2c[i].astype(np.float64)
        Rwc = w2ci[:3, :3]; twc = w2ci[:3, 3]
        C = -Rwc.T @ twc                                   # camera center (world)
        # reference pixels = conf-gated, strided
        m = (conf[i] >= fl) & (dk > 1e-3)
        vs, us = np.where(m); sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
        vs, us = vs[sel], us[sel]
        dd = dk[vs, us].astype(np.float64)
        x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
        y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        X = (np.linalg.inv(w2ci) @ cam)[:3].T              # (Nref,3) world points
        views.append(dict(dk=dk, K=Ki, w2c=w2ci, invw2c=np.linalg.inv(w2ci),
                          Rwc=Rwc, twc=twc, C=C, wid=wid, fidx=fidx[i], H=H, W=W,
                          vs=vs, us=us, X=X))
NV = len(views)
centers = np.array([v["C"] for v in views])                # (NV,3)
wids = np.array([v["wid"] for v in views])
log(f"{NV} frames flattened, {len(ws)} windows")

# ---- per-frame: count distinct OTHER windows passing depth+reproj gates ----
t0 = time.time()
for ri, rv in enumerate(views):
    X = rv["X"]; Nref = len(X)
    if Nref == 0:
        rv["keep"] = np.zeros(0, bool); continue
    col = rv["us"].astype(np.float64); row = rv["vs"].astype(np.float64)
    Rwc_r, twc_r, Kr = rv["Rwc"], rv["twc"], rv["K"]
    support = np.zeros((Nref, len(ws)), bool)
    # nearest N_CAND frames from OTHER windows
    d2 = np.sum((centers - rv["C"]) ** 2, axis=1)
    order = np.argsort(d2)
    cand = [j for j in order if wids[j] != rv["wid"]][:N_CAND]
    for j in cand:
        cv = views[j]; Wj, Hj, Kj = cv["W"], cv["H"], cv["K"]
        cam = (cv["Rwc"] @ X.T).T + cv["twc"]              # ref pts in cand cam
        z2 = cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u2 = Kj[0, 0] * cam[:, 0] / z2 + Kj[0, 2]
            v2 = Kj[1, 1] * cam[:, 1] / z2 + Kj[1, 2]
        ui = np.round(u2).astype(int); vi = np.round(v2).astype(int)
        inb = (z2 > 1e-3) & (ui >= 0) & (ui < Wj) & (vi >= 0) & (vi < Hj)
        if not inb.any(): continue
        dj = np.zeros(Nref); uic = np.clip(ui, 0, Wj - 1); vic = np.clip(vi, 0, Hj - 1)
        dj[inb] = cv["dk"][vic[inb], uic[inb]]
        # gate 1: relative depth error (COLMAP)
        depth_ok = inb & (dj > 1e-3) & (np.abs(z2 - dj) / np.maximum(dj, 1e-9) < MAX_DEPTH_ERR)
        if not depth_ok.any(): continue
        # gate 2: forward-backward reprojection. backproject (ui,vi,dj) in cand -> world -> reproject into ref
        xj = (ui + 0.5 - Kj[0, 2]) / Kj[0, 0] * dj
        yj = (vi + 0.5 - Kj[1, 2]) / Kj[1, 1] * dj
        camp = np.stack([xj, yj, dj, np.ones_like(dj)])
        Xp = (cv["invw2c"] @ camp)[:3].T                   # world surface cand actually sees
        cr = (Rwc_r @ Xp.T).T + twc_r                      # into ref cam
        zr = cr[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            ur = Kr[0, 0] * cr[:, 0] / zr + Kr[0, 2]
            vr = Kr[1, 1] * cr[:, 1] / zr + Kr[1, 2]
        reproj_ok = (zr > 1e-3) & ((ur - col) ** 2 + (vr - row) ** 2 < MAX_REPROJ2)
        ok = depth_ok & reproj_ok
        support[ok, cv["wid"]] = True
    rv["keep"] = support.sum(axis=1) >= MIN_WIN
    if (ri + 1) % 60 == 0:
        kr = np.mean([v["keep"].mean() for v in views[:ri + 1] if len(v["keep"])])
        log(f"  consistency {ri+1}/{NV} frames, running keep≈{100*kr:.0f}%")
kept = sum(int(v["keep"].sum()) for v in views); tot = sum(len(v["X"]) for v in views)
log(f"geom-consistency done in {time.time()-t0:.0f}s | kept {kept/1e6:.1f}M / {tot/1e6:.1f}M px "
    f"({100*kept/max(tot,1):.0f}%)")

# ---- surviving (consistency-kept) depths -> TSDF or screened Poisson ----
if MESHER == "poisson":                         # 滤后点云 -> screened Poisson (保细结构,同 button3 但带过滤)
    P, N, C = [], [], []
    for rv in views:
        if not len(rv["keep"]) or not rv["keep"].any(): continue
        kv, ku = rv["vs"][rv["keep"]], rv["us"][rv["keep"]]
        dk = rv["dk"]; Ki = rv["K"]
        nrm = depth_normals(dk.astype(np.float64), Ki)
        dd = dk[kv, ku].astype(np.float64)
        x = (ku + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd; y = (kv + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)]); c2w = rv["invw2c"]
        P.append((c2w @ cam)[:3].T)
        nw = (c2w[:3, :3] @ nrm[kv, ku].T).T
        N.append(nw / np.clip(np.linalg.norm(nw, axis=1, keepdims=True), 1e-9, None))
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[rv["fidx"]]["jpegPath"]))
        img = cv2.resize(img, (rv["W"], rv["H"]), interpolation=cv2.INTER_AREA)
        C.append(img[kv, ku][:, ::-1].astype(np.float64) / 255.0)
    P = np.concatenate(P); N = np.concatenate(N); C = np.concatenate(C)
    log(f"kept cloud {len(P):,} pts -> screened Poisson")
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(P); pcd.normals = o3d.utility.Vector3dVector(N)
    pcd.colors = o3d.utility.Vector3dVector(C); pcd = pcd.voxel_down_sample(0.003)
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=10, linear_fit=True, n_threads=1)
    dens = np.asarray(dens); mesh.remove_vertices_by_mask(dens <= np.quantile(dens, 0.04))
    mesh.compute_vertex_normals()
else:
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for rv in views:
        if not len(rv["keep"]) or not rv["keep"].any():
            continue
        H, W = rv["H"], rv["W"]
        dk2 = np.zeros((H, W), np.float32)
        kv, ku = rv["vs"][rv["keep"]], rv["us"][rv["keep"]]
        dk2[kv, ku] = rv["dk"][kv, ku]
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[rv["fidx"]]["jpegPath"]))
        img = np.ascontiguousarray(cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(img), o3d.geometry.Image(dk2),
            depth_scale=1.0, depth_trunc=DEPTH_TRUNC, convert_rgb_to_intensity=False)
        Ki = rv["K"]
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, Ki[0, 0], Ki[1, 1], Ki[0, 2], Ki[1, 2])
        vol.integrate(rgbd, intr, rv["w2c"])
    mesh = vol.extract_triangle_mesh(); mesh.compute_vertex_normals()
log(f"raw mesh {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")
tri_ids, n_tri, _ = mesh.cluster_connected_triangles()
tri_ids = np.asarray(tri_ids); n_tri = np.asarray(n_tri)
small = n_tri[tri_ids] < max(200, int(0.001 * len(mesh.triangles)))
mesh.remove_triangles_by_mask(small); mesh.remove_unreferenced_vertices()
log(f"after floater cull {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")

o3d.io.write_triangle_mesh(str(OUT / f"tsdf_{OUT_TAG}_o3d.ply"), mesh)
import shutil; shutil.copy(OUT / f"tsdf_{OUT_TAG}_o3d.ply", DELIVER / f"poisson/colored_mesh_{OUT_TAG}.ply")
log(f"colored_mesh_{OUT_TAG}.ply written; EXPAT-DONE")
