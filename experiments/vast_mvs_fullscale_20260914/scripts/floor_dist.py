#!/usr/bin/env python3
"""两个有出处的阈值,都不是拍的:

A) 噪声地板的分位数 —— 同一种子跑两遍的逐像素相对差(cudnn.benchmark 按计时选算法造成)。
   取它的 p99:方差超过这条线的像素, **其分歧无法用算法噪声解释**, 只能是模型自己在挑不同答案。
   这是标准的"零假设 = 只有噪声"的单侧检验, 阈值由测量本身给出。

B) 官方 --geo_depth_thres 0.01 —— 官方融合门判定"两个视图一致"的容差就是 1% 相对深度。
   模型自己的采样分歧若超过官方认定的"一致"容差, 按官方自己的标准就是不一致。
   这个常数逐字来自 casdiffmvs_run_official.sh。
"""
import os, sys, glob
import numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
MS = "/root/ms"
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{MS}/floorA/depth_est/*.pfm"))
F = []
for i in frames:
    a = f"{MS}/floorA/depth_est/{i:08d}.pfm"; b = f"{MS}/floorB/depth_est/{i:08d}.pfm"
    if not (os.path.exists(a) and os.path.exists(b)): continue
    A = np.array(read_pfm(a)[0], dtype=np.float32); B = np.array(read_pfm(b)[0], dtype=np.float32)
    m = (A > 0) & (B > 0)
    if m.sum() < 1000: continue
    F.append((np.abs(A - B) / np.maximum((A + B) / 2, 1e-6))[m][::7])
F = np.concatenate(F)
print(f"噪声地板(同种子两遍) {len(F):,} 像素")
for q in (50, 90, 95, 99, 99.9):
    print(f"   p{q:<5} {np.percentile(F,q)*100:.4f}%")
p99 = float(np.percentile(F, 99))
print(f"\nA) 地板 p99 = {p99*100:.4f}%  -> VAR_GATE={p99:.6f}")
print(f"B) 官方 geo_depth_thres = 1%  -> VAR_GATE=0.01")
