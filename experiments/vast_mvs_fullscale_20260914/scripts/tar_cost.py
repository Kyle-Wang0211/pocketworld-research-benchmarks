import os, glob, sys, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
R = 29.68   # BlendedMVG 官方 cam 文件的 dmax/dmin 比值 p99, 取自官方数据分布
names = [l.strip() for l in open("/root/MonoMVSNet/lists/ours/train.txt") if l.strip() and l.startswith("ta_")]
rng = np.random.default_rng(0)
pick = rng.choice(len(names), size=min(25, len(names)), replace=False)
tot_before, tot_after, n = 0.0, 0.0, 0
ratios = []
for i in pick:
    s = names[i]
    cams = sorted(glob.glob(f"/root/monotrain/{s}/cams/*_cam.txt"))
    for c in cams[::7][:6]:
        idx = os.path.basename(c).split("_")[0]
        p = f"/root/monotrain/{s}/rendered_depth_maps/{idx}.pfm"
        if not os.path.exists(p): continue
        d = np.array(read_pfm(p)[0], dtype=np.float32)
        L = open(c).read().rstrip("\n").split("\n"); a = L[-1].split()
        lo, hi = float(a[0]), float(a[-1])
        if not (hi > lo > 0): continue
        ratios.append(hi / lo)
        v = d[np.isfinite(d) & (d > 0)]
        if v.size < 100: continue
        tot_before += float(((v >= lo) & (v <= hi)).mean())
        hi2 = min(hi, lo * R)
        tot_after += float(((v >= lo) & (v <= hi2)).mean())
        n += 1
ratios = np.array(ratios)
print(f"抽样 {n} 帧 TartanAir")
print(f"  当前 dmax/dmin 比值: p50 {np.median(ratios):.1f}  p90 {np.percentile(ratios,90):.1f}  max {ratios.max():.0f}")
print(f"  超过 R={R} 的帧占 {(ratios>R).mean()*100:.1f}%")
print(f"  参与损失的有效像素比例: 当前 {tot_before/n*100:.1f}%  ->  压到 R 后 {tot_after/n*100:.1f}%")
print(f"  代价 = 丢掉 {(tot_before-tot_after)/max(tot_before,1e-9)*100:.1f}% 的远端像素(天空/地平线)")
