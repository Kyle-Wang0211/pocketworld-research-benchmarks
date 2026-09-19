#!/usr/bin/env python3.11
"""把 region_results.json 渲染成 markdown 表(任意 tag 数,列名不写死)。

结构与 region_metric_20260824/make_tables.py 一致,但 make_tables.py 把
TAGS/列名硬编码成 blendmvg/C/new 三臂(vals[2]-vals[1] 当成 "new−C"),
换 tag 会出错标,所以这里只重写渲染,不碰任何指标计算。
"""
import argparse
import json

TOLS = ["0.01", "0.02", "0.05"]
REG = ["wall", "ceiling", "floor", "clutter"]
CN = {"wall": "墙", "ceiling": "天花板", "floor": "地板", "clutter": "杂物"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--new", required=True, help="本次被评的 tag,差值列以它为被减数")
    a = ap.parse_args()
    tags = [t for t in a.tags.split(",") if t]
    R = json.loads(open(a.results).read())
    M = R["metrics"]

    def g(metric, region, tag, tol, ls="main"):
        return M[f"{metric}|{ls}|{tag}|{tol}|{region}"]

    others = [t for t in tags if t != a.new]
    sc = R["self_check"]
    print(f"SELF-CHECK passed={sc['passed']} worst={sc['worst_abs_diff']:.3e}"
          f"({len(sc['comparisons'])} 次 ALL-vs-official 比对)\n")

    for metric, title in (("comp", "completeness"), ("acc", "accuracy")):
        print(f"## {title}(主口径)\n")
        print("| 区域 | 容差 | " + " | ".join(tags) + " | " +
              " | ".join(f"{a.new}−{o}" for o in others) + " |")
        print("|---|---|" + "---|" * (len(tags) + len(others)))
        for reg in REG:
            for tol in TOLS:
                vals = {t: g(metric, reg, t, tol) for t in tags}
                row = " | ".join(f"{vals[t]:.4f}" for t in tags)
                dd = " | ".join(f"{(vals[a.new]-vals[o])*100:+.2f}pp" for o in others)
                print(f"| {CN[reg]} | {float(tol)*100:.0f}cm | {row} | {dd} |")
        print()

    print("## ALL vs official(自证口径)\n")
    print("| 指标 | 容差 | " + " | ".join(tags) + " |")
    print("|---|---|" + "---|" * len(tags))
    for metric in ("comp", "acc"):
        for tol in TOLS:
            print(f"| {metric} | {float(tol)*100:.0f}cm | " +
                  " | ".join(f"{g(metric,'ALL',t,tol):.6f}" for t in tags) + " |")
    print()

    print("## 墙 vs 杂物 completeness 比值(主口径)\n")
    print("| 权重 | 容差 | 墙 | 杂物 | 杂物/墙 |")
    print("|---|---|---|---|---|")
    for t in tags:
        for tol in TOLS:
            w = g("comp", "wall", t, tol)
            c = g("comp", "clutter", t, tol)
            print(f"| {t} | {float(tol)*100:.0f}cm | {w:.4f} | {c:.4f} | {c/w:.2f}× |")
    print()

    print("## 敏感性变体 altwall(墙区 completeness)\n")
    print("| 容差 | " + " | ".join(tags) + " | " +
          " | ".join(f"{a.new}−{o}" for o in others) + " |")
    print("|---|" + "---|" * (len(tags) + len(others)))
    for tol in TOLS:
        vals = {t: g("comp", "wall", t, tol, "altwall") for t in tags}
        print(f"| {float(tol)*100:.0f}cm | " +
              " | ".join(f"{vals[t]:.4f}" for t in tags) + " | " +
              " | ".join(f"{(vals[a.new]-vals[o])*100:+.2f}pp" for o in others) + " |")


if __name__ == "__main__":
    main()
