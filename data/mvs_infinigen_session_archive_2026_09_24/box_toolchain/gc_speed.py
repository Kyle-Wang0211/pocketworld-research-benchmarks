# -*- coding: utf-8 -*-
"""闸3: ξ 的真实耗时, 以及按 CasDiffMVS 的迭代结构换算成每步开销。"""
import sys, time, torch, numpy as np
sys.path.insert(0, "/root/diffmvs_gc")
from datasets.blend import MVSDataset
from models.geo_weights import GeometricWeights
from torch.utils.data import DataLoader

class Args:
    mask_type="joint_inconsistency_mask"; cons2incon_type="average"
    avg_weight_gap="0.1"; dist_thresh="1,0.5,0.25"
    relative_depth_diff_min_thresh="0.01,0.005,0.0025"
    geo_mask_sum_thresh=10; photo_mask_thresh=0.9

ds = MVSDataset("/root/monotrain","/root/diffmvs_gc/lists/full_v3/train.txt","test",8,384,gc_src_depth=True)
sample = next(iter(DataLoader(ds,4,shuffle=False,num_workers=4,drop_last=True)))
gw = GeometricWeights(Args()); S2I={2:0,3:1,4:2}
# CasDiffMVS iters=[1,3,3] => stage_id = [1] + [2]*4 + [3]*4 + [4]
per_step_count = {2:4, 3:4, 4:1}
print("%-8s %10s %10s %10s %8s %12s" % ("stage","ξ中位ms","最小","最大","每步次数","每步小计ms"))
tot_all=0.0; tot_last=0.0
for s in (2,3,4):
    sk="stage%d"%s
    pm=sample["proj_matrices"][sk].cuda()
    src=[x.cuda() for x in sample["src_depths"][sk]]
    ref=sample["depth"][sk].cuda(); conf=torch.zeros_like(ref)
    ts=[]
    for _ in range(7):
        torch.cuda.synchronize(); t0=time.time()
        gw.generate_geometric_weights(conf, ref, pm, src, S2I[s])
        torch.cuda.synchronize(); ts.append((time.time()-t0)*1000)
    med=float(np.median(ts))
    print("%-8s %10.1f %10.1f %10.1f %8d %12.1f" % (sk,med,min(ts),max(ts),per_step_count[s],med*per_step_count[s]))
    tot_all += med*per_step_count[s]; tot_last += med
print()
BASE=346.0
print("基线每步            %.0f ms  (150,000 步/epoch = %.1f h)" % (BASE, BASE*150000/3.6e6))
print("方案A 每次迭代都算 ξ (9次/步)  +%.0f ms => 每步 %.0f ms = %.1f h/epoch  (%.1f×)" %
      (tot_all, BASE+tot_all, (BASE+tot_all)*150000/3.6e6, (BASE+tot_all)/BASE))
print("方案B 每档只算一次 ξ (3次/步)  +%.0f ms => 每步 %.0f ms = %.1f h/epoch  (%.1f×)" %
      (tot_last, BASE+tot_last, (BASE+tot_last)*150000/3.6e6, (BASE+tot_last)/BASE))
