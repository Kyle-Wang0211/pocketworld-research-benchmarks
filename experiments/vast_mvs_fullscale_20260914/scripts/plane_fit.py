# -*- coding: utf-8 -*-
"""严格复刻 Sensors 2022, 22(23), 9391 (CC-BY)
   Xu, Y.; So, Y.; Woo, S. "Plane Fitting in 3D Reconstruction to Preserve Smooth Homogeneous Surfaces"
   全文: PMC9738859

参数逐项出处(零自定):
  n_min    = 0.01 * n      论文 3.2 节 "The default values of n_min, d_max and iter_max are
  d_max    = 0.01          defined as 0.01n, 0.01, and 100, respectively, where n represents
  iter_max = 100           the point cloud size."
  ransac_n        = 3      Open3D 官方教程 Plane segmentation 示例
  num_iterations  = 1000   Open3D 官方教程 Plane segmentation 示例
                           (该示例的 distance_threshold=0.01 与论文 d_max 完全一致)

算法 (论文 3.2 + 3.3):
  3.2 反复检测「包含最多点的平面」, 直到剩余点 < n_min, 或拟合不出 >= n_min 的平面;
      最多 iter_max 次外层循环。
  3.3 "project all inliers onto the corresponding planes; that is, replace the point with
      its projection on the plane, so as to maintain the initial density of the point cloud"
      剩余未被任何平面接纳的点 = outliers, 论文 "removing only outliers" => 删除。

两处必须标明的移位前提 (不改论文, 只标注, 结果按此解读):
  (1) d_max=0.01 的单位是论文点云的坐标单位。论文用 AliceVision 重建转台物体(SfM 任意尺度),
      我们的点云是米制(radius 约 4.8m), 照搬即「1 厘米」。
  (2) 论文场景是 Manhattan-like 平面结构, outlier 很少; 我们场景含大量非平面物体,
      n_min=0.01n 意味着只有占 >=1% 点数的大平面被接受 => 小物体会落进 outlier 被删。
"""
import sys, time
import numpy as np
import open3d as o3d
from plyfile import PlyData, PlyElement   # 与官方 filter.py:459-471 同一写法

SRC, DST = sys.argv[1], sys.argv[2]
N_MIN_FRAC, D_MAX, ITER_MAX = 0.01, 0.01, 100      # 论文 3.2
RANSAC_N, NUM_ITERS = 3, 1000                       # Open3D 官方示例

t0 = time.time()
# 🔴 用 plyfile 直读, 与官方 filter.py 的写出格式(f4 xyz + u1 rgb)对齐;
#    不走 Open3D 的 float64/[0,1] 往返, 避免 dtype 与颜色舍入两处失真。
_ply = PlyData.read(SRC)
_v = _ply['vertex'].data
P = np.stack([_v['x'], _v['y'], _v['z']], axis=1).astype(np.float64)
C = np.stack([_v['red'], _v['green'], _v['blue']], axis=1)   # 原样 uint8
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(P)
n0 = len(P)
n_min = int(N_MIN_FRAC * n0)
print("[in] %s  %d points  read %.1fs" % (SRC, n0, time.time() - t0), flush=True)
print("[param] n_min=%d (0.01n)  d_max=%.4f  iter_max=%d  ransac_n=%d  num_iterations=%d"
      % (n_min, D_MAX, ITER_MAX, RANSAC_N, NUM_ITERS), flush=True)
ext = pcd.get_axis_aligned_bounding_box().get_extent()
print("[scale] bbox %.2f x %.2f x %.2f m  => d_max=0.01 equals %.1f mm"
      % (ext[0], ext[1], ext[2], D_MAX * 1000), flush=True)

alive = np.ones(n0, dtype=bool)
out_P = P.copy()
planes = 0
projected = 0

for it in range(ITER_MAX):
    idx_alive = np.flatnonzero(alive)
    if len(idx_alive) < n_min:
        print("[stop] remaining %d < n_min %d (paper 3.2)" % (len(idx_alive), n_min), flush=True)
        break
    sub = o3d.geometry.PointCloud()
    sub.points = o3d.utility.Vector3dVector(P[idx_alive])
    model, inl = sub.segment_plane(distance_threshold=D_MAX,
                                   ransac_n=RANSAC_N,
                                   num_iterations=NUM_ITERS)
    if len(inl) < n_min:
        print("[stop] round %d best plane has only %d points < n_min %d (paper 3.2)"
              % (it + 1, len(inl), n_min), flush=True)
        break
    a, b, c, d = model
    nrm = np.array([a, b, c], dtype=np.float64)
    L = float(np.linalg.norm(nrm))
    gi = idx_alive[np.asarray(inl)]
    sd = (P[gi] @ nrm + d) / (L * L)
    out_P[gi] = P[gi] - sd[:, None] * nrm[None, :]
    alive[gi] = False
    planes += 1
    projected += len(gi)
    print("  plane %02d  inliers %9d (%.4f)  median |residual| %.5f m  remaining %d"
          % (planes, len(gi), len(gi) / n0, float(np.median(np.abs(sd) * L)), int(alive.sum())),
          flush=True)

n_out = int(alive.sum())
keep = ~alive
# 写出: 逐字照官方 filter.py:459-471 的 dtype 与流程
_xyz = np.array([tuple(v) for v in out_P[keep].astype(np.float32)],
                dtype=[('x', 'f4'), ('y', 'f4'), ('z', 'f4')])
_rgb = np.array([tuple(v) for v in C[keep]],
                dtype=[('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
_all = np.empty(len(_xyz), _xyz.dtype.descr + _rgb.dtype.descr)
for prop in _xyz.dtype.names:
    _all[prop] = _xyz[prop]
for prop in _rgb.dtype.names:
    _all[prop] = _rgb[prop]
PlyData([PlyElement.describe(_all, 'vertex')]).write(DST)
assert np.isfinite(out_P[keep]).all(), "写出的点含非有限值"
res = type('R', (), {'points': out_P[keep]})()
print("", flush=True)
print("[out] planes %d  projected %d (%.4f)  outliers removed %d (%.4f)  written %d -> %s"
      % (planes, projected, projected / n0, n_out, n_out / n0, len(res.points), DST), flush=True)
print("[time] %.1f min" % ((time.time() - t0) / 60), flush=True)
