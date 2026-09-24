#!/usr/bin/env python3
# MapAnything depth (fed our poses) -> the same KIRI/GauStudio 1 cm TSDF step (extract_mesh.py @132d749d :86/:115/:145/:146).
# Self-check first: with our poses as input, the output camera centres must equal ours up to one global similarity.
import json, time, numpy as np, vdbfusion, trimesh
t0 = time.time()
z = np.load("/root/mapany_eval/mapany_pred.npz"); names = z["names"]; poses = z["poses"]; pts = z["pts"]; mask = z["mask"]
Co, Ro = [], []
for n in names:
    e = np.load(f"/root/tsdf_improve/four/cache/{int(str(n)[:8]):08d}.npz")["extr"]; Ro.append(e[:3, :3]); Co.append(-e[:3, :3].T @ e[:3, 3])
Co = np.array(Co); Cm = poses[:, :3, 3]
def umeyama(X, Y):
    mx, my = X.mean(0), Y.mean(0); Xc, Yc = X - mx, Y - my
    U, S, Vt = np.linalg.svd(Yc.T @ Xc / len(X)); D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt; s = np.trace(np.diag(S) @ D) / (Xc ** 2).sum(1).mean(); return s, R, my - s * R @ mx
s, R, T = umeyama(Cm, Co)
res = np.linalg.norm((s * (R @ Cm.T)).T + T - Co, axis=1)
ang = [np.degrees(np.arccos(np.clip((np.trace(Ro[i].T @ (R @ poses[i, :3, :3]).T) - 1) / 2, -1, 1))) for i in range(len(names))]
al = {"scale": float(s), "rot_of_frame_deg": float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))),
      "centre_res_mm_median": 1000 * float(np.median(res)), "centre_res_mm_max": 1000 * float(res.max()),
      "cam_rot_res_deg_median": float(np.median(ang)), "cam_rot_res_deg_max": float(np.max(ang))}
print("output cameras vs our input cameras:", json.dumps(al), flush=True)
vdb_volume = vdbfusion.VDBVolume(voxel_size=0.01, sdf_trunc=0.04, space_carving=False)
npts = 0
for i in range(len(names)):
    X = pts[i][mask[i]].astype(np.float64); X = (s * (R @ X.T)).T + T
    vdb_volume.integrate(np.ascontiguousarray(X), extrinsic=s * R @ Cm[i] + T); npts += len(X)
print(f"integrated {npts:,} points {time.time()-t0:.0f}s", flush=True)
vertices, faces = vdb_volume.extract_triangle_mesh(min_weight=5)
geo_mesh = trimesh.Trimesh(vertices, faces); geo_mesh.export("/root/tsdf_improve/kiri/out/mapany_v0.01_t0.04_w5.ply")
json.dump(al, open("/root/tsdf_improve/kiri/out/mapany_alignment.json", "w"), indent=1)
print(f"mesh {len(geo_mesh.vertices):,} v / {len(geo_mesh.faces):,} f  {time.time()-t0:.0f}s")
