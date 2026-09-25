# -*- coding: utf-8 -*-
import sys, json
import numpy as np
sc=sys.argv[1]
Z=np.load('pts_%s.npz'%sc)
X=Z['pts']; PR=Z['pairs']
pid,ua,va,ub,vb,z,zb,ea,eb,ang,dnn,conf,dbil,drng=X.T
pid=pid.astype(int)
t_a=PR[:,1]; t_b=PR[:,2]; dtp=t_b-t_a; base=PR[:,3]; rot=PR[:,4]; fxa=PR[:,5]
T0=t_a.min()
fin=np.isfinite(z)&np.isfinite(dnn)
def filt(reproj=2.0,angmin=1.0,cmin=2,dsrc=None,extra=None):
    d=dnn if dsrc is None else dsrc
    m=fin&(z>0)&(zb>0)&(ea<reproj)&(eb<reproj)&(ang>angmin)&np.isfinite(d)&(d>0)&(conf>=cmin)
    if extra is not None: m&=extra
    return m,d
def per_pair(m,d,minpts=20,est='rom',pairsel=None):
    out={}
    order=np.argsort(pid[m]); P=pid[m][order]; D=d[m][order]; Zt=z[m][order]
    u,st,cnt=np.unique(P,return_index=True,return_counts=True)
    for p,s,c in zip(u,st,cnt):
        if c<minpts: continue
        if pairsel is not None and not pairsel[p]: continue
        dd=D[s:s+c]; zz=Zt[s:s+c]
        if est=='rom': out[p]=np.median(dd)/np.median(zz)
        else: out[p]=np.median(dd/zz)
    return out
def kof(pp): 
    if len(pp)==0: return np.nan
    return 1/np.median(list(pp.values()))
