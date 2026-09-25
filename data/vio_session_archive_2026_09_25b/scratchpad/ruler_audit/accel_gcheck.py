# -*- coding: utf-8 -*-
"""加计刻度自检:低运动时刻 |f − b_a| 应等于当地重力(中国城市 9.78–9.80)。b_a 取加计尺子全局解(d=17 ms)。
再看 f 在机身各轴上的投影,判断哪几根轴被检验到。"""
import sys, json
sys.dont_write_bytecode=True
import numpy as np
import accel_diag as A
for sc in ('13f5','6d18','7353'):
    t,R,P,imu=A.load(sc)
    o=A.solve(sc,t,R,P,imu,0.017)
    b=np.array(o['b_a'])
    ti=imu['t']; w=imu['w']; a=imu['a']
    # 低运动:陀螺 <0.15 rad/s 且 ±50 ms 内加计模长变化 <0.05
    wn=np.linalg.norm(w,axis=1); an=np.linalg.norm(a,axis=1)
    k=5; loc=np.array([an[max(0,i-k):i+k+1].std() for i in range(len(an))])
    m=(wn<float(sys.argv[1]))&(loc<float(sys.argv[2]))
    g1=np.linalg.norm(a[m]-b,axis=1); g0=np.linalg.norm(a[m],axis=1)
    dirs=np.abs((a[m]-b)/g1[:,None]).mean(0)
    print(sc,'低运动样本 %d/%d;|f| 中位 %.4f;|f−b_a| 中位 %.4f(IQR %.4f)⇒ 若当地 g=9.79 则刻度 %+.2f%%;平均方向 |x,y,z| %s;b_a %s'%(m.sum(),len(m),np.median(g0),np.median(g1),np.subtract(*np.percentile(g1,[75,25])),(np.median(g1)/9.79-1)*100,np.round(dirs,2),np.round(b,3)))
