"""expAR: CONSENSUS-weighted TSDF (= expAP + 跨窗共识软衰减) at trunc24.

Problem (user, 2026-06-14): big sdf_trunc collapses ghost layers but a
global low-pass also grinds off real geometric detail; hard consistency
filter (expAL) removes ghosts but leaves HAIRY boundaries (binary delete
confuses "windows disagree=ghost" with "few windows see it=true edge" ->
density cliff -> marching-cubes spikes).

Fix (this file): keep trunc SMALL (24mm) so the true surface and the ghost
layer stay SEPARATE voxels (detail preserved, not averaged). Then remove
the ghost NOT by deleting points but by a per-voxel CONSENSUS soft-fade:

  support(voxel) = # distinct windows whose surface points land within
                   TAU_CONS of the voxel.
  true floor/cabinet face -> seen by MANY windows  -> support high -> kept crisp
  ghost layer           -> seen by FEW (misaligned) -> support low  -> faded to empty
  m = 1 - FADE*(1 - sigmoid(K*(support - S0)))          (soft, never a hard cut)
  val_faded = val*m + (+1 empty)*(1-m)                   (smooth fade -> no hair)

Per-observation weight is unchanged from expAP: conf²(=1/σ² MLE) × max(0,n·v).
Surface = global volumetric marching-cubes on the faded TSDF field (watertight,
no hairy boundary — same no-hair property a weighted DPSR/SAP solve would give;
true DPSR needs pytorch3d which isn't installed here).

Tunables (argv): VOXEL S0 K FADE TAU_CONS
"""
import json, sys, time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import cv2
from skimage import measure

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
VOXEL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.006
TRUNC = 0.024                                   # ★ small trunc -> keep detail, layers stay separate
SAMPLE_STRIDE = 2
NV_FLOOR = 0.1
# consensus soft-fade knobs
SUPPORT_S0   = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0    # window-count midpoint
SUPPORT_K    = float(sys.argv[3]) if len(sys.argv) > 3 else 1.3    # softness slope
SUPPORT_FADE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8    # 0=pure expAP, 1=full fade
TAU_CONS     = float(sys.argv[5]) if len(sys.argv) > 5 else 0.012  # agreement radius (2 voxels)


