#!/usr/bin/env python3
"""多次采样方差能不能分开"白墙 vs 有纹理"。

信号 = 6 个不同种子的逐像素深度标准差(相对深度)
地板 = 同一种子跑两遍的逐像素差(cudnn.benchmark 按计时选算法带来的不确定性)
判据必须先过地板:若信号 ≈ 地板, 这把尺子是空的。
"""
import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

MS = "/root/ms"
seeds = [f"s{i}" for i in (1, 2, 3, 4, 5, 6)]
have = [t for t in seeds if os.path.isdir(f"{MS}/{t}/depth_est")]
print("可用种子:", have)
if len(have) < 3: print("种子不够, 等跑完"); raise SystemExit

def load(tag, i):
    p = f"{MS}/{tag}/depth_est/{i:08d}.pfm"
    return np.array(read_pfm(p)[0], dtype=np.float32) if os.path.exists(p) else None

W, R, FW, FR = [], [], [], []
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{MS}/{have[0]}/depth_est/*.pfm"))
for i in frames:
    ds = [load(t, i) for t in have]
    ds = [d for d in ds if d is not None]
    if len(ds) < 3: continue
    D = np.stack(ds)                       # [S,H,W]
    m = (D > 0).all(0)
    if m.sum() < 1000: continue
    mu = D.mean(0)
    rel = np.where(mu > 0, D.std(0) / np.maximum(mu, 1e-6), 0)      # 相对标准差
    a, b = load("floorA", i), load("floorB", i)
    fl = None
    if a is not None and b is not None:
        mf = (a > 0) & (b > 0)
        fl = np.where(mf, np.abs(a - b) / np.maximum((a + b) / 2, 1e-6), 0)
    img = cv2.imread(f"{MS}/{have[0]}/images/{i:08d}.jpg")
    if img is None: img = cv2.imread(f"/root/out_official/images/{i:08d}.jpg")
    if img is None: continue
    img = cv2.resize(img, (rel.shape[1], rel.shape[0]), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    wall = (g > 150) & (np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3)) < 4) & m
    rest = (~wall) & m
    if wall.sum() > 500: W.append(rel[wall]); FW.append(fl[wall] if fl is not None else np.zeros(wall.sum()))
    if rest.sum() > 500: R.append(rel[rest]); FR.append(fl[rest] if fl is not None else np.zeros(rest.sum()))

W, R = np.concatenate(W), np.concatenate(R)
FW, FR = np.concatenate(FW), np.concatenate(FR)
print(f"\n像素:白墙 {len(W):,} | 非白墙 {len(R):,}")
print(f"{'':<10} {'白墙':>10} {'非白墙':>10} {'比值':>8}")
print(f"{'信号 p50':<10} {np.median(W)*100:>9.3f}% {np.median(R)*100:>9.3f}% {np.median(W)/max(np.median(R),1e-9):>8.2f}")
print(f"{'信号 p90':<10} {np.percentile(W,90)*100:>9.3f}% {np.percentile(R,90)*100:>9.3f}%")
print(f"{'地板 p50':<10} {np.median(FW)*100:>9.3f}% {np.median(FR)*100:>9.3f}%   <- 同种子两遍, 必须远小于信号")
print(f"\n信噪比(信号中位/地板中位): 白墙 {np.median(W)/max(np.median(FW),1e-12):.1f}x | 非白墙 {np.median(R)/max(np.median(FR),1e-12):.1f}x")
print(f"\n按方差阈值切(能不能把墙切掉而留住别的):")
print(f"{'阈值':>8} {'白墙存活':>9} {'非白墙存活':>11} {'比值':>8}")
for t in np.percentile(np.concatenate([W, R]), [50, 70, 80, 90, 95, 99]):
    a, b = (W < t).mean(), (R < t).mean()
    print(f"{t*100:>7.3f}% {a*100:>8.1f}% {b*100:>10.1f}% {a/max(b,1e-9):>8.3f}")
