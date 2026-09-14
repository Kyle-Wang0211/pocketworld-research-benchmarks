# -*- coding: utf-8 -*-
"""训前/训后深度图逐帧对比。两臂唯一变量=权重(位姿/照片/pair/融合门全同),
   所以深度图的差异就是权重带来的全部改变。纯测量,不设判定阈值。"""
import sys, glob, os, numpy as np
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm
A="/root/arm_before/depth_est"; B="/root/arm_after/depth_est"
rows=[]
for p in sorted(glob.glob(A+"/*.pfm")):
    v=os.path.basename(p)
    da=np.array(read_pfm(p)[0],dtype=np.float32)
    db=np.array(read_pfm(os.path.join(B,v))[0],dtype=np.float32)
    m=np.isfinite(da)&np.isfinite(db)&(da>0)&(db>0)
    if m.sum()<1000: continue
    rel=np.abs(db-da)/da
    # 纯测量: 相对差的分位数 + "差异>10% 的像素占比"(10% 只是报告口径,不用于判定)
    rows.append((v, float(np.median(rel[m])), float(np.percentile(rel[m],95)),
                 float((rel[m]>0.10).mean()), float(np.median(da[m])), float(np.median(db[m]))))
r=np.array([x[1:] for x in rows])
print("帧数 %d" % len(rows))
print()
print("逐帧相对深度差 |after-before|/before :")
print("  中位数的分布   p5/25/50/75/95: " + "  ".join("%.4f"%x for x in np.percentile(r[:,0],[5,25,50,75,95])))
print("  p95 的分布     p5/25/50/75/95: " + "  ".join("%.4f"%x for x in np.percentile(r[:,1],[5,25,50,75,95])))
print("  差异>10%%像素占比 p5/25/50/75/95: " + "  ".join("%.4f"%x for x in np.percentile(r[:,2],[5,25,50,75,95])))
print()
print("差异最大的 8 帧 (按 >10%% 像素占比):")
for v,med,p95,frac,mda,mdb in sorted(rows,key=lambda x:-x[3])[:8]:
    print("  %s  中位差 %.4f  p95差 %.4f  >10%%占比 %.4f   深度中位 训前 %.2f -> 训后 %.2f" % (v,med,p95,frac,mda,mdb))
print()
print("差异最小的 3 帧:")
for v,med,p95,frac,mda,mdb in sorted(rows,key=lambda x:x[3])[:3]:
    print("  %s  中位差 %.4f  >10%%占比 %.4f" % (v,med,frac))
