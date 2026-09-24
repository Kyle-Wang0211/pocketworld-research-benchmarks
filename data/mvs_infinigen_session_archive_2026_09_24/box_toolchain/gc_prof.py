# -*- coding: utf-8 -*-
"""GPU 路径下剩余开销在哪。逐段掐表, 不猜。"""
import sys, time, torch, numpy as np
sys.path.insert(0, "/root/diffmvs_gc")
from datasets.blend import MVSDataset
from torch.utils.data import DataLoader
import models.geo_weights as GW
GW.GPU_REMAP = True
from models.geo_weights import GeometricWeights

class Args:
    mask_type="joint_inconsistency_mask"; cons2incon_type="average"
    avg_weight_gap="0.1"; dist_thresh="1,0.5,0.25"
    relative_depth_diff_min_thresh="0.01,0.005,0.0025"
    geo_mask_sum_thresh=10; photo_mask_thresh=0.9

ds = MVSDataset("/root/monotrain","/root/diffmvs_gc/lists/full_v3/train.txt","test",8,384,gc_src_depth=True)
sample = next(iter(DataLoader(ds,4,shuffle=False,num_workers=4,drop_last=True)))
sk="stage4"; H,W = sample["depth"][sk].shape[1:]
pm=sample["proj_matrices"][sk].cuda(); src=[x.cuda() for x in sample["src_depths"][sk]]
ref=sample["depth"][sk].cuda()
print("stage4 %dx%d, batch %d, 源 %d => 每次 ξ 做 %d 次 reproject" % (H,W,ref.shape[0],len(src),ref.shape[0]*len(src)))

def t(fn, n=30):
    for _ in range(3): fn()
    torch.cuda.synchronize(); t0=time.time()
    for _ in range(n): fn()
    torch.cuda.synchronize(); return (time.time()-t0)/n*1000

N = ref.shape[0]*len(src)
print()
print("%-46s %10s %12s" % ("单次操作", "ms", "×%d 合计ms" % N))
# 1) 上游每次都在 CPU 建 meshgrid 再传显存 (reproject_with_depth 和 geometric_*_mask 各建一次)
def mg():
    x,y = torch.meshgrid(torch.arange(0,W), torch.arange(0,H), indexing='xy')
    x,y = x.reshape([-1]), y.reshape([-1])
    return x.to(device='cuda'), y.to(device='cuda')
a = t(mg); print("%-46s %10.3f %12.1f" % ("CPU建meshgrid+搬显存 (每次reproject建1次)", a, a*N))
print("%-46s %10.3f %12.1f" % ("  同上, geometric_*_mask 里还建一次(只建不搬)", t(lambda: torch.meshgrid(torch.arange(0,W), torch.arange(0,H), indexing='xy')), t(lambda: torch.meshgrid(torch.arange(0,W), torch.arange(0,H), indexing='xy'))*N))
# 2) 四次 inv
Ki=pm[0,0,1,:3,:3]; Ei=pm[0,0,0,:4,:4]
b = t(lambda: (torch.linalg.inv(Ki), torch.linalg.inv(Ei), torch.linalg.inv(Ki), torch.linalg.inv(Ei)))
print("%-46s %10.3f %12.1f" % ("4× torch.linalg.inv (3x3/4x4)", b, b*N))
# 3) grid_sample 本身
d = torch.rand(H,W,device='cuda'); xm=torch.rand(H,W,device='cuda')*W; ym=torch.rand(H,W,device='cuda')*H
c = t(lambda: GW._remap_bilinear_gpu(d, xm, ym))
print("%-46s %10.3f %12.1f" % ("grid_sample 本体", c, c*N))
# 4) 整个 reproject
gw=GeometricWeights(Args())
e = t(lambda: gw.reproject_with_depth(ref[0], Ki, Ei, src[0][0], pm[0,1,1,:3,:3], pm[0,1,0,:4,:4]), 10)
print("%-46s %10.3f %12.1f" % ("整个 reproject_with_depth", e, e*N))
f = t(lambda: gw.generate_geometric_weights(torch.zeros_like(ref), ref, pm, src, 2), 5)
print()
print("整个 ξ (generate_geometric_weights)  %.1f ms" % f)
print("其中 %d 次 reproject 占 %.1f ms (%.0f%%)" % (N, e*N, 100*e*N/f))
