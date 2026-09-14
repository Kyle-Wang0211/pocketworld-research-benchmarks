# 深度/外参约定自证 + 阴性对照。判据用官方 filter.py 的几何一致性 (dist<1 & rel_diff<0.01)
import os, sys, glob, numpy as np
sys.path.insert(0,"/root"); os.environ.setdefault("DIFFMVS_DIR","/root/diffmvs")
import tartanground2mvsnet as tg
EX="/root/sp_probe/ex"
def load(sc,f):
    d=np.load("%s/scene_%s_%08d.npy"%(EX,sc,f))
    L=[l.rstrip() for l in open("%s/scene_%s_%08d.txt"%(EX,sc,f))]
    E=np.fromstring(" ".join(L[1:5]),dtype=np.float32,sep=" ").reshape(4,4)
    K=np.fromstring(" ".join(L[7:10]),dtype=np.float32,sep=" ").reshape(3,3)
    return d,K,E
def gate(sc,i,j,xform=None):
    di,Ki,Ei=load(sc,i); dj,Kj,Ej=load(sc,j)
    if xform is not None: di=xform(di,Ki); dj=xform(dj,Kj)
    d2r,x2r,y2r=tg.reproject_with_depth(di,Ki,Ei,dj,Kj,Ej)
    H,W=di.shape; xx,yy=np.meshgrid(np.arange(W),np.arange(H))
    fg=(di>0)&(di<1e3)                      # 官方有效性 infinigen_cubism.py:337
    dist=np.sqrt((x2r-xx)**2+(y2r-yy)**2)
    rel=np.abs(d2r-di)/di
    ok=(dist<1)&(rel<0.01)&fg               # 官方 filter.py 判据
    sub=fg&(dist<1)
    return float(ok[fg].mean()), (float(np.median(rel[sub])) if sub.sum()>500 else float("nan")), int(fg.sum())
def to_radial(d,K):                          # 阴性对照: 若深度其实是 planar,强行当 radial 反算会变差
    H,W=d.shape; u,v=np.meshgrid(np.arange(W),np.arange(H))
    x=(u-K[0,2])/K[0,0]; y=(v-K[1,2])/K[1,1]
    return d/np.sqrt(1+x*x+y*y)
print("场景 0 (背景占比 0) —— 正臂: 原样")
for j in range(1,8):
    c,r,n=gate("0",0,j); print("  v0->v%d  几何一致率 %.4f   一致像素上深度相对差中位 %.2e" % (j,c,r))
print()
print("阴性对照: 把深度当 radial 反算成 planar (若原本已是 planar,必须变差)")
for j in (1,2,7):
    c,r,n=gate("0",0,j,xform=to_radial); print("  v0->v%d  几何一致率 %.4f   深度相对差中位 %.2e" % (j,c,r))
print()
print("=== 跨场景抽样 (含高背景场景) ===")
scs=sorted(set(f.split("_")[1] for f in os.listdir(EX) if f.endswith(".npy")),key=int)[:8]
for sc in scs:
    cs=[gate(sc,0,j)[0] for j in (1,2,3)]
    d0,_,_=load(sc,0); bg=float((d0>=1e3).mean())
    print("  scene_%-5s 背景 %.3f   v0->v1/2/3 一致率 %.4f %.4f %.4f" % (sc,bg,*cs))
