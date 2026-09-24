#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务 1 的自证: 位姿插值的留出法 (leave-one-out) + 阴性对照。

判据要能对我要排除的失效模式报警, 所以一次跑四条腿:
  interp(c2w)  正解: 在 camera->world 里 slerp+lerp                 <- 要赢
  interp(w2c)  阴性对照 A: 在 world->camera 里插 (对 t_w_to_p 线性插值, D3 说这是错的)
  nearest      阴性对照 B: 不插值, 直接取最近的保留样本
               (= 把容差从 5 ms 放宽到半个间隔的朴素做法)
  const        阴性对照 C: 永远返回第一个保留样本 (完全无信息的下界)

留出法: 把 10 Hz 的 traj 按 k 抽稀 (保留 index%k==0), 在【被丢掉的】时间戳上插值,
和真值比。k=2 的评估点正好落在 0.2 s 洞的中点 —— 这是 0.2 s 洞的最坏情形。
我们真正的工况是 0.1 s 的洞, 没有真值可留出, 所以用 k=2,3,4,6,10 量出
误差随洞宽的标度, 再外推回 0.1 s (报告里如实标为【推断】)。
"""
import argparse, glob, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ak_pose_interp import read_traj, TrajInterp, pose_err


def mat(R, C):
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = C
    return T


def run_one(path, ks=(2, 3, 4, 6, 10)):
    ts, R, C = read_traj(path)
    gaps = np.diff(ts)
    out = {"file": path, "n": len(ts), "span": float(ts[-1] - ts[0]),
           "gap_med": float(np.median(gaps)), "gap_p99": float(np.percentile(gaps, 99)),
           "gap_max": float(gaps.max()),
           "gap_gt_0.2": int((gaps > 0.20).sum()), "gap_gt_0.5": int((gaps > 0.50).sum()),
           "rows": []}
    for k in ks:
        keep = np.arange(0, len(ts), k)
        if len(keep) < 4:
            continue
        drop = np.array([i for i in range(keep[0], keep[-1]) if i % k != 0])
        if len(drop) == 0:
            continue
        kts, kR, kC = ts[keep], R[keep], C[keep]
        legs = {
            "interp_c2w": TrajInterp(kts, kR, kC, max_gap=10.0, space="c2w"),
            "interp_w2c": TrajInterp(kts, kR, kC, max_gap=10.0, space="w2c"),
        }
        res = {n: {"dt": [], "dr": []} for n in list(legs) + ["nearest", "const"]}
        for i in drop:
            gt = mat(R[i], C[i])
            t = ts[i]
            for n, f in legs.items():
                T = f(t)
                if T is None:
                    continue
                a, b = pose_err(gt, T)
                res[n]["dt"].append(a); res[n]["dr"].append(b)
            j = int(np.abs(kts - t).argmin())
            a, b = pose_err(gt, mat(kR[j], kC[j]))
            res["nearest"]["dt"].append(a); res["nearest"]["dr"].append(b)
            a, b = pose_err(gt, mat(kR[0], kC[0]))
            res["const"]["dt"].append(a); res["const"]["dr"].append(b)
        row = {"k": k, "eval_gap": float(np.median(np.diff(kts))), "n_eval": len(drop)}
        for n in res:
            d = np.asarray(res[n]["dt"]); r = np.asarray(res[n]["dr"])
            if d.size == 0:
                continue
            row[n] = dict(t_med=float(np.median(d)), t_p95=float(np.percentile(d, 95)),
                          t_max=float(d.max()),
                          r_med=float(np.median(r)), r_p95=float(np.percentile(r, 95)),
                          r_max=float(r.max()))
        out["rows"].append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", nargs="+", required=True)
    a = ap.parse_args()
    files = []
    for p in a.traj:
        files.extend(sorted(glob.glob(p)))
    allrows = {}
    for f in files:
        o = run_one(f)
        vid = os.path.basename(os.path.dirname(f))
        print("\n== %s  n=%d span=%.1fs  gap: med %.5f p99 %.5f max %.3f | >0.2s %d | >0.5s %d"
              % (vid, o["n"], o["span"], o["gap_med"], o["gap_p99"], o["gap_max"],
                 o["gap_gt_0.2"], o["gap_gt_0.5"]))
        print("   %-4s %-7s %-6s | %-28s | %-28s | %-28s | %-12s"
              % ("k", "gap", "n", "interp_c2w  t_med/p95/max(mm)",
                 "interp_w2c  t_med/p95/max(mm)", "nearest     t_med/p95/max(mm)", "const t_med"))
        for r in o["rows"]:
            def f3(n):
                if n not in r: return "        --        "
                return "%7.2f /%7.2f /%7.2f" % (r[n]["t_med"] * 1e3, r[n]["t_p95"] * 1e3, r[n]["t_max"] * 1e3)
            print("   %-4d %-7.3f %-6d | %s | %s | %s | %8.1f"
                  % (r["k"], r["eval_gap"], r["n_eval"], f3("interp_c2w"), f3("interp_w2c"),
                     f3("nearest"), r["const"]["t_med"] * 1e3))
            print("   %-4s %-7s %-6s | %7.4f /%7.4f /%7.4f deg | %7.4f /%7.4f /%7.4f deg | %7.4f /%7.4f /%7.4f deg |"
                  % ("", "", "",
                     r["interp_c2w"]["r_med"], r["interp_c2w"]["r_p95"], r["interp_c2w"]["r_max"],
                     r["interp_w2c"]["r_med"], r["interp_w2c"]["r_p95"], r["interp_w2c"]["r_max"],
                     r["nearest"]["r_med"], r["nearest"]["r_p95"], r["nearest"]["r_max"]))
            allrows.setdefault(r["k"], []).append(r)
    print("\n== 汇总 (跨 %d 个视频的中位数) ==" % len(files))
    print("   k  gap(s)   interp_c2w t_med(mm) r_med(deg) | interp_w2c t_med(mm) | nearest t_med(mm) r_med(deg)")
    xs, ys = [], []
    for k in sorted(allrows):
        rs = allrows[k]
        g = float(np.median([r["eval_gap"] for r in rs]))
        a1 = float(np.median([r["interp_c2w"]["t_med"] for r in rs])) * 1e3
        r1 = float(np.median([r["interp_c2w"]["r_med"] for r in rs]))
        a2 = float(np.median([r["interp_w2c"]["t_med"] for r in rs])) * 1e3
        a3 = float(np.median([r["nearest"]["t_med"] for r in rs])) * 1e3
        r3 = float(np.median([r["nearest"]["r_med"] for r in rs]))
        print("   %-2d %-8.3f %12.3f %10.4f | %20.3f | %15.3f %10.4f" % (k, g, a1, r1, a2, a3, r3))
        xs.append(g); ys.append(a1)
    if len(xs) >= 2:
        p = np.polyfit(np.log(xs), np.log(ys), 1)
        print("   平移误差 ~ gap^%.2f  =>  外推到 gap=0.100 s 的中位平移误差 ≈ %.3f mm 【推断, 非实测】"
              % (p[0], np.exp(np.polyval(p, np.log(0.10)))))


if __name__ == "__main__":
    main()
