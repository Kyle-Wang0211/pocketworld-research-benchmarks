#!/usr/bin/env python3
"""修 TartanAir 的深度动态范围。

问题:无人机/机器人视角一帧里既有近物又有天边, dmax/dmin 中位 45.6、p90 19764、最大 25.9万。
级联 MVS 只有 384 个深度假设, 铺不开这种范围 => 训练 epe 出现 18823 这种尖刺。

修法不自定阈值:上限取**官方 BlendedMVG 自己的 dmax/dmin 分布的 p99 = 29.68**
(我们训练集里 17,194 个官方 cam 文件实测得出)。超出部分把 dmax 压到 dmin*R,
远端像素自然落到 [dmin,dmax] 之外, 被 blendedmvs.py 的
`mask = (depth>=depth_min) & (depth<=depth_max)` 排除 —— 这正是天空/地平线该有的待遇。

只改 cam 文件第 11 行的 dmax, 不碰深度图、不碰内外参。幂等。
"""
import os, glob, sys
R = 29.68
ROOT = "/root/hs/blendfmt"
scans = sorted(d for d in glob.glob(f"{ROOT}/*") if os.path.exists(f"{d}/cams/pair.txt"))
n_scan = n_cam = n_fix = 0
before, after = [], []
for s in scans:
    for c in sorted(glob.glob(f"{s}/cams/*_cam.txt")):
        L = open(c).read().rstrip("\n").split("\n")
        p = L[-1].split()
        if len(p) < 2: continue
        lo, hi = float(p[0]), float(p[-1])
        n_cam += 1
        if not (hi > lo > 0): continue
        before.append(hi / lo)
        if hi / lo > R:
            hi = lo * R
            L[-1] = f"{lo:.6f} {hi:.6f}"
            open(c, "w").write("\n".join(L) + "\n")
            n_fix += 1
        after.append(hi / lo)
    n_scan += 1
import statistics as st
print(f"扫 {n_scan} scan / {n_cam} 个 cam 文件, 改写 {n_fix} 个 ({n_fix/max(n_cam,1)*100:.1f}%)")
print(f"阳性对照 dmax/dmin: 改前 中位 {st.median(before):.1f} 最大 {max(before):.0f}"
      f"  ->  改后 中位 {st.median(after):.1f} 最大 {max(after):.2f}  (上限 {R})")
assert max(after) <= R + 1e-6, "还有超限的"
print("上限已生效")
