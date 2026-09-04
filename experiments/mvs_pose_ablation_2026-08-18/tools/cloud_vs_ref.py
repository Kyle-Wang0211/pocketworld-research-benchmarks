#!/usr/bin/env python3
"""云对云偏离 —— 不做任何"哪面是墙"的假设。

🔴 立项:我连试三把平面尺子都没复现用户的肉眼排名(2026-08-19)。
   前两把(点数/覆盖/局部粗糙度)对全局形状失明;
   后两把(大平面残差)败在**无法自动定位到用户看的那面墙** ——
   最大平面是地板(7.3×4.7m),次大平面族根本不是干净平面(75% 点偏离>2cm)。
⇒ 放弃"先找面再量" ,改成**直接量两朵云的差**:
   把用户判为正确的那条臂当基准,量其余臂每个点到它的最近距离。
   翘起 = 一整片点飘离基准面 ⇒ 必然表现为一簇大距离。
   这不需要知道那面墙在哪。
"""
import argparse, json
import numpy as np
from scipy.spatial import cKDTree

DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])


def load(p, sub=1):
    f = open(p, "rb"); n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"): n = int(l.split()[-1])
        if l.strip() == b"end_header": break
    rec = np.fromfile(f, dtype=DT, count=n)
    if sub > 1: rec = rec[::sub]
    return np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--arms", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--sub", type=int, default=8)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    arms = [x.split("=", 1) for x in a.arms.split(",")]

    R = load(f"{a.dir}/{dict(arms)[a.ref]}", a.sub)
    tree = cKDTree(R)
    print(f"  基准 {a.ref}: {len(R):,} 点(1/{a.sub} 抽样,四臂同率)\n")
    print(f"{'臂':<12}{'点数':>11}{'到基准 中位':>13}{'p90':>9}{'p99':>10}{'>2cm占比':>10}{'>5cm占比':>10}")
    res = {}
    for lab, fn in arms:
        P = load(f"{a.dir}/{fn}", a.sub)
        d, _ = tree.query(P, k=1, workers=-1)
        res[lab] = dict(n=len(P), p50=float(np.median(d)*1000),
                        p90=float(np.percentile(d, 90)*1000),
                        p99=float(np.percentile(d, 99)*1000),
                        gt2=float((d > 0.02).mean()*100),
                        gt5=float((d > 0.05).mean()*100))
        v = res[lab]
        print(f"  {lab:<10}{v['n']:>11,}{v['p50']:>12.2f}mm{v['p90']:>8.1f}mm"
              f"{v['p99']:>9.1f}mm{v['gt2']:>9.2f}%{v['gt5']:>9.2f}%")
        del P, d
    if a.out: json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
