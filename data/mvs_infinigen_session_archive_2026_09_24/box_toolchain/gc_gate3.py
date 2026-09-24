# -*- coding: utf-8 -*-
"""GPU 版 remap 的等价闸 + 速度闸。同一进程内翻开关, 输入逐位相同。

判据(cv2.remap 把亚像素量化到 1/32 px, 不可能逐位等于全精度 grid_sample):
  A 布尔掩码逐像素一致率 >= 99.99%   <- 这才是真正喂进 ξ 的东西
  B ξ 最大绝对差 < 1/总源数 (= 改变了不超过一个源视图的投票)
  C 每步开销回到预算内
"""
import sys, time, torch, numpy as np
sys.path.insert(0, "/root/diffmvs_gc")
from datasets.blend import MVSDataset
from torch.utils.data import DataLoader
import models.geo_weights as GW
from models.geo_weights import GeometricWeights


class Args:
    mask_type = "joint_inconsistency_mask"; cons2incon_type = "average"
    avg_weight_gap = "0.1"; dist_thresh = "1,0.5,0.25"
    relative_depth_diff_min_thresh = "0.01,0.005,0.0025"
    geo_mask_sum_thresh = 10; photo_mask_thresh = 0.9


ds = MVSDataset("/root/monotrain", "/root/diffmvs_gc/lists/full_v3/train.txt",
                "test", 8, 384, gc_src_depth=True)
sample = next(iter(DataLoader(ds, 4, shuffle=False, num_workers=4, drop_last=True)))
gw = GeometricWeights(Args())
S2I = {2: 0, 3: 1, 4: 2}
NSRC = len(sample["src_depths"]["stage4"])

print("=" * 82)
print("闸A/B  CPU(cv2.remap) vs GPU(grid_sample) 等价性 —— 同输入, 只翻开关")
print("=" * 82)
print("%-8s %-20s %14s %14s %10s" % ("stage", "喂的参考深度", "掩码一致率", "ξ最大绝对差", "判定"))
allok = True
for s in (2, 3, 4):
    sk = "stage%d" % s
    pm = sample["proj_matrices"][sk].cuda()
    src = [x.cuda() for x in sample["src_depths"][sk]]
    ref_gt = sample["depth"][sk].cuda()
    conf = torch.zeros_like(ref_gt)
    # 用真值 和 一个被扰动过的深度 各测一次: 后者代表训练中途的"预测还不准"的状态
    for lab, ref in (("真值", ref_gt), ("真值+3%噪声", ref_gt * (1 + 0.03 * torch.randn_like(ref_gt)))):
        GW.GPU_REMAP = False
        xi_cpu = gw.generate_geometric_weights(conf, ref, pm, src, S2I[s])[0].clone()
        GW.GPU_REMAP = True
        xi_gpu = gw.generate_geometric_weights(conf, ref, pm, src, S2I[s])[0].clone()
        GW.GPU_REMAP = False
        # ξ = 1 + mask_sum/NSRC  =>  mask_sum = (ξ-1)*NSRC, 还原成整数票数比掩码
        m_cpu = torch.round((xi_cpu - 1.0) * NSRC)
        m_gpu = torch.round((xi_gpu - 1.0) * NSRC)
        agree = float((m_cpu == m_gpu).float().mean())
        dmax = float((xi_cpu - xi_gpu).abs().max())
        ok = agree >= 0.9999 and dmax < 1.0 / NSRC + 1e-6
        allok &= ok
        print("%-8s %-20s %13.4f%% %14.6f %10s" % (sk, lab, 100 * agree, dmax, "OK" if ok else "FAIL"))
print()
print("闸A/B:", "通过" if allok else "未通过")

print()
print("=" * 82)
print("闸C  速度")
print("=" * 82)
PER_STEP = {2: 1, 3: 1, 4: 1}          # 方案B: 每档只算一次 (与上游 geo_loss 同基数)
BASE = 346.0
print("%-8s %12s %12s %10s" % ("stage", "CPU版 中位ms", "GPU版 中位ms", "提速"))
tot_cpu = tot_gpu = 0.0
for s in (2, 3, 4):
    sk = "stage%d" % s
    pm = sample["proj_matrices"][sk].cuda()
    src = [x.cuda() for x in sample["src_depths"][sk]]
    ref = sample["depth"][sk].cuda(); conf = torch.zeros_like(ref)
    res = {}
    for flag in (False, True):
        GW.GPU_REMAP = flag
        for _ in range(2):
            gw.generate_geometric_weights(conf, ref, pm, src, S2I[s])
        ts = []
        for _ in range(7):
            torch.cuda.synchronize(); t0 = time.time()
            gw.generate_geometric_weights(conf, ref, pm, src, S2I[s])
            torch.cuda.synchronize(); ts.append((time.time() - t0) * 1000)
        res[flag] = float(np.median(ts))
    GW.GPU_REMAP = False
    print("%-8s %12.1f %12.1f %9.1f×" % (sk, res[False], res[True], res[False] / res[True]))
    tot_cpu += res[False] * PER_STEP[s]; tot_gpu += res[True] * PER_STEP[s]
print()
print("基线每步 %.0f ms = %.1f h/epoch" % (BASE, BASE * 150000 / 3.6e6))
for lab, t in (("CPU版", tot_cpu), ("GPU版", tot_gpu)):
    print("%s  +%.0f ms => 每步 %.0f ms = %.1f h/epoch  (%.2f×)"
          % (lab, t, BASE + t, (BASE + t) * 150000 / 3.6e6, (BASE + t) / BASE))
