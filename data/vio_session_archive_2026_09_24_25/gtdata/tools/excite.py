#!/usr/bin/env python3
"""Does the scale error track initialisation-window excitation?  Spearman over XRSLAM runs in results.json."""
import json
import sys

import numpy as np
from scipy.stats import spearmanr

W = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata"
R = [r for r in json.load(open(W + "/results.json")) if r["lineage"] in ("S", "M", "O") and r["dataset"] in sys.argv[1:] or (len(sys.argv) == 1 and r["lineage"] in ("S", "M", "O"))]
rows = []
for r in R:
    ex = r.get("init_excitation_gt") or {}; ei = r.get("init_excitation_imu") or {}; po = r.get("post_init_excitation_gt") or {}
    fk = (r.get("first_k") or {}).get("10")
    rows.append(dict(id=f"{r['dataset']}/{r['seq']}/{r['lineage']}", L=r["lineage"], k=r["k"], err=abs(r["k"] - 1),
                     k10=fk["k"] if fk else np.nan, path=ex.get("speed_mps", np.nan), acc=ex.get("acc_rms", np.nan),
                     imu=ei.get("acc_axis_std", np.nan), gyro=ei.get("gyro_rms", np.nan), post_path=po.get("path_m", np.nan),
                     post_acc=po.get("acc_rms", np.nan)))
print("| run | k | |k-1| | k first 10 s | init ≤2 s mean speed m/s | init acc_rms m/s² | init IMU acc std | init gyro rms | post-init 5 s path m | post 5 s acc_rms |")
print("|---|---|---|---|---|---|---|---|---|---|")
for x in rows:
    print(f"| {x['id']} | {x['k']:.4f} | {100*x['err']:.1f}% | {x['k10']:.3f} | {x['path']:.3f} | {x['acc']:.2f} | {x['imu']:.2f} | {x['gyro']:.2f} | {x['post_path']:.2f} | {x['post_acc']:.2f} |")
for L in ("S", "O", "M", None):
    sub = [x for x in rows if L is None or x["L"] == L]
    if len(sub) < 4:
        continue
    print(f"\n[{L or 'S+M'}] n={len(sub)} Spearman rho (p) of |k-1| and |k10-1| vs excitation:")
    for key in ("path", "acc", "imu", "gyro", "post_path", "post_acc"):
        a = np.array([x["err"] for x in sub]); b = np.array([x[key] for x in sub]); c = np.array([abs(x["k10"] - 1) for x in sub])
        m = np.isfinite(b)
        r1 = spearmanr(a[m], b[m]); r2 = spearmanr(c[m & np.isfinite(c)], b[m & np.isfinite(c)])
        print(f"  {key:10s}  |k-1|: {r1.statistic:+.2f} (p={r1.pvalue:.2f})   |k10-1|: {r2.statistic:+.2f} (p={r2.pvalue:.2f})")
