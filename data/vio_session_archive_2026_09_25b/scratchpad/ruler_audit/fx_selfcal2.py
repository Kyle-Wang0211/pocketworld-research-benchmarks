# -*- coding: utf-8 -*-
"""焦距 + 径向畸变联合自检(固定 ARKit 相对位姿):归一化坐标 x_u = x_d·(1+k1·|x_d|²),x_d=(u−cx)/(α·fx)。
再用最优 (α,k1) 重新三角化,看 LiDAR 米尺 k 变多少。"""
import sys, os, json
sys.dont_write_bytecode=True
import numpy as np, cv2
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
P={}
for p in PR:
    i=int(p[0]); s=np.nonzero(pid==i)[0]
    if len(s)<20: continue
    ta=near(keys,int(round(p[1]*1e9))); tb=near(keys,int(round(p[2]*1e9)))
    R,t=LR.rel_pose(ark[ta],ark[tb])
    P[i]=(R,t,intr[near(ik,ta)],intr[near(ik,tb)],s,p[4])
def norm(u,v,K,alpha,k1):
    fx,fy,cx,cy=K; x=(u-cx)/(alpha*fx); y=(v-cy)/(alpha*fy); r2=x*x+y*y
    return x*(1+k1*r2), y*(1+k1*r2)
def cost(alpha,k1,center=None,tau=2.0):
    tot=0;n=0
    for i,(R,t,Ka,Kb,s,rot) in P.items():
        if rot<3: continue
        m=(ea[s]<4)&(eb[s]<4)&np.isfinite(z[s])
        if center is not None: m&=(np.hypot(ua[s]-960,va[s]-720)<center)
        if m.sum()<10: continue
        xa,ya=norm(ua[s][m],va[s][m],Ka,alpha,k1); xb,yb=norm(ub[s][m],vb[s][m],Kb,alpha,k1)
        E=skew(t/np.linalg.norm(t))@R
        ha=np.stack([xa,ya,np.ones_like(xa)],1); hb=np.stack([xb,yb,np.ones_like(xb)],1)
        Ea=ha@E.T; Etb=hb@E
        d2=(np.sum(hb*Ea,1)**2)/(Ea[:,0]**2+Ea[:,1]**2+Etb[:,0]**2+Etb[:,1]**2)*(Ka[0]*alpha)**2
        tot+=np.sum(np.minimum(d2,tau**2)); n+=len(d2)
    return tot/max(n,1)
al=np.arange(0.97,1.0451,0.0025)
print('==',sc)
for c in (400,):
    cc=[cost(a,0.0,center=c) for a in al]; print('   只用中心 r<%dpx:α 最优 %.4f'%(c,al[int(np.argmin(cc))]))
best=(1e9,None)
for k1 in np.arange(-0.10,0.1001,0.02):
    cc=[cost(a,k1) for a in al]; j=int(np.argmin(cc))
    if cc[j]<best[0]: best=(cc[j],(al[j],k1))
    print('   k1 %+.2f:α 最优 %.4f 代价 %.4f'%(k1,al[j],cc[j]))
a_opt,k1_opt=best[1]
print('   联合最优 α %.4f k1 %+.2f'%(a_opt,k1_opt))
# 用 (α,k1) 重新三角化 → 米尺 k
def ruler_k(alpha,k1):
    out=[]
    for i,(R,t,Ka,Kb,s,rot) in P.items():
        xa,ya=norm(ua[s],va[s],Ka,alpha,k1); xb,yb=norm(ub[s],vb[s],Kb,alpha,k1)
        Pa=np.hstack([np.eye(3),np.zeros((3,1))]); Pb=np.hstack([R,t.reshape(3,1)])
        Xh=cv2.triangulatePoints(Pa,Pb,np.stack([xa,ya]),np.stack([xb,yb])); Xe=(Xh[:3]/Xh[3]).T
        za=Xe[:,2]; zbb=(R@Xe.T).T[:,2]+t[2]
        pa_=Xe[:,:2]/za[:,None]; Xb=(R@Xe.T).T+t; pb_=Xb[:,:2]/Xb[:,2:3]
        ra=np.hypot(pa_[:,0]-xa,pa_[:,1]-ya)*Ka[0]*alpha; rb=np.hypot(pb_[:,0]-xb,pb_[:,1]-yb)*Kb[0]*alpha
        C=-R.T@t; v2=Xe-C
        cosg=np.sum(Xe*v2,1)/(np.linalg.norm(Xe,axis=1)*np.linalg.norm(v2,axis=1)); an=np.degrees(np.arccos(np.clip(cosg,-1,1)))
        m=(za>0)&(zbb>0)&(ra<2)&(rb<2)&(an>1)&np.isfinite(dnn[s])&(dnn[s]>0)&(conf[s]>=2)
        if m.sum()>=20: out.append(np.median(dnn[s][m])/np.median(za[m]))
    return (1/np.median(out)-1)*100,len(out)
for a,k1,l in ((1.0,0.0,'原样(α=1,无畸变)'),(a_opt,0.0,'只改焦距 α=%.4f'%a_opt),(a_opt,k1_opt,'焦距+畸变 最优'),(1.0,k1_opt,'只加畸变 k1')):
    k,n=ruler_k(a,k1); print('   米尺 k-1(ARKit)%-22s %+.2f%%  帧对 %d'%(l,k,n))
