# -*- coding: utf-8 -*-
"""「最保守」LiDAR 米尺变体:全帧 + 画面中心 r<600px + LiDAR 深度 0.5–1.5 m + high 置信,焦距 α ∈ {1, 陀螺版, ARKit 版}。"""
import sys, os, json
sys.dont_write_bytecode=True
import numpy as np, cv2
LRDIR=os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0,LRDIR)
import lidar_ruler as LR
ALPHA={'13f5':(1.0133,1.0270),'6d18':(1.0064,1.0154),'7353':(1.0169,1.0247)}
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
keys=np.array(sorted(ark)); ik=np.array(sorted(intr))
near=lambda arr,t: int(arr[np.argmin(np.abs(arr-t))])
P={}
for p in PR:
    i=int(p[0]); s=np.nonzero(pid==i)[0]
    if len(s)<20: continue
    ta=near(keys,int(round(p[1]*1e9))); tb=near(keys,int(round(p[2]*1e9)))
    R,t=LR.rel_pose(ark[ta],ark[tb]); P[i]=(R,t,intr[near(ik,ta)],intr[near(ik,tb)],s,p[1])
def run(alpha,center=None,drange=None,nb=500):
    out={}
    for i,(R,t,Ka,Kb,s,ta) in P.items():
        def nrm(u,v,K): return (u-K[2])/(alpha*K[0]),(v-K[3])/(alpha*K[1])
        xa,ya=nrm(ua[s],va[s],Ka); xb,yb=nrm(ub[s],vb[s],Kb)
        Xh=cv2.triangulatePoints(np.hstack([np.eye(3),np.zeros((3,1))]),np.hstack([R,t.reshape(3,1)]),np.stack([xa,ya]),np.stack([xb,yb]))
        Xe=(Xh[:3]/Xh[3]).T; za=Xe[:,2]; Xb=(R@Xe.T).T+t
        ra=np.hypot(Xe[:,0]/za-xa,Xe[:,1]/za-ya)*Ka[0]*alpha; rb=np.hypot(Xb[:,0]/Xb[:,2]-xb,Xb[:,1]/Xb[:,2]-yb)*Kb[0]*alpha
        C=-R.T@t; v2=Xe-C; an=np.degrees(np.arccos(np.clip(np.sum(Xe*v2,1)/(np.linalg.norm(Xe,axis=1)*np.linalg.norm(v2,axis=1)),-1,1)))
        m=(za>0)&(Xb[:,2]>0)&(ra<2)&(rb<2)&(an>1)&np.isfinite(dnn[s])&(dnn[s]>0)&(conf[s]>=2)
        if center: m&=np.hypot(ua[s]-960,va[s]-720)<center
        if drange: m&=(dnn[s]>=drange[0])&(dnn[s]<drange[1])
        if m.sum()>=20: out[i]=(np.median(dnn[s][m])/np.median(za[m]),ta)
    v=np.array([o[0] for o in out.values()]); tt=np.array([o[1] for o in out.values()])
    blk=((tt-tt.min())//3).astype(int); g=[v[blk==b] for b in np.unique(blk)]
    rng=np.random.default_rng(0)
    bs=[1/np.median(np.concatenate([g[j] for j in rng.integers(0,len(g),len(g))])) for _ in range(nb)]
    lo,hi=np.percentile(bs,[2.5,97.5])
    return (1/np.median(v)-1)*100,(lo-1)*100,(hi-1)*100,len(v)
for a,lbl in ((1.0,'α=1(原样)'),(ALPHA[sc][0],'α 陀螺版 %.4f'%ALPHA[sc][0]),(ALPHA[sc][1],'α ARKit版 %.4f'%ALPHA[sc][1])):
    for c,dr,l2 in ((None,None,'全部点'),(600,(0.5,1.5),'中心r<600 & 0.5–1.5m')):
        k,lo,hi,n=run(a,c,dr); print(sc,'%-18s %-22s k-1 %+.2f%% 95%% [%+.2f, %+.2f] 帧对 %d'%(lbl,l2,k,lo,hi,n),flush=True)
