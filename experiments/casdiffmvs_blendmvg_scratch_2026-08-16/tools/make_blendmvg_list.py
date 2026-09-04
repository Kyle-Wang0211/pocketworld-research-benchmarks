#!/usr/bin/env python3
"""为 BlendedMVG 生成训练/验证场景清单 —— cvg/diffmvs 仓库里没有。

仓库自带的 lists/blend/train.txt 只有 **106 个场景 = BlendedMVS**,
而 BlendedMVS 是 BlendedMVG 的一个子集(官方 README 2025-09-11 原话)。
要用 BlendedMVG 训练就必须自己建清单。

同时做数据体检 —— 这一步比建清单更重要:
    datasets/blend.py 在 __getitem__ 里才拼路径(:94-105),
    缺文件要等训练跑到那个样本才炸。几十 GB 的下载出现零星缺文件很常见,
    在 H100 上跑到第 3 小时才崩是最贵的失败方式。
    ⇒ 上机第一件事就是全量体检,不是抽查。

用法:
    python3 make_blendmvg_list.py <BLENDEDMVG_ROOT> <OUT_DIR> [--val-from <旧val.txt>]

产出:
    <OUT_DIR>/train.txt   通过体检且不在 val 里的场景
    <OUT_DIR>/val.txt     验证场景(默认沿用官方 7 个,保证与历史可比)
    <OUT_DIR>/report.txt  体检报告:每个被剔除的场景及原因
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# 官方 lists/blend/val.txt 的 7 个场景 —— 逐字节抄自仓库,别手打。
# ⚠️ 我第一版凭记忆写,最后一个 ID 写错了一位(59817bed… 实际是 59817e4a…)。
#    场景 ID 是 24 位十六进制,错一位不会报错,只会让那个场景静默落进 train,
#    验证集少一个 —— 典型静默 bug。所以下面优先从仓库原文件读,硬编码只是兜底。
# ⚠️ 脚本被拷到别处时 parents[3] 会 IndexError(2026-08-19 在租的机器上踩到)。
# 兜底成 None,靠 --val-from 或下面的硬编码。
try:
    _REPO_VAL = Path(__file__).resolve().parents[3] / "tools/python/diffmvs/lists/blend/val.txt"
except IndexError:
    _REPO_VAL = None
DEFAULT_VAL = [
    "5b7a3890fc8fcf6781e2593a", "5c189f2326173c3a09ed7ef3",
    "5b950c71608de421b1e7318f", "5a6400933d809f1d8200af15",
    "59d2657f82ca7774b1ec081d", "5ba19a8a360c7c30c1c169df",
    "59817e4a1bd4b175e7038d19",
]


def load_default_val() -> list[str]:
    if _REPO_VAL.is_file():
        v = [l.strip() for l in open(_REPO_VAL) if l.strip()]
        print(f"val 场景取自仓库原文件 {_REPO_VAL}({len(v)} 个)")
        return v
    print(f"⚠️ 找不到 {_REPO_VAL},退回内置副本(请核对)")
    return DEFAULT_VAL

REQUIRED_DIRS = ("blended_images", "cams", "rendered_depth_maps")


def check_scene(root: Path, scan: str, nviews: int) -> tuple[bool, str]:
    """返回 (是否可用, 原因)。原因为空表示通过。"""
    d = root / scan
    for sub in REQUIRED_DIRS:
        if not (d / sub).is_dir():
            return False, f"缺目录 {sub}"

    pair = d / "cams" / "pair.txt"
    if not pair.is_file():
        return False, "缺 cams/pair.txt"

    # 照 datasets/blend.py:36-44 的解析方式读 pair.txt
    try:
        with open(pair) as f:
            num_viewpoint = int(f.readline())
            usable = 0
            for _ in range(num_viewpoint):
                ref = int(f.readline().rstrip())
                src = [int(x) for x in f.readline().rstrip().split()[1::2]]
                # blend.py:41 —— 源视图不足会被 continue 掉,不是报错
                if len(src) < nviews - 1:
                    continue
                # 逐文件核对(ref + 前 nviews-1 个源视图)
                ids = [ref] + src[: nviews - 1]
                ok = True
                for vid in ids:
                    if not (d / "blended_images" / f"{vid:0>8}.jpg").is_file():
                        ok = False
                        break
                    if not (d / "cams" / f"{vid:0>8}_cam.txt").is_file():
                        ok = False
                        break
                # 深度图只有参考视图会被读(blend.py:118-124)
                if ok and not (d / "rendered_depth_maps" / f"{ref:0>8}.pfm").is_file():
                    ok = False
                if ok:
                    usable += 1
    except Exception as e:  # pair.txt 格式坏
        return False, f"pair.txt 解析失败 {type(e).__name__}"

    if usable == 0:
        return False, f"0 个可用参考视图(共 {num_viewpoint} 个,可能缺图/缺深度)"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="BlendedMVG 根目录")
    ap.add_argument("out", help="清单输出目录")
    ap.add_argument("--nviews", type=int, default=9,
                    help="与 --trainviews 一致,默认 9(官方 blend 段的值)")
    ap.add_argument("--val-from", default=None,
                    help="沿用某个已有 val.txt;默认用内置的官方 7 个场景")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    out = Path(args.out).expanduser()
    if not root.is_dir():
        print(f"❌ 根目录不存在: {root}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    val = ([l.strip() for l in open(args.val_from) if l.strip()]
           if args.val_from else load_default_val())

    scans = sorted(d.name for d in root.iterdir() if d.is_dir())
    print(f"扫到 {len(scans)} 个候选场景目录")

    good, bad = [], []
    for i, s in enumerate(scans, 1):
        ok, why = check_scene(root, s, args.nviews)
        (good if ok else bad).append(s if ok else (s, why))
        if i % 50 == 0:
            print(f"  体检 {i}/{len(scans)}", flush=True)

    val_present = [s for s in val if s in good]
    train = [s for s in good if s not in set(val)]

    (out / "train.txt").write_text("\n".join(train) + "\n")
    (out / "val.txt").write_text("\n".join(val_present) + "\n")

    with open(out / "report.txt", "w") as f:
        f.write(f"root={root}\nnviews={args.nviews}\n")
        f.write(f"候选 {len(scans)} / 通过 {len(good)} / 剔除 {len(bad)}\n")
        f.write(f"train {len(train)} / val {len(val_present)}\n\n")
        for s, why in bad:
            f.write(f"剔除 {s}: {why}\n")

    print(f"\n通过 {len(good)} / 剔除 {len(bad)}")
    print(f"→ {out}/train.txt  ({len(train)} 场景)")
    print(f"→ {out}/val.txt    ({len(val_present)} 场景)")
    if len(val_present) < len(val):
        missing = set(val) - set(val_present)
        print(f"⚠️ 官方 val 场景有 {len(missing)} 个不在本次数据里: {sorted(missing)}")
        print("   验证指标将与官方日志不完全可比,记账。")
    if bad:
        print(f"⚠️ {len(bad)} 个场景被剔除,原因见 {out}/report.txt")
    # 与官方 BlendedMVS 的 106 场景对照,确认拿到的确实是超集
    if len(train) <= 106:
        print(f"🔴 train 只有 {len(train)} 个场景 —— BlendedMVS 就有 106 个。")
        print("   你下到的很可能是 BlendedMVS 而不是 BlendedMVG,请核对下载来源。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
