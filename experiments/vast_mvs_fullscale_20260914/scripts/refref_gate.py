# -*- coding: utf-8 -*-
"""ref-ref 门测量:除官方的【同意票】外,再数【反对票】。
   同意票 = 官方 check_geometric_consistency 判据 (dist<1.0 且 rel_diff<0.01)
   反对票 = 投影落在 src 图内、src 深度有效,但 rel_diff>=0.01  (即 src 在那条视线上看到了别的深度)
   阈值 0.01/1.0 全部取自官方 filter.py 调用 (geo_depth_thres / geo_pixel_thres)。
   🔴 移位前提: 官方这两个常数是用在「ref 对 src 的支持度」上, 这里用来数「反对度」——
      属于我们的扩展, 必须像判据一样验证: 先算预期, 再对实测, 并过阳性对照(白墙 vs 非白墙)。
   纯测量, 不改任何官方文件。"""
import sys, os, numpy as np, cv2
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import reproject_with_depth
from datasets.data_io import read_pfm

GEO_PIX, GEO_DEP = 1.0, 0.01
def tex_std(bgr,win=11):
    g=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY).astype("float32")/255.0
    m=cv2.blur(g,(win,win)); m2=cv2.blur(g*g,(win,win))
    return np.sqrt(np.clip(m2-m*m,0,None))
def cam(root,v):
    L=[l.rstrip() for l in open("%s/cams/%08d_cam.txt"%(root,v))]
    return (np.fromstring(" ".join(L[7:10]),dtype=np.float32,sep=" ").reshape(3,3),
            np.fromstring(" ".join(L[1:5]),dtype=np.float32,sep=" ").reshape(4,4))
def dep(root,v): return np.array(read_pfm("%s/depth_est/%08d.pfm"%(root,v))[0],dtype=np.float32)
pairs={}
with open("/root/mvs_P16k/pair.txt") as f:
    n=int(f.readline())
    for _ in range(n):
        r=int(f.readline()); t=f.readline().split(); pairs[r]=[int(x) for x in t[1::2]]

REFS=list(range(0,132,4))          # 均匀取 33 个 ref
for root,name in [("/root/arm_before","训前"),("/root/arm_after","训后")]:
    AG=[]; DS=[]; LOW=[]
    for ref in REFS:
        Ki,Ei=cam(root,ref); di=dep(root,ref)
        H,W=di.shape
        ts=tex_std(cv2.imread("%s/images/%08d.jpg"%(root,ref)))
        low = ts <= np.percentile(ts,25)
        agree=np.zeros((H,W),np.int32); disag=np.zeros((H,W),np.int32)
        xr,yr=np.meshgrid(np.arange(W),np.arange(H))
        for src in pairs[ref]:
            Kj,Ej=cam(root,src); dj=dep(root,src)
            d2r,x2r,y2r,x2s,y2s = reproject_with_depth(di,Ki,Ei,dj,Kj,Ej)
            dist=np.sqrt((x2r-xr)**2+(y2r-yr)**2)
            rel=np.abs(d2r-di)/np.maximum(di,1e-6)
            inview=(x2s>=0)&(x2s<W)&(y2s>=0)&(y2s<H)&(d2r>0)&(di>0)
            agree += ((dist<GEO_PIX)&(rel<GEO_DEP)&inview).astype(np.int32)
            disag += (inview&~((dist<GEO_PIX)&(rel<GEO_DEP))).astype(np.int32)
        valid=di>0
        AG.append(agree[valid]); DS.append(disag[valid]); LOW.append(low[valid])
    ag=np.concatenate(AG); ds=np.concatenate(DS); lw=np.concatenate(LOW)
    keep = ag>=2                       # 官方 geo_mask_thres=2 已通过的点(=会被输出的点)
    print("=== %s  (33 个 ref, 每个 10 src) ===" % name)
    print("  官方门通过(同意>=2)的像素 %d / %d = %.4f" % (keep.sum(), len(ag), keep.mean()))
    a=ds[keep&lw]; b=ds[keep&~lw]
    print("  这些通过的点里, 反对票数:")
    print("    低纹理 n=%8d  p50 %.1f  p90 %.1f  均值 %.2f" % (len(a),np.percentile(a,50),np.percentile(a,90),a.mean()))
    print("    有纹理 n=%8d  p50 %.1f  p90 %.1f  均值 %.2f" % (len(b),np.percentile(b,50),np.percentile(b,90),b.mean()))
    print("  若加门「反对票 <= N」的删除率 (低纹理 / 有纹理 / 比值,>1 表示优先删白墙):")
    for N in (0,1,2,3,4,5,6):
        ra=(a>N).mean(); rb=(b>N).mean()
        print("    N=%d   删低纹理 %.4f   删有纹理 %.4f   比值 %.2f" % (N,ra,rb,ra/max(rb,1e-9)))
