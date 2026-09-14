#!/usr/bin/env python3
"""决定性测量:把 CasDiffMVS 官方几何门的"至少几个视图一致"逐档拉高,
看白墙像素会不会比非白墙像素先死。

目标已被用户重新定义:不是"把墙重建准",而是"不知道就别输出"——
白墙粘连 = 瞎造的几何。所以我们要找的是一个能**优先杀掉瞎造区**的门。

判据:某个阈值下 白墙存活率 → ~0 而 非白墙存活率仍高,即为可用的门。
若两者同步下降(比值不变),说明视图数这把刀切不开它们,要换判据。
"""
import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency
from datasets.data_io import read_pfm

D = "/root/out_official"
THRESH = [1, 2, 3, 4, 5, 6, 7, 8, 10]

def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), dtype=np.float64, sep=" ").reshape(4, 4)
    K = np.fromstring(" ".join(L[7:10]), dtype=np.float64, sep=" ").reshape(3, 3)
    return K, E

raw, wall = {}, {}
for f in sorted(glob.glob(f"{D}/depth_est/*.pfm")):
    i = int(os.path.basename(f)[:8])
    d = np.array(read_pfm(f)[0], dtype=np.float32)
    K, E = read_cam(f"{D}/cams/{i:08d}_cam.txt")
    raw[i] = (d, K, E)
    img = cv2.imread(f"{D}/images/{i:08d}.jpg")
    img = cv2.resize(img, (d.shape[1], d.shape[0]), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # 白墙判据:亮 且 局部二阶导小(无纹理)。只用来分区做统计, 不参与任何过滤
    wall[i] = (g > 150) & (np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3)) < 4)
print(f"载入 {len(raw)} 帧 {next(iter(raw.values()))[0].shape}; 白墙像素占全局 "
      f"{np.mean([w.mean() for w in wall.values()])*100:.1f}%", flush=True)

lines = [l.strip() for l in open("/root/mvs_P16k/pair.txt") if l.strip()]
n = int(lines[0]); pairs = []; k = 1
for _ in range(n):
    ref = int(lines[k]); t = lines[k+1].split(); m = int(t[0])
    pairs.append((ref, [int(t[1+2*j]) for j in range(m)][:10])); k += 2

wall_keep = {t: [] for t in THRESH}
rest_keep = {t: [] for t in THRESH}
for ci, (ref, srcs) in enumerate(pairs):
    if ref not in raw: continue
    dref, Kr, Er = raw[ref]
    gsum = np.zeros(dref.shape, np.int32)
    for s in srcs:
        if s not in raw: continue
        ds, Ks, Es = raw[s]
        gm, _, _, _ = check_geometric_consistency(dref, Kr, Er, ds, Ks, Es, 30.0, 0.3, 1.0, 0.01)
        gsum += gm.astype(np.int32)
    w = wall[ref] & (dref > 0); r = (~wall[ref]) & (dref > 0)
    for t in THRESH:
        keep = gsum >= t
        if w.sum() > 500: wall_keep[t].append(float(keep[w].mean()))
        if r.sum() > 500: rest_keep[t].append(float(keep[r].mean()))
    if ci % 40 == 0: print(f"  ...{ci}/{len(pairs)}", flush=True)

print(f"\n{'门槛':>5} {'白墙存活':>9} {'非白墙存活':>11} {'比值(越小越好)':>14}  含义")
for t in THRESH:
    a = np.mean(wall_keep[t]); b = np.mean(rest_keep[t])
    print(f"{t:>5} {a*100:>8.1f}% {b*100:>10.1f}% {a/max(b,1e-9):>13.3f}")
