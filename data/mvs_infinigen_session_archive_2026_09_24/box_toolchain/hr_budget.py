#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确算 highres 臂的产出: 对全部 2172 个视频, 用 traj + highres_depth 的帧时间戳
(从 zip 中央目录 HTTP Range 解析, 不下图) 复算 有位姿帧 / 关键帧 / 磁盘。"""
import glob, os, re, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import pose_distance
from ak_pose_interp import read_traj, TrajInterp

v1k = {}
for l in open("/root/arkit_all.log"):
    m = re.match(r"\s+ak_(\d+): 图 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+)", l)
    if m: v1k[m.group(1)] = int(m.group(4))
sz = {}
for l in open("/root/ak2_sizes.txt"):
    p = l.split()
    if len(p) == 4: sz[p[0]] = (int(p[2]), int(p[3]))

rows = []
for f in sorted(glob.glob("/root/ak2_hr/*.hts")):
    vid = os.path.basename(f)[:-4]
    ls = open(f).read().split("\n")
    if not ls or not ls[0].startswith("#"): continue
    tot, got = (int(x) for x in ls[0][1:].split())
    stamps = [float(x) for x in ls[1:] if x.strip()]
    if abs(tot - 1 - got) > 1 or len(stamps) < 5: continue        # 中央目录没取全就丢弃
    try: ts_t, R_t, C_t = read_traj("/root/ak2_hr/%s.traj" % vid)
    except Exception: continue
    itp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20)
    Ts = [itp(t) for t in stamps]; ok = [T for T in Ts if T is not None]
    kf = []
    for T in ok:
        if not kf or pose_distance(kf[-1], T)[0] >= 0.1: kf.append(T)
    ex = sum(1 for t in stamps if abs(ts_t[int(np.abs(ts_t - t).argmin())] - t) < 0.005)
    rows.append(dict(vid=vid, n=len(stamps), wp=len(ok), ex=ex, kf=len(kf),
                     v1k=v1k.get(vid, 0), w=sz.get(vid, (0, 0))[0], h=sz.get(vid, (0, 0))[1]))

a = pd.DataFrame(rows)
print("=== highres 臂精确普查 (%d / 2172 个视频, 中央目录校验通过) ===" % len(a))
print("highres 帧数:   总 %d  中位/视频 %.0f  p10 %.0f  p90 %.0f" % (a.n.sum(), a.n.median(), a.n.quantile(.1), a.n.quantile(.9)))
print("5ms 容差能配上位姿的: %d (%.2f%%)   插值后有位姿: %d (%.2f%%)"
      % (a.ex.sum(), 100.*a.ex.sum()/a.n.sum(), a.wp.sum(), 100.*a.wp.sum()/a.n.sum()))
print("关键帧:         v2-highres 总 %d   (v1 在同一批视频上 %d, 比值 %.3f)"
      % (a.kf.sum(), a.v1k.sum(), a.kf.sum()/max(1, a.v1k.sum())))
print("   逐视频 v2/v1 关键帧比: 中位 %.3f  p10 %.3f  p90 %.3f"
      % ((a.kf/a.v1k.clip(lower=1)).median(), (a.kf/a.v1k.clip(lower=1)).quantile(.1), (a.kf/a.v1k.clip(lower=1)).quantile(.9)))
print("   关键帧 < 12 会被 SKIP 的视频: %d (%.1f%%)" % ((a.kf < 12).sum(), 100.*(a.kf < 12).mean()))
keep = a[a.kf >= 12]
MB = 1.78
print("磁盘: 产物 %.0f GB (%.3f TiB)  [仅关键帧>=12 的 %d 个视频, %d 关键帧 x %.2f MB]"
      % (keep.kf.sum()*MB/1024, keep.kf.sum()*MB/2**20, len(keep), keep.kf.sum(), MB))
print("      v1 在这 %d 个视频上的产物 %.0f GB  =>  净变化 %+.0f GB"
      % (len(a), a.v1k.sum()*MB/1024, (keep.kf.sum()-a.v1k.sum())*MB/1024))
print("下载: wide %.2f TiB + highres_depth %.2f TiB = %.2f TiB (流式, 用完即删)"
      % (a.w.sum()/2**40, a.h.sum()/2**40, (a.w.sum()+a.h.sum())/2**40))
print("      单视频解压峰值: 中位 %.0f MB  p90 %.0f MB  p99 %.0f MB  max %.0f MB"
      % (((a.w+a.h)*1.0).median()/2**20, ((a.w+a.h)).quantile(.9)/2**20,
         ((a.w+a.h)).quantile(.99)/2**20, (a.w+a.h).max()/2**20))
# 耗时: 试点实测 下载 MB/s 与 转换 帧/s
dl_MBps = (403+136+128+461+538+250)/(10+4+4+10+47)   # 试点 5+1 个视频的实测
cv_fps  = (347+85+27+44+102)/(22+5+2+3+6)
print("耗时: 试点实测 下载 %.0f MB/s, 转换 %.1f 关键帧/s" % (dl_MBps, cv_fps))
print("      批量单线程 ≈ 下载 %.1f h + 转换 %.1f h = %.1f h;  8 路并行 ≈ %.1f h"
      % ((a.w.sum()+a.h.sum())/2**20/dl_MBps/3600, keep.kf.sum()/cv_fps/3600,
         ((a.w.sum()+a.h.sum())/2**20/dl_MBps + keep.kf.sum()/cv_fps)/3600,
         ((a.w.sum()+a.h.sum())/2**20/dl_MBps + keep.kf.sum()/cv_fps)/3600/8*1.3))
