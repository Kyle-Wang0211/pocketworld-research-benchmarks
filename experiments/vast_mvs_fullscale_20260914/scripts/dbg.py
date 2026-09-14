import sys, os, glob, numpy as np
sys.path.insert(0,"/root/diffmvs")
from filter import check_geometric_consistency
import inspect
print("check_geometric_consistency 签名:", inspect.signature(check_geometric_consistency))
d=np.load(sorted(glob.glob("/root/da3_r616/exports/npz/*.npz"))[0],allow_pickle=True)
D,C,E,K=d["depth"],d["conf"],d["extrinsics"],d["intrinsics"]
def E44(i):
    M=np.eye(4); M[:3,:4]=E[i]; return M
ref=60; src=61
gm,dr,x2,y2 = check_geometric_consistency(D[ref].astype(np.float64),K[ref].astype(np.float64),E44(ref),
                                          D[src].astype(np.float64),K[src].astype(np.float64),E44(src),1.0,0.01)
print("ref60 vs src61: geo_mask 通过率 %.4f%%" % (100*gm.mean()))
# 放宽看曲线
for px,dp in ((1.0,0.01),(2.0,0.02),(4.0,0.04),(8.0,0.08),(1e9,1e9)):
    g,_,_,_ = check_geometric_consistency(D[ref].astype(np.float64),K[ref].astype(np.float64),E44(ref),
                                          D[src].astype(np.float64),K[src].astype(np.float64),E44(src),px,dp)
    print(f"   {px}px/{dp*100:g}% -> {100*g.mean():.2f}%")
# 对照:官方768 的深度过同一函数
import re
def rd(p):
    with open(p,"rb") as f:
        f.readline(); w,h=map(int,f.readline().split()); s=float(f.readline())
        a=np.fromfile(f,"<f4" if s<0 else ">f4").reshape(h,w)
    return np.flipud(a).astype(np.float64)
def rc(p):
    L=[l.rstrip() for l in open(p)]
    return (np.fromstring(" ".join(L[7:10]),sep=" ").reshape(3,3),
            np.fromstring(" ".join(L[1:5]),sep=" ").reshape(4,4))
K0,E0=rc("/root/off768_true/cams/00000060_cam.txt"); K1,E1=rc("/root/off768_true/cams/00000061_cam.txt")
d0=rd("/root/off768_true/depth_est/00000060.pfm"); d1=rd("/root/off768_true/depth_est/00000061.pfm")
g,_,_,_=check_geometric_consistency(d0,K0,E0,d1,K1,E1,1.0,0.01)
print("对照 官方768 同一对 ref60/src61: %.2f%%" % (100*g.mean()))
