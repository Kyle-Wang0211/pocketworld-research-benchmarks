# -*- coding: utf-8 -*-
"""GC 权重移植的三道闸。在花任何 GPU 训练预算之前跑。

  闸1 关闭等价性 : --gc_weight 0 时, 打过补丁的 loss 必须与原版【逐位相同】
                   (两个独立进程, 一个 sys.path 指 diffmvs_full, 一个指 diffmvs_gc)
  闸2 阳/阴对照  : 喂【参考视图自己的真值深度】当预测 => ξ 必须≈1 (几何自洽);
                   喂被破坏的深度 => ξ 必须显著变大。证明它真在量几何, 不是恒返回 1。
  闸3 速度       : 实测每次 ξ 的耗时。上游 batch1×2源×3档=6 次重投影/步,
                   我们 batch4×7源×3档=84 次。超过预算就得先把 cv2.remap 改写。

用法: gc_gate.py loss <repo>   |   gc_gate.py gc
"""
import sys, os, time, struct

MODE = sys.argv[1]

# ----------------------------------------------------------------- 闸1
if MODE == "loss":
    repo = sys.argv[2]
    sys.path.insert(0, repo)
    import torch
    from models.loss import compute_inverse_loss

    class A: conf_weight = 0.05
    torch.manual_seed(1234)
    B, ND = 2, 384
    HW = {1: (72, 96), 2: (144, 192), 3: (288, 384), 4: (576, 768)}
    iters = [1, 3, 3]
    stage_id = ([1] * iters[0] + [2] * (iters[1] + 1) + [3] * (iters[2] + 1) + [4])
    conf_flag = ([False] * (iters[0] + 1) + [True] * iters[1] + [False] +
                 [True] * iters[2] + [False])
    # 固定种子 => 两个进程拿到逐位相同的输入
    inputs, confs, gt, msk = [], [], {}, {}
    for s in (1, 2, 3, 4):
        h, w = HW[s]
        gt["stage{}".format(s)] = torch.rand(B, h, w) * 4 + 0.5
        msk["stage{}".format(s)] = (torch.rand(B, h, w) > 0.2).float()
    for sid in stage_id:
        h, w = HW[sid]
        inputs.append(torch.rand(B, h, w) * 4 + 0.5)
    for f in conf_flag:
        if f:
            pass
    for _ in range(sum(conf_flag)):
        confs.append(torch.rand(B, 1, 1) * 0)          # 占位, 形状会被广播
    # confs 要与 depth 同形
    confs = []
    ci = 0
    for i, f in enumerate(conf_flag):
        if f:
            h, w = HW[stage_id[i]]
            confs.append(torch.rand(B, h, w) * 0.8 + 0.1)
    dmin, dmax = 0.5, 6.0
    depth_values = torch.linspace(1 / dmax, 1 / dmin, ND).unsqueeze(0).repeat(B, 1)

    inputs = [x.cuda() for x in inputs]
    confs = [x.cuda() for x in confs]
    gt = {k: v.cuda() for k, v in gt.items()}
    msk = {k: v.cuda() for k, v in msk.items()}
    depth_values = depth_values.cuda()

    total, d = compute_inverse_loss(A(), inputs, confs, gt, msk, depth_values,
                                    loss_rate=0.9, iters=iters)
    # 打印逐位表示, 不是打印小数
    out = [struct.pack(">d", float(total)).hex()]
    for k in sorted(d, key=lambda x: int(x[1:])):
        out.append("%s=%s" % (k, struct.pack(">d", float(d[k])).hex()))
    print(" ".join(out))
    sys.exit(0)

# ----------------------------------------------------------------- 闸2 + 闸3
sys.path.insert(0, "/root/diffmvs_gc")
import torch, numpy as np
from datasets.blend import MVSDataset
from models.geo_weights import GeometricWeights
from torch.utils.data import DataLoader


class Args:
    mask_type = "joint_inconsistency_mask"
    cons2incon_type = "average"
    avg_weight_gap = "0.2"
    dist_thresh = "1,0.5,0.25"
    relative_depth_diff_min_thresh = "0.01,0.005,0.0025"
    geo_mask_sum_thresh = 8
    photo_mask_thresh = 0.9


BATCH = 4
ds = MVSDataset("/root/monotrain", "/root/diffmvs_gc/lists/full_v3/train.txt",
                "test", 8, 384, gc_src_depth=True)
dl = DataLoader(ds, BATCH, shuffle=False, num_workers=4, drop_last=True)
sample = next(iter(dl))
print("[数据] imgs", len(sample["imgs"]), "视图 | src_depths 每档", len(sample["src_depths"]["stage4"]), "个源")
for s in (1, 2, 3, 4):
    print("       stage%d 参考深度 %s  源深度 %s" % (
        s, tuple(sample["depth"]["stage%d" % s].shape),
        tuple(sample["src_depths"]["stage%d" % s][0].shape)))

gw = GeometricWeights(Args())
STAGE2IDX = {2: 0, 3: 1, 4: 2}

print()
print("%-8s %-26s %8s %8s %8s %8s" % ("stage", "喂给它的参考深度", "ξ均值", "ξ最小", "ξ最大", "耗时ms"))
for s in (2, 3, 4):
    sk = "stage%d" % s
    pm = sample["proj_matrices"][sk].cuda()
    src = [x.cuda() for x in sample["src_depths"][sk]]
    ref_gt = sample["depth"][sk].cuda()
    conf = torch.zeros_like(ref_gt)

    for label, ref in (("真值(阳性:应≈1)", ref_gt),
                       ("真值×1.10(阴性)", ref_gt * 1.10),
                       ("真值左右翻转(阴性)", torch.flip(ref_gt, dims=[2]))):
        torch.cuda.synchronize(); t0 = time.time()
        xi = gw.generate_geometric_weights(conf, ref, pm, src, STAGE2IDX[s])[0]
        torch.cuda.synchronize(); ms = (time.time() - t0) * 1000
        v = xi[ref_gt > 0]
        print("%-8s %-26s %8.4f %8.4f %8.4f %8.1f" % (
            sk, label, float(v.mean()), float(v.min()), float(v.max()), ms))
    print()
