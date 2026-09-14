#!/usr/bin/env python3
"""老师傅(DAv2-Small,冻结)在白墙帧上到底看成什么样。
   三联:原图 | 单目相对深度 | 官方768 CasDiffMVS 深度(过官方门)
   两边都转成"相对深度",逐帧按 p2/p98 归一化,同一色标 ⇒ 比的是形状不是绝对距离。"""
import numpy as np, cv2, os, glob
OUT="/root/mono_vs"; os.makedirs(OUT, exist_ok=True)
FRAMES=[105,107,110,115,121,131]
def norm(x, m):
    v=x[m]
    if v.size<50: return np.zeros(x.shape+(3,), np.uint8)
    lo,hi=np.percentile(v,[2,98])
    t=np.clip((x-lo)/max(1e-9,hi-lo),0,1)
    c=cv2.applyColorMap((t*255).astype(np.uint8), cv2.COLORMAP_TURBO)
    c[~m]=(20,20,20)
    return c
def read_pfm(p):
    with open(p,"rb") as f:
        f.readline(); w,h=map(int,f.readline().split()); s=float(f.readline())
        a=np.fromfile(f,"<f4" if s<0 else ">f4").reshape(h,w)
    return np.flipud(a).astype(np.float32)
for i in FRAMES:
    rgb=cv2.imread(f"/root/mvs_P16k/images/{i:08d}.jpg")
    rgb=cv2.resize(rgb,(1152,832))
    disp=np.load(f"/root/mono_only/dav2s/{i:08d}.npy")          # DAv2 视差,越大越近
    mono_d=1.0/np.maximum(disp,1e-6)                             # -> 相对深度
    mono_c=norm(mono_d, np.ones(mono_d.shape,bool))
    z=read_pfm(f"/root/off768_true/depth_est/{i:08d}.pfm")
    m=cv2.imread(f"/root/off768_true/mask/{i:08d}_final.png", cv2.IMREAD_GRAYSCALE)>0
    mvs_c=norm(z, m&(z>0))
    mvs_c=cv2.resize(mvs_c,(1152,832),interpolation=cv2.INTER_NEAREST)
    lab=lambda img,t:(cv2.putText(img.copy(),t,(16,40),cv2.FONT_HERSHEY_SIMPLEX,1.1,(255,255,255),3,cv2.LINE_AA))
    row=np.hstack([lab(rgb,f"frame {i}  RGB"),
                   lab(mono_c,"DAv2-Small (frozen) relative depth"),
                   lab(mvs_c,"CasDiffMVS official768 depth")])
    row=cv2.resize(row,(row.shape[1]//2,row.shape[0]//2))
    cv2.imwrite(f"{OUT}/f{i:03d}.jpg", row, [cv2.IMWRITE_JPEG_QUALITY,88])
    print("wrote", i, "有效MVS像素 %.1f%%" % (100.0*(m&(z>0)).mean()), flush=True)
