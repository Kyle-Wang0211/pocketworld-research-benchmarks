# -*- coding: utf-8 -*-
"""bug ① 动手前的前提检验: 「天空切点」到底是不是一个自由参数?

假设: 真几何与天空之间存在 1.5-2 个数量级的空白 ⇒ 切点落在空白内任意位置, 结果相同。
若成立, 则「排除天空」不是调参, 是把双峰分布切在它自己的断崖上。
若不成立(不同切点给出不同 depth_max), 我就不能改, 得回去要官方分割标注。

做法: 抽 400 个受影响帧, 在 5 个相差 20 倍的切点下分别按官方 p99 规则算 depth_max,
      看它们是否一致(相对差 < 1%)。
"""
import glob, os, sys, random
import numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

CUTS = [500.0, 1000.0, 2000.0, 5000.0, 10000.0]

fs = sorted(glob.glob("/root/monotrain/ta_*/cams/*_cam.txt"))
random.seed(20260922)
aff = []
for p in random.sample(fs, 12000):
    dm = float(open(p).read().strip().split("\n")[-1].split()[-1])
    if dm > 1000:
        aff.append(p)
print("抽 12000 个 cam, 受影响(dmax>1000) %d 个, 取前 400 个查" % len(aff))

agree = 0; checked = 0; nogap = []
rows = []
for p in aff[:400]:
    sc = os.path.dirname(os.path.dirname(p)); ix = os.path.basename(p).split("_")[0]
    f = "%s/rendered_depth_maps/%s.pfm" % (sc, ix)
    if not os.path.exists(f):
        continue
    d = np.array(read_pfm(f)[0])
    fin = np.isfinite(d) & (d > 0)
    res = []
    for c in CUTS:
        v = d[fin & (d < c)]
        res.append(np.percentile(v, 99) if v.size >= 100 else np.nan)
    res = np.array(res)
    checked += 1
    if np.any(~np.isfinite(res)):
        nogap.append((os.path.basename(sc), "某切点下有效像素不足"))
        continue
    rel = (res.max() - res.min()) / max(res.max(), 1e-9)
    if rel < 0.01:
        agree += 1
    else:
        nogap.append((os.path.basename(sc), "切点间相对差 %.1f%%  值 %s" % (100 * rel, np.round(res, 1).tolist())))
    if len(rows) < 6:
        rows.append((os.path.basename(sc)[:38], np.round(res, 2).tolist()))

print("\n样例(5 个切点下的 depth_max, 切点相差 20 倍):")
print("  %-40s %s" % ("场景", "  ".join("cut=%d" % c for c in CUTS)))
for n, r in rows:
    print("  %-40s %s" % (n, "  ".join("%9.2f" % x for x in r)))

print("\n总计 %d 帧: %d 帧 (%.1f%%) 在 5 个切点下 depth_max 相对差 < 1%%" %
      (checked, agree, 100 * agree / max(checked, 1)))
if nogap:
    print("不一致的 %d 帧, 前 6 例:" % len(nogap))
    for n, why in nogap[:6]:
        print("   %-40s %s" % (n[:38], why))
print("\n⇒ %s" % ("✅ 切点不是自由参数, 可以改" if agree / max(checked, 1) > 0.95
                  else "🔴 切点会改变结果, 不能自己定, 需要官方分割标注"))
