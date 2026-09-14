# -*- coding: utf-8 -*-
"""逐 epoch 测「多层程度」,与 val 曲线对照,判断 val 这把尺子可不可信。

判据 = ref 间深度分歧(逐像素全量统计, 确定性, 无 RANSAC 随机性)
       与 09-13 的 layer_gap2.py 完全同法:
         - 用官方 filter.py 的 reproject_with_depth
         - dist<1px 才比深度(官方 geo_pixel_thres)
         - 按纹理分区: 最平的 25% 像素 = 低纹理(报告口径)
       低纹理区 >0.1m 占比 = 多层的直接度量(层间距 p99 曾测得 0.32m)

⚠️ 已被证伪、不再使用的判据: 平面检测的「平行面对数」
   (同点云跑 5 次极差 13 对, 噪声 > 信号 —— 见 09-13 记录)
"""
import sys, os, numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
os.chdir("/root/diffmvs")
from filter import reproject_with_depth
from datasets.data_io import read_pfm

GEO_PIX = 1.0
REFS = (131, 130, 122, 125, 121, 117, 116, 70)


def tex_std(bgr, win=11):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype("float32") / 255.0
    m = cv2.blur(g, (win, win))
    m2 = cv2.blur(g * g, (win, win))
    return np.sqrt(np.clip(m2 - m * m, 0, None))


def cam(root, v):
    L = [l.rstrip() for l in open("%s/cams/%08d_cam.txt" % (root, v))]
    return (np.fromstring(" ".join(L[7:10]), dtype=np.float32, sep=" ").reshape(3, 3),
            np.fromstring(" ".join(L[1:5]), dtype=np.float32, sep=" ").reshape(4, 4))


def dep(root, v):
    return np.array(read_pfm("%s/depth_est/%08d.pfm" % (root, v))[0], dtype=np.float32)


pairs = {}
with open("/root/mvs_P16k/pair.txt") as f:
    n = int(f.readline())
    for _ in range(n):
        r = int(f.readline())
        t = f.readline().split()
        pairs[r] = [int(x) for x in t[1::2]]

print("%-22s %10s %10s %10s %10s" % ("臂", "低纹理p50", "低纹理>0.1m", "有纹理p50", "低/高比"))
for name, root in [a.split("=", 1) for a in sys.argv[1:]]:
    if not os.path.isdir(os.path.join(root, "depth_est")):
        print("%-22s (无深度图,跳过)" % name)
        continue
    lo, hi = [], []
    for ref in REFS:
        Ki, Ei = cam(root, ref)
        di = dep(root, ref)
        img = cv2.imread("%s/images/%08d.jpg" % (root, ref))
        ts = tex_std(img)
        thr = float(np.percentile(ts, 25))
        H, W = di.shape
        xx, yy = np.meshgrid(np.arange(W), np.arange(H))
        for src in pairs[ref][:3]:
            Kj, Ej = cam(root, src)
            dj = dep(root, src)
            d2r, x2r, y2r, _, _ = reproject_with_depth(di, Ki, Ei, dj, Kj, Ej)
            ok = (np.sqrt((x2r - xx) ** 2 + (y2r - yy) ** 2) < GEO_PIX) & (di > 0) & (d2r > 0)
            gap = np.abs(d2r - di)
            lo.append(gap[ok & (ts <= thr)])
            hi.append(gap[ok & (ts > thr)])
    lo = np.concatenate(lo)
    hi = np.concatenate(hi)
    p50l = float(np.percentile(lo, 50))
    p50h = float(np.percentile(hi, 50))
    frac = float((lo > 0.10).mean())
    print("%-22s %9.4fm %10.4f %9.4fm %9.2fx" % (name, p50l, frac, p50h, p50l / max(p50h, 1e-9)))
