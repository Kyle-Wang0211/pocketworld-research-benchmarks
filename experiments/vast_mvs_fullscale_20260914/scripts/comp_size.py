#!/usr/bin/env python3
"""被方差门删掉的像素:是零散的点,还是成片的?
若零散 => Canny 滞回逻辑(严门做种子, 只删含种子的连通块)能保住物体表面。
若成片 => 模型在那些表面上确实也在犹豫, 救不回来。
分白墙区/非白墙区分别统计连通块大小。"""
import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
VD = "/root/ms/varmap16"; T = 0.000624
frames = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{VD}/*.npy"))
sz_wall, sz_rest = [], []
for i in frames[::3]:
    v = np.load(f"{VD}/{i:08d}.npy")
    d = np.array(read_pfm(f"/root/off768_true/depth_est/{i:08d}.pfm")[0], dtype=np.float32)
    img = cv2.imread(f"/root/off768_true/images/{i:08d}.jpg")
    if img is None: continue
    img = cv2.resize(img, (v.shape[1], v.shape[0]), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    wall = (g > 150) & (np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3)) < 4)
    kill = ((v >= T) & (d > 0)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(kill, connectivity=8)
    for k in range(1, n):
        a = int(stats[k, cv2.CC_STAT_AREA])
        m = (lab == k)
        (sz_wall if wall[m].mean() > 0.5 else sz_rest).append(a)
sw, sr = np.array(sz_wall), np.array(sz_rest)
print(f"抽 {len(frames[::3])} 帧;删除连通块:白墙区 {len(sw):,} 块 | 非白墙区 {len(sr):,} 块")
for name, a in (("白墙区", sw), ("非白墙区", sr)):
    if not len(a): continue
    tot = a.sum()
    print(f"  {name}: 块大小 p50 {np.median(a):.0f}px  p90 {np.percentile(a,90):.0f}  最大 {a.max():,}")
    for th in (4, 16, 64, 256):
        small = a[a < th]
        print(f"     <{th:>3}px 的块占 {len(small)/len(a)*100:5.1f}% 的块数, 但只占 {small.sum()/tot*100:5.1f}% 的删除像素")
