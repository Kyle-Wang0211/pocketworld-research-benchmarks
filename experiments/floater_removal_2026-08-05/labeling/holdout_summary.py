#!/usr/bin/env python3
"""汇总:口径对比(median vs max)、三分类阈值建议、遮挡失败模式统计。"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
d = np.load(f"{HERE}/holdout_ncc.npz", allow_pickle=True)
c = np.load(f"{HERE}/holdout_control.npz")
med, mx, mn = d["ncc_median"], d["ncc_max"], d["ncc_min"]
nh, dep, ntr = d["n_holdout"], d["ref_depth"], d["n_track"]
F = list(c["factors"]); NF = len(F)
cm, cx = c["ncc_median_ctrl"], c["ncc_max_ctrl"]

def auc(pos, neg):
    pos = pos[np.isfinite(pos)]; neg = neg[np.isfinite(neg)]
    a = np.concatenate([pos, neg]); y = np.concatenate([np.ones(pos.size), np.zeros(neg.size)])
    o = np.argsort(a); r = np.empty(len(a)); r[o] = np.arange(1, len(a) + 1)
    # 处理并列
    import scipy.stats as st  # noqa
    return float((r[y == 1].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))

print("=== 口径对比:AUC(real vs 各零分布) ===")
print(f"{'null':>12s} {'ncc_median':>11s} {'ncc_max':>9s} {'ncc_min':>9s}")
for fi, s in enumerate(F):
    print(f"{'s=%.2f'%s:>12s} {auc(med, cm[:,fi]):11.3f} {auc(mx, cx[:,fi]):9.3f} "
          f"{'-':>9s}")
print(f"{'random':>12s} {auc(med, cm[:,NF]):11.3f} {auc(mx, cx[:,NF]):9.3f}")

# 合并所有深度扰动作为统一 floater 零分布
neg_med = np.concatenate([cm[:, fi][np.isfinite(cm[:, fi])] for fi in range(NF)])
neg_max = np.concatenate([cx[:, fi][np.isfinite(cx[:, fi])] for fi in range(NF)])
print(f"\n合并深度扰动零分布 n={neg_med.size}: "
      f"med p50={np.percentile(neg_med,50):+.3f} p75={np.percentile(neg_med,75):+.3f} "
      f"p90={np.percentile(neg_med,90):+.3f} p95={np.percentile(neg_med,95):+.3f} "
      f"p99={np.percentile(neg_med,99):+.3f}")
print(f"                          max p50={np.percentile(neg_max,50):+.3f} "
      f"p75={np.percentile(neg_max,75):+.3f} p90={np.percentile(neg_max,90):+.3f} "
      f"p95={np.percentile(neg_max,95):+.3f} p99={np.percentile(neg_max,99):+.3f}")
print(f"AUC(real vs 合并零分布): median={auc(med, neg_med):.3f} max={auc(mx, neg_max):.3f}")

v = np.isfinite(med)
print("\n=== 三分类阈值候选(以零分布分位数锚定) ===")
print(f"{'real_thr':>9s} {'flt_thr':>8s} | {'real':>5s} {'unc':>5s} {'flt':>5s} | "
      f"{'零分布落入real(污染)':>12s} {'零分布落入flt(召回)':>12s}")
for rt, ft in [(0.45, 0.15), (0.45, 0.10), (0.50, 0.15), (0.40, 0.15),
               (0.55, 0.20), (0.50, 0.20), (0.60, 0.10)]:
    nr = int((med[v] >= rt).sum()); nf = int((med[v] < ft).sum())
    nu = int(v.sum()) - nr - nf
    print(f"{rt:9.2f} {ft:8.2f} | {nr:5d} {nu:5d} {nf:5d} | "
          f"{100*(neg_med>=rt).mean():17.1f}% {100*(neg_med<ft).mean():17.1f}%")

print("\n=== 遮挡/假阴性诊断(median 低但 max 高) ===")
for ft in [0.15, 0.20]:
    lowm = v & (med < ft)
    for mt in [0.5, 0.6, 0.7]:
        k = int((lowm & (mx >= mt)).sum())
        print(f"  med<{ft:.2f} & max>={mt:.1f}: {k:3d} / {int(lowm.sum())} "
              f"({100*k/max(lowm.sum(),1):.0f}%)  <- 疑似遮挡假阴性")
    break
print("  同口径在合并零分布上的比例(基准):")
lowneg = neg_med < 0.15
for mt in [0.5, 0.6, 0.7]:
    k = int((lowneg & (neg_max >= mt)).sum())
    print(f"  med<0.15 & max>={mt:.1f}: {k:4d} / {int(lowneg.sum())} "
          f"({100*k/max(lowneg.sum(),1):.0f}%)")

print("\n=== median 与 max 的口径差 ===")
sp = (mx - med)[v]
print(f"  max-median: p25={np.percentile(sp,25):.3f} p50={np.percentile(sp,50):.3f} "
      f"p75={np.percentile(sp,75):.3f} p95={np.percentile(sp,95):.3f}")
print(f"  合并零分布同口径差 p50={np.percentile(neg_max,50)-np.percentile(neg_med,50):.3f}")

print("\n=== 覆盖率 ===")
st = d["status"]
print("  status:", {k: int((st == k).sum()) for k in sorted(set(st.tolist()))})
print("  n_holdout:", {int(k): int((nh == k).sum()) for k in sorted(set(nh.tolist()))})
print(f"  ref_depth: p5={np.nanpercentile(dep,5):.2f} p50={np.nanpercentile(dep,50):.2f} "
      f"p95={np.nanpercentile(dep,95):.2f} m")
print(f"  n_track:   p5={np.percentile(ntr,5):.0f} p50={np.percentile(ntr,50):.0f} "
      f"p95={np.percentile(ntr,95):.0f}")

# 建议标签(供主会话参考,阈值可改)
RT, FT = 0.45, 0.15
lab = np.full(len(med), "uncertain", dtype=object)
lab[~v] = "excluded"
lab[v & (med >= RT)] = "real"
lab[v & (med < FT)] = "floater"
np.save(f"{HERE}/holdout_label_suggested.npy", np.array(lab))
print(f"\n建议标签(real>={RT}, floater<{FT})已存 holdout_label_suggested.npy:",
      {k: int((lab == k).sum()) for k in ["real", "uncertain", "floater", "excluded"]})
