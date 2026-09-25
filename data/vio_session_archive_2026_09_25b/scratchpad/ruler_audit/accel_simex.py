# -*- coding: utf-8 -*-
"""自变量噪声(ARKit 位置抖动)对加计尺子的偏差:各窗长 T 下 SIMEX 求敏感度 c(T)(k 对 σ² 的斜率),
再用 k(T) = k* + c(T)·σ0² 跨窗长拟合 ARKit 自身抖动 σ0 与去偏后的 k*。"""
import sys
sys.dont_write_bytecode=True
import numpy as np
import accel_diag as A
sc=sys.argv[1]
t,R,P,imu=A.load(sc)
rng=np.random.default_rng(11)
rows=[]
for T in (0.5,1.0,2.0,3.0):
    st=min(0.5,T/2)
    k0=A.solve(sc,t,R,P,imu,0.017,T=T,step=st)['k']
    ks=[A.solve(sc,t,R,P,imu,0.017,T=T,step=st,rng=rng,noise=0.0015)['k'] for _ in range(6)]
    c=(np.mean(ks)-k0)/(0.0015**2)
    rows.append((T,k0,c))
    print(sc,'T=%.1f  k-1 %+.2f%%  敏感度 c = %+.3f pp/mm²'%(T,(k0-1)*100,c*1e-6*100),flush=True)
Tm=np.array([r[0] for r in rows]); K=np.array([r[1] for r in rows]); C=np.array([r[2] for r in rows])
Am=np.stack([np.ones_like(C),C],1); x,*_=np.linalg.lstsq(Am,K,rcond=None)
s0=np.sqrt(max(x[1],0))
print(sc,'跨窗长拟合:去偏 k*-1 = %+.2f%%,隐含 ARKit 位置白噪声 σ0 = %.2f mm(x[1]=%.3g);残差 %s pp'%((x[0]-1)*100,s0*1e3,x[1],np.round((K-Am@x)*100,2)))