def boot(pp,nb=1000,block=3.0,seed=0):
    rng=np.random.default_rng(seed)
    ks=np.array(list(pp.keys())); vals=np.array(list(pp.values()))
    blk=((t_a[ks]-T0)//block).astype(int); ub=np.unique(blk)
    groups=[vals[blk==b] for b in ub]
    res=[]
    for _ in range(nb):
        pick=rng.integers(0,len(groups),len(groups))
        res.append(1/np.median(np.concatenate([groups[i] for i in pick])))
    return np.percentile(res,[2.5,97.5]),np.std(res)
def dsel(target): return np.abs(dtp-target)<=0.25*target
pct=lambda k:(k-1)*100
print('==',sc,'帧对',len(PR),'点',len(X))
res={}
m,d=filt()
for tgt in (0.2,0.3,0.4,0.6,0.9):
    pp=per_pair(m,d,pairsel=dsel(tgt))
    ci,sd=boot(pp)
    res['dt%.1f'%tgt]=dict(k=kof(pp),n=len(pp),ci=list(ci),sd=sd)
    print(' 帧对间隔 %.1fs: k-1 %+.2f%%  有效帧对 %d/%d  块bootstrap 95%% [%+.2f, %+.2f] sd %.2f%%'%(tgt,pct(kof(pp)),len(pp),dsel(tgt).sum(),pct(ci[0]),pct(ci[1]),sd*100))
ppall=per_pair(m,d); ci,sd=boot(ppall)
print(' 全部间隔合并: k-1 %+.2f%% n %d 95%% [%+.2f, %+.2f] sd %.2f%%'%(pct(kof(ppall)),len(ppall),pct(ci[0]),pct(ci[1]),sd*100))
res['all']=dict(k=kof(ppall),ci=list(ci),sd=sd)
sel=dsel(0.6)|dsel(0.3)|dsel(0.9)
print(' -- 以下敏感度用全部间隔合并 --')
def show(lbl,pp):
    print('   %-34s k-1 %+.2f%%  n %d'%(lbl,pct(kof(pp)),len(pp))); res[lbl]=kof(pp)
show('基线(high,2px,1°,最近邻,中位数之比)',ppall)
show('估计器=逐点比值中位数',per_pair(m,d,est='mor'))
for c in (1,0):
    mm,dd=filt(cmin=c); show('置信度≥%d'%c,per_pair(mm,dd))
mm,dd=filt(dsrc=dbil); show('双线性取深度',per_pair(mm,dd))
for a in (2,4,8):
    mm,dd=filt(angmin=a); show('三角化角>%d°'%a,per_pair(mm,dd))
for r in (1.0,4.0):
    mm,dd=filt(reproj=r); show('重投影<%.0fpx'%r,per_pair(mm,dd))
mm,dd=filt(extra=drng<0.05*dnn); show('去掉深度边缘点(3×3极差<5%)',per_pair(mm,dd))
rad=np.hypot(ua-960,va-720)
mm,dd=filt(extra=rad<500); show('只用画面中心 r<500px',per_pair(mm,dd))
mm,dd=filt(extra=rad>=700); show('只用画面边缘 r≥700px',per_pair(mm,dd))
for lo,hi in ((0,0.5),(0.5,0.8),(0.8,1.2),(1.2,2),(2,5)):
    mm,dd=filt(extra=(dnn>=lo)&(dnn<hi)); pp=per_pair(mm,dd,minpts=10); show('LiDAR 深度 %.1f–%.1f m(每对≥10点)'%(lo,hi),pp)
# 逐点合并(全局一个 k 下):r=d/z 按深度/半径/行分箱的中位数,相对全体中位
mm,dd=filt()
r=dd[mm]/z[mm]; rmed=np.median(r)
print(' -- 逐点 LiDAR/三角化 比值分箱(相对全体中位数 %%,正=该箱 LiDAR 相对偏大) --')
for name,v,edges in (('LiDAR深度m',dd[mm],[0,0.4,0.6,0.8,1.0,1.3,1.7,2.5,5]),('离主点半径px',rad[mm],[0,200,400,600,800,1000,1300]),('图像行v',va[mm],[0,240,480,720,960,1200,1440]),('三角化角°',ang[mm],[1,2,3,5,8,15,90])):
    cells=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        s=(v>=lo)&(v<hi)
        if s.sum()>200: cells.append('%g–%g:%+.2f(%d)'%(lo,hi,(np.median(r[s])/rmed-1)*100,s.sum()))
    print('   %s  '%name+'  '.join(cells))
# 焦距相关:逐对 log s 对 fx
pp=ppall; ks=np.array(list(pp.keys())); ls=np.log(np.array(list(pp.values())))
cf=np.polyfit(fxa[ks]/np.median(fxa[ks])-1,ls,1)
print(' 焦距:fx 范围 %.1f–%.1f(中位 %.1f);逐对 log(s) 对 fx 相对变化的斜率 %.3f(0=与焦距无关;+1/-1=完全随焦距)'%(fxa[ks].min(),fxa[ks].max(),np.median(fxa[ks]),cf[0]))
res['fx_slope']=cf[0]; res['fx_range']=[fxa[ks].min(),fxa[ks].max()]
# 分段(四等分时间)
ed=np.linspace(t_a.min(),t_a.max()+1e-6,5)
seg=[]
for i in range(4):
    s=(t_a[ks]>=ed[i])&(t_a[ks]<ed[i+1]); seg.append(1/np.median(np.exp(ls[s])))
print(' 分段 k-1(四等分 %s s): '%np.round(ed-T0,1)+' '.join('%+.2f%%'%pct(k) for k in seg))
res['seg4']=seg; res['seg4_edges']=list(ed-T0)
# 帧对内 IQR 与点数
print(' 逐对尺度 IQR/中位 %.3f'%(np.subtract(*np.percentile(np.exp(ls),[75,25]))/np.median(np.exp(ls))))
json.dump(res,open('lidar_an_%s.json'%sc,'w'),indent=1,default=float)
