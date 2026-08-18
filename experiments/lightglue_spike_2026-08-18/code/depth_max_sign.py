#!/usr/bin/env python3
"""depth_max 的差异是"16384 撑开了远景"还是纯噪声?——量有符号差。

mvs_channels.py 量的是绝对差(p95 = 15.84%),但绝对值分不清两种情形:
  · 16384 系统性地把远平面推得更远 ⇒ 它在保下游远景的命(8192 会漏掉那片)
  · 正负各半 ⇒ 只是 1%/99% 分位在稀疏尾部的抖动,与预算无关

判据:符号是否一头倒。
"""
import argparse

import numpy as np

from mvs_channels import centers, depth_range, load, umeyama


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="高预算臂(参照)")
    ap.add_argument("--b", required=True, help="低预算臂")
    args = ap.parse_args()

    ra, na = load(args.a)
    rb, nb = load(args.b)
    common = sorted(set(na) & set(nb))
    s, _R, _t = umeyama(centers(rb, common), centers(ra, common))

    sg, lo = [], []
    for nm in common:
        A, B = depth_range(ra, nm), depth_range(rb, nm)
        if A is None or B is None:
            continue
        sg.append((A[1] - B[1] * s) / abs(A[1]))       # >0 ⇒ A(高预算)的远平面更远
        lo.append((B[0] * s - A[0]) / abs(A[0]))       # >0 ⇒ A 的近平面更近

    sg, lo = np.array(sg), np.array(lo)
    print(f"gauge 尺度 {s:.4f}   有效视图 {len(sg)}/{len(common)}")
    print(f"\ndepth_max 有符号相对差 ({args.a} − {args.b}) / {args.a}")
    print(f"  中位 {np.median(sg)*100:+.2f}%   均值 {sg.mean()*100:+.2f}%   "
          f"p05 {np.percentile(sg,5)*100:+.2f}%   p95 {np.percentile(sg,95)*100:+.2f}%")
    print(f"  高预算远平面更远的视图 {(sg>0).sum()}/{len(sg)} ({(sg>0).mean()*100:.0f}%)")
    q = np.abs(sg) > 0.05
    if q.any():
        print(f"  |差异|>5% 的视图 {q.sum()} 个 —— 其中高预算更远 {(sg[q]>0).sum()}/{q.sum()}")
    print(f"\ndepth_min 有符号(>0 ⇒ 高预算近平面更近)"
          f"  中位 {np.median(lo)*100:+.2f}%   高预算更近 {(lo>0).sum()}/{len(lo)}")


if __name__ == "__main__":
    main()
