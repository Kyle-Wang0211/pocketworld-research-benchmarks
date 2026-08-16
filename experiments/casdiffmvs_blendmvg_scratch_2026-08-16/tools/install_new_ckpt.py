#!/usr/bin/env python3
"""把训出来的权重装进现有评测链,并做**加载完整性核对**。

为什么需要这个脚本而不是直接 cp:
    pw_diffmvs_common.py:79 用的是 `load_state_dict(state["model"], strict=False)`。
    **strict=False 意味着 key 对不上不会报错** —— 缺的层保持随机初始化,
    多的层被静默丢弃。你会得到一个能跑、不报错、但精度莫名其妙的模型,
    然后把它当成"重训效果不好"记进账本。

    这正是 [[feedback-silent-bugs-need-ground-truth-probe]] 里那类 bug:
    不崩溃、不报错、只是数字不对。所以装之前必须逐 key 比对。

用法:
    python3 install_new_ckpt.py <新ckpt路径> [--dom mvgscratch] [--apply]

不带 --apply 只做核对与打印,不动任何文件。
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[3]
CKPT_DIR = REPO / "tools/python/diffmvs/checkpoints"
COMMON_PY = REPO / "tools/python/pw_diffmvs_common.py"


def load_model_state(p: Path) -> dict:
    st = torch.load(p, map_location="cpu")
    # train.py:135-139 存的是 {'epoch','model','optimizer'}
    return st["model"] if isinstance(st, dict) and "model" in st else st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt", help="训练产出的 .ckpt")
    ap.add_argument("--dom", default="mvgscratch",
                    help="AETHER_CKPT 的取值,默认 mvgscratch")
    ap.add_argument("--ref", default=None,
                    help="参照权重,默认用 casdiffmvs_blend.ckpt")
    ap.add_argument("--apply", action="store_true", help="真正落盘")
    args = ap.parse_args()

    new_p = Path(args.ckpt).expanduser()
    ref_p = Path(args.ref).expanduser() if args.ref else CKPT_DIR / "casdiffmvs_blend.ckpt"
    if not new_p.is_file():
        print(f"❌ 找不到 {new_p}", file=sys.stderr); return 1
    if not ref_p.is_file():
        print(f"❌ 找不到参照权重 {ref_p}", file=sys.stderr); return 1

    new_sd, ref_sd = load_model_state(new_p), load_model_state(ref_p)
    nk, rk = set(new_sd), set(ref_sd)

    print(f"新权重   {new_p.name}: {len(nk)} 个 key")
    print(f"参照     {ref_p.name}: {len(rk)} 个 key")

    missing = sorted(rk - nk)     # 参照有、新的没有 ⇒ 加载后会保持随机初始化
    extra = sorted(nk - rk)       # 新的有、参照没有 ⇒ 会被静默丢弃
    shape_bad = [k for k in (nk & rk) if new_sd[k].shape != ref_sd[k].shape]

    ok = True
    if missing:
        ok = False
        print(f"\n🔴 缺 {len(missing)} 个 key —— 这些层加载后是**随机初始化**:")
        for k in missing[:15]:
            print(f"    {k}  {tuple(ref_sd[k].shape)}")
        if len(missing) > 15:
            print(f"    …还有 {len(missing)-15} 个")
    if extra:
        print(f"\n⚠️ 多出 {len(extra)} 个 key(会被静默丢弃):")
        for k in extra[:10]:
            print(f"    {k}")
    if shape_bad:
        ok = False
        print(f"\n🔴 {len(shape_bad)} 个 key 形状不符:")
        for k in shape_bad[:10]:
            print(f"    {k}: 新 {tuple(new_sd[k].shape)} vs 参照 {tuple(ref_sd[k].shape)}")

    # 训练是否真的动过权重(全零/未训的兜底检查)
    tot = sum(v.numel() for v in new_sd.values() if v.is_floating_point())
    nz = sum(int((v != 0).sum()) for v in new_sd.values() if v.is_floating_point())
    print(f"\n参数量 {tot/1e6:.3f}M,非零 {100*nz/max(tot,1):.1f}%")
    if tot == 0 or nz / max(tot, 1) < 0.5:
        ok = False
        print("🔴 非零比例异常低 —— 这个 ckpt 可能没真正训过")

    if not ok:
        print("\n❌ 核对未通过,拒绝安装。strict=False 会让这些问题静默通过,别绕过。")
        return 2

    print("\n✅ key 集合与形状完全一致")
    dst = CKPT_DIR / f"casdiffmvs_{args.dom}.ckpt"
    print(f"\n将安装到: {dst}")
    print(f"并需在 {COMMON_PY.name}:71 的 assert 里加入 {args.dom!r}")

    if not args.apply:
        print("\n(未加 --apply,以上均未执行)")
        return 0

    shutil.copy2(new_p, dst)
    src = COMMON_PY.read_text()
    needle = '("dtu", "blend", "blendmvg")'
    if args.dom in src:
        print("assert 已含该值,跳过")
    elif needle in src:
        COMMON_PY.write_text(src.replace(
            needle, f'("dtu", "blend", "blendmvg", "{args.dom}")'))
        print(f"✅ 已在 assert 中加入 {args.dom!r}")
    else:
        print(f"⚠️ 没在 {COMMON_PY} 找到预期的 assert 元组,请手工加入 {args.dom!r}")

    print(f"\n下一步(与历史数字同一把尺子):")
    print(f"    AETHER_CKPT={args.dom} <现有 138 帧对比流程>")
    print("  ⚠️ 必须用**同一个 138 帧内部自洽子集**跑,否则不可比。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
