# -*- coding: utf-8 -*-
"""标定 plane_diag 判据的噪声地板。
   segment_plane 是 RANSAC 且 Open3D 0.19 无 seed 参数 => 同一点云多次跑结果会抖。
   在拿它比较不同臂之前, 必须先知道「同一个点云重复跑」的波动有多大,
   否则读出的差可能全是噪声 (见 09-09 种子方差门: 地板不减掉, 结论不成立)。
   参数与 plane_fit.py / plane_diag.py 完全相同。"""
import sys, numpy as np, open3d as o3d

SRC = sys.argv[1]
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
N_MIN_FRAC, D_MAX, ITER_MAX = 0.01, 0.01, 100
RANSAC_N, NUM_ITERS = 3, 1000

pcd = o3d.io.read_point_cloud(SRC)
P = np.asarray(pcd.points)
n0 = len(P)
n_min = int(N_MIN_FRAC * n0)
print("[in] %s  %d points  n_min=%d" % (SRC, n0, n_min), flush=True)

def run_once():
    alive = np.ones(n0, dtype=bool)
    models = []
    for it in range(ITER_MAX):
        ia = np.flatnonzero(alive)
        if len(ia) < n_min:
            break
        sub = o3d.geometry.PointCloud()
        sub.points = o3d.utility.Vector3dVector(P[ia])
        m, inl = sub.segment_plane(distance_threshold=D_MAX, ransac_n=RANSAC_N,
                                   num_iterations=NUM_ITERS)
        if len(inl) < n_min:
            break
        a, b, c, d = m
        nv = np.array([a, b, c])
        L = float(np.linalg.norm(nv))
        models.append((nv / L, d / L))
        alive[ia[np.asarray(inl)]] = False
    pairs = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            ni, di = models[i]
            nj, dj = models[j]
            dot = float(np.dot(ni, nj))
            if abs(dot) > np.cos(np.deg2rad(5)):
                pairs.append(abs(di - dj) if dot > 0 else abs(di + dj))
    return len(models), len(pairs), (max(pairs) if pairs else 0.0), \
           len([g for g in pairs if g > 0.10]), (float(np.mean(pairs)) if pairs else 0.0)

rows = []
for r in range(REPEATS):
    res = run_once()
    rows.append(res)
    print("  run %d: 平面 %2d  平行对 %2d  最大间距 %.3fm  >0.1m %2d  平均 %.3fm"
          % (r + 1, res[0], res[1], res[2], res[3], res[4]), flush=True)

A = np.array(rows, dtype=float)
names = ["平面数", "平行对数", "最大间距", ">0.1m对数", "平均间距"]
print("", flush=True)
print("%-12s %10s %10s %10s %10s" % ("量", "min", "max", "极差", "标准差"), flush=True)
for k, nm in enumerate(names):
    col = A[:, k]
    print("%-12s %10.3f %10.3f %10.3f %10.3f"
          % (nm, col.min(), col.max(), col.max() - col.min(), col.std()), flush=True)
print("", flush=True)
print("判读: 任何两臂之间小于上面【极差】的差, 都无法与 RANSAC 噪声区分。", flush=True)
