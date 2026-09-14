#!/usr/bin/env python3
"""预算逐帧的种子方差图, 供官方 filter.py 当门用。
方差 = 6 个不同种子的逐像素深度相对标准差。地板(同种子两遍)已实测为它的 1/64, 可忽略。"""
import os, sys, glob
import numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
MS = "/root/ms"; OUT = "/root/ms/varmap"
os.makedirs(OUT, exist_ok=True)
seeds = [f"s{i}" for i in (1,2,3,4,5,6)]
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{MS}/{seeds[0]}/depth_est/*.pfm"))
for i in frames:
    D = []
    for t in seeds:
        p = f"{MS}/{t}/depth_est/{i:08d}.pfm"
        if os.path.exists(p): D.append(np.array(read_pfm(p)[0], dtype=np.float32))
    if len(D) < 3: continue
    D = np.stack(D); mu = D.mean(0)
    rel = np.where(mu > 1e-6, D.std(0) / np.maximum(mu, 1e-6), 9.9).astype(np.float32)
    np.save(f"{OUT}/{i:08d}.npy", rel)
print(f"写出 {len(frames)} 张方差图 -> {OUT}")
a = np.concatenate([np.load(f"{OUT}/{i:08d}.npy").ravel()[::13] for i in frames[:40]])
print("方差分布:", " ".join(f"p{q}={np.percentile(a,q)*100:.3f}%" for q in (10,30,50,70,90)))
