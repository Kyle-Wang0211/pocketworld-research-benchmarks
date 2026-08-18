#!/usr/bin/env python3
"""局部表面粗糙度:不用先框出"哪片是墙、哪片是地板"再测厚度(RANSAC 太慢
且要调平面数),直接对每个点用它自己的邻域算——任何局部平面结构(墙、地板、
家具边缘)都适用,一次批量算完不用逐点循环。

原理:每个点取 k 个最近邻,做局部 PCA。三个特征值里最小那个对应的方向,
就是这片邻域最贴近的"法线"方向;那个特征值的平方根,就是这片点沿法线方向
散布的均方根宽度——也就是"这片本该是纸片的结构,实际有多厚"。

这就是标准的点云表面粗糙度/法线一致性度量,直接对应用户在截图里指出的
"墙面、地板本该薄如纸,却被吹松"——不需要预先分割出具体是哪面墙、哪块地板,
在整朵云上一次性覆盖所有局部平面结构。
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


def local_roughness(xyz, k=15, batch=20000):
    """返回每点的局部粗糙度(米):最小特征值开方,即邻域沿法线方向的 RMS 宽度。"""
    tree = cKDTree(xyz)
    n = len(xyz)
    out = np.empty(n, dtype=np.float64)
    for i in range(0, n, batch):
        j = min(i + batch, n)
        _, idx = tree.query(xyz[i:j], k=k, workers=-1)     # [b,k]
        nb = xyz[idx]                                        # [b,k,3]
        c = nb.mean(axis=1, keepdims=True)                   # [b,1,3]
        d = nb - c
        cov = np.einsum("bki,bkj->bij", d, d) / k             # [b,3,3]
        ev = np.linalg.eigvalsh(cov)                          # [b,3] 升序
        out[i:j] = np.sqrt(np.clip(ev[:, 0], 0, None))
    return out


CLOUDS = [
    ("基线 延长前", "ctl.bin.gz"), ("基线 延长后", "ctl_e.bin.gz"),
    ("LoFTR 延长前", "lk4b.bin.gz"), ("LoFTR 延长后", "loftr_e.bin.gz"),
    ("臂A 延长前", "armA2.bin.gz"), ("臂A 延长后", "armA_e.bin.gz"),
    ("ALIKED 延长前", "p16k2.bin.gz"), ("ALIKED 延长后", "p16k_e.bin.gz"),
]

print(f"{'臂':<14} {'点数':>9} {'粗糙度中位(mm)':>14} {'p75(mm)':>9} {'p90(mm)':>9} "
      f"{'>10mm占比':>9} {'>20mm占比':>9}", flush=True)
for name, fn in CLOUDS:
    p = Path(fn)
    if not p.exists():
        print(f"{name:<14} 缺文件 {fn}", flush=True); continue
    xyz = load_new(p)
    r = local_roughness(xyz) * 1000    # → mm
    print(f"{name:<14} {len(xyz):>9,} {np.median(r):>14.2f} {np.percentile(r,75):>9.2f} "
          f"{np.percentile(r,90):>9.2f} {(r>10).mean()*100:>8.2f}% {(r>20).mean()*100:>8.2f}%",
          flush=True)
