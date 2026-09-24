# -*- coding: utf-8 -*-
"""闸2 重做。

第一次的阳性对照设计错了: 我拿"喂参考视图自己的真值深度 => ξ 应≈1"当判据,
但真实多视图里一个像素本来就只在一部分源视图里可见, 不可见的源必然判不一致。
ξ=2.40 有可能是【方法本身的行为】而不是【移植错了】。要分开这两件事, 得换对照。

真正的阳性对照 = 拿我们项目自己独立写的那份实现比:
  /root/diffmvs/filter.py::check_geometric_consistency  (同一个 Yao 检查, 另一套代码)
同输入同阈值下, GC 的"不一致掩码"必须恰好是 filter.py"一致掩码"的补集。
这条过了, 就证明几何算对了; ξ 高是方法特性, 不是 bug。
"""
import sys, numpy as np, torch
sys.path.insert(0, "/root/diffmvs_gc")
from datasets.blend import MVSDataset
from models.geo_weights import GeometricWeights
from torch.utils.data import DataLoader
import importlib.util
spec = importlib.util.spec_from_file_location("pwfilter", "/root/diffmvs/filter.py")
pwf = importlib.util.module_from_spec(spec)
sys.modules["pwfilter"] = pwf
spec.loader.exec_module(pwf)


class Args:
    mask_type = "joint_inconsistency_mask"
    cons2incon_type = "average"
    avg_weight_gap = "0.2"
    dist_thresh = "1,0.5,0.25"
    relative_depth_diff_min_thresh = "0.01,0.005,0.0025"
    geo_mask_sum_thresh = 8
    photo_mask_thresh = 0.9


ds = MVSDataset("/root/monotrain", "/root/diffmvs_gc/lists/full_v3/train.txt",
                "test", 8, 384, gc_src_depth=True)
dl = DataLoader(ds, 4, shuffle=False, num_workers=4, drop_last=True)
sample = next(iter(dl))
gw = GeometricWeights(Args())
S2I = {2: 0, 3: 1, 4: 2}
DIST = [1.0, 0.5, 0.25]
RDD = [0.01, 0.005, 0.0025]

print("=" * 78)
print("闸2-A  两份独立实现的掩码是否互补 (GC不一致 vs filter.py一致)")
print("=" * 78)
print("%-8s %-5s %10s %10s %10s %10s" % ("stage", "源", "GC不一致%", "filter一致%", "互补一致率", "判定"))
allok = True
for s in (2, 3, 4):
    sk = "stage%d" % s
    pm = sample["proj_matrices"][sk]
    ref_gt_t = sample["depth"][sk]
    for b in (0,):
        Kref = pm[b, 0, 1, :3, :3]; Eref = pm[b, 0, 0, :4, :4]
        ref = ref_gt_t[b]
        for si in (0, 1, 2):
            Ksrc = pm[b, si + 1, 1, :3, :3]; Esrc = pm[b, si + 1, 0, :4, :4]
            src = sample["src_depths"][sk][si][b]
            # GC 版 (cuda)
            gcm = gw.geometric_inconsistency_mask(
                ref.cuda(), Kref.cuda(), Eref.cuda(), src.cuda(),
                Ksrc.cuda(), Esrc.cuda(), S2I[s]).cpu().numpy().astype(bool)
            # 我们自己的 filter.py 版 (numpy)。把深度范围门放到最宽, 只比几何那两项
            fm, _, _, _ = pwf.check_geometric_consistency(
                ref.numpy(), Kref.numpy(), Eref.numpy(), src.numpy(),
                Ksrc.numpy(), Esrc.numpy(),
                1e9, -1e9, DIST[S2I[s]], RDD[S2I[s]])
            agree = float((gcm == ~fm).mean())
            ok = agree > 0.999
            allok &= ok
            print("%-8s %-5d %9.2f%% %10.2f%% %10.4f%% %10s" % (
                sk, si, 100 * gcm.mean(), 100 * fm.mean(), 100 * agree,
                "✅" if ok else "🔴"))
print()
print("闸2-A:", "✅ 通过 —— 两份独立实现逐像素互补" if allok else "🔴 未通过")

print()
print("=" * 78)
print("闸2-B  ξ=2.4 到底是遮挡还是 bug: 真值深度下有几个源视图判一致")
print("=" * 78)
sk = "stage3"
pm = sample["proj_matrices"][sk]; ref_gt_t = sample["depth"][sk]
b = 0
Kref = pm[b, 0, 1, :3, :3].numpy(); Eref = pm[b, 0, 0, :4, :4].numpy()
ref = ref_gt_t[b].numpy()
sumok = np.zeros(ref.shape, np.int32)
inview = np.zeros(ref.shape, np.int32)
for si in range(7):
    Ksrc = pm[b, si + 1, 1, :3, :3].numpy(); Esrc = pm[b, si + 1, 0, :4, :4].numpy()
    src = sample["src_depths"][sk][si][b].numpy()
    fm, _, x2, y2 = pwf.check_geometric_consistency(
        ref, Kref, Eref, src, Ksrc, Esrc, 1e9, -1e9, DIST[1], RDD[1])
    sumok += fm.astype(np.int32)
    H, W = ref.shape
    inview += ((x2 >= 0) & (x2 < W) & (y2 >= 0) & (y2 < H) & (src.max() > 0)).astype(np.int32)
v = ref > 0
print("参考视图有效像素 %d / %d" % (v.sum(), ref.size))
print("落在源视图画面内的源数  中位 %.1f  均值 %.2f" % (np.median(inview[v]), inview[v].mean()))
print("判为几何一致的源数      中位 %.1f  均值 %.2f" % (np.median(sumok[v]), sumok[v].mean()))
for k in range(8):
    print("   恰好 %d 个源一致: %6.2f%%" % (k, 100 * (sumok[v] == k).mean()))
print()
print("若「一致源数」远小于「在画面内的源数」=> 是真不一致; 二者接近 => ξ 高来自遮挡/不共视")
