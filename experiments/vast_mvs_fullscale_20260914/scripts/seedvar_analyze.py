# -*- coding: utf-8 -*-
"""训前/训后 种子方差 × 白墙掩码。全部沿用 09-09 的定义,保证与当时的 5.18x 可比:
   方差   = 6 种子逐像素相对标准差 std/mean        [var_maps.py:20]
   地板   = 同一 seed 123 跑两遍, 同法 std/mean     [multiseed.sh 注释]
   白墙   = (灰度>150) & (|Laplacian ksize=3|<4)   [wallframes.py:10]
   纯测量, 不设新阈值。"""
import os, sys, glob, numpy as np, cv2
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm
MS="/root/ms2"
def load(arm,tag,i):
    p="%s/%s/%s/depth_est/%08d.pfm"%(MS,arm,tag,i)
    return np.array(read_pfm(p)[0],dtype=np.float32) if os.path.exists(p) else None
def wallmask(arm,i):
    p="%s/%s/s1/images/%08d.jpg"%(MS,arm,i)
    if not os.path.exists(p): p="/root/arm_before/images/%08d.jpg"%i
    g=cv2.cvtColor(cv2.imread(p),cv2.COLOR_BGR2GRAY).astype(np.float32)
    return (g>150)&(np.abs(cv2.Laplacian(g,cv2.CV_32F,ksize=3))<4)
print("%-8s %-26s %-12s %-12s %-8s" % ("臂","量","白墙 p50","非白墙 p50","比值"))
res={}
for arm in ("before","after"):
    seeds=["s%d"%k for k in (1,2,3,4,5,6)]
    if not all(os.path.isdir("%s/%s/%s/depth_est"%(MS,arm,t)) for t in seeds+["floorA","floorB"]):
        print("%-8s 数据未齐,跳过" % arm); continue
    frames=sorted(int(os.path.basename(f)[:8]) for f in glob.glob("%s/%s/s1/depth_est/*.pfm"%(MS,arm)))
    VW=[];VN=[];FW=[];FN=[]
    for i in frames:
        D=[load(arm,t,i) for t in seeds]
        if any(d is None for d in D): continue
        D=np.stack(D); mu=D.mean(0); ok=mu>1e-6
        rel=np.where(ok, D.std(0)/np.maximum(mu,1e-6), np.nan)
        a,b=load(arm,"floorA",i),load(arm,"floorB",i)
        F=np.stack([a,b]); fmu=F.mean(0)
        fl=np.where(fmu>1e-6, F.std(0)/np.maximum(fmu,1e-6), np.nan)
        w=wallmask(arm,i)&ok
        n=(~wallmask(arm,i))&ok
        VW.append(rel[w]); VN.append(rel[n]); FW.append(fl[w]); FN.append(fl[n])
    vw=np.concatenate(VW); vn=np.concatenate(VN); fw=np.concatenate(FW); fn=np.concatenate(FN)
    vw=vw[np.isfinite(vw)]; vn=vn[np.isfinite(vn)]; fw=fw[np.isfinite(fw)]; fn=fn[np.isfinite(fn)]
    r=np.median(vw)/np.median(vn)
    res[arm]=(np.median(vw),np.median(vn),r,np.median(fw),np.median(fn))
    print("%-8s %-26s %-12s %-12s %-8s" % (arm,"6种子相对标准差 p50",
          "%.4f%%"%(np.median(vw)*100), "%.4f%%"%(np.median(vn)*100), "%.2fx"%r))
    print("%-8s %-26s %-12s %-12s %-8s" % ("","噪声地板(同种子两遍) p50",
          "%.4f%%"%(np.median(fw)*100), "%.4f%%"%(np.median(fn)*100),
          "信噪比 %.1fx/%.1fx"%(np.median(vw)/max(np.median(fw),1e-12), np.median(vn)/max(np.median(fn),1e-12))))
    print("%-8s 白墙像素 %d, 非白墙 %d, 帧数 %d" % ("",len(vw),len(vn),len(VW)))
    print()
if len(res)==2:
    print("=== 判决 ===")
    print("  09-09 基线(casdiffmvs_blendmvg 权重): 白墙 0.228%% / 非白墙 0.044%% = 5.18x")
    print("  训前 %.2fx   训后 %.2fx   变化 %+.1f%%" %
          (res["before"][2],res["after"][2],(res["after"][2]/res["before"][2]-1)*100))
