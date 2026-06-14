"""expAU: B-light = VISIBILITY / free-space-violation filter -> Open3D TSDF.

The problem with expAT (confirmation-count): "keep iff >= N windows CONFIRM"
puts the real-but-weakly-supported chair and the fake weakly-supported ghost
on the SAME axis -- any threshold that cleans the floor ghost also eats the
chair (Jancosek's weakly-supported-surface problem). depth_err and sdf_trunc
are both just positions on that one axis.

B-light changes the AXIS: drop a point only if it is CONTRADICTED by free
space, not merely unconfirmed (Merrell 2007 free-space violation, the cheap
local form of Jancosek 2014 -- reimplemented from the papers, no OpenMVS code,
so license stays permissive).

  For ref point X, project into the N_CAND nearest OTHER-window frames.
  A frame j VIOLATES X if it measures a surface BEHIND X along that ray:
      d_j(proj) > z_X + MARGIN          (j saw empty space where X sits)
  X is DROPPED iff >= VIOL_MIN distinct windows violate it.
  Occlusion (d_j < z_X) and mere non-coverage are NOT violations -> kept.

Why this decouples the two: the ghost floor sits in the free space of the
many windows that see the TRUE floor -> many violations -> dropped, regardless
of how many windows produced it. The chair is never seen as free space by
anyone (it really occludes) -> 0-1 violations -> kept, regardless of how few
windows confirm it. Floor cleaning no longer costs chair completeness.

Caveat (occlusion boundary): a grazing window that sees floor *behind* a thin
chair leg can false-violate it; VIOL_MIN>=2 + a depth MARGIN absorb most of it
(robust global handling = OpenMVS graph-cut, which we are NOT copying).

Tunables (argv): VOXEL  VIOL_MIN  MARGIN_M  SDF_TRUNC  N_CAND  OUT_TAG  STRIDE
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
VOXEL     = float(sys.argv[1]) if len(sys.argv) > 1 else 0.005
VIOL_MIN  = int(sys.argv[2])   if len(sys.argv) > 2 else 2        # >= this many windows must contradict to drop
MARGIN_M  = float(sys.argv[3]) if len(sys.argv) > 3 else 0.03     # surface must be >3cm BEHIND X to count (>ghost noise, <chair scale)
SDF_TRUNC = float(sys.argv[4]) if len(sys.argv) > 4 else 0.018
N_CAND    = int(sys.argv[5])   if len(sys.argv) > 5 else 40
OUT_TAG   = sys.argv[6]        if len(sys.argv) > 6 else "visib"
STRIDE    = int(sys.argv[7])   if len(sys.argv) > 7 else 1
DEPTH_TRUNC = 12.0


def log(m): print(f"[expAU {time.strftime('%H:%M:%S')}] {m}", flush=True)


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


ws = load_windows()
log(f"{len(ws)} windows | voxel {VOXEL*1000:.0f}mm trunc {SDF_TRUNC*1000:.0f}mm | "
    f"VIOL_MIN {VIOL_MIN} margin {MARGIN_M*1000:.0f}mm N_CAND {N_CAND} stride {STRIDE}")

views = []
for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
    n, H, W = depth.shape
    fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = (depth[i] * s).astype(np.float32)
        Ki = K[i].astype(np.float64); w2ci = w2c[i].astype(np.float64)
        Rwc = w2ci[:3, :3]; twc = w2ci[:3, 3]; C = -Rwc.T @ twc
        m = (conf[i] >= fl) & (dk > 1e-3)
        vs, us = np.where(m); sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
        vs, us = vs[sel], us[sel]
        dd = dk[vs, us].astype(np.float64)
        x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
        y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        X = (np.linalg.inv(w2ci) @ cam)[:3].T
        views.append(dict(dk=dk, K=Ki, w2c=w2ci, Rwc=Rwc, twc=twc, C=C,
                          wid=wid, fidx=fidx[i], H=H, W=W, vs=vs, us=us, X=X))
NV = len(views)
centers = np.array([v["C"] for v in views]); wids = np.array([v["wid"] for v in views])
log(f"{NV} frames flattened")

# ---- per pixel: count distinct OTHER windows that VIOLATE (see free space behind X) ----
t0 = time.time()
for ri, rv in enumerate(views):
    X = rv["X"]; Nref = len(X)
    if Nref == 0:
        rv["keep"] = np.zeros(0, bool); continue
    viol = np.zeros((Nref, len(ws)), bool)
    d2 = np.sum((centers - rv["C"]) ** 2, axis=1)
    cand = [j for j in np.argsort(d2) if wids[j] != rv["wid"]][:N_CAND]
    for j in cand:
        cv = views[j]; Wj, Hj, Kj = cv["W"], cv["H"], cv["K"]
        cam = (cv["Rwc"] @ X.T).T + cv["twc"]; z2 = cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u2 = Kj[0, 0] * cam[:, 0] / z2 + Kj[0, 2]
            v2 = Kj[1, 1] * cam[:, 1] / z2 + Kj[1, 2]
        ui = np.round(u2).astype(int); vi = np.round(v2).astype(int)
        inb = (z2 > 1e-3) & (ui >= 0) & (ui < Wj) & (vi >= 0) & (vi < Hj)
        if not inb.any(): continue
        dj = np.zeros(Nref); dj[inb] = cv["dk"][np.clip(vi, 0, Hj - 1)[inb], np.clip(ui, 0, Wj - 1)[inb]]
        # free-space violation: cand sees a real surface BEHIND X by > margin
        violates = inb & (dj > 1e-3) & (dj - z2 > MARGIN_M)
        viol[violates, cv["wid"]] = True
    rv["keep"] = viol.sum(axis=1) < VIOL_MIN
    if (ri + 1) % 120 == 0:
        kr = np.mean([v["keep"].mean() for v in views[:ri + 1] if len(v["keep"])])
        log(f"  visibility {ri+1}/{NV}, running keep≈{100*kr:.0f}%")
kept = sum(int(v["keep"].sum()) for v in views); tot = sum(len(v["X"]) for v in views)
log(f"visibility done in {time.time()-t0:.0f}s | kept {kept/1e6:.1f}M / {tot/1e6:.1f}M ({100*kept/max(tot,1):.0f}%)")

# ---- surviving depths -> Open3D TSDF ----
vol = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
for rv in views:
    if not len(rv["keep"]) or not rv["keep"].any(): continue
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
log(f"raw mesh {len(mesh.vertices):,} verts")
tri_ids, n_tri, _ = mesh.cluster_connected_triangles()
tri_ids = np.asarray(tri_ids); n_tri = np.asarray(n_tri)
small = n_tri[tri_ids] < max(200, int(0.001 * len(mesh.triangles)))
mesh.remove_triangles_by_mask(small); mesh.remove_unreferenced_vertices()
log(f"after floater cull {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris")
o3d.io.write_triangle_mesh(str(OUT / f"tsdf_{OUT_TAG}_o3d.ply"), mesh)
import shutil; shutil.copy(OUT / f"tsdf_{OUT_TAG}_o3d.ply", DELIVER / f"poisson/colored_mesh_{OUT_TAG}.ply")
log(f"colored_mesh_{OUT_TAG}.ply written; EXPAU-DONE")
