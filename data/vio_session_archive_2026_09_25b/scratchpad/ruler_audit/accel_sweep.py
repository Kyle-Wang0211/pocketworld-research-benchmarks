# -*- coding: utf-8 -*-
import sys, json
sys.dont_write_bytecode=True
import numpy as np
import accel_diag as A
sc=sys.argv[1]
t,R,P,imu=A.load(sc)
res={}
def run(tag,**kw):
    d=kw.pop('d',0.017)
    o=A.solve(sc,t,R,P,imu,d,**kw)
    res[tag]=o
    print(sc,tag.ljust(28),'k-1 %+.2f%%'%((o['k']-1)*100),'rms %.4f'%o['rms'],('dg '+str(np.round(o['dg'],4))) if 'dg' in o else '',flush=True)
for dms in (0,5,10,15,17,20,25): run('d=%dms'%dms,d=dms/1e3)
for T in (0.5,1.0,2.0,3.0,5.0): run('T=%.1f'%T,T=T,step=min(0.5,T/2))
for chk in (1,6): run('chk=%d'%chk,chk=chk)
for b in ('none','block5'): run('bias=%s'%b,bias=b)
for T in (1.0,2.0,3.0): run('dg T=%.0f'%T,T=T,dg=True)
for g in (9.79,9.80,9.81,9.82): run('g=%.2f'%g,gmag=g)
run('dg bias=block5 T=2',T=2.0,dg=True,bias='block5')
# 杠杆臂
tn,Rn,Pn,_=A.load(sc,lever=False); o=A.solve(sc,tn,Rn,Pn,imu,0.017); res['no_lever']=o; print(sc,'no_lever'.ljust(28),'k-1 %+.2f%%'%((o['k']-1)*100),flush=True)
# 外参旋转扰动 0.3°(绕相机系三轴各一次)
from rotcal import expm
for ax in range(3):
    v=np.zeros(3); v[ax]=np.radians(0.3); dR=expm(v)
    A._C.pop(sc,None)
    o=A.solve(sc,t,R@dR,P,imu,0.017); res['Rbc+0.3deg_ax%d'%ax]=o
    print(sc,('Rbc 扰动0.3° 轴%d'%ax).ljust(28),'k-1 %+.2f%%'%((o['k']-1)*100),'rms %.4f'%o['rms'],flush=True)
A._C.pop(sc,None)
# SIMEX:给 ARKit 位置加白噪声
rng=np.random.default_rng(3)
for sg in (0.001,0.002,0.004):
    ks=[A.solve(sc,t,R,P,imu,0.017,rng=rng,noise=sg)['k'] for _ in range(4)]
    res['simex_%g'%sg]=ks; print(sc,('SIMEX σ=%.0fmm'%(sg*1e3)).ljust(28),'k-1 均值 %+.2f%%'%((np.mean(ks)-1)*100),flush=True)
# 分段(四等分,与米尺分段口径近似)
t0,t1=t[5],t[-5]-1.0; ed=np.linspace(t0,t1,5)
seg=[]
for i in range(4):
    o=A.solve(sc,t,R,P,imu,0.017,tmask=(ed[i],ed[i+1])); seg.append(o['k'])
res['seg4']=seg; res['seg4_edges']=list(ed-t[0]); print(sc,'分段4'.ljust(28),' '.join('%+.2f%%'%((k-1)*100) for k in seg),flush=True)
# 块 bootstrap
ci,sd=A.boot(sc,t,R,P,imu,0.017,nb=300)
res['boot']={'ci':list(ci),'sd':sd}; print(sc,'块bootstrap(5s)'.ljust(28),'k-1 95%% [%+.2f, %+.2f] 中位 %+.2f sd %.2f%%'%((ci[0]-1)*100,(ci[2]-1)*100,(ci[1]-1)*100,sd*100),flush=True)
json.dump(res,open('accel_sweep_%s.json'%sc,'w'),indent=1,default=float)
