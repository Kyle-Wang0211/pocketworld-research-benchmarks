#!/usr/bin/env python3
"""直接用训练用的那个 MVSDataset 拉样本,量每个数据集的有效掩码占比。
   mask = (depth>=depth_min)&(depth<=depth_max),掩码为零的像素对 loss 完全没贡献。"""
import sys, os, collections, numpy as np
sys.path.insert(0,"/root/MonoMVSNet"); os.chdir("/root/MonoMVSNet")
from datasets.blendedmvs import MVSDataset
ds = MVSDataset("/root/monotrain", "lists/ours/train_exact.txt", "train", 9, robust_train=True)
print("metas(训练组数):", len(ds.metas))
def bucket(s): return "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
idx_by = collections.defaultdict(list)
for i,(scan,_,_) in enumerate(ds.metas): idx_by[bucket(scan)].append(i)
print("每桶组数:", {k:len(v) for k,v in idx_by.items()})
rng = np.random.default_rng(0)
print()
print(f"{'数据集':<12}{'样本':>5}{'stage4掩码%':>12}{'stage1掩码%':>12}{'GT>0被范围框住%':>17}{'depth_min':>11}{'depth_max':>11}")
for b in ("Hypersim","BlendedMVG","TartanAir"):
    sel = rng.choice(idx_by[b], 24, replace=False)
    m4=[]; m1=[]; cov=[]; dmn=[]; dmx=[]
    for i in sel:
        try: s = ds[int(i)]
        except Exception as e:
            print(f"  {b} idx {i} 取样失败: {type(e).__name__} {str(e)[:60]}"); continue
        m4.append(float(s["mask"]["stage4"].mean())*100)
        m1.append(float(s["mask"]["stage1"].mean())*100)
        d = s["depth"]["stage4"]; lo,hi = s["depth_values"][0], s["depth_values"][-1]
        pos = d>0
        cov.append(100.0*float(((d>=lo)&(d<=hi)&pos).sum())/max(1,int(pos.sum())))
        dmn.append(float(lo)); dmx.append(float(hi))
    print(f"{b:<12}{len(m4):>5}{np.median(m4):>12.1f}{np.median(m1):>12.1f}{np.median(cov):>17.1f}"
          f"{np.median(dmn):>11.1f}{np.median(dmx):>11.1f}")
