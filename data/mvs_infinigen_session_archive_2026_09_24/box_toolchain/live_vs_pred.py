import re, glob, os, numpy as np
# 已跑完的视频的【实际】关键帧 vs 普查【预测】关键帧 —— 只比这批, 避免早期视频偏大造成的假警报
pat=re.compile(r"ak_(\d+)\[highres\]: 帧 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+)")
act={}
for f in ("/root/ak2_all_v2.log","/root/ak2_smoke.log","/root/ak2_pilot_hi.log"):
    if os.path.exists(f):
        for l in open(f):
            m=pat.search(l)
            if m: act[m.group(1)]=(int(m.group(2)),int(m.group(4)))
import sys
sys.path.insert(0,"/root/ta2"); sys.path.insert(0,"/root")
# 预测来自之前 hr_budget 的同一算法, 这里直接复用已缓存的 .hts + traj
from tartanair_to_blend import pose_distance
from ak_pose_interp import read_traj, TrajInterp
pred={}
for v in act:
    f="/root/ak2_hr/%s.hts"%v
    if not os.path.exists(f): continue
    ls=open(f).read().split("\n")
    if not ls[0].startswith("#"): continue
    st=[float(x) for x in ls[1:] if x.strip()]
    if len(st)<5: continue
    try: ts,R,C=read_traj("/root/ak2_hr/%s.traj"%v)
    except Exception: continue
    itp=TrajInterp(ts,R,C,max_gap=0.20)
    ok=[T for T in (itp(t) for t in st) if T is not None]
    kf=[]
    for T in ok:
        if not kf or pose_distance(kf[-1],T)[0]>=0.1: kf.append(T)
    pred[v]=(len(st),len(kf))
com=[v for v in act if v in pred]
a=np.array([[act[v][0],act[v][1],pred[v][0],pred[v][1]] for v in com],float)
print("已完成且有普查预测的 %d 个视频"%len(com))
print("  帧数   实测 %d vs 预测 %d  (逐视频一致 %d)"%(a[:,0].sum(),a[:,2].sum(),int((a[:,0]==a[:,2]).sum())))
print("  关键帧 实测 %d vs 预测 %d  (逐视频一致 %d, 比值 %.4f)"%(a[:,1].sum(),a[:,3].sum(),int((a[:,1]==a[:,3]).sum()),a[:,1].sum()/a[:,3].sum()))
print("  => 按这个比值, 全量 223,683 预测关键帧 对应实际 %.0f, 产物 %.0f GB"%(223683*a[:,1].sum()/a[:,3].sum(), 223683*a[:,1].sum()/a[:,3].sum()*1.789/1024))
