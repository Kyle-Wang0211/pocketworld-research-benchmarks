# -*- coding: utf-8 -*-
"""直接在融合点云上量「杂层有多厚」+「覆盖有多大」。

为什么要换尺子: layer_gap2 量的是【融合前】ref 之间的分歧【比例】, 已经三次与用户肉眼反向
(ep0/ep1、动态融合、ep0/ep5)。用户判的是【融合后】杂层的厚度, 那是另一个量。

做法(标准 PCA 局部平面拟合, 不是新算法):
  1. 体素下采样定位候选点(只为选点, 不改交付几何)
  2. 每个候选点取半径 R 邻域, PCA 求最小特征向量 = 法向
  3. 平面度 = λ0/(λ0+λ1+λ2), 只保留平面度 < PLANAR 的邻域(= 墙面/桌面这类平面, 不是杂物)
  4. 该邻域内所有点到拟合平面的有符号距离分布:
       厚度 = p95 − p05          <- 单层应该很薄; 有杂层就宽
       远层占比 = |d| > 2cm 的比例 <- 明确的"另一层"
  5. 覆盖 = 总点数, 以及通过平面度筛选的邻域数

🔴 我自己定的参数(必须标出来): R=0.15 m、体素 0.05 m、平面度阈 0.02、远层判据 2 cm、采样 8000 个邻域。
   这些没有出处, 是为了让六个 epoch 在同一把尺子下可比; 绝对值不可外推, 只看臂之间的相对关系。
"""
import sys, numpy as np
from plyfile import PlyData

R = 0.15
VOX = 0.05
PLANAR = 0.02
FAR = 0.02
NSAMP = 8000
SEED = 20260919


def load(p):
    v = PlyData.read(p)['vertex'].data
    return np.stack([v['x'], v['y'], v['z']], 1).astype(np.float64)


def measure(xyz, rng):
    from scipy.spatial import cKDTree
    tree = cKDTree(xyz)
    # 体素中心选点, 保证各臂在空间上取样一致(不是随机点, 避免密度偏置)
    key = np.floor(xyz / VOX).astype(np.int64)
    _, first = np.unique(key, axis=0, return_index=True)
    cand = first if len(first) <= NSAMP else rng.choice(first, NSAMP, replace=False)
    th, farfrac, nplan = [], [], 0
    for i in cand:
        idx = tree.query_ball_point(xyz[i], R)
        if len(idx) < 50:
            continue
        q = xyz[idx]
        q = q - q.mean(0)
        w, V = np.linalg.eigh(q.T @ q / len(q))
        if w.sum() <= 0:
            continue
        if w[0] / w.sum() >= PLANAR:      # 不够平, 不是墙面/桌面
            continue
        nplan += 1
        d = q @ V[:, 0]                   # 到拟合平面的有符号距离
        th.append(np.percentile(d, 95) - np.percentile(d, 5))
        farfrac.append((np.abs(d) > FAR).mean())
    return np.array(th), np.array(farfrac), nplan, len(cand)


print("%-10s %12s %10s %10s %10s %10s %8s" %
      ("臂", "总点数", "厚度p50", "厚度p90", "远层占比", "平面邻域", "采样"))
for spec in sys.argv[1:]:
    name, path = spec.split("=", 1)
    rng = np.random.default_rng(SEED)
    xyz = load(path)
    th, ff, nplan, ncand = measure(xyz, rng)
    if len(th) == 0:
        print("%-10s %12s  无平面邻域" % (name, format(len(xyz), ","))); continue
    print("%-10s %12s %9.1fmm %9.1fmm %9.2f%% %10d %8d" %
          (name, format(len(xyz), ","), np.median(th) * 1000,
           np.percentile(th, 90) * 1000, 100 * np.mean(ff), nplan, ncand), flush=True)
