# -*- coding: utf-8 -*-
"""地面点 vs 非地面点:用 LiDAR 深度 + ARKit 位姿把每个匹配点抬到世界系(y 向上),按高度分出地面,分别算尺子 k。"""
import sys, os, json
sys.dont_write_bytecode=True
import numpy as np
LRDIR=os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0,LRDIR)
import lidar_ruler as LR
sc=sys.argv[1]
Z=np.load('pts_%s.npz'%sc); X=Z['pts']; PR=Z['pairs']
pid,ua,va,ub,vb,z,zb,ea,eb,ang,dnn,conf,dbil,drng=X.T; pid=pid.astype(int)
rec='full_'+sc
ts=[int(l.split(',')[0]) for l in open(rec+'/camera_index.csv').read().split('\n')[1:] if l]
ark,_=LR.arkit_poses(rec,rec+'/arkit_poses.tum',ts)
intr={}
for l in open(rec+'/intrinsics.jsonl'):
    if l.strip():
        d=json.loads(l); intr[int(round(d['t']*1e9))]=d['intrinsics_fxfycxcy']
ik=np.array(sorted(intr))
def K_at(tns):
    j=ik[np.argmin(np.abs(ik-tns))]; return intr[int(j)]
ta_ns={}
for p in PR:
    t=int(round(p[1]*1e9)); 
    # 找 ARKit 键(整数纳秒)
    ta_ns[int(p[0])]=t
keys=np.array(sorted(ark))
yw=np.full(len(X),np.nan)
for p in np.unique(pid):
    t=ta_ns[p]; j=keys[np.argmin(np.abs(keys-t))]
    if abs(j-t)>1000: continue
    Rwc,C=ark[int(j)]
    fx,fy,cx,cy=K_at(j)
    s=pid==p
    ray=np.stack([(ua[s]-cx)/fx,(va[s]-cy)/fy,np.ones(s.sum())],1)*dnn[s][:,None]
    Pw=(Rwc@ray.T).T+np.asarray(C)
    yw[s]=Pw[:,1]
m0=np.isfinite(z)&(z>0)&(zb>0)&(ea<2)&(eb<2)&(ang>1)&np.isfinite(dnn)&(dnn>0)&(conf>=2)&np.isfinite(yw)
h,e=np.histogram(yw[m0],bins=np.arange(np.nanpercentile(yw[m0],0.5),np.nanpercentile(yw[m0],99.5),0.01))
floor=e[np.argmax(h[:max(5,len(h)//3)])]+0.005   # 最低三分之一里的峰
isfloor=np.abs(yw-floor)<0.03
print('==',sc,'地面高度 %.3f m;地面点占有效点 %.1f%%'%(floor,100*isfloor[m0].mean()))
def kpp(mask,minpts=15):
    m=m0&mask; out=[]
    for p in np.unique(pid[m]):
        s=m&(pid==p)
        if s.sum()>=minpts: out.append(np.median(dnn[s])/np.median(z[s]))
    return (1/np.median(out)-1)*100 if out else np.nan, len(out)
for lbl,mask in (('全部',np.ones(len(X),bool)),('只地面(±3cm)',isfloor),('只非地面(高于地面 8cm 以上)',yw>floor+0.08)):
    k,n=kpp(mask); print('   %-28s k-1 %+.2f%%  帧对 %d'%(lbl,k,n))
# 同一帧对内:地面点中位比值 / 非地面点中位比值(轨迹尺度约掉)
rat=[]
for p in np.unique(pid[m0]):
    a=m0&(pid==p)&isfloor; b=m0&(pid==p)&(yw>floor+0.08)
    if a.sum()>=10 and b.sum()>=10:
        rat.append(np.median(dnn[a]/z[a])/np.median(dnn[b]/z[b]))
if rat: print('   同帧对内 地面/非地面 的 LiDAR÷三角化 比值:中位 %+.2f%%(帧对 %d,IQR %.2f%%)'%((np.median(rat)-1)*100,len(rat),100*np.subtract(*np.percentile(rat,[75,25]))))
