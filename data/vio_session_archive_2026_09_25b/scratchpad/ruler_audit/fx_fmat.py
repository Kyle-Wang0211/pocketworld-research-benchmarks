# -*- coding: utf-8 -*-
"""不依赖任何位姿/陀螺的焦距自检:每个帧对只用图像匹配 RANSAC 估基础矩阵 F,
对候选 f 算 E = K^T F K,「本质矩阵两个非零奇异值相等」(Hartley & Zisserman §9.6 / Bougnoux 2 视图自标定的判据),
代价 ((σ1−σ2)/(σ1+σ2))² 对全部帧对求和取最小;主点取 ARKit 报的。"""
import sys, json
import numpy as np, cv2
sc=sys.argv[1]
Z=np.load('pts_%s.npz'%sc); X=Z['pts']; PR=Z['pairs']
pid=X[:,0].astype(int); ua,va,ub,vb=X[:,1],X[:,2],X[:,3],X[:,4]
intr={}
for l in open('full_%s/intrinsics.jsonl'%sc):
    if l.strip():
        d=json.loads(l); intr[int(round(d['t']*1e9))]=d['intrinsics_fxfycxcy']
ik=np.array(sorted(intr)); near=lambda t: intr[int(ik[np.argmin(np.abs(ik-t))])]
order=np.argsort(pid); P=pid[order]; u,st,cnt=np.unique(P,return_index=True,return_counts=True)
Fs=[]
cv2.setRNGSeed(1)
for p,s,c in zip(u,st,cnt):
    if c<150 or PR[p,4]<3.0: continue
    idx=order[s:s+c]
    a=np.stack([ua[idx],va[idx]],1).astype(np.float64); b=np.stack([ub[idx],vb[idx]],1).astype(np.float64)
    F,m=cv2.findFundamentalMat(a,b,cv2.FM_RANSAC,1.0,0.999,5000)
    if F is None or F.shape!=(3,3) or m.sum()<100: continue
    Ka=near(int(round(PR[p,1]*1e9))); Kb=near(int(round(PR[p,2]*1e9)))
    Fs.append((F,Ka,Kb))
fg=np.arange(1250,1480.1,2.5)
def costf(f,sel=None):
    tot=0
    for F,Ka,Kb in Fs:
        KA=np.array([[f*Ka[0]/Ka[0],0,Ka[2]],[0,f,Ka[3]],[0,0,1]]); KB=np.array([[f,0,Kb[2]],[0,f,Kb[3]],[0,0,1]])
        E=KB.T@F@KA; s=np.linalg.svd(E,compute_uv=False)
        tot+=((s[0]-s[1])/(s[0]+s[1]))**2
    return tot/len(Fs)
c=np.array([costf(f) for f in fg]); i=int(np.argmin(c))
fmed=np.median([k[0] for _,k,_ in Fs])
# 逐对最优 f 的中位数(诊断)
per=[]
for F,Ka,Kb in Fs:
    cc=[]
    for f in fg:
        KA=np.array([[f,0,Ka[2]],[0,f,Ka[3]],[0,0,1]]); KB=np.array([[f,0,Kb[2]],[0,f,Kb[3]],[0,0,1]])
        s=np.linalg.svd(KB.T@F@KA,compute_uv=False); cc.append(((s[0]-s[1])/(s[0]+s[1]))**2)
    j=int(np.argmin(cc))
    if 0<j<len(fg)-1: per.append(fg[j])
per=np.array(per)
rng=np.random.default_rng(0); bs=[]
for _ in range(200):
    pick=rng.integers(0,len(Fs),len(Fs)); sub=[Fs[k] for k in pick]
    cc=[]
    for f in fg[::2]:
        t=0
        for F,Ka,Kb in sub:
            KA=np.array([[f,0,Ka[2]],[0,f,Ka[3]],[0,0,1]]); KB=np.array([[f,0,Kb[2]],[0,f,Kb[3]],[0,0,1]])
            s=np.linalg.svd(KB.T@F@KA,compute_uv=False); t+=((s[0]-s[1])/(s[0]+s[1]))**2
        cc.append(t)
    bs.append(fg[::2][int(np.argmin(cc))])
print('== %s 帧对 %d;ARKit 报的 fx 中位 %.1f;F 矩阵自标定:总代价最优 f = %.1f(= 报的 ×%.4f),bootstrap 95%% [%.1f, %.1f];逐对最优 f 中位 %.1f(内部 %d 对)'%(
    sc,len(Fs),fmed,fg[i],fg[i]/fmed,*np.percentile(bs,[2.5,97.5]),np.median(per),len(per)))
