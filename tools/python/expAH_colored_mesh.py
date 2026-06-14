#!/usr/bin/env python3
"""expAH: PHOTO-colored Poisson mesh for OLD-11 / NEW-12 conf>=6 Fix-B
windows. Builds a cloud with position + TRUE normals (depth-space
cross-product, camera-oriented, world-rotated — ship method, reused
verbatim from expAG_normals_check) + REAL photo RGB, then screened
Poisson (n_threads=1 to dodge the C++ loop-close race) interpolates
the photo color onto mesh vertices.

NOTE: this is a VERTEX-COLOR mesh, not a UV-texture bake. The shipped
pipeline's texture step (xatlas UV + back-projection bake) is sharper;
vertex color on a dense mesh approximates the final colored look.
"""
import json
import sys
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
OUT = DELIVER / "poisson"
OUT.mkdir(exist_ok=True)
CONF_BAR = 6.0
CONF_PCT = 40.0
STRIDE = 2
VOXEL = 0.003
POISSON_DEPTH = 10
DENSITY_TRIM_Q = 0.04

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
frames = [r for r in man if r["jpegPath"].split("/")[-1] in azel]
z = np.load(ANCH)
anchors = fixb.AnchorSet(z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"])
ONLY = sys.argv[1] if len(sys.argv) > 1 else None


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
    P = np.stack([x, y, depth], axis=-1)
    dPdu = np.zeros_like(P); dPdv = np.zeros_like(P)
    dPdu[:, 1:-1, :] = P[:, 2:, :] - P[:, :-2, :]
    dPdv[1:-1, :, :] = P[2:, :, :] - P[:-2, :, :]
    n = np.cross(dPdu, dPdv)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    n[(np.sum(n * P, axis=-1) > 0)] *= -1
    return n


def build_cloud(windows):
    allP, allN, allC = [], [], []
    for w in windows:
        depth, conf, K, w2c, fidx, s = (w["depth"], w["conf"], w["K"], w["w2c"],
                                        w["fidx"], w["scale"])
        n_, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for k in range(n_):
            dk = depth[k] * s
            nrm = depth_normals(dk, K[k])
            m = (conf[k] >= floor) & (dk > 1e-3)
            vs, us = np.where(m)
            sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
            vs, us = vs[sel], us[sel]
            if not len(vs):
                continue
            img = cv2.imread(str(D / "capture_seq_k35_strict" / man[fidx[k]]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            cols = img[vs, us][:, ::-1].astype(np.float64) / 255.0
            Ki = K[k]
            dd = dk[vs, us].astype(np.float64)
            x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
            y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
            cam = np.stack([x, y, dd, np.ones_like(dd)])
            c2w = np.linalg.inv(w2c[k])
            allP.append((c2w @ cam)[:3].T)
            nworld = (c2w[:3, :3] @ nrm[vs, us].T).T
            ln = np.linalg.norm(nworld, axis=1, keepdims=True)
            allN.append(np.divide(nworld, ln, out=np.zeros_like(nworld), where=ln > 1e-9))
            allC.append(cols)
    return (np.concatenate(allP), np.concatenate(allN), np.concatenate(allC))


def make(tag, windows):
    P, N, C = build_cloud(windows)
    print(f"[{tag}] cloud {len(P):,} pts (stride {STRIDE})", flush=True)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(P)
    pcd.normals = o3d.utility.Vector3dVector(N)
    pcd.colors = o3d.utility.Vector3dVector(C)
    pcd = pcd.voxel_down_sample(VOXEL)
    print(f"[{tag}] after {VOXEL*1000:.0f}mm voxel: {len(pcd.points):,} pts", flush=True)
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=POISSON_DEPTH, linear_fit=True, n_threads=1)
    dens = np.asarray(dens)
    mesh.remove_vertices_by_mask(dens <= np.quantile(dens, DENSITY_TRIM_Q))
    mesh.compute_vertex_normals()
    out = OUT / f"colored_mesh_{tag}.ply"
    o3d.io.write_triangle_mesh(str(out), mesh)
    print(f"[{tag}] colored mesh: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris -> {out.name}", flush=True)


def load_old():
    old_w = []
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
        old_w.append({"depth": depth, "conf": conf, "K": K, "w2c": w2c, "fidx": fidx,
                      "scale": s if s else 1.0})
    return old_w


def load_new():
    rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    scales = [r for r in rows if r["kind"] == "scales"][0]
    new_w = []
    for w in range(len(scales["s_B"])):
        if scales["conf_medians"][w] < CONF_BAR:
            continue
        zz = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
        new_w.append({"depth": zz["depth"].astype(np.float32),
                      "conf": zz["conf"].astype(np.float32),
                      "K": zz["K"].astype(np.float64), "w2c": w2c4(zz["w2c"]),
                      "fidx": list(wdef[w]["frame_idx"]), "scale": scales["s_B"][w]})
    return new_w


if ONLY in (None, "old11"):
    make("old11", load_old())
if ONLY in (None, "new12"):
    make("new12", load_new())
if ONLY == "union23":
    make("union23", load_old() + load_new())

print("EXPAH-DONE", flush=True)
