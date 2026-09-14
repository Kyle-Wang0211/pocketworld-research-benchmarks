import os, sys, glob, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
ROOT="/root/monotrain"
scans=[d for d in sorted(os.listdir(ROOT)) if os.path.isdir(os.path.join(ROOT,d,"cams"))]
bmvs=[s for s in scans if len(s)==24 and all(c in "0123456789abcdef" for c in s)]
R=[]
for s in bmvs[:60]:
    for c in sorted(glob.glob(os.path.join(ROOT,s,"cams","*_cam.txt")))[:6]:
        vid=os.path.basename(c).split("_")[0]
        pfm=os.path.join(ROOT,s,"rendered_depth_maps",vid+".pfm")
        if not os.path.exists(pfm): continue
        L=[l.rstrip() for l in open(c)]
        if len(L)<12: continue
        t=L[11].split(); dmin,dmax=float(t[0]),float(t[-1])
        d=np.array(read_pfm(pfm)[0],dtype=np.float32)
        v=d[np.isfinite(d)&(d>0)]
        if v.size<1000: continue
        R.append([dmin,dmax,v.min(),v.max()]+[np.percentile(v,p) for p in (0.1,0.5,1,2,5)])
R=np.array(R,dtype=np.float64); print("n=",len(R))
print("cam 行 token 数分布:", end=" ")
import collections
print(collections.Counter(len([l.rstrip() for l in open(c)][11].split()) for s in bmvs[:20] for c in sorted(glob.glob(os.path.join(ROOT,s,"cams","*_cam.txt")))[:3]))
print()
print("dmax / gt_max      中位 %.6f   std %.6f" % (np.median(R[:,1]/R[:,3]), (R[:,1]/R[:,3]).std()))
for j,name in zip(range(4,9), ["p0.1","p0.5","p1","p2","p5"]):
    r=R[:,0]/R[:,j]
    print("dmin / gt_%-5s    中位 %.6f   std %.6f   [p25 %.4f p75 %.4f]" % (name, np.median(r), r.std(), np.percentile(r,25), np.percentile(r,75)))
r=R[:,0]/R[:,2]; print("dmin / gt_min      中位 %.6f   std %.6f" % (np.median(r), r.std()))
