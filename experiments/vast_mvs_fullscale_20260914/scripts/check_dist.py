#!/usr/bin/env python3
"""训练用均匀深度假设(train_bld.sh 没传 --inverse_depth)。
   若 GT 挤在 [dmin,dmax] 的极小一段,8 个均匀假设就有大半落在空处 = 有效分辨率崩掉。
   量: GT 归一化位置 (d-dmin)/(dmax-dmin) 的分位数,以及 GT 实际占满范围的比例。"""
import sys, os, collections, numpy as np
sys.path.insert(0,"/root/MonoMVSNet"); os.chdir("/root/MonoMVSNet")
from datasets.blendedmvs import MVSDataset
ds = MVSDataset("/root/monotrain", "lists/ours/train_exact.txt", "train", 9, robust_train=True)
def bucket(s): return "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
idx_by = collections.defaultdict(list)
for i,(scan,_,_) in enumerate(ds.metas): idx_by[bucket(scan)].append(i)
rng = np.random.default_rng(1)
print(f"{'数据集':<12}{'样本':>4}{'p10':>8}{'p25':>8}{'p50':>8}{'p75':>8}{'p90':>8}{'p90-p10占满范围%':>18}{'8格里有GT的格数':>17}")
for b in ("BlendedMVG","Hypersim","TartanAir"):
    sel = rng.choice(idx_by[b], 24, replace=False)
    qs=[]; span=[]; bins=[]
    for i in sel:
        try: s = ds[int(i)]
        except Exception: continue
        d = s["depth"]["stage4"]; m = s["mask"]["stage4"]>0.5
        lo,hi = float(s["depth_values"][0]), float(s["depth_values"][-1])
        v = d[m]
        if v.size<100: continue
        t = (v-lo)/max(1e-9,(hi-lo))
        q = np.percentile(t,[10,25,50,75,90]); qs.append(q)
        span.append(100.0*(q[4]-q[0]))
        h,_ = np.histogram(t, bins=8, range=(0,1))
        bins.append(int((h > 0.005*len(t)).sum()))     # 占比>0.5%才算这一格"有GT"
    Q=np.median(np.array(qs),axis=0)
    print(f"{b:<12}{len(qs):>4}{Q[0]:>8.3f}{Q[1]:>8.3f}{Q[2]:>8.3f}{Q[3]:>8.3f}{Q[4]:>8.3f}"
          f"{np.median(span):>18.1f}{np.median(bins):>17.1f}")
