#!/usr/bin/env python3
"""16 个种子样本的双峰性 vs 单纯方差。

机制假设:白墙粘连处代价曲线有两个谷底(物体表面 / 墙面),扩散采样每次随机掉进一个
=> 样本呈双峰、中间空。而真正难重建的表面是单峰宽散(围绕同一深度抖)。
方差把两者混为一谈 => 有效点云被一起删。

双峰性判据用 **dip 的无参版本**:把 16 个样本排序, 最大相邻间隙 / 全距。
  单峰宽散 => 样本均匀铺开 => 最大间隙 ≈ 全距/15 ≈ 0.067
  双峰     => 中间一条大缝 => 最大间隙 → 接近全距
这个量纲无关、无需拟合、无自定常数;它的"无信息基线" 1/(n-1) 由样本数决定。
"""
import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
MS = "/root/ms"
seeds = [f"s{i}" for i in range(1, 17)]
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{MS}/s1/depth_est/*.pfm"))
BASE = 1.0 / (len(seeds) - 1)          # 均匀铺开时最大间隙的期望量级
print(f"种子 {len(seeds)} 个, 无信息基线 = 1/(n-1) = {BASE:.4f}")

os.makedirs("/root/ms/gapmap", exist_ok=True)
G_hi, G_lo, V_hi, V_lo = [], [], [], []
for i in frames:
    D = np.stack([np.array(read_pfm(f"{MS}/{t}/depth_est/{i:08d}.pfm")[0], dtype=np.float32) for t in seeds])
    S = np.sort(D, axis=0)
    rng = S[-1] - S[0]
    gap = np.max(np.diff(S, axis=0), axis=0)
    g = np.where(rng > 1e-6, gap / np.maximum(rng, 1e-9), 0).astype(np.float32)   # 最大间隙占全距
    np.save(f"/root/ms/gapmap/{i:08d}.npy", g)
    if i % 11: continue
    mu = D.mean(0); v = np.where(mu > 1e-6, D.std(0)/np.maximum(mu,1e-6), 0)
    m = (D > 0).all(0)
    hi = m & (v >= 0.000624)           # 方差门会删的
    lo = m & (v < 0.000624)            # 方差门会留的
    if hi.sum() > 500: G_hi.append(g[hi]); V_hi.append(v[hi])
    if lo.sum() > 500: G_lo.append(g[lo]); V_lo.append(v[lo])
Gh, Gl = np.concatenate(G_hi), np.concatenate(G_lo)
print(f"\n在「方差门会删」的像素里({len(Gh):,}) 最大间隙/全距: p50 {np.median(Gh):.3f} p90 {np.percentile(Gh,90):.3f}")
print(f"在「方差门会留」的像素里({len(Gl):,})                p50 {np.median(Gl):.3f} p90 {np.percentile(Gl,90):.3f}")
print(f"\n若双峰性有独立信息, 前者应显著高于基线 {BASE:.3f} 且高于后者")
for t in (0.2, 0.3, 0.4, 0.5, 0.6):
    print(f"  间隙>{t}: 会删的里 {(Gh>t).mean()*100:5.1f}%  会留的里 {(Gl>t).mean()*100:5.1f}%")
