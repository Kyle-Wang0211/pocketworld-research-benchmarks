#!/usr/bin/env python3.11
"""把 TG 白墙子集按指定比例混进 BlendedMVG 训练清单 —— 零代码改动的做法。

原理(读过 datasets/blend.py::build_list 之后确定的):
  * MVSDataset 只吃 (datapath, listfile);listfile 每行一个 scan 名,
    scan 目录挂在 datapath 下。
  * build_list() 逐行处理清单,**同一个 scan 名写两遍就会产生两份 metas**。
  ⇒ 于是:
      ① 建一个"混合根目录",里面全是软链:MVG 的每个 scan + TG 的每个 scan;
      ② 训练清单 = MVG 全部 scan 各一行 + TG 的 scan 各重复 R 行;
      R 由目标比例反解。train.py / blend.py / 网络代码一行不改。

  * 每个 scan 的样本数 = pair.txt 里 src 数 >= (trainviews-1) 的 ref 数
    —— 与 build_list() 的判据逐字一致(它把 src 不够的 ref 直接 continue)。

用法:
  python3.11 make_mixed_list.py \
      --mvg_root /data/BlendedMVG --mvg_list /data/lists/train.txt \
      --mvg_val  /data/lists/val.txt \
      --tg_root  /data/tg_mvs     --tg_list  /data/tg_mvs/lists_all_scans.txt \
      --ratio 0.2 --trainviews 9 \
      --out_root /data/mixed --out_lists /data/mixed_lists
"""
import argparse
import json
import os
import sys


def count_metas(root, scan, nviews):
    """复刻 blend.py::build_list 的计数口径。返回 (可用 ref 数, 总 ref 数)。"""
    p = os.path.join(root, scan, "cams", "pair.txt")
    if not os.path.isfile(p):
        return None, None
    with open(p) as f:
        try:
            n = int(f.readline())
        except ValueError:
            return None, None
        ok = 0
        for _ in range(n):
            f.readline()                      # ref id
            line = f.readline().rstrip().split()
            if not line:
                return ok, n
            srcs = line[1::2]
            if len(srcs) >= nviews - 1:
                ok += 1
    return ok, n


def read_list(p):
    return [l.strip() for l in open(p) if l.strip()]


def link(src, dst):
    if os.path.islink(dst) or os.path.exists(dst):
        return
    os.symlink(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mvg_root", required=True)
    ap.add_argument("--mvg_list", required=True)
    ap.add_argument("--mvg_val", required=True)
    ap.add_argument("--tg_root", required=True)
    ap.add_argument("--tg_list", required=True)
    ap.add_argument("--ratio", type=float, default=0.2,
                    help="TG 样本占混合训练集的比例(0.2 = 20%%)")
    ap.add_argument("--trainviews", type=int, default=9)
    ap.add_argument("--out_root", required=True, help="混合根目录(全是软链)")
    ap.add_argument("--out_lists", required=True)
    ap.add_argument("--max_repeat", type=int, default=200)
    a = ap.parse_args()

    assert 0.0 < a.ratio < 1.0, a.ratio

    mvg = read_list(a.mvg_list)
    tg = read_list(a.tg_list)
    print(f"[info] MVG {len(mvg)} scan / TG {len(tg)} scan;trainviews={a.trainviews}")

    mvg_metas, tg_metas = 0, 0
    bad = []
    per_scan = {}
    for scan in mvg:
        ok, tot = count_metas(a.mvg_root, scan, a.trainviews)
        if ok is None:
            bad.append(("mvg", scan)); continue
        mvg_metas += ok
        per_scan[scan] = ok
    for scan in tg:
        ok, tot = count_metas(a.tg_root, scan, a.trainviews)
        if ok is None:
            bad.append(("tg", scan)); continue
        tg_metas += ok
        per_scan[scan] = ok
    if bad:
        print(f"[fatal] {len(bad)} 个 scan 缺 cams/pair.txt: {bad[:10]}", file=sys.stderr)
        sys.exit(1)
    if tg_metas == 0:
        print("[fatal] TG 侧可用样本为 0 —— pair.txt 的 src 数不足 trainviews-1?",
              file=sys.stderr)
        sys.exit(1)

    print(f"[info] 可用样本数: MVG={mvg_metas}  TG(单份)={tg_metas}")

    # ratio = R*tg / (mvg + R*tg)  =>  R = ratio*mvg / ((1-ratio)*tg)
    R_exact = a.ratio * mvg_metas / ((1.0 - a.ratio) * tg_metas)
    if R_exact < 1.0:
        # TG 单份就已经超过目标比例 ⇒ 不能靠重复,只能按 scan 抽子集。
        # 按 scan 名排序后贪心累加,取满目标样本数为止(确定性,可复现)。
        want = a.ratio * mvg_metas / (1.0 - a.ratio)
        acc, keep = 0, []
        for scan in sorted(tg):
            if acc >= want:
                break
            keep.append(scan)
            acc += per_scan[scan]
        print(f"[info] TG 单份({tg_metas})已超目标({want:.0f}),改为抽 "
              f"{len(keep)}/{len(tg)} 个 scan,共 {acc} 样本")
        tg = keep
        tg_metas = acc
        R = 1
    else:
        R = min(a.max_repeat, int(round(R_exact)))
    achieved = R * tg_metas / float(mvg_metas + R * tg_metas)
    print(f"[info] 目标比例 {a.ratio:.3f} -> TG 重复次数 R={R} "
          f"(精确值 {R_exact:.2f}),实际达成 {achieved:.4f}")

    os.makedirs(a.out_root, exist_ok=True)
    os.makedirs(a.out_lists, exist_ok=True)
    for scan in mvg:
        link(os.path.abspath(os.path.join(a.mvg_root, scan)),
             os.path.join(a.out_root, scan))
    for scan in tg:
        link(os.path.abspath(os.path.join(a.tg_root, scan)),
             os.path.join(a.out_root, scan))

    tag = "tg%02d" % round(a.ratio * 100)
    train_p = os.path.join(a.out_lists, "train_%s.txt" % tag)
    with open(train_p, "w") as f:
        for scan in mvg:
            f.write(scan + "\n")
        for _ in range(R):
            for scan in tg:
                f.write(scan + "\n")
    # 验证集保持纯 MVG,否则与历史数字不可比
    val_p = os.path.join(a.out_lists, "val.txt")
    with open(val_p, "w") as f:
        for scan in read_list(a.mvg_val):
            f.write(scan + "\n")
            link(os.path.abspath(os.path.join(a.mvg_root, scan)),
                 os.path.join(a.out_root, scan))

    meta = {"ratio_requested": a.ratio, "ratio_achieved": achieved,
            "tg_repeat": R, "mvg_metas": mvg_metas, "tg_metas_single": tg_metas,
            "total_metas": mvg_metas + R * tg_metas,
            "trainviews": a.trainviews,
            "n_mvg_scans": len(mvg), "n_tg_scans": len(tg),
            "train_list": train_p, "val_list": val_p, "root": a.out_root}
    with open(os.path.join(a.out_lists, "mix_%s.json" % tag), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[done] {train_p}  ({mvg_metas + R*tg_metas} 样本/轮)")
    print(f"[done] {val_p}    (纯 MVG,保持与历史可比)")


if __name__ == "__main__":
    main()
