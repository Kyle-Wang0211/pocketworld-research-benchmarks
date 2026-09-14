#!/usr/bin/env python3
"""扩散集成:用 16 个种子的逐像素中位数替换单次采样的深度, 再走官方融合门。
不删任何点、不设任何阈值 —— 只是把"模型每次给的答案不同"这件事从缺陷变成信息。
先例:Murre 用 10 步 x 5 ensemble 的扩散集成(档案 §..);我们此前一直用单次采样当交付。

置信度沿用官方那一份(conf0/1/2 不变),只替换 depth_est。
"""
import os, sys, glob, shutil
import numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm, save_pfm
MS = "/root/ms"; SRC = "/root/off768_true"; OUT = "/root/off_ens"
seeds = [f"s{i}" for i in range(1, 17)]
os.makedirs(f"{OUT}/depth_est", exist_ok=True)
for sub in ("conf0", "conf1", "conf2", "cams", "images"):
    d = f"{OUT}/{sub}"
    if not os.path.exists(d): os.symlink(f"{SRC}/{sub}", d)
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{MS}/s1/depth_est/*.pfm"))
for i in frames:
    D = np.stack([np.array(read_pfm(f"{MS}/{t}/depth_est/{i:08d}.pfm")[0], dtype=np.float32) for t in seeds])
    med = np.median(D, axis=0).astype(np.float32)
    save_pfm(f"{OUT}/depth_est/{i:08d}.pfm", med)
print(f"写出 {len(frames)} 张 16 种子中位数深度 -> {OUT}/depth_est")
