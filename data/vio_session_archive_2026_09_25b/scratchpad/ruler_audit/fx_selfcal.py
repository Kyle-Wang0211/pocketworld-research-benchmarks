# -*- coding: utf-8 -*-
"""焦距自检:固定 ARKit 相对位姿(旋转近陀螺级精度),只把 fx,fy 乘一个 α,看哪个 α 让所有匹配点的 Sampson 极线误差最小。
α≠1 ⇒ ARKit 报的焦距与图像实际运动不符;LiDAR 米尺 k 会按 α 同比例偏(k_est = k·f_用/f_真)。"""
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
keys=np.array(sorted(ark)); ik=np.array(sorted(intr))
near=lambda arr,t: int(arr[np.argmin(np.abs(arr-t))])
def skew(t): return np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])
data=[]
for p in PR:
    if p[4]<3.0: continue   # 旋转 ≥3°
    i=int(p[0]); s=(pid==i)&np.isfinite(z)&(z>0)&(zb>0)&(ea<4)&(eb<4)
    if s.sum()<30: continue
    ta=near(keys,int(round(p[1]*1e9))); tb=near(keys,int(round(p[2]*1e9)))
    R,t=LR.rel_pose(ark[ta],ark[tb])
    Ka=intr[near(ik,ta)]; Kb=intr[near(ik,tb)]
    data.append((R,t/np.linalg.norm(t),Ka,Kb,np.stack([ua[s],va[s]],1),np.stack([ub[s],vb[s]],1),p[1]))
print('==',sc,'旋转≥3° 的帧对',len(data))
def cost(alpha,dc=(0,0),tau=2.0,sel=None):
    tot=0; n=0; meds=[]
    for j,(R,t,Ka,Kb,xa,xb,ta) in enumerate(data):
        if sel is not None and not sel(ta): continue
        def Kinv(K):
            fx,fy,cx,cy=K; fx*=alpha; fy*=alpha; cx+=dc[0]; cy+=dc[1]
            return np.array([[1/fx,0,-cx/fx],[0,1/fy,-cy/fy],[0,0,1]])
        F=Kinv(Kb).T@skew(t)@R@Kinv(Ka)
        ha=np.hstack([xa,np.ones((len(xa),1))]); hb=np.hstack([xb,np.ones((len(xb),1))])
        Fa=ha@F.T; Ftb=hb@F
        num=np.sum(hb*Fa,1)**2; den=Fa[:,0]**2+Fa[:,1]**2+Ftb[:,0]**2+Ftb[:,1]**2
        d2=num/den
        tot+=np.sum(np.minimum(d2,tau**2)); n+=len(d2)
    return tot/max(n,1)
al=np.arange(0.95,1.0501,0.0025)
c=np.array([cost(a) for a in al]); i=int(np.argmin(c))
if 0<i<len(al)-1:
    y0,y1,y2=c[i-1],c[i],c[i+1]; aopt=al[i]+0.5*(y0-y2)/(y0-2*y1+y2)*(al[1]-al[0])
else: aopt=al[i]
print('   全场:极线误差最小的焦距倍率 α = %.4f(即 ARKit 报的 fx 应乘 %.2f%%);代价 α=1 %.3f,最优 %.3f px²'%(aopt,(aopt-1)*100,cost(1.0),c.min()))
# 分两半看稳定性
T=np.array([d[6] for d in data]); mid=np.median(T)
for lbl,sel in (('前半',lambda ta:ta<mid),('后半',lambda ta:ta>=mid)):
    cc=np.array([cost(a,sel=sel) for a in al]); j=int(np.argmin(cc))
    print('   %s:α 最优 %.4f'%(lbl,al[j]))
json.dump({'alpha':aopt,'curve':list(zip(al.tolist(),c.tolist()))},open('fx_selfcal_%s.json'%sc,'w'))
