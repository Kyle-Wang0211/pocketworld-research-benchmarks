#!/usr/bin/env python3
"""汇总:五臂 x 三尺子,原生密度 vs 密度归一,各写一份 CSV。"""
import json, csv

OUT = "~/Documents/progecttwo/_host_experiments/pose_ablation_20260818/ruler_audit_20260824"
ARMS = ["blendmvg", "blend", "dtu", "C", "新权重"]


def dump(name, native_path, dnorm_path, fields, csv_name):
    nat = json.load(open(native_path))
    dn = json.load(open(dnorm_path))
    rows = []
    for a in ARMS:
        row = {"arm": a}
        for f in fields:
            row[f"native_{f}"] = nat.get(a, {}).get(f)
            row[f"dnorm_{f}"] = dn.get(a, {}).get(f)
        rows.append(row)
    path = f"{OUT}/{csv_name}"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm"] + [f"native_{f}" for f in fields] + [f"dnorm_{f}" for f in fields])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


dump("cloud_vs_ref", f"{OUT}/cloud_vs_ref_full5.json", f"{OUT}/dnorm_cloud_vs_ref.json",
     ["n", "p50", "p90", "p99", "gt2", "gt5"], "matrix_cloud_vs_ref.csv")

dump("wall_flatness", f"{OUT}/wall_flatness_full5.json", f"{OUT}/dnorm_wall_flatness.json",
     ["n", "rms", "p95", "gt2cm", "slope", "span"], "matrix_wall_flatness.csv")

dump("ghost_mass",
     "~/Documents/progecttwo/_host_experiments/pose_ablation_20260818/ghost_mass.json",
     f"{OUT}/dnorm_ghost_mass.json",
     ["n", "far", "clustered", "mass", "biggest"], "matrix_ghost_mass.csv")
