# -*- coding: utf-8 -*-
"""生成逐像素 geo_depth_thres 图: thres(x) = base * (1 + k * s(x))
   s = secmass 归一化到 [0,1](用全体 99 分位截断, 防离群点)。
   🔴 函数形式和 k 都是我定的、无出处 => 所以扫 k。"""
import glob, os, sys, numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import read_pfm
from datasets.data_io import save_pfm
OUT, K, BASE = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
fs = sorted(glob.glob(os.path.join(OUT, "secmass", "*.pfm")))
# 先用全局 99 分位定标(同一个标度跨视图, 否则各图不可比)
vals = np.concatenate([read_pfm(f)[0].ravel()[::7] for f in fs])
hi = float(np.percentile(vals, 99))
print("  secmass 全局: 中位 %.4f  p99 %.4f  max %.4f" % (np.median(vals), hi, vals.max()), flush=True)
d0 = read_pfm(os.path.join(OUT, "depth_est", os.path.basename(fs[0])))[0]
os.makedirs(os.path.join(OUT, "dthres"), exist_ok=True)
for f in fs:
    s = read_pfm(f)[0]
    s = np.clip(s / max(hi, 1e-8), 0, 1)
    s = cv2.resize(s.astype(np.float32), (d0.shape[1], d0.shape[0]), interpolation=cv2.INTER_LINEAR)
    t = (BASE * (1.0 + K * s)).astype(np.float32)
    save_pfm(os.path.join(OUT, "dthres", os.path.basename(f)), np.ascontiguousarray(t))
print("  k=%.1f base=%.4f => 阈值范围 %.5f .. %.5f" % (K, BASE, BASE, BASE*(1+K)), flush=True)
