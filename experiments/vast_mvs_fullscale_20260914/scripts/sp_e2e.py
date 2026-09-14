# -*- coding: utf-8 -*-
"""端到端自证: 直接用 CasDiffMVS 官方 datasets/blend.py 的 MVSDataset 加载 SimpleProc。
   每项先按公式算预期,再对实测。含阴性对照。"""
import os, sys, numpy as np
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from datasets import find_dataset_def

ROOT="/root/monotrain"; LST="/root/sp_all.txt"
scans=sorted([d for d in os.listdir(ROOT) if d.startswith("sp_scene_")], key=lambda s:int(s.split("_")[-1]))
open(LST,"w").write("\n".join(scans)+"\n")
NS=len(scans); NDEPTH=384
print("场景数 = %d" % NS)
fail=[]
def ck(n,got,exp,tol=0.0):
    ok=(abs(got-exp)<=tol) if isinstance(exp,(int,float)) and not isinstance(exp,bool) else (got==exp)
    print("  %-52s 预期 %-20s 实测 %-20s %s"%(n,exp,got,"OK" if ok else "*** FAIL ***"))
    if not ok: fail.append(n)

MVSDataset=find_dataset_def("blend")

print()
print("=== 阴性对照: nviews=9 (官方 CasDiffMVS 值) 应被 blend.py:41 跳光 ===")
import contextlib, io as _io
buf=_io.StringIO()
with contextlib.redirect_stdout(buf):
    d9=MVSDataset(ROOT,LST,"train",9,NDEPTH)
ck("nviews=9 的元组数", len(d9), 0)

print()
print("=== 正臂: nviews=8 (SimpleProc 官方 num_images_in_tuple) ===")
with contextlib.redirect_stdout(buf):
    d8=MVSDataset(ROOT,LST,"train",8,NDEPTH)
ck("nviews=8 的元组数 = 场景数 x 8", len(d8), NS*8)

print()
print("=== 真实取样,逐项对形状/数值 ===")
s=d8[0]
ck("imgs 张数 = nviews", len(s["imgs"]), 8)
ck("imgs[0].shape (C,H,W)", tuple(s["imgs"][0].shape), (3,576,768))
ck("proj_matrices[stage4].shape", tuple(s["proj_matrices"]["stage4"].shape), (8,2,4,4))
ck("depth[stage4].shape", tuple(s["depth"]["stage4"].shape), (576,768))
ck("depth[stage1].shape = /8", tuple(s["depth"]["stage1"].shape), (72,96))
ck("depth_values.shape = ndepths", tuple(s["depth_values"].shape), (NDEPTH,))
ck("mask[stage4].sum() > 0  (上次训练崩在这)", float(s["mask"]["stage4"].sum())>0, True)

# depth_values 闭式解: linspace(1/dmax, 1/dmin, ndepths, endpoint=False)   blend.py:119-121
ref=s["proj_matrices"]["stage4"][0]
cam=os.path.join(ROOT,scans[0],"cams","00000000_cam.txt")
L=[l.rstrip() for l in open(cam)]
dmin,dmax=float(L[11].split()[0]),float(L[11].split()[-1])
exp=np.linspace(1/dmax,1/dmin,NDEPTH,endpoint=False).astype(np.float32)
ck("depth_values 与闭式解最大差", float(np.abs(s["depth_values"]-exp).max()), 0.0, tol=1e-9)

# stage1 内参 = stage4 内参/8   blend.py:147
p4=s["proj_matrices"]["stage4"]; p1=s["proj_matrices"]["stage1"]
ck("stage1 内参 == stage4/8 最大差", float(np.abs(p1[:,1,:2,:]-p4[:,1,:2,:]/8.0).max()), 0.0, tol=1e-6)

print()
print("=== 扫全量元组: 文件齐备 + mask 非空 (train 崩溃的两个根因) ===")
import random
random.seed(0)
idxs=random.sample(range(len(d8)), min(400,len(d8)))
bad_mask=0; err=0
for i in idxs:
    try:
        t=d8[i]
        if float(t["mask"]["stage4"].sum())<=0: bad_mask+=1
    except Exception as e:
        err+=1
        if err<=3: print("    异常:", type(e).__name__, str(e)[:110])
ck("抽 %d 条: 加载异常数"%len(idxs), err, 0)
ck("抽 %d 条: mask 全零数"%len(idxs), bad_mask, 0)

print()
print("===== %s =====" % ("端到端自证全部通过" if not fail else "失败: "+", ".join(fail)))
sys.exit(1 if fail else 0)
