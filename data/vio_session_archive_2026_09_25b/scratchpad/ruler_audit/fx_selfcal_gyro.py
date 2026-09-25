# -*- coding: utf-8 -*-
"""焦距自检(陀螺版):相对旋转改用录制的 100 Hz 陀螺积分(帧时间 + 曝光中点 7.7 ms),平移方向仍取 ARKit。
与 ARKit 旋转版比较 ⇒ 若两者都给 α>1,说明是 ARKit 报的焦距偏小,而不是 ARKit 旋转幅值偏大。"""
import sys, os, json
sys.dont_write_bytecode=True
import numpy as np
LRDIR=os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0,LRDIR)
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0,SP+'/wobble/tools')
import lidar_ruler as LR, wob
from rotcal import gyro_integrate
BG={'13f5':[-0.0063,0.0001,0.0029],'6d18':[-0.0066,0.0015,0.0021],'7353':[-0.0008,-0.0051,0.0051]}
sc=sys.argv[1]
Z=np.load('pts_%s.npz'%sc); X=Z['pts']; PR=Z['pairs']
pid,ua,va,ub,vb,z,zb,ea,eb,ang,dnn,conf,dbil,drng=X.T; pid=pid.astype(int)
rec='full_'+sc
ts=[int(l.split(',')[0]) for l in open(rec+'/camera_index.csv').read().split('\n')[1:] if l]
ark,_=LR.arkit_poses(rec,rec+'/arkit_poses.tum',ts)
intr={}
for l in open(rec+'/intrinsics.jsonl'):
    if l.strip():
        d=json.loads(l); intr[int(round(d['t']*1e9))]=(d['intrinsics_fxfycxcy'],d.get('exposure_s',0.0))
E=json.load(open(SP+'/wobble/stats/extrinsic_from_arkit.json')); Rbc=wob.qmat(np.array([E['q_bc']]))[0]
imu=wob.load_imu(sc)
keys=np.array(sorted(ark)); ik=np.array(sorted(intr))
near=lambda arr,t: int(arr[np.argmin(np.abs(arr-t))])
def skew(t): return np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])
data=[]; dang=[]
for p in PR:
    if p[4]<3.0: continue
    i=int(p[0]); s=(pid==i)&np.isfinite(z)&(z>0)&(zb>0)&(ea<4)&(eb<4)
    if s.sum()<30: continue
    ta=near(keys,int(round(p[1]*1e9))); tb=near(keys,int(round(p[2]*1e9)))
    Ra,t=LR.rel_pose(ark[ta],ark[tb])
    Ka,xa_=intr[near(ik,ta)]; Kb,xb_=intr[near(ik,tb)]
    off=0.0077
    Rab=gyro_integrate(imu,ta*1e-9+off,tb*1e-9+off,bias=np.array(BG[sc]))
    Rg=(Rbc.T@Rab@Rbc).T
    c=np.clip((np.trace(Rg.T@Ra)-1)/2,-1,1); dang.append(np.degrees(np.arccos(c)))
    data.append((Rg,Ra,t/np.linalg.norm(t),Ka,Kb,np.stack([ua[s],va[s]],1),np.stack([ub[s],vb[s]],1)))
print('==',sc,'帧对',len(data),'陀螺 vs ARKit 相对旋转差 中位 %.3f° p90 %.3f°'%(np.median(dang),np.percentile(dang,90)))
def cost(alpha,use,tau=2.0):
    tot=0;n=0
    for Rg,Ra,t,Ka,Kb,xa,xb in data:
        R=Rg if use=='gyro' else Ra
        def Kinv(K):
            fx,fy,cx,cy=K; fx*=alpha; fy*=alpha
            return np.array([[1/fx,0,-cx/fx],[0,1/fy,-cy/fy],[0,0,1]])
        F=Kinv(Kb).T@skew(t)@R@Kinv(Ka)
        ha=np.hstack([xa,np.ones((len(xa),1))]); hb=np.hstack([xb,np.ones((len(xb),1))])
        Fa=ha@F.T; Ftb=hb@F
        d2=np.sum(hb*Fa,1)**2/(Fa[:,0]**2+Fa[:,1]**2+Ftb[:,0]**2+Ftb[:,1]**2)
        tot+=np.sum(np.minimum(d2,tau**2)); n+=len(d2)
    return tot/n
al=np.arange(0.96,1.0601,0.0025)
for use in ('arkit','gyro'):
    c=np.array([cost(a,use) for a in al]); i=int(np.argmin(c))
    y0,y1,y2=c[max(i-1,0)],c[i],c[min(i+1,len(c)-1)]
    ao=al[i]+(0.5*(y0-y2)/(y0-2*y1+y2)*(al[1]-al[0]) if 0<i<len(al)-1 else 0)
    print('   旋转取 %-5s:α 最优 %.4f(代价 α=1 %.3f → 最优 %.3f px²)'%(use,ao,cost(1.0,use),c.min()))
