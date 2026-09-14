# -*- coding: utf-8 -*-
"""TartanGround 端到端自证: 直接用 CasDiffMVS 官方 datasets/blend.py 的 MVSDataset。"""
import os, sys, random, contextlib, io as _io, numpy as np
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
from datasets import find_dataset_def
ROOT="/root/monotrain"
tg=sorted([d for d in os.listdir(ROOT) if d.startswith("tg_")])
LST="/root/tg_probe.txt"; open(LST,"w").write("\n".join(tg)+"\n")
print("TartanGround scans: %d" % len(tg))
MVS=find_dataset_def("blend"); buf=_io.StringIO()
fail=[]
def ck(n,got,exp,tol=0.0):
    ok=(abs(got-exp)<=tol) if isinstance(exp,(int,float)) and not isinstance(exp,bool) else (got==exp)
    print("  %-46s 预期 %-18s 实测 %-18s %s"%(n,exp,got,"OK" if ok else "*** FAIL ***"))
    if not ok: fail.append(n)
for nv in (8,9):
    with contextlib.redirect_stdout(buf):
        d=MVS(ROOT,LST,"train",nv,384)
    print()
    print("=== nviews=%d : %d 条元组 ===" % (nv, len(d)))
    if len(d)==0: continue
    random.seed(0); idxs=random.sample(range(len(d)), min(300,len(d)))
    err=0; badmask=0; shapes=set(); nimg=set()
    for i in idxs:
        try:
            s=d[i]
            nimg.add(len(s["imgs"])); shapes.add(tuple(s["imgs"][0].shape))
            if float(s["mask"]["stage4"].sum())<=0: badmask+=1
        except Exception as e:
            err+=1
            if err<=2: print("    异常:",type(e).__name__,str(e)[:100])
    ck("抽 %d 条: 加载异常"%len(idxs), err, 0)
    ck("抽 %d 条: mask 全零"%len(idxs), badmask, 0)
    ck("imgs 张数集合", sorted(nimg), [nv])
    ck("imgs[0].shape 集合", sorted(shapes), [(3,576,768)])
print()
print("===== %s =====" % ("TartanGround 端到端自证通过" if not fail else "失败: "+", ".join(fail)))
