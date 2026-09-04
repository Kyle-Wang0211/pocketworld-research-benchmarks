#!/usr/bin/env python3
"""鬼层质量 —— 抓"多出来的一整片致密面",而不是"离基准远的点"。

🔴 立项(2026-08-23):前面所有尺子都失效了。
   点数/覆盖/局部粗糙度 —— 对整片位移结构性失明(鬼墙点不少、占体素、局部平滑)
   云对云 arm→ref —— **惩罚合法的额外覆盖**(新权重比基准多 19% 点,多出的记成大距离)
   云对云 ref→arm —— 只罚缺失,抓不到"多出来的东西"
   实测:两个方向都把 C 排在新权重之前,而用户肉眼说新权重几乎追平基准。

关键区分(用户原话"多出了第二面墙跟旅行箱粘连"):
   **鬼墙 = 离基准远 且 彼此致密聚集成面**
   合法额外覆盖 = 离基准远 但 稀疏散布
⇒ 判据 = 在"远点"里再筛一次密度,只统计成团的那部分。
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
    ap.add_argument("--dir", required=True); ap.add_argument("--arms", required=True)
    ap.add_argument("--ref", required=True); ap.add_argument("--sub", type=int, default=8)
    ap.add_argument("--far", type=float, default=0.05, help="离基准多远算'远点'(米)")
    ap.add_argument("--nbr", type=float, default=0.02, help="判定致密的邻域半径(米)")
    ap.add_argument("--kmin", type=int, default=20, help="邻域内至少几个远点才算成团")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    arms = [x.split("=", 1) for x in a.arms.split(",")]
    R = load(f"{a.dir}/{dict(arms)[a.ref]}", a.sub); tree = cKDTree(R)
    print(f"  基准 {a.ref}: {len(R):,} 点  ·  远点门 {a.far*100:.0f}cm  ·  "
          f"致密判定 {a.nbr*100:.0f}cm 内 ≥{a.kmin} 个远点\n")
    print(f"{'臂':<11}{'点数':>10}{'远点':>9}{'其中成团':>10}{'鬼层质量':>11}{'最大团':>10}")
    res = {}
    for lab, fn in arms:
        Q = load(f"{a.dir}/{fn}", a.sub)
        d, _ = tree.query(Q, k=1, workers=-1)
        far = Q[d > a.far]
        if len(far) < 50:
            print(f"  {lab:<9}{len(Q):>10,}{len(far):>9,}{'—':>10}{'0.000%':>11}{'—':>10}")
            res[lab] = dict(n=len(Q), far=len(far), clustered=0, mass=0.0, biggest=0); continue
        ft = cKDTree(far)
        cnt = np.array([len(x) for x in ft.query_ball_point(far, a.nbr, workers=-1)])
        clu = cnt >= a.kmin
        # 最大连通团(用致密点再做一次半径连通近似:统计致密点的最大邻域计数)
        biggest = int(cnt[clu].max()) if clu.any() else 0
        mass = 100.0 * clu.sum() / len(Q)
        res[lab] = dict(n=len(Q), far=int(len(far)), clustered=int(clu.sum()),
                        mass=float(mass), biggest=biggest)
        print(f"  {lab:<9}{len(Q):>10,}{len(far):>9,}{clu.sum():>10,}{mass:>10.3f}%{biggest:>10,}")
        del Q, d, far, ft, cnt
    if a.out: json.dump(res, open(a.out, "w"), indent=1)
    print("\n  鬼层质量 = 成团远点 / 本臂总点数。越小越好。")


if __name__ == "__main__":
    main()
