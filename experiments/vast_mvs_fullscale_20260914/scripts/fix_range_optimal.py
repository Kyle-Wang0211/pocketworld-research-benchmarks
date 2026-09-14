#!/usr/bin/env python3
"""深度范围修正 v2:不再把窗口锚死在 dmin 上,而是在 R 倍宽度的约束下
**找覆盖有效像素最多的那个窗口**,把代价压到架构允许的最小值。

约束 R=29.68 的来源:官方 BlendedMVG 自己的 dmax/dmin 分布 p99(我们训练集里 17,194 个官方
cam 文件实测)。它不是我拍的 —— 它就是"级联 MVS 在 384 档反深度采样下能表示的动态范围"。
超出这个范围的内容分不到一个采样格, 学不动, 只会往梯度里灌噪声(实测 epe 尖刺 18823)。

v1(锚在 dmin)的毛病:病态帧的 dmin 本身就是离群值(有帧 dmin=7mm),
于是 dmin*R 把整帧掏空 —— 实测 3.4% 的帧有效像素跌破 50%。
v2 在反深度空间滑窗取最优, 保证"该留的都留下"。

只改 cam 第 11 行,不碰深度图/内外参。幂等(会先从深度图重算,不依赖上一次的写入)。
"""
import os, glob, sys
import numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

R = 29.68
ROOT = sys.argv[1] if len(sys.argv) > 1 else "/root/ta2/blendfmt"

def best_window(v):
    """在 [a, a*R] 的约束下最大化落入窗口的像素数。反深度空间等价于固定宽度滑窗。"""
    s = np.sort(v)
    n = s.size
    lo_all, hi_all = float(s[int(n * .01)]), float(s[int(n * .99)])
    if hi_all / max(lo_all, 1e-9) <= R:
        return lo_all, hi_all, 1.0                    # 本来就在范围内, 原样
    # 候选左端取分位点网格; 右端 = 左*R; 用 searchsorted 数覆盖
    cand = s[np.linspace(0, int(n * .99), 400).astype(int)]
    hi = cand * R
    cnt = np.searchsorted(s, hi, "right") - np.searchsorted(s, cand, "left")
    k = int(np.argmax(cnt))
    return float(cand[k]), float(min(hi[k], s[-1])), float(cnt[k] / n)

scans = sorted(d for d in glob.glob(f"{ROOT}/*") if os.path.exists(f"{d}/cams/pair.txt"))
n_cam = n_fix = 0
cov_v1, cov_v2 = [], []
for si, s in enumerate(scans):
    for c in sorted(glob.glob(f"{s}/cams/*_cam.txt")):
        idx = os.path.basename(c).split("_")[0]
        p = f"{s}/rendered_depth_maps/{idx}.pfm"
        if not os.path.exists(p): continue
        d = np.array(read_pfm(p)[0], dtype=np.float32)
        v = d[np.isfinite(d) & (d > 0)]
        if v.size < 100: continue
        n_cam += 1
        lo, hi, cov = best_window(v)
        # v1 口径(锚 dmin)的覆盖率, 只为对照
        s_ = np.sort(v); l1 = float(s_[int(s_.size * .01)]); h1 = min(float(s_[int(s_.size * .99)]), l1 * R)
        cov_v1.append(float(((v >= l1) & (v <= h1)).mean())); cov_v2.append(cov)
        L = open(c).read().rstrip("\n").split("\n")
        L[-1] = f"{lo:.6f} {hi:.6f}"
        open(c, "w").write("\n".join(L) + "\n")
        n_fix += 1
    if si % 80 == 0: print(f"  ...{si}/{len(scans)}", flush=True)
a1, a2 = np.array(cov_v1), np.array(cov_v2)
print(f"{ROOT}: {len(scans)} scan / {n_cam} 帧, 全部重写")
print(f"  覆盖率(落在[dmin,dmax]内的有效像素):")
print(f"    v1 锚 dmin : 中位 {np.median(a1)*100:5.1f}%  p10 {np.percentile(a1,10)*100:5.1f}%  掏空帧(<50%) {(a1<.5).mean()*100:.1f}%")
print(f"    v2 最优窗口: 中位 {np.median(a2)*100:5.1f}%  p10 {np.percentile(a2,10)*100:5.1f}%  掏空帧(<50%) {(a2<.5).mean()*100:.1f}%")
