#!/usr/bin/env python3
"""剔掉深度范围退化的 scan。判据不是我拍的 —— 是 MonoMVSNet 自己 datasets/blendedmvs.py:93
   `assert mask.sum() > 0` 的直接前提:该帧在自己的 [dmin,dmax] 内必须至少有一个有效像素。
   实测 1334 个 scan 里只有 1 个不满足(BlendedMVS+ 的 00000000000000000000000f/00000008,
   深度图全零、cam 写着 dmin=9.5e8 dmax=0 —— 上游数据损坏)。
"""
import os, sys, glob, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
ROOT = "/root/monotrain"
L = "/root/MonoMVSNet/lists/ours/train.txt"
names = [l.strip() for l in open(L) if l.strip()]
keep, drop = [], []
for s in names:
    ok = True
    for c in sorted(glob.glob(f"{ROOT}/{s}/cams/*_cam.txt")):
        idx = os.path.basename(c).split("_")[0]
        p = f"{ROOT}/{s}/rendered_depth_maps/{idx}.pfm"
        if not os.path.exists(p): ok = False; break
        a = open(c).read().rstrip("\n").split("\n")[-1].split()
        lo, hi = float(a[0]), float(a[-1])
        if not (hi > lo > 0): ok = False; break
        d = np.array(read_pfm(p)[0], dtype=np.float32)
        if not ((d >= lo) & (d <= hi)).any(): ok = False; break
    (keep if ok else drop).append(s)
open(L, "w").write("\n".join(keep) + "\n")
print(f"保留 {len(keep)} / 剔除 {len(drop)}: {drop}")
