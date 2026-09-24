#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分层汇总: A 层 = v1 SKIP 掉的 178 个; B 层 = 从 4869 个已转视频里随机抽的样本。
两层分开报, 再按 178 : 4866 加权外推到全域。"""
import glob, os, re, sys, random
import numpy as np, pandas as pd
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import pose_distance
from ak_pose_interp import read_traj, TrajInterp

v1 = {}
skipset = set()
for l in open("/root/arkit_all.log"):
    m = re.match(r"\s+ak_(\d+): 图 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+)", l)
    if m: v1[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.match(r"\s+SKIP (\d+): 关键帧 (\d+) < \d+\s+\{'imgs': (\d+).*'with_pose': (\d+)", l)
    if m:
        v1[m.group(1)] = (int(m.group(3)), int(m.group(4)), int(m.group(2))); skipset.add(m.group(1))
meta = pd.read_csv("/root/arkit_raw/raw/metadata.csv")
ups = set(str(int(v)) for v in meta[meta["is_in_upsampling"] == True]["video_id"])

rows = []
for tf in sorted(glob.glob("/root/ak2_proj/*.ts")):
    vid = os.path.basename(tf)[:-3]
    if vid not in v1: continue
    try: ts_t, R_t, C_t = read_traj("/root/ak2_proj/%s.traj" % vid)
    except Exception: continue
    itp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20)
    stamps = [float(x) for x in open(tf) if x.strip()]
    if len(stamps) < 5: continue
    Ts = [itp(t) for t in stamps]; ok = [T for T in Ts if T is not None]
    kf = []
    for T in ok:
        if not kf or pose_distance(kf[-1], T)[0] >= 0.1: kf.append(T)
    gaps = [pose_distance(kf[i], kf[i+1])[0] for i in range(len(kf)-1)]
    rows.append(dict(vid=vid, imgs=len(stamps), wp=len(ok), kf=len(kf),
                     gap=float(np.median(gaps)) if gaps else np.nan,
                     v1i=v1[vid][0], v1p=v1[vid][1], v1k=v1[vid][2],
                     skip=vid in skipset, ups=vid in ups))

def rep(name, rs):
    if not rs: return None
    a = np.array([[r["v1i"], r["v1p"], r["v1k"], r["imgs"], r["wp"], r["kf"]] for r in rs], float)
    g = np.array([r["gap"] for r in rs if np.isfinite(r["gap"])])
    print("%s  n=%d" % (name, len(rs)))
    print("   帧数核对 v1图==复算帧: %d/%d" % (int((a[:,0]==a[:,3]).sum()), len(a)))
    print("   有位姿占比(总): v1 %.4f -> v2 %.4f | 逐视频中位: %.4f -> %.4f"
          % (a[:,1].sum()/a[:,0].sum(), a[:,4].sum()/a[:,3].sum(),
             np.median(a[:,1]/np.maximum(a[:,0],1)), np.median(a[:,4]/np.maximum(a[:,3],1))))
    print("   关键帧: v1 %d -> v2 %d  (总倍数 x%.2f; 逐视频倍数 中位 %.2f p10 %.2f p90 %.2f)"
          % (a[:,2].sum(), a[:,5].sum(), a[:,5].sum()/max(1,a[:,2].sum()),
             np.median(a[:,5]/np.maximum(a[:,2],1)), np.percentile(a[:,5]/np.maximum(a[:,2],1),10),
             np.percentile(a[:,5]/np.maximum(a[:,2],1),90)))
    print("   v2 关键帧间距中位 %.4f (设计值 0.10)" % np.median(g))
    return a

B = [r for r in rows if not r["skip"]]
A = [r for r in rows if r["skip"]]
aB = rep("== B 层: 随机抽的已转视频 (代表 4866 个)", B)
aA = rep("== A 层: v1 因关键帧<12 被 SKIP 的视频 (全体 178 个)", A)
if aA is not None:
    print("   其中 v2 关键帧 >= 12 (可被救回) 的: %d / %d" % (int((aA[:,5] >= 12).sum()), len(aA)))
if aB is not None and aA is not None:
    mult = aB[:,5].sum()/max(1,aB[:,2].sum())
    print("\n== 外推到全域 ==")
    print("   已转 4866 个: v1 815521 关键帧 -> v2 约 %.0f 万 (x%.2f), 产物 %.2f -> %.2f TiB"
          % (815521*mult/1e4, mult, 815521*1.78/2**20, 815521*mult*1.78/2**20))
    resc = (aA[:,5] >= 12).mean(); kfA = np.median(aA[:,5])
    print("   被 SKIP 的 178 个: 约 %.0f%% 可救回, 新增约 %.0f 个场景 / %.0f 关键帧 / %.3f TiB"
          % (resc*100, 178*resc, 178*resc*kfA, 178*resc*kfA*1.78/2**20))
