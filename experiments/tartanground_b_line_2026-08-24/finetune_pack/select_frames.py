#!/usr/bin/env python3.11
"""按纹理分数从 TartanGround 轨迹中挑"白墙帧",并切成可转换的 scan 分块。

筛选口径(与 step0 完全同一把尺子:step0/lowtex.py,THR=100,短边 640,
Sobel ksize=3 -> g2 -> 5x5 box -> 低纹理像素占比 f100):
  * Office 系:  f100 > --f100_min
  * House  系:  先 mean_gray >= --gray_min 筛掉暗帧,再 f100 > --f100_min
    (依据:House 的高 f100 一半来自"太黑"而不是"平" —— 平均灰度仅 ~57,
     亮度归一后低纹理优势从 2.24x 掉到 1.28x。)

分块理由:转换器的共视分数矩阵是 O(n^2) 次全图几何一致性检验(本机实测
10.7 ms/对 @768x576),且轨迹上相隔很远的帧本来就没有共视。因此把筛后帧按
轨迹序切成 <= --chunk 帧的连续块,每块 = 一个 scan;块内帧号跨度超过
--max_gap 的地方强制断开。

输出:{out_dir}/{scan_name}.json  = 该 scan 的轨迹帧号整数列表
      {out_dir}/selection.json   = 全部 scan 的汇总统计
"""
import argparse
import json
import os

import numpy as np


def load_rows(path):
    d = json.load(open(path))
    return d


def frame_id_from_path(p):
    # .../000123_lcam_front.png -> 123
    base = os.path.basename(p)
    return int(base.split("_")[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex_json", required=True,
                    help="lowtex.py 的输出(必须是全帧统计,--n -1)")
    ap.add_argument("--scan_prefix", required=True)
    ap.add_argument("--f100_min", type=float, default=0.4)
    ap.add_argument("--gray_min", type=float, default=-1.0,
                    help=">=0 时启用亮度门(House 用 90);-1 = 不启用(Office)")
    ap.add_argument("--chunk", type=int, default=120)
    ap.add_argument("--chunk_min", type=int, default=20)
    ap.add_argument("--max_gap", type=int, default=15,
                    help="相邻入选帧的轨迹帧号差超过它就断开成新 scan")
    ap.add_argument("--out_dir", required=True)
    a = ap.parse_args()

    d = load_rows(a.tex_json)
    rows = d["rows"]
    ids = np.array([frame_id_from_path(r["path"]) for r in rows])
    f100 = np.array([r["f100"] for r in rows])
    gray = np.array([r["mean_gray"] for r in rows])
    order = np.argsort(ids)
    ids, f100, gray = ids[order], f100[order], gray[order]

    keep = f100 > a.f100_min
    n_after_f = int(keep.sum())
    n_after_gray = None
    if a.gray_min >= 0:
        gmask = gray >= a.gray_min
        n_after_gray = int(gmask.sum())
        keep = keep & gmask

    sel_ids = ids[keep].tolist()
    sel_f = f100[keep]
    sel_g = gray[keep]

    # 切块
    chunks, cur = [], []
    prev = None
    for fid in sel_ids:
        if prev is not None and (fid - prev > a.max_gap or len(cur) >= a.chunk):
            chunks.append(cur)
            cur = []
        cur.append(fid)
        prev = fid
    if cur:
        chunks.append(cur)
    chunks = [c for c in chunks if len(c) >= a.chunk_min]

    os.makedirs(a.out_dir, exist_ok=True)
    scans = []
    for k, c in enumerate(chunks):
        name = "%s_c%02d" % (a.scan_prefix, k)
        p = os.path.join(a.out_dir, name + ".json")
        with open(p, "w") as fh:
            json.dump(c, fh)
        scans.append({"scan": name, "n": len(c), "first": c[0], "last": c[-1],
                      "json": p})

    summary = {
        "tex_json": a.tex_json,
        "source_name": d.get("name"),
        "source_dir": d.get("dir"),
        "n_frames_total": len(ids),
        "criteria": {"f100_min": a.f100_min, "gray_min": a.gray_min},
        "n_pass_f100": n_after_f,
        "n_pass_gray": n_after_gray,
        "n_selected": len(sel_ids),
        "selected_f100_median": float(np.median(sel_f)) if len(sel_f) else None,
        "selected_gray_median": float(np.median(sel_g)) if len(sel_g) else None,
        "chunk": a.chunk, "chunk_min": a.chunk_min, "max_gap": a.max_gap,
        "n_scans": len(scans),
        "n_frames_in_scans": sum(s["n"] for s in scans),
        "scans": scans,
    }
    with open(os.path.join(a.out_dir, a.scan_prefix + "_selection.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    print("[%s] 全轨迹 %d 帧 -> f100>%.2f 留 %d%s -> 最终入选 %d 帧 -> %d 个 scan(共 %d 帧)"
          % (a.scan_prefix, len(ids), a.f100_min, n_after_f,
             ("" if n_after_gray is None else " / gray>=%.0f 留 %d" % (a.gray_min, n_after_gray)),
             len(sel_ids), len(scans), summary["n_frames_in_scans"]))
    for s in scans:
        print("   %s: %d 帧 (轨迹帧号 %d..%d)" % (s["scan"], s["n"], s["first"], s["last"]))


if __name__ == "__main__":
    main()
