#!/usr/bin/env python3
# [2026-09-24] VGGT depth -> the same KIRI/GauStudio TSDF step as out/kiri_v0.01 (extract_mesh.py @132d749d :86/:115/:145/:146).
# VGGT's own cameras and depth are kept together (official: unproject depth with the predicted cameras); one global
# similarity (Umeyama on the 132 camera centres) maps VGGT's frame onto ours, so the 1 cm voxel means the same thing as
# for the MVS-depth mesh and the result overlays mesh A in the comparison page.
import sys, json, time
import numpy as np, vdbfusion, trimesh
t0 = time.time()
z = np.load("/root/vggt_eval/vggt_pred.npz")
E = z["extrinsic"]; P = z["points"]; keep = z["keep"]; order = z["order"]
Cv = np.stack([-E[i, :3, :3].T @ E[i, :3, 3] for i in range(len(E))])
Co, Ro = [], []
for v in order:
    e = np.load(f"/root/tsdf_improve/four/cache/{int(v):08d}.npz")["extr"]; Ro.append(e[:3, :3]); Co.append(-e[:3, :3].T @ e[:3, 3])
Co = np.array(Co)
def umeyama(X, Y):
    mx, my = X.mean(0), Y.mean(0); Xc, Yc = X - mx, Y - my
    U, S, Vt = np.linalg.svd(Yc.T @ Xc / len(X)); D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt; s = np.trace(np.diag(S) @ D) / (Xc ** 2).sum(1).mean(); return s, R, my - s * R @ mx
s, R, T = umeyama(Cv, Co)
res = np.linalg.norm((s * (R @ Cv.T)).T + T - Co, axis=1)
ext = np.ptp(Co, 0).max()
ang = [np.degrees(np.arccos(np.clip((np.trace(Ro[i] @ (E[i, :3, :3] @ R.T).T) - 1) / 2, -1, 1))) for i in range(len(E))]
al = {"scale": s, "centre_res_mm_median": 1000 * float(np.median(res)), "centre_res_mm_max": 1000 * float(res.max()),
      "camera_path_extent_m": float(ext), "rot_res_deg_median": float(np.median(ang)), "rot_res_deg_max": float(np.max(ang))}
print("alignment VGGT->ours:", json.dumps(al), flush=True)
vdb_volume = vdbfusion.VDBVolume(voxel_size=0.01, sdf_trunc=0.04, space_carving=False)
npts = 0
for i in range(len(E)):
    Xw = P[i][keep[i]].astype(np.float64)
    Xw = (s * (R @ Xw.T)).T + T
    c = s * R @ Cv[i] + T
    vdb_volume.integrate(np.ascontiguousarray(Xw), extrinsic=c)
    npts += len(Xw)
print(f"integrated VGGT points {npts:,}  {time.time()-t0:.0f}s", flush=True)
vertices, faces = vdb_volume.extract_triangle_mesh(min_weight=5)
geo_mesh = trimesh.Trimesh(vertices, faces)
geo_mesh.export("/root/tsdf_improve/kiri/out/vggt_v0.01_t0.04_w5.ply")
json.dump(al, open("/root/tsdf_improve/kiri/out/vggt_alignment.json", "w"), indent=1)
print(f"mesh {len(geo_mesh.vertices):,} v / {len(geo_mesh.faces):,} f  {time.time()-t0:.0f}s")
