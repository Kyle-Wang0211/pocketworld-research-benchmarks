# -*- coding: utf-8 -*-
"""量「不同 ref 视角对同一处给出的深度分歧」—— 即点云里多层之间的实际间距。
   用官方 filter.py 的 reproject_with_depth。纯测量,不设判定阈值。
   关键: filter.py 只检验 ref<->src 一致性,【从不检验两个 ref 之间】,
        所以每个 ref 都能各自通过门、各自输出一层。"""
import sys, os, numpy as np
sys.path.insert(0,"/root"); os.environ.setdefault("DIFFMVS_DIR","/root/diffmvs")
import tartanground2mvsnet as tg
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm

def cam(root,v):
    L=[l.rstrip() for l in open("%s/cams/%08d_cam.txt"%(root,v))]
    E=np.fromstring(" ".join(L[1:5]),dtype=np.float32,sep=" ").reshape(4,4)
    K=np.fromstring(" ".join(L[7:10]),dtype=np.float32,sep=" ").reshape(3,3)
    return K,E
def dep(root,v): return np.array(read_pfm("%s/depth_est/%08d.pfm"%(root,v))[0],dtype=np.float32)

# 从官方 pair.txt 取共视最强的邻居
pairs={}
with open("/root/mvs_P16k/pair.txt") as f:
    n=int(f.readline())
    for _ in range(n):
        r=int(f.readline()); t=f.readline().split()
        pairs[r]=[int(x) for x in t[1::2]]

for root,name in [("/root/arm_before","训前"),("/root/arm_after","训后")]:
    print("=== %s ===" % name)
    allgap=[]
    for ref in (131,130,122,125,121):
        Ki,Ei=cam(root,ref); di=dep(root,ref)
        for src in pairs[ref][:3]:
            Kj,Ej=cam(root,src); dj=dep(root,src)
            d2r,x2r,y2r = tg.reproject_with_depth(di,Ki,Ei,dj,Kj,Ej)
            H,W=di.shape; xx,yy=np.meshgrid(np.arange(W),np.arange(H))
            dist=np.sqrt((x2r-xx)**2+(y2r-yy)**2)
            ok=(dist<1)&(di>0)&(d2r>0)          # 像素对上了才比深度
            gap=np.abs(d2r-di)[ok]              # 米
            allgap.append(gap)
    g=np.concatenate(allgap)
    print("  像素对上的样本 %d" % len(g))
    print("  两 ref 深度分歧(米)  p50 %.4f  p90 %.4f  p99 %.4f  p99.9 %.4f  max %.3f"
          % tuple(np.percentile(g,[50,90,99,99.9]).tolist()+[g.max()]))
    for t in (0.02,0.05,0.10,0.30,1.00):
        print("     分歧 > %4.2f m 的占比 %.4f" % (t,(g>t).mean()))
