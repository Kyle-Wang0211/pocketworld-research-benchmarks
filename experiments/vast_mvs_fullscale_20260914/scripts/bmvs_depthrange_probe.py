# 量:BlendedMVS 官方 cam.txt 的 depth_min/max 与该帧 GT 深度图的实际分布是什么关系
# 零自由参数,纯测量
import os, sys, glob, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

ROOT = "/root/monotrain"
scans = [d for d in sorted(os.listdir(ROOT)) if os.path.isdir(os.path.join(ROOT, d, "cams"))]
# 只取 BlendedMVG 原生 scan(16进制长名),排除我们自己转的 TartanAir
bmvs = [s for s in scans if len(s) == 24 and all(c in "0123456789abcdef" for c in s)]
print("BlendedMVG scans:", len(bmvs))
rows = []
for s in bmvs[:40]:
    cams = sorted(glob.glob(os.path.join(ROOT, s, "cams", "*_cam.txt")))[:6]
    for c in cams:
        vid = os.path.basename(c).split("_")[0]
        pfm = os.path.join(ROOT, s, "rendered_depth_maps", vid + ".pfm")
        if not os.path.exists(pfm): continue
        lines = [l.rstrip() for l in open(c)]
        if len(lines) < 12: continue
        toks = lines[11].split()
        dmin, dmax = float(toks[0]), float(toks[-1])
        d = np.array(read_pfm(pfm)[0], dtype=np.float32)
        v = d[np.isfinite(d) & (d > 0)]
        if v.size < 1000: continue
        rows.append((dmin, dmax, float(v.min()), float(v.max()),
                     float(np.percentile(v,1)), float(np.percentile(v,99)),
                     float(((d>=dmin)&(d<=dmax)).mean())))
r = np.array(rows)
print("samples:", len(r))
print()
print("           cam_dmin / gt_min   cam_dmax / gt_max   cam_dmin/gt_p1   cam_dmax/gt_p99")
q = lambda a: "  ".join("%8.4f" % x for x in np.percentile(a, [5,25,50,75,95]))
print("ratio dmin/gtmin  p5/25/50/75/95:", q(r[:,0]/r[:,2]))
print("ratio dmax/gtmax  p5/25/50/75/95:", q(r[:,1]/r[:,3]))
print("ratio dmin/gt_p1  p5/25/50/75/95:", q(r[:,0]/r[:,4]))
print("ratio dmax/gt_p99 p5/25/50/75/95:", q(r[:,1]/r[:,5]))
print()
print("blend.py mask 覆盖率 (depth in [dmin,dmax]) p5/25/50/75/95:", q(r[:,6]))
