# -*- coding: utf-8 -*-
"""09-13 的 layer_gap2.py,逐字保留度量口径,只把写死的两个臂换成命令行传入的一串臂。
纹理度量复用 filter.py 的 _tex_std(11x11 局部灰度标准差),只当分区依据,不当门。
  layer_gap_eps.py <名字>=<臂目录> [...]
"""
import sys, os, numpy as np, cv2
sys.path.insert(0, "/root"); os.environ.setdefault("DIFFMVS_DIR", "/root/diffmvs")
import tartanground2mvsnet as tg
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

def tex_std(bgr, win=11):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype("float32") / 255.0
    m = cv2.blur(g, (win, win)); m2 = cv2.blur(g * g, (win, win))
    return np.sqrt(np.clip(m2 - m * m, 0, None))

def cam(root, v):
    L = [l.rstrip() for l in open("%s/cams/%08d_cam.txt" % (root, v))]
    return (np.fromstring(" ".join(L[7:10]), dtype=np.float32, sep=" ").reshape(3, 3),
            np.fromstring(" ".join(L[1:5]), dtype=np.float32, sep=" ").reshape(4, 4))

def dep(root, v): return np.array(read_pfm("%s/depth_est/%08d.pfm" % (root, v))[0], dtype=np.float32)

pairs = {}
with open("/root/mvs_P16k/pair.txt") as f:
    n = int(f.readline())
    for _ in range(n):
        r = int(f.readline()); t = f.readline().split(); pairs[r] = [int(x) for x in t[1::2]]

print("%-8s %10s %8s %8s %8s %9s | %8s %8s %9s | %7s" %
      ("臂", "低纹理n", "p50", "p90", "p99", ">0.1m", "高p50", "高p90", "高>0.1m", "低/高"))
for spec in sys.argv[1:]:
    name, root = spec.split("=", 1)
    lowg = []; higg = []
    for ref in (131, 130, 122, 125, 121, 117, 116, 70):
        Ki, Ei = cam(root, ref); di = dep(root, ref)
        img = cv2.imread("%s/images/%08d.jpg" % (root, ref))
        ts = tex_std(img)
        thr = float(np.percentile(ts, 25))       # 报告口径:最平的 25% 像素 = 低纹理
        for src in pairs[ref][:3]:
            Kj, Ej = cam(root, src); dj = dep(root, src)
            d2r, x2r, y2r = tg.reproject_with_depth(di, Ki, Ei, dj, Kj, Ej)
            H, W = di.shape; xx, yy = np.meshgrid(np.arange(W), np.arange(H))
            ok = (np.sqrt((x2r - xx) ** 2 + (y2r - yy) ** 2) < 1) & (di > 0) & (d2r > 0)
            gap = np.abs(d2r - di)
            lowg.append(gap[ok & (ts <= thr)]); higg.append(gap[ok & (ts > thr)])
    lo = np.concatenate(lowg); hi = np.concatenate(higg)
    print("%-8s %10d %8.4f %8.4f %8.4f %9.4f | %8.4f %8.4f %9.4f | %7.2fx" %
          (name, len(lo), *np.percentile(lo, [50, 90, 99]), (lo > 0.1).mean(),
           np.percentile(hi, 50), np.percentile(hi, 90), (hi > 0.1).mean(),
           (lo > 0.1).mean() / max((hi > 0.1).mean(), 1e-9)), flush=True)