def log(m): print(f"[expAR {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


def depth_normals_cam(depth, K):
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


ws = load_windows(); log(f"{len(ws)} windows, trunc {TRUNC*1000:.0f}mm, "
                        f"S0={SUPPORT_S0} K={SUPPORT_K} fade={SUPPORT_FADE} tau={TAU_CONS*1000:.0f}mm")

# ---- photo-colored point cloud (bbox + active mask + color + WINDOW-ID tag) ----
PC, CC, WID = [], [], []
for wid, (depth, conf, K, w2c, fidx, s) in enumerate(ws):
    n, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = depth[i] * s; m = (conf[i] >= fl) & (dk > 1e-3)
        vs, us = np.where(m); sel = (vs % SAMPLE_STRIDE == 0) & (us % SAMPLE_STRIDE == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs): continue
        dd = dk[vs, us].astype(np.float64)
        x = (us + 0.5 - K[i][0, 2]) / K[i][0, 0] * dd
        y = (vs + 0.5 - K[i][1, 2]) / K[i][1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        PC.append((np.linalg.inv(w2c[i]) @ cam)[:3].T.astype(np.float32))
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[i]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        CC.append(img[vs, us][:, ::-1])
        WID.append(np.full(len(vs), wid, np.int32))
PC = np.concatenate(PC); CC = np.concatenate(CC); WID = np.concatenate(WID)
log(f"point cloud {len(PC):,} pts, {len(ws)} window ids")
lo = np.percentile(PC, 0.5, axis=0) - 3 * VOXEL
hi = np.percentile(PC, 99.5, axis=0) + 3 * VOXEL
dims = np.ceil((hi - lo) / VOXEL).astype(int)
log(f"grid {dims} = {np.prod(dims)/1e6:.0f}M voxels, bbox {np.round(hi-lo,2)}")

# ---- active voxel mask: voxels near the cloud ----
vidx = np.floor((PC - lo) / VOXEL).astype(np.int32)
vidx = np.clip(vidx, 0, dims - 1)
active = np.zeros(tuple(dims), bool)
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        for dz in (-1, 0, 1):
            a = np.clip(vidx + [dx, dy, dz], 0, dims - 1)
            active[a[:, 0], a[:, 1], a[:, 2]] = True
ai = np.argwhere(active)
centers = lo + (ai + 0.5) * VOXEL
log(f"active voxels {len(ai):,} ({100*len(ai)/np.prod(dims):.1f}%)")

# ---- per-voxel CONSENSUS: # distinct windows with a surface point within TAU_CONS ----
dimsC = (np.ceil((hi - lo) / TAU_CONS).astype(np.int64) + 2)
cellP = np.clip(np.floor((PC - lo) / TAU_CONS).astype(np.int64), 0, dimsC - 1)
linP = (cellP[:, 0] * dimsC[1] + cellP[:, 1]) * dimsC[2] + cellP[:, 2]
# distinct (cell, window) pairs -> count distinct windows per cell
pair = np.unique(linP * 32 + WID.astype(np.int64))           # <32 windows -> 5-bit tag
cell_of_pair = pair // 32
uc, cnt = np.unique(cell_of_pair, return_counts=True)        # uc sorted, cnt = #distinct win
cellV = np.clip(np.floor((centers - lo) / TAU_CONS).astype(np.int64), 0, dimsC - 1)
linV = (cellV[:, 0] * dimsC[1] + cellV[:, 1]) * dimsC[2] + cellV[:, 2]
pos = np.clip(np.searchsorted(uc, linV), 0, len(uc) - 1)
support = np.where(uc[pos] == linV, cnt[pos], 0).astype(np.float64)
m_soft = 1.0 / (1.0 + np.exp(-SUPPORT_K * (support - SUPPORT_S0)))
m_fade = 1.0 - SUPPORT_FADE * (1.0 - m_soft)                 # in [1-FADE, 1]
log(f"support: median {np.median(support):.0f} windows, "
    f"{100*np.mean(support<=1):.0f}% voxels <=1 window (ghost/edge candidates)")

# ---- weighted TSDF integrate (conf² × n·v), identical to expAP ----
tsum = np.zeros(len(ai), np.float64)
wsum = np.zeros(len(ai), np.float64)
t0 = time.time()
for depth, conf, K, w2c, fidx, s in ws:
    n, H, W = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for i in range(n):
        dk = (depth[i] * s)
        nrm = depth_normals_cam(dk, K[i])
        Rt = w2c[i]
        cam = (Rt[:3, :3] @ centers.T + Rt[:3, 3:4]).T
        z = cam[:, 2]
        front = z > 1e-3
        u = cam[:, 0] / np.where(z == 0, 1, z) * K[i][0, 0] + K[i][0, 2]
        v = cam[:, 1] / np.where(z == 0, 1, z) * K[i][1, 1] + K[i][1, 2]
        ui = np.round(u).astype(int); vi = np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any(): continue
        idx = np.where(ok)[0]
        du = dk[vi[idx], ui[idx]]; dc = conf[i][vi[idx], ui[idx]]
        good = (du > 1e-3) & (dc >= fl)
        idx = idx[good]; du = du[good]; dc = dc[good]
        if not len(idx): continue
        sdf = du - z[idx]
        band = np.abs(sdf) < TRUNC
        idx = idx[band]; sdf = sdf[band]; dc = dc[band]
        if not len(idx): continue
        nc = nrm[vi[idx], ui[idx]]
        vray = cam[idx] / np.linalg.norm(cam[idx], axis=1, keepdims=True)
        nv = np.clip(-np.sum(nc * vray, 1), 0, 1)
        wpix = (dc ** 2) * np.maximum(nv, NV_FLOOR)
        tval = np.clip(sdf / TRUNC, -1, 1)
        np.add.at(tsum, idx, wpix * tval)
        np.add.at(wsum, idx, wpix)
log(f"integrated weighted in {time.time()-t0:.0f}s")

# ---- fold consensus soft-fade, then global volumetric marching cubes ----
val = np.where(wsum > 0, tsum / np.maximum(wsum, 1e-9), 1.0)
val = val * m_fade + 1.0 * (1.0 - m_fade)        # low support -> pushed to +1 (empty), smooth
vol = np.ones(tuple(dims), np.float32)
vol[ai[:, 0], ai[:, 1], ai[:, 2]] = val.astype(np.float32)
try:
    verts, faces, normals, _ = measure.marching_cubes(vol, level=0.0)
except Exception as e:
    log(f"MC fail: {e}"); sys.exit(1)
Vw = lo + verts * VOXEL
log(f"mesh {len(Vw):,} verts {len(faces):,} faces")

# color transfer from point cloud
tree = cKDTree(PC)
_, nn = tree.query(Vw.astype(np.float32), workers=-1)
Vcol = CC[nn]


def write_mesh_ply(path, V, F, C):
    fh = open(path, "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(V)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              f"element face {len(F)}\nproperty list uchar int vertex_indices\nend_header\n").encode())
    vrec = np.empty(len(V), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
    vrec["xyz"] = V; vrec["rgb"] = C; fh.write(vrec.tobytes())
    frec = np.empty(len(F), dtype=[("c", np.uint8), ("i", np.int32, 3)])
    frec["c"] = 3; frec["i"] = F[:, ::-1]; fh.write(frec.tobytes())
    fh.close()


write_mesh_ply(OUT / "tsdf_consensus_mesh.ply", Vw.astype(np.float32), faces, Vcol)
import shutil; shutil.copy(OUT / "tsdf_consensus_mesh.ply", DELIVER / "poisson/colored_mesh_consensus.ply")
log(f"colored_mesh_consensus.ply: {len(Vw):,} verts")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
xmid = np.median(Vw[:, 0]); slab = Vw[np.abs(Vw[:, 0] - xmid) < 0.03]
fig, ax = plt.subplots(figsize=(9, 8))
ax.scatter(slab[:, 2], slab[:, 1], s=0.6, c="#3a3", alpha=0.5, linewidths=0)
ax.set_title(f"consensus-weighted TSDF trunc{TRUNC*1000:.0f}mm "
             f"S0={SUPPORT_S0} fade={SUPPORT_FADE}  slab|x-{xmid:.2f}|<3cm"); ax.set_aspect("equal")
fig.savefig(OUT / "consensus_tsdf_slab.png", dpi=110)
log("saved consensus_tsdf_slab.png; EXPAR-DONE")
