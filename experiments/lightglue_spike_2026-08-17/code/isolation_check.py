#!/usr/bin/env python3
"""空间孤立度:治我上一版代理指标的盲区。

上一版(floater_risk.py)用视差角+track长度,能被"镜像鬼点"这类多视一致但
错误的点骗过——反光面/重复纹理在多张照片里三角化出自洽但错误的点,判据看
起来完美,因为骗过判据的机制就是"看起来被多视角验证过"。绝对数字也证明了
这一点:LoFTR 按那把尺子的风险点(1,355)比 ALIKED(1,961)还少,但用户肉眼
看到的是反过来的。

这里换一把更接近"肉眼看到的飘"的尺子:一个点离它周围最近的邻居有多远。
真正的表面上点是密集排布的,飘在半空的浮点/鬼层跟主体结构脱节 —— k近邻距离
会明显大于局部密度。判据:每个点到第 k 近邻的距离,相对该点云中位密度的倍数。
"""
import gzip
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def load_new(p: Path):
    b = gzip.decompress(p.read_bytes())
    lo = np.frombuffer(b[0:12], dtype="<f4")
    span = np.frombuffer(b[12:24], dtype="<f4")
    n = int(np.frombuffer(b[24:28], dtype="<i4")[0])
    d = np.frombuffer(b[28:28 + n * 6], dtype="<u2").reshape(n, 3)
    q = np.cumsum(d.astype(np.int64), axis=0).astype(np.uint16)
    return lo + q.astype(np.float64) / 65535.0 * span


CLOUDS = [
    ("基线 延长前", "ctl.bin.gz"), ("基线 延长后", "ctl_e.bin.gz"),
    ("LoFTR 延长前", "lk4b.bin.gz"), ("LoFTR 延长后", "loftr_e.bin.gz"),
    ("臂A 延长前", "armA2.bin.gz"), ("臂A 延长后", "armA_e.bin.gz"),
    ("ALIKED 延长前", "p16k2.bin.gz"), ("ALIKED 延长后", "p16k_e.bin.gz"),
]

K = 8
print(f"{'臂':<14} {'点数':>9} {'k近邻中位':>10} {'孤立点(>5×中位)':>16} {'占比':>7} {'孤立点(>10×中位)':>17} {'占比':>7}")
for name, fn in CLOUDS:
    p = Path(fn)
    if not p.exists():
        print(f"{name:<14} 缺文件 {fn}")
        continue
    xyz = load_new(p)
    tree = cKDTree(xyz)
    d, _ = tree.query(xyz, k=K + 1, workers=-1)   # 第0列是自己,取第K列
    knn = d[:, K]
    med = np.median(knn)
    iso5 = (knn > 5 * med).sum()
    iso10 = (knn > 10 * med).sum()
    print(f"{name:<14} {len(xyz):>9,} {med:>10.4f} {iso5:>16,} {iso5/len(xyz)*100:>6.2f}% "
          f"{iso10:>17,} {iso10/len(xyz)*100:>6.2f}%")
