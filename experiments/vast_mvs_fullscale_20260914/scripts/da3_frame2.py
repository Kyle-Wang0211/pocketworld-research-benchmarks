import numpy as np, glob
d = np.load(sorted(glob.glob("/root/da3_full/exports/npz/*.npz"))[0], allow_pickle=True)
Eo = d["extrinsics"]                      # (132,3,4) 输出
Ko = d["intrinsics"]
# 输入(我们喂的)
import os
cams = sorted(glob.glob("/root/off768_true/cams/*_cam.txt"))
Ei=[]; Ki=[]
for p in cams:
    L=[l.rstrip() for l in open(p)]
    Ei.append(np.fromstring(" ".join(L[1:5]),sep=" ").reshape(4,4))
    Ki.append(np.fromstring(" ".join(L[7:10]),sep=" ").reshape(3,3))
Ei=np.stack(Ei); Ki=np.stack(Ki)
def centres(E34):
    R=E34[:,:3,:3]; t=E34[:,:3,3]
    return -np.einsum("nij,nj->ni", np.transpose(R,(0,2,1)), t)
Co = centres(Eo); Ci = centres(Ei[:,:3,:])
print("输出相机中心[0]", np.round(Co[0],4), " 输入", np.round(Ci[0],4))
print("逐相机中心距离 mm: p50 %.3f  p90 %.3f  max %.3f" % tuple(
      np.percentile(np.linalg.norm(Co-Ci,axis=1)*1000,[50,90,100])))
print("旋转逐位相同:", bool(np.allclose(Eo[:,:3,:3], Ei[:,:3,:3], atol=1e-4)))
print("内参逐位相同:", bool(np.allclose(Ko, Ki, atol=1e-2)), " 输出K[0]", np.round(Ko[0],1).tolist())
print("深度: 有效%%=%.1f  p50=%.3f m" % (100*float((d["depth"]>0).mean()), float(np.median(d["depth"][d["depth"]>0]))))
print("置信度 p40/p50/p90:", np.round(np.percentile(d["conf"],[40,50,90]),4).tolist())
