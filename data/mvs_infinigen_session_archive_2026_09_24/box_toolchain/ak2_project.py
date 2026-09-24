#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 /root/ak2_proj/<vid>.traj + <vid>.ts 精确复算 v2(lowres 臂) 的 有位姿/关键帧,
与 /root/arkit_all.log 里 v1 的实测数逐视频配对比较。不下任何图像。"""
import glob, os, re, sys
import numpy as np
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import pose_distance
from ak_pose_interp import read_traj, TrajInterp

v1 = {}
for l in open("/root/arkit_all.log"):
    m = re.match(r"\s+ak_(\d+): 图 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+)", l)
    if m: v1[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.match(r"\s+SKIP (\d+): 关键帧 (\d+) < \d+\s+\{'imgs': (\d+).*'with_pose': (\d+)", l)
    if m: v1[m.group(1)] = (int(m.group(3)), int(m.group(4)), int(m.group(2)))

rows = []
for tf in sorted(glob.glob("/root/ak2_proj/*.ts")):
    vid = os.path.basename(tf)[:-3]
    try:
        ts_t, R_t, C_t = read_traj("/root/ak2_proj/%s.traj" % vid)
    except Exception:
        continue
    itp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20)
    stamps = [float(x) for x in open(tf) if x.strip()]
    if not stamps: continue
    Ts = [itp(t) for t in stamps]
    ok = [T for T in Ts if T is not None]
    kf = []
    for T in ok:
        if not kf or pose_distance(kf[-1], T)[0] >= 0.1: kf.append(T)
    gaps = [pose_distance(kf[i], kf[i+1])[0] for i in range(len(kf)-1)]
    rows.append(dict(vid=vid, imgs=len(stamps), wp=len(ok), kf=len(kf),
                     gap=float(np.median(gaps)) if gaps else 0.0,
                     v1=v1.get(vid)))
print("复算 %d 个视频 (不下图)" % len(rows))
have = [r for r in rows if r["v1"]]
print("有 v1 实测可配对的 %d 个" % len(have))
a = np.array([[r["v1"][0], r["v1"][1], r["v1"][2], r["imgs"], r["wp"], r["kf"]] for r in have], float)
print("  帧数核对: v1 图 vs 复算帧 一致的 %d / %d" % (int((a[:,0]==a[:,3]).sum()), len(a)))
print("  有位姿占比: v1 %.4f -> v2 %.4f  (逐视频中位 %.4f -> %.4f)"
      % (a[:,1].sum()/a[:,0].sum(), a[:,4].sum()/a[:,3].sum(),
         np.median(a[:,1]/a[:,0]), np.median(a[:,4]/a[:,3])))
print("  关键帧总数: v1 %d -> v2 %d  (x%.3f)" % (a[:,2].sum(), a[:,5].sum(), a[:,5].sum()/max(1,a[:,2].sum())))
print("  逐视频关键帧倍数: 中位 %.3f p10 %.3f p90 %.3f"
      % (np.median(a[:,5]/np.maximum(a[:,2],1)), np.percentile(a[:,5]/np.maximum(a[:,2],1),10),
         np.percentile(a[:,5]/np.maximum(a[:,2],1),90)))
g = np.array([r["gap"] for r in rows if r["gap"] > 0])
print("  v2 关键帧间距 (pose_distance) 中位 %.4f (设计值 0.10)" % np.median(g))
lost = [r for r in have if r["v1"][2] < 12]
print("  v1 因关键帧<12 被 SKIP 的 %d 个 -> v2 关键帧中位 %d, 其中 >=12 的 %d 个"
      % (len(lost), int(np.median([r["kf"] for r in lost])) if lost else 0,
         sum(1 for r in lost if r["kf"] >= 12)))
