# -*- coding: utf-8 -*-
"""算训后/训前的种子方差图,并按 09-09 的方法重新标定 VAR_GATE 阈值。
   方差    = 6 种子逐像素相对标准差 std/mean        [09-09 var_maps.py:20]
   阈值    = 同 seed 两遍(floorA/floorB)的逐像素相对差分布的 p99
             [09-09 原文: 「A = 0.0624% = 同一 --seed 123 跑两遍的逐像素相对差分布的 p99」]
   🔴 训后的噪声地板变了(p50 0.0012%->0.0006%),所以阈值必须重标,不能照搬 09-09 的 0.000624。"""
import os, sys, glob, numpy as np
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm
MS="/root/ms2"
for arm in ("after","before"):
    OUT="%s/%s/varmap"%(MS,arm); os.makedirs(OUT,exist_ok=True)
    seeds=["s%d"%k for k in (1,2,3,4,5,6)]
    frames=sorted(int(os.path.basename(f)[:8]) for f in glob.glob("%s/%s/s1/depth_est/*.pfm"%(MS,arm)))
    floor=[]
    for i in frames:
        D=[np.array(read_pfm("%s/%s/%s/depth_est/%08d.pfm"%(MS,arm,t,i))[0],dtype=np.float32) for t in seeds]
        D=np.stack(D); mu=D.mean(0)
        rel=np.where(mu>1e-6, D.std(0)/np.maximum(mu,1e-6), 9.9).astype(np.float32)
        np.save("%s/%08d.npy"%(OUT,i), rel)
        a=np.array(read_pfm("%s/%s/floorA/depth_est/%08d.pfm"%(MS,arm,i))[0],dtype=np.float32)
        b=np.array(read_pfm("%s/%s/floorB/depth_est/%08d.pfm"%(MS,arm,i))[0],dtype=np.float32)
        m=(a>1e-6)&(b>1e-6)
        floor.append((np.abs(a-b)/np.maximum(a,1e-6))[m][::7])
    f=np.concatenate(floor)
    p99=float(np.percentile(f,99))
    print("%-7s 方差图 %d 张 -> %s" % (arm,len(frames),OUT))
    print("        地板(同种子两遍)相对差: n=%d  p50 %.5f%%  p99 %.5f%%  => VAR_GATE = %.6f" %
          (len(f), np.percentile(f,50)*100, p99*100, p99))
    v=np.concatenate([np.load("%s/%08d.npy"%(OUT,i)).ravel()[::13] for i in frames])
    v=v[v<9]
    print("        方差分布 p10/30/50/70/90: %s" % "  ".join("%.4f%%"%(np.percentile(v,q)*100) for q in (10,30,50,70,90)))
    print("        若门 = p99 地板 %.6f, 全图删除率 %.4f" % (p99,(v>=p99).mean()))
