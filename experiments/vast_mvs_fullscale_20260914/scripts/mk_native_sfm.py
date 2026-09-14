#!/usr/bin/env python3
"""把 768x576 的 SfMData 换成 4032x3008 原生:内参逐视图从 off_native/cams 读,约定与 sfm_poses_pp.sfm 一致
   (principalPoint = 相对图像中心的偏移, focalLength = fx*sensorWidth/width, pixelRatio = fy/fx)。"""
import json, glob, numpy as np, os
d=json.load(open("/root/av/sfm_poses_pp.sfm"))
K={}
for p in sorted(glob.glob("/root/off_native/cams/*_cam.txt")):
    i=int(os.path.basename(p)[:8]); L=[l.rstrip() for l in open(p)]
    K[i]=np.fromstring(" ".join(L[7:10]),sep=" ").reshape(3,3)
W,H=4032,3008
name2idx={f"{i:08d}.jpg":i for i in K}
for v in d["views"]:
    n=v["path"].rsplit("/",1)[-1]; i=name2idx[n]
    v["path"]=f"/root/off_native/images/{n}"; v["width"]=str(W); v["height"]=str(H)
for it in d["intrinsics"]:
    iid=int(it["intrinsicId"]); k=K[iid]
    it["width"]=str(W); it["height"]=str(H)
    it["sensorWidth"]="36"; it["sensorHeight"]=f"{36.0*H/W:.17g}"
    it["focalLength"]=f"{k[0,0]*36.0/W:.17g}"
    it["pixelRatio"]=f"{k[1,1]/k[0,0]:.17g}"
    it["principalPoint"]=[f"{k[0,2]-W/2:.6f}", f"{k[1,2]-H/2:.6f}"]
json.dump(d, open("/root/av/sfm_native_pp.sfm","w"))
v=d["views"][0]; it=d["intrinsics"][0]
print("view0:", v["path"], v["width"]+"x"+v["height"])
print("intr0:", {q:it[q] for q in ("width","height","focalLength","pixelRatio","principalPoint","sensorWidth","sensorHeight")})
print("自证 fx =", float(it["focalLength"])/36.0*W, " (cam文件", K[0][0,0], ")")
print("自证 fy =", float(it["focalLength"])/36.0*W*float(it["pixelRatio"]), " (cam文件", K[0][1,1], ")")
