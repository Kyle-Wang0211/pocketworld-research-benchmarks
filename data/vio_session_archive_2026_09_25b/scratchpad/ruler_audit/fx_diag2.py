# -*- coding: utf-8 -*-
"""焦距 × 对焦:逐帧真焦距模型 f = F + β·(f_报 − 中位),ARKit 旋转固定,网格拟合 (F, β);
β=1 ⇒ ARKit 报的随对焦变化是真的;β=0 ⇒ 图像实际焦距与对焦无关(报的变化是假的)。另扫位姿时间 δ 的代价。"""
import sys
sys.dont_write_bytecode=True
import numpy as np
exec(open('fx_diag.py').read().split("print('==',sc")[0])
fmed=np.median([d['Ka'][0] for d in data])
def cost_fb(F,beta,key='R',tau=2.0):
    tot=0;n=0
    for d in data:
        R=d['R'] if key=='R' else d[key+'_R']; t=d['t'] if key=='R' else d[key+'_t']
        fs=[]
        for K,x in ((d['Ka'],d['xa']),(d['Kb'],d['xb'])):
            f=F+beta*(K[0]-fmed); nx=(x[:,0]-K[2])/f; ny=(x[:,1]-K[3])/f
            fs.append((np.stack([nx,ny,np.ones_like(nx)],1),f))
        (fa,f1),(fb,f2)=fs
        Em=skew(t)@R; Ea=fa@Em.T; Etb=fb@Em
        d2=np.sum(fb*Ea,1)**2/(Ea[:,0]**2+Ea[:,1]**2+Etb[:,0]**2+Etb[:,1]**2)*f1*f2
        tot+=np.sum(np.minimum(d2,tau**2)); n+=len(d2)
    return tot/n
fr=np.array([d['Ka'][0] for d in data])
print('==',sc,'报的 fx:中位 %.1f,5–95%% %.1f–%.1f'%(fmed,*np.percentile(fr,[5,95])))
g=[(F,b,cost_fb(F,b)) for F in np.arange(fmed*0.99,fmed*1.045,fmed*0.0025) for b in (-0.5,0,0.25,0.5,0.75,1.0,1.5)]
F,b,c=min(g,key=lambda r:r[2])
cb1=min((r for r in g if r[1]==1.0),key=lambda r:r[2]); cb0=min((r for r in g if r[1]==0),key=lambda r:r[2])
print('  最优 F %.1f(=中位×%.4f) β %.2f 代价 %.4f;β=1 时最优 F×%.4f 代价 %.4f;β=0 时最优 F×%.4f 代价 %.4f'%(F,F/fmed,b,c,cb1[0]/fmed,cb1[2],cb0[0]/fmed,cb0[2]))
for delta in (-0.016,-0.008,0.0,0.008,0.016):
    for d in data: d['s_R'],d['s_t']=rel(d,delta)
    a,cm=best(lambda a:cost(a,key='s')); print('  位姿时间 %+3.0f ms:α %.4f 最小代价 %.4f'%(delta*1e3,a,cm))
