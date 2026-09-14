# -*- coding: utf-8 -*-
import sys, os, numpy as np
sys.path.insert(0,"/root/diffmvs")
from datasets.data_io import read_pfm
from PIL import Image
import matplotlib; matplotlib.use("Agg")
import matplotlib.cm as cm
A="/root/arm_before"; B="/root/arm_after"
def load(root,v):
    return np.array(read_pfm("%s/depth_est/%s.pfm"%(root,v))[0],dtype=np.float32)
def colorize(d, lo, hi):
    x=np.clip((d-lo)/(hi-lo),0,1); x[~np.isfinite(d)]=0
    return (cm.turbo(x)[:,:,:3]*255).astype(np.uint8)
frames=["00000131","00000122","00000130","00000125"]
tiles=[]
for v in frames:
    img=np.array(Image.open("%s/images/%s.jpg"%(A,v)).convert("RGB"))
    da,db=load(A,v),load(B,v)
    m=np.isfinite(da)&np.isfinite(db)&(da>0)&(db>0)
    lo,hi=float(np.percentile(da[m],2)),float(np.percentile(da[m],98))
    ca,cb=colorize(da,lo,hi),colorize(db,lo,hi)
    rel=np.zeros_like(da); rel[m]=np.abs(db[m]-da[m])/da[m]
    cd=(cm.inferno(np.clip(rel/0.5,0,1))[:,:,:3]*255).astype(np.uint8)
    row=np.concatenate([img,ca,cb,cd],axis=1)
    tiles.append(row)
    print("%s  深度色标 %.2f-%.2f m  差异>10%%占比 %.4f" % (v,lo,hi,float((rel[m]>0.1).mean())))
sheet=np.concatenate(tiles,axis=0)
Image.fromarray(sheet).resize((sheet.shape[1]//2, sheet.shape[0]//2)).save("/root/wedge_diag.jpg",quality=92)
print("列: 原图 | 训前深度 | 训后深度 | 相对差(0-50%%,亮=大)")
print("行:", frames)
