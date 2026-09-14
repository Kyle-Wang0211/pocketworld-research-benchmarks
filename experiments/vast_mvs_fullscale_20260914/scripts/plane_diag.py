# -*- coding: utf-8 -*-
"""诊断: 检测出的 13 个平面里, 有没有【法向相同但偏移不同】的平行面对?
   若有 => 同一面墙的多层被各自检测成独立平面, 论文方法没有把它们压成一层。
   纯测量, 参数与 plane_fit.py 完全相同(论文 3.2 + Open3D 官方示例)。"""
import sys, numpy as np, open3d as o3d
SRC = sys.argv[1]
N_MIN_FRAC, D_MAX, ITER_MAX = 0.01, 0.01, 100
RANSAC_N, NUM_ITERS = 3, 1000
pcd = o3d.io.read_point_cloud(SRC)
P = np.asarray(pcd.points); n0 = len(P); n_min = int(N_MIN_FRAC * n0)
alive = np.ones(n0, dtype=bool); models = []
for it in range(ITER_MAX):
    ia = np.flatnonzero(alive)
    if len(ia) < n_min: break
    sub = o3d.geometry.PointCloud(); sub.points = o3d.utility.Vector3dVector(P[ia])
    m, inl = sub.segment_plane(distance_threshold=D_MAX, ransac_n=RANSAC_N, num_iterations=NUM_ITERS)
    if len(inl) < n_min: break
    a,b,c,d = m; nv = np.array([a,b,c]); L = np.linalg.norm(nv)
    models.append((nv/L, d/L, len(inl)))
    alive[ia[np.asarray(inl)]] = False
print("检测到 %d 个平面 (n=%d, n_min=%d)" % (len(models), n0, n_min))
print()
print("%-4s %-28s %-10s %-10s" % ("#", "法向 (单位向量)", "偏移 d(m)", "inliers"))
for i,(nv,d,k) in enumerate(models):
    print("%-4d [%6.3f %6.3f %6.3f]        %8.3f   %9d" % (i+1, nv[0],nv[1],nv[2], d, k))
print()
print("=== 平行面对 (法向夹角 < 5 度) ===")
found = 0
for i in range(len(models)):
    for j in range(i+1, len(models)):
        ni, di, ki = models[i]; nj, dj, kj = models[j]
        cos = abs(float(np.dot(ni, nj)))
        if cos > np.cos(np.deg2rad(5)):
            # 同向或反向; 面间距 = |d_i -/+ d_j|
            gap = abs(di - dj) if float(np.dot(ni,nj)) > 0 else abs(di + dj)
            found += 1
            print("  平面%02d 与 平面%02d  夹角 %.2f 度  【面间距 %.3f m】  inliers %d / %d"
                  % (i+1, j+1, np.rad2deg(np.arccos(min(cos,1.0))), gap, ki, kj))
print("平行面对数: %d" % found)
print()
print("判据: d_max = 0.01 m。面间距 >> 0.01 m 的平行面对 = 同一物理平面的多层被拆成了独立平面。")
