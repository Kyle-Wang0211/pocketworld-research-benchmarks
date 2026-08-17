#!/usr/bin/env python3
"""PLY → 显卡直吃的裸二进制(位置 f32 / 颜色 u8 分开存)。

⚠️ 为什么要这一步:PLY 是 15 字节交错格式(3×f32 + 3×u8),
   浏览器里只能逐点 DataView 解析 —— 1700 万点要几分钟。
   拆成两个连续数组后,JS 端 `new Float32Array(buf)` 零解析直接上传显卡。
   **不降采样,一个点都不少。**
"""
import sys, os, json
import numpy as np
from plyfile import PlyData

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
meta = {}
if os.path.exists(f"{out}/meta.json"):
    meta = json.load(open(f"{out}/meta.json"))   # 🔴 合并而非覆盖(踩过:新增一份把旧四份冲掉了)
for a in sys.argv[2:]:
    tag, path = a.split("=", 1)
    v = PlyData.read(path)["vertex"]
    n = len(v)
    pos = np.empty((n, 3), np.float32)
    pos[:, 0], pos[:, 1], pos[:, 2] = v["x"], v["y"], v["z"]
    col = np.empty((n, 3), np.uint8)
    col[:, 0], col[:, 1], col[:, 2] = v["red"], v["green"], v["blue"]
    pos.tofile(f"{out}/{tag}.pos")
    col.tofile(f"{out}/{tag}.col")
    # 逐轴中位数定心 + 5-95 百分位定尺度(与既有 compare 页同法,
    # 用第一份的值共享给全部,保证切换时坐标系不跳)
    med = np.median(pos, axis=0).tolist()
    p5, p95 = np.percentile(pos, 5, axis=0), np.percentile(pos, 95, axis=0)
    meta[tag] = {"n": int(n), "center": med, "ext": (p95 - p5).tolist()}
    print(f"  {tag:<16} {n:>10,} 点  pos {pos.nbytes/2**20:.0f}MB + col {col.nbytes/2**20:.0f}MB")
json.dump(meta, open(f"{out}/meta.json", "w"))
print(f"→ {out}/meta.json")
