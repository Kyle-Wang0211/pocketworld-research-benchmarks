import os, glob, numpy as np, cv2, sys
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm
GM="/root/regionmerge/gated_mono_noconf"; GA="/root/regionmerge/gated_mvsa"
GN="/root/regionmerge/gated_mvsa_nomono"; GC="/root/regionmerge/gated_mono"
SRC="/root/MonoMVSNet/outputs/ours/scene0"
# 逐帧白墙占比
wall={}
for f in sorted(glob.glob(f"{GM}/color/*.png")):
    i=int(os.path.basename(f)[:8]); g=cv2.cvtColor(cv2.imread(f),cv2.COLOR_BGR2GRAY).astype(np.float32)
    wall[i]=float(((g>150)&(np.abs(cv2.Laplacian(g,cv2.CV_32F,ksize=3))<4)).mean())
order=sorted(wall,key=lambda k:-wall[k])
def keep(d,i):
    p=f"{d}/depth/{i:08d}.npy"
    return float((np.load(p)>0).mean()) if os.path.exists(p) else float("nan")
print(f"{'帧':>4} {'白墙%':>7} | {'MVSA完整':>9} {'MVSA无单目':>11} {'Mono几何门':>11} {'Mono conf0.6':>13}")
for i in order[:8]:
    print(f"{i:>4} {wall[i]*100:>6.1f}% | {keep(GA,i)*100:>8.1f}% {keep(GN,i)*100:>10.1f}% {keep(GM,i)*100:>10.1f}% {keep(GC,i)*100:>12.1f}%")
# 全局: 白墙多的帧 vs 少的帧
hi=[i for i in order[:33]]; lo=[i for i in order[-33:]]
for name,d in (("MVSA完整",GA),("Mono几何门",GM),("Mono conf0.6",GC)):
    h=np.nanmean([keep(d,i) for i in hi]); l=np.nanmean([keep(d,i) for i in lo])
    print(f"  {name:<14} 白墙最多的1/4帧 存活 {h*100:5.1f}%  |  白墙最少的1/4帧 {l*100:5.1f}%  比值 {h/max(l,1e-9):.2f}")
# MonoMVSNet 置信度在白墙帧上有多高
c=np.array(read_pfm(f"{SRC}/confidence/{order[0]:08d}.pfm")[0])
g=cv2.cvtColor(cv2.imread(f"{GM}/color/{order[0]:08d}.png"),cv2.COLOR_BGR2GRAY).astype(np.float32)
wm=(g>150)&(np.abs(cv2.Laplacian(g,cv2.CV_32F,ksize=3))<4)
print(f"\n帧 {order[0]} 上 MonoMVSNet 的置信度: 白墙区中位 {np.median(c[wm]):.3f} | 非白墙区中位 {np.median(c[~wm]):.3f}")
for t in (0.6,0.8,0.9,0.95):
    print(f"   conf>={t}: 白墙区还剩 {(c[wm]>=t).mean()*100:5.1f}%   非白墙区 {(c[~wm]>=t).mean()*100:5.1f}%")
