import os, glob, sys, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
ROOT = "/root/ta2/blendfmt"
rng = np.random.default_rng(1)
scans = sorted(d for d in glob.glob(f"{ROOT}/*") if os.path.exists(f"{d}/cams/pair.txt"))
pick = rng.choice(len(scans), size=min(30, len(scans)), replace=False)
loss, dmins, cut_depth_med = [], [], []
gutted = 0; n = 0
for i in pick:
    s = scans[i]
    for c in sorted(glob.glob(f"{s}/cams/*_cam.txt"))[::9][:5]:
        idx = os.path.basename(c).split("_")[0]
        p = f"{s}/rendered_depth_maps/{idx}.pfm"
        if not os.path.exists(p): continue
        d = np.array(read_pfm(p)[0], dtype=np.float32)
        v = d[np.isfinite(d) & (d > 0)]
        if v.size < 100: continue
        L = open(c).read().rstrip("\n").split("\n"); a = L[-1].split()
        lo, hi = float(a[0]), float(a[-1])            # 已是压缩后的
        inside = ((v >= lo) & (v <= hi)).mean()
        loss.append(1 - inside); dmins.append(lo); n += 1
        out = v[(v < lo) | (v > hi)]
        if out.size: cut_depth_med.append(float(np.median(out)))
        if inside < 0.5: gutted += 1
loss = np.array(loss); dmins = np.array(dmins); cm = np.array(cut_depth_med)
print(f"抽样 {n} 帧(压缩后的 TartanAir)")
print(f"  被排除像素占比: 中位 {np.median(loss)*100:.1f}%  p90 {np.percentile(loss,90)*100:.1f}%  最大 {loss.max()*100:.1f}%")
print(f"  被掏空的帧(有效像素<50%): {gutted}/{n} = {gutted/n*100:.1f}%   <- 这才是真损失")
print(f"  被排除像素的深度中位: {np.median(cm):.1f} m   (若远大于场景尺度=天空,无价值)")
print(f"  这些帧的 dmin: 中位 {np.median(dmins):.3f} m  p5 {np.percentile(dmins,5):.4f} m  最小 {dmins.min():.5f} m")
bad = dmins < 0.05
print(f"  dmin<5cm 的病态帧: {bad.sum()}/{n} = {bad.mean()*100:.1f}%,"
      f" 它们的排除率 中位 {np.median(loss[bad])*100:.1f}%" if bad.sum() else "  无 dmin<5cm 的帧")
