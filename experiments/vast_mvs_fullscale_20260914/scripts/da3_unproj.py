#!/usr/bin/env python3
"""从 DA3 官方 npz(depth/conf/extrinsics/intrinsics/image)反投影成点云。
   外参/内参已验证与我们喂进去的逐位一致(相机中心 p50 0.000mm),所以结果直接落在 COLMAP 帧。
   置信度门用官方 glb 导出的同一个默认值 conf_thresh_percentile=40。"""
import numpy as np, glob, json, os
d = np.load(sorted(glob.glob("" + __import__("os").environ.get("NPZDIR","/root/da3_full") + "/exports/npz/*.npz"))[0], allow_pickle=True)
D, C, E, K, I = d["depth"], d["conf"], d["extrinsics"], d["intrinsics"], d["image"]
N, H, W = D.shape
thr = float(np.percentile(C, 40.0))                      # 官方默认
print(f"{N} 视图 {H}x{W}  conf p40 = {thr:.4f}")
u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
P = []; COL = []
for i in range(N):
    m = (D[i] > 0) & (C[i] >= thr)
    if not m.any(): continue
    z = D[i][m]
    x = (u[m] - K[i][0,2]) / K[i][0,0] * z
    y = (v[m] - K[i][1,2]) / K[i][1,1] * z
    Xc = np.stack([x, y, z], 1)
    R = E[i][:3,:3]; t = E[i][:3,3]
    P.append((Xc - t) @ R)                                # R^T (Xc - t)
    COL.append(I[i][m])
P = np.concatenate(P).astype(np.float32); COL = np.concatenate(COL).astype(np.uint8)
print("点数", f"{len(P):,}", " COLMAP帧 bbox", np.round(P.min(0),2).tolist(), np.round(P.max(0),2).tolist())
P[:,1] *= -1; P[:,2] *= -1                                # -> 展示帧
os.makedirs("/root/bins_da3", exist_ok=True)
P.tofile("" + __import__("os").environ.get("TAG","/root/bins_da3/da3base") + ".pos"); COL.tofile("" + __import__("os").environ.get("TAG","/root/bins_da3/da3base") + ".col")
med = np.median(P,0)
print("展示帧 中位", np.round(med,3).tolist())
R = np.fromfile("/root/bins_fc/fusecut.pos", dtype=np.float32).reshape(-1,3)
print("官方768 中位", np.round(np.median(R,0),3).tolist(), "  (两者应接近)")
json.dump({"da3base":{"n":int(len(P)),"med":med.tolist(),
  "radius":float(np.percentile(np.linalg.norm(P-med,axis=1),90))}},
  open("/root/bins_da3/meta_da3base.json","w"))
