#!/usr/bin/env python3.11
"""真彩 ROI viewer: ensemble 杀的点 vs 留的点 (top-down X-Z). 不加载 4K 图, 只用逐点 RGB."""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier"
d = np.load(OUT + "/joined_points.npz", allow_pickle=True)
xyz = d["xyz"]; rgb = d["rgb"].astype(float) / 255.0
E = d["enemy"]; W = d["wood"]; F = d["floor"]; allprob = d["allprob"]
pop = d["pop"]

# in-ROI 操作点: 选阈值使 chairFP kill≈0.81 (与诚实检验对齐)
ths = np.unique(np.round(allprob, 4))
target = 0.81
best_th = 0.5
for th in np.sort(ths):
    if (allprob[E] >= th).mean() <= target:
        best_th = th; break
kill = allprob >= best_th
ROI = E | W  # ROI 内点 (chairFP + 真木地板)

def panel(ax, sel, title):
    ax.scatter(xyz[sel, 0], xyz[sel, 2], c=rgb[sel], s=14, edgecolors="none")
    ax.set_title(title, fontsize=11)
    ax.set_xlim(0.25, 1.05); ax.set_ylim(-1.70, -0.55)
    ax.set_aspect("equal"); ax.set_xlabel("X (m)"); ax.set_ylabel("Z (m)")
    ax.invert_yaxis()

fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))
panel(axes[0], ROI, f"ROI 全部 ({ROI.sum()})\n蓝灰=椅子假阳 木色=真地板")
panel(axes[1], ROI & kill, f"ensemble 杀掉 ({int((ROI&kill).sum())})\nchairFP {int((E&kill).sum())}/{int(E.sum())}  真地板误杀 {int((W&kill).sum())}/{int(W.sum())}")
panel(axes[2], ROI & (~kill), f"ensemble 保留 ({int((ROI&~kill).sum())})\n残留 chairFP {int((E&~kill).sum())}  真地板存活 {int((W&~kill).sum())}")
fig.suptitle(f"U3 合成分类器 @ in-ROI 操作点 (p>={best_th:.3f}, chairFP kill {(kill[E]).mean()*100:.0f}%, 真地板保留 {(~kill[W]).mean()*100:.0f}%) — 真彩 top-down", fontsize=12)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT + "/viewer_roi_kill_vs_keep_truecolor.png", dpi=110)
print("saved viewer_roi_kill_vs_keep_truecolor.png  th=%.4f" % best_th)

# ROC-like 曲线 (in-ROI honest CV + clean-floor)
sw = json.load(open(OUT + "/sweeps.json"))
fig2, ax = plt.subplots(figsize=(6.4, 6))
roc_cf = np.array(sw["roc_lr_cv"])  # (1-floor_ret, fp_kill, th) vs clean floor
ax.plot(roc_cf[:, 0], roc_cf[:, 1], "-", color="#888", label="vs 区外干净地板 (乐观 AUC=0.92)")
# in-ROI: reconstruct from report
rep = json.load(open(OUT + "/classifier_report.json"))
ax.plot([1 - rep["results"]["HONEST_chairFP_vs_ROIwood_CV"]["roi_wood_retention"]],
        [rep["results"]["HONEST_chairFP_vs_ROIwood_CV"]["fp_kill_rate"]], "r*", ms=18,
        label="vs ROI内真地板 最佳操作点 (诚实 AUC=0.81)")
ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
ax.set_xlabel("真地板误杀率 (1 - retention)"); ax.set_ylabel("chairFP 杀灭率")
ax.set_title("ROC-like: 区外干净地板(伪) vs ROI内真地板(诚实)")
ax.legend(fontsize=8, loc="lower right"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
fig2.tight_layout(); fig2.savefig(OUT + "/roc_like_honest_vs_confound.png", dpi=110)
print("saved roc_like_honest_vs_confound.png")
