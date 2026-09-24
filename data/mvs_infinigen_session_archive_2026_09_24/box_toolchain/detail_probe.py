#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量 768x576 深度图在【全分辨率那一层】到底有没有信息。
判据要能报警: v1 的深度是 256x192 经 INTER_NEAREST x3 复制来的, 所以
  - 2x2 邻块非常数比例  应该接近 0 (块内 100% 是复制品)
  - blend.py 的 stage3(384x288) -> stage4(768x576) 不新增任何值
阴性对照: 把 FARO 的 768x576 图【再退化一次】(降到 256x192 再 NEAREST 拉回),
  指标必须掉回 v1 的水平 —— 否则说明这把尺子测的不是"有没有细节"。
"""
import glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import frame_range
W, H = 768, 576

def rd_area(d):
    m = (d > 0).astype(np.float32)
    num = cv2.resize(d*m, (W, H), interpolation=cv2.INTER_AREA)
    den = cv2.resize(m,   (W, H), interpolation=cv2.INTER_AREA)
    o = np.zeros((H, W), np.float32); ok = den > 0; o[ok] = num[ok]/den[ok]; return o

def nonconst2x2(x):
    """相邻 2x2 块里不是常数的比例 (只统计块内全有效的块)"""
    b = x[:H//2*2, :W//2*2].reshape(H//2, 2, W//2, 2).transpose(0, 2, 1, 3).reshape(-1, 4)
    ok = (b > 0).all(1)
    b = b[ok]
    return float((b.max(1) != b.min(1)).mean()), int(ok.sum())

def sup_px(x):
    fr = frame_range(x)
    if fr is None: return 0
    return int(((x >= fr[0]) & (x <= fr[1])).sum())

vd, vid = sys.argv[1], sys.argv[2]
hs = sorted((os.path.basename(p).split("_",1)[1][:-4] for p in glob.glob(vd+"/highres_depth/*.png")), key=float)
rows = []
for s in hs[::max(1, len(hs)//40)]:
    d = cv2.imread("%s/highres_depth/%s_%s.png" % (vd, vid, s), cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.
    faro = rd_area(d)
    lp = "%s/lowres_depth/%s_%s.png" % (vd, vid, s)
    if not os.path.exists(lp): continue
    lo = cv2.resize(cv2.imread(lp, cv2.IMREAD_UNCHANGED).astype(np.float32)/1000., (W, H), interpolation=cv2.INTER_NEAREST)
    # 阴性对照: FARO 也退化成 256x192 再拉回
    deg = cv2.resize(cv2.resize(faro, (256, 192), interpolation=cv2.INTER_AREA), (W, H), interpolation=cv2.INTER_NEAREST)
    r = {}
    for nm, x in (("FARO_area", faro), ("LiDAR_v1", lo), ("FARO_退化对照", deg)):
        nc, n = nonconst2x2(x)
        r[nm] = (nc, sup_px(x))
    rows.append(r)
names = ["FARO_area", "LiDAR_v1", "FARO_退化对照"]
print("样本 %d 帧   (768x576 全图 = %d px)" % (len(rows), W*H))
print("  %-16s %-22s %-18s" % ("", "2x2 非常数比例(中位)", "stage4 有效监督像素(中位)"))
for nm in names:
    nc = np.median([r[nm][0] for r in rows]); sp = np.median([r[nm][1] for r in rows])
    print("  %-16s %18.4f %18.0f  (%.1f%% of 442368)" % (nm, nc, sp, 100.*sp/(W*H)))
