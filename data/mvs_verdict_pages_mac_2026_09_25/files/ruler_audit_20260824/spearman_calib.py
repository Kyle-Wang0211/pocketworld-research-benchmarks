#!/usr/bin/env python3
"""秩相关校准 —— 用户肉眼四臂排序当标签,算每把尺子输出排序与肉眼的 Spearman 秩相关。

肉眼排序(2026-08-19 给定,唯一被校准的标签):
    blendmvg(完全没有) > blend(有一些连接) > dtu ≈ C(明显鬼层)
  -> "肉眼坏度"(越大越差,ties 用平均秩): blendmvg=1, blend=2, dtu=3, C=3

只在这四臂上算(新权重没有肉眼标签,不参与本步)。
"""
import json
from scipy.stats import spearmanr

ARMS = ["blendmvg", "blend", "dtu", "C"]
EYE_BAD = {"blendmvg": 1, "blend": 2, "dtu": 3, "C": 3}  # 越大越差,dtu/C 并列

OUT = "~/Documents/progecttwo/_host_experiments/pose_ablation_20260818/ruler_audit_20260824"


def load(p):
    return json.load(open(p))


def calib(name, data, fields, note=""):
    print(f"\n### {name} {note}")
    eye = [EYE_BAD[a] for a in ARMS]
    for field in fields:
        vals = [data[a][field] for a in ARMS]
        rho, p = spearmanr(eye, vals)
        tag = "✅与肉眼一致" if rho > 0.5 else ("❌与肉眼反向(退役候选)" if rho < -0.5 else "⚠️弱/无相关")
        print(f"  {field:<10} 值={['%.3f'%v for v in vals]}  rho={rho:+.3f}  p={p:.3f}  {tag}")


def main():
    print("肉眼坏度标签(4臂,越大越差): " + str(EYE_BAD))

    # cloud_vs_ref / verdict_vs_ref(同一脚本,已确认逐比特一致)
    d = load(f"{OUT}/cloud_vs_ref_full5.json")
    calib("cloud_vs_ref.py(原生密度,sub=8)", d, ["p50", "p90", "p99", "gt2", "gt5"])

    # wall_flatness
    d = load(f"{OUT}/wall_flatness_full5.json")
    calib("wall_flatness.py(原生密度,sub=4)", d, ["rms", "p95", "gt2cm", "slope", "span"])

    # ghost_mass(原 JSON 已含五臂,直接读原文件)
    d = load("~/Documents/progecttwo/_host_experiments/pose_ablation_20260818/ghost_mass.json")
    calib("ghost_mass.py(原生密度,sub=8)", d, ["mass", "far", "clustered", "biggest"])

    print("\n" + "=" * 70)
    print("同保留率(降采样到 dtu 的 2,329,310 点,种子 20260824)之后:")
    print("=" * 70)

    d = load(f"{OUT}/dnorm_cloud_vs_ref.json")
    calib("cloud_vs_ref.py(密度归一)", d, ["p50", "p90", "p99", "gt2", "gt5"])

    d = load(f"{OUT}/dnorm_wall_flatness.json")
    calib("wall_flatness.py(密度归一)", d, ["rms", "p95", "gt2cm", "slope", "span"])

    d = load(f"{OUT}/dnorm_ghost_mass.json")
    calib("ghost_mass.py(密度归一)", d, ["mass", "far", "clustered", "biggest"])


if __name__ == "__main__":
    main()
