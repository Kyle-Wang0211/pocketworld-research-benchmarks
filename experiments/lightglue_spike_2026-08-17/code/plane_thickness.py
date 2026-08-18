#!/usr/bin/env python3
"""平面厚度:量用户指出的那种浮点——不是孤立单点,是一整片结构沿法线方向被
"吹松"。截图里那道斜穿画面的白色亮带(墙/顶交界)和地板,在 LoFTR 窗口明显
比 ALIKED 窗口更"毛"更"喷",ALIKED 是一条紧实的线。前两把尺子(视差角、
空间孤立度)都测不到这个,因为一片致密但偏离真实表面的结构,局部密度正常、
多视角也"一致"(哪怕一致的是错的)。

做法:序贯 RANSAC 在每朵云自己的坐标系里找最大的几个平面结构(不依赖跨云
gauge 对齐,避免把对齐残差和真实厚度混在一起——gauge 残差本身就有几厘米,
和我们要抓的鬼层同量级,不能忽略),对每个平面报告内点到平面距离的分布:
std 是"糊成一片"的严不严重,p99 是极端拖尾,内点数是这片结构有多大。
"""
import gzip
from pathlib import Path

import numpy as np


def load_new(p: Path):
    b = gzip.decompress(p.read_bytes())
    lo = np.frombuffer(b[0:12], dtype="<f4")
    span = np.frombuffer(b[12:24], dtype="<f4")
    n = int(np.frombuffer(b[24:28], dtype="<i4")[0])
    d = np.frombuffer(b[28:28 + n * 6], dtype="<u2").reshape(n, 3)
    q = np.cumsum(d.astype(np.int64), axis=0).astype(np.uint16)
    return lo + q.astype(np.float64) / 65535.0 * span


def ransac_plane(pts, thresh, iters=300, score_cap=15000, rng=None):
    """⚠️ 全量 remaining 每次迭代都做点积,240k点×800次直接 OOM。
    改成:候选三点组一次性抽好;打分只用最多 score_cap 个点的子样本
    (子样本内点比例是全量比例的无偏估计);选出最优平面后,调用方再
    用全量点做精确重拟合与厚度测量。"""
    rng = rng or np.random.default_rng(0)
    n = len(pts)
    if n > score_cap:
        score_idx = rng.choice(n, score_cap, replace=False)
        score_pts = pts[score_idx]
    else:
        score_pts = pts
    tri = rng.integers(0, n, size=(iters, 3))
    best_count, best_plane = -1, None
    for i, j, k in tri:
        if i == j or j == k or i == k:
            continue
        p0, p1, p2 = pts[i], pts[j], pts[k]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal /= norm
        d = -normal @ p0
        count = int((np.abs(score_pts @ normal + d) < thresh).sum())
        if count > best_count:
            best_count, best_plane = count, (normal, d)
    if best_plane is None:
        return None, None
    normal, d = best_plane
    inliers = np.abs(pts @ normal + d) < thresh   # 只在最优平面上,对全量点做一次
    return inliers, best_plane


def refine_and_measure(pts, inliers, normal, d):
    """用 SVD 在内点上重新拟合一次(RANSAC 的3点解噪声大),再报告厚度。"""
    P = pts[inliers]
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c)
    normal = vt[-1]
    dist = (P - c) @ normal
    return dict(n=len(P), std=float(dist.std()), p1=float(np.percentile(dist, 1)),
                p99=float(np.percentile(dist, 99)), ptp=float(np.percentile(dist, 99) -
                np.percentile(dist, 1)), normal=normal)


CLOUDS = [
    ("基线+延长", "ctl_e.bin.gz"), ("LoFTR+延长", "loftr_e.bin.gz"),
    ("臂A+延长", "armA_e.bin.gz"), ("ALIKED16k+延长", "p16k_e.bin.gz"),
]
THRESH_INIT = 0.05    # 初始 RANSAC 内点阈值(m),粗筛出结构,细厚度看 refine 后的 std/ptp
N_PLANES = 2          # 每朵云找前 2 大平面(通常=地板+一面墙)

print(f"{'臂':<16} {'平面#':>5} {'内点数':>8} {'占比':>6} {'std(mm)':>9} {'ptp(p1-p99,mm)':>15}")
for name, fn in CLOUDS:
    xyz = load_new(Path(fn))
    remaining = xyz.copy()
    for k in range(N_PLANES):
        if len(remaining) < 500:
            break
        inliers, plane = ransac_plane(remaining, THRESH_INIT)
        if inliers is None or inliers.sum() < 200:
            break
        stat = refine_and_measure(remaining, inliers, *plane)
        print(f"{name:<16} {k+1:>5} {stat['n']:>8,} {stat['n']/len(xyz)*100:>5.1f}% "
              f"{stat['std']*1000:>9.2f} {stat['ptp']*1000:>15.2f}")
        remaining = remaining[~inliers]
