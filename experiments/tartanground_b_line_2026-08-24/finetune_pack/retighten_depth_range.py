#!/usr/bin/env python3.11
"""重写 TG scan 的 cams/*_cam.txt 深度范围行(只改那一行,原文件备份为 .orig)。

## 为什么需要它(本机实测,不是猜)

转换器按官方常见做法取深度的 1/99 百分位当 [depth_min, depth_max]。
TartanGround 的 Office/House 是**室内但有窗**,窗外的天空/远景在 AirSim 深度里
是几百米甚至上万米,于是 99 百分位被污染。952 个 cam.txt 实测:

| | |
|---|---|
| depth_max 中位 | 14.04 m |
| depth_max p75 / p90 / p99 | 149.50 / 249.36 / 324.59 m |
| depth_max > 100 m 的帧 | **278/952 = 29.2%** |
| depth_max/depth_min 比值 p90 | 144.5 |

`blend.py` 用这个范围生成 384 个**视差**等距采样:
`depth_values = linspace(1/depth_max, 1/depth_min, 384)`。
depth_max 从 15 m 变成 250 m,384 个假设里绝大多数就压在"很远"那一端,
真正的室内 1–15 m 段被挤薄。这会伤训练,而且是静默的。

## 这个脚本做什么

从已有的 `rendered_depth_maps/*.pfm` 重算范围,可选三种更严的口径,
**只改 cam.txt 的最后一行**,图像/深度/pair.txt 一律不动。可随时 `--revert` 还原。

    # 看看会变成什么样,不写盘
    python3.11 retighten_depth_range.py --root tg_mvs --hi 95 --dry_run
    # 应用:99 -> 95 百分位
    python3.11 retighten_depth_range.py --root tg_mvs --hi 95
    # 或者:保持 99 百分位但给个绝对上限
    python3.11 retighten_depth_range.py --root tg_mvs --hi 99 --max_abs 30
    # 还原
    python3.11 retighten_depth_range.py --root tg_mvs --revert
"""
import argparse
import glob
import os
import sys

import numpy as np

import os as _os
DIFFMVS = _os.environ.get("DIFFMVS_REPO",
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, DIFFMVS)
from datasets.data_io import read_pfm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="tg_mvs 根目录")
    ap.add_argument("--lo", type=float, default=1.0, help="depth_min 的百分位")
    ap.add_argument("--hi", type=float, default=95.0, help="depth_max 的百分位")
    ap.add_argument("--max_abs", type=float, default=0.0,
                    help=">0 时再给 depth_max 一个绝对上限(米)")
    ap.add_argument("--depth_num", type=int, default=192,
                    help="cam.txt 深度行的 depth_num 字段(blend.py 只读首尾两个 token)")
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--revert", action="store_true", help="从 .orig 还原并退出")
    a = ap.parse_args()

    cams = sorted(glob.glob(os.path.join(a.root, "*", "cams", "*_cam.txt")))
    if not cams:
        sys.exit(f"[fatal] {a.root} 下没有 cams/*_cam.txt")

    if a.revert:
        n = 0
        for c in cams:
            o = c + ".orig"
            if os.path.exists(o):
                os.replace(o, c)
                n += 1
        print(f"[done] 还原 {n}/{len(cams)} 个 cam.txt")
        return

    old_max, new_max = [], []
    for c in cams:
        scan_dir = os.path.dirname(os.path.dirname(c))
        idx = os.path.basename(c).split("_")[0]
        pfm = os.path.join(scan_dir, "rendered_depth_maps", idx + ".pfm")
        d = np.array(read_pfm(pfm)[0], dtype=np.float32)
        v = d[np.isfinite(d) & (d > 0) & (d < 1000)]
        if v.size == 0:
            sys.exit(f"[fatal] {pfm} 无有效深度")
        dmin = float(np.percentile(v, a.lo))
        dmax = float(np.percentile(v, a.hi))
        if a.max_abs > 0:
            dmax = min(dmax, a.max_abs)
        if dmax <= dmin:
            dmax = dmin * 1.5
        interval = (dmax - dmin) / max(a.depth_num - 1, 1)

        with open(c) as f:
            lines = f.readlines()
        old_max.append(float(lines[11].split()[-1]))
        new_max.append(dmax)
        lines[11] = f"{dmin:.6f} {interval:.6f} {a.depth_num} {dmax:.6f} \n"
        if not a.dry_run:
            if not os.path.exists(c + ".orig"):
                os.replace(c, c + ".orig")
            with open(c, "w") as f:
                f.writelines(lines)

    o, n = np.array(old_max), np.array(new_max)
    print(f"[{'dry-run' if a.dry_run else 'done'}] {len(cams)} 个 cam.txt  "
          f"(lo=p{a.lo} hi=p{a.hi} max_abs={a.max_abs})")
    for q in (50, 75, 90, 99, 100):
        print("  depth_max p%-3d : %9.2f m -> %9.2f m" %
              (q, np.percentile(o, q), np.percentile(n, q)))
    print("  >100m 的帧: %d -> %d" % ((o > 100).sum(), (n > 100).sum()))


if __name__ == "__main__":
    main()
