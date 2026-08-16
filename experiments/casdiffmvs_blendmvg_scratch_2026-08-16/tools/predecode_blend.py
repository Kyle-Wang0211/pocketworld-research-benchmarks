#!/usr/bin/env python3
"""把 BlendedMVS/MVG 的 JPEG 一次性预解码成单个 mmap 文件,消灭训练期的 CPU 瓶颈。

## 为什么需要

datasets/blend.py:107 每取一个样本要解码 **9 张 JPEG**(trainviews=9),
batch=4 就是每批 36 次解码 —— 纯 CPU 活。租来的机器 vCPU 往往只有 24-40,
并发多个训练时 CPU 先饱和,**H100 空转**。

⚠️ 注意:CPU 与 GPU 本来就是重叠的(DataLoader 多进程预取 + pin_memory 异步拷贝),
   问题不是"没重叠",是**产能不匹配**。加重叠没用,得把 CPU 的活拿走。

## 为什么是 mmap 而不是内存字典

🔴 `num_workers > 0` 时每个 worker 是**独立进程**,Python 字典缓存会被
**逐个 worker 复制一份**。20GB 缓存 × 16 worker = 320GB,当场打爆。

mmap 单文件则所有 worker 共享同一份 OS page cache —— 零复制。
机器内存大时它整份驻留在页缓存里,等价于内存缓存但没有复制问题。
(同 [[feedback-host-memory-budget-18gb-mac]] 里那条 mmap 教训。)

## 数值保真

存 uint8(比 float32 省 4×),取用时 `astype(np.float32)/255.`,
与原版 `np.array(PIL_img, np.float32)/255.` **逐位相同** —— 因为解码器同为 PIL。
⇒ 训练结果不受影响,这不是近似。

用法:
    python3 predecode_blend.py <DATA_ROOT> <LIST.txt> <OUT_DIR> [--nviews 9] [--depth]

产出:
    <OUT_DIR>/images.u8     所有被引用图像的 uint8 像素,首尾相接
    <OUT_DIR>/images.json   相对路径 → (offset, h, w, c)
    <OUT_DIR>/depths.f32    (--depth 时)参考视图深度图
    <OUT_DIR>/depths.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def collect_referenced(root: Path, scans: list[str], nviews: int):
    """照 datasets/blend.py:26-46 的逻辑,收集会被真正读到的图像与深度。

    ⚠️ 必须与 build_list 完全一致(含 `len(src_views) < nviews-1 → continue`),
       否则会预解码一堆用不到的图,或者漏掉要用的。
    """
    imgs: set[str] = set()
    deps: set[str] = set()
    for scan in scans:
        pair = root / scan / "cams" / "pair.txt"
        if not pair.is_file():
            continue
        with open(pair) as f:
            n = int(f.readline())
            for _ in range(n):
                ref = int(f.readline().rstrip())
                src = [int(x) for x in f.readline().rstrip().split()[1::2]]
                if len(src) < nviews - 1:
                    continue
                # 训练模式是 random.sample(src_views, nviews-1)(blend.py:81)
                # ⇒ **所有**源视图都可能被抽到,不能只存前 nviews-1 个
                for vid in [ref] + src:
                    imgs.add(f"{scan}/blended_images/{vid:0>8}.jpg")
                deps.add(f"{scan}/rendered_depth_maps/{ref:0>8}.pfm")
    return sorted(imgs), sorted(deps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("listfile")
    ap.add_argument("out")
    ap.add_argument("--nviews", type=int, default=9)
    ap.add_argument("--depth", action="store_true",
                    help="同时预读参考视图深度(省掉 PFM 解析,占盘较大)")
    ap.add_argument("--repo", default=None,
                    help="diffmvs 仓库路径(--depth 时需要,用它的 read_pfm)")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    scans = [l.strip() for l in open(args.listfile) if l.strip()]
    print(f"场景 {len(scans)} 个,nviews={args.nviews}")

    imgs, deps = collect_referenced(root, scans, args.nviews)
    print(f"被引用图像 {len(imgs)} 张;参考深度 {len(deps)} 张")
    if not imgs:
        print("🔴 一张都没收集到 —— 检查 root 与 list 是否匹配", file=sys.stderr)
        return 1

    # ── 图像 ──
    idx: dict[str, list[int]] = {}
    off = 0
    with open(out / "images.u8", "wb") as fo:
        for i, rel in enumerate(imgs):
            p = root / rel
            try:
                a = np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)
            except Exception as e:
                print(f"🔴 解码失败 {rel}: {type(e).__name__} —— 数据不完整,先修数据",
                      file=sys.stderr)
                return 2
            fo.write(a.tobytes())
            idx[rel] = [off, int(a.shape[0]), int(a.shape[1]), int(a.shape[2])]
            off += a.nbytes
            if (i + 1) % 2000 == 0:
                print(f"  图像 {i+1}/{len(imgs)}  已写 {off/2**30:.1f} GiB", flush=True)
    json.dump(idx, open(out / "images.json", "w"))
    print(f"→ images.u8  {off/2**30:.2f} GiB / {len(imgs)} 张")

    # ── 深度(可选)──
    if args.depth:
        # ⚠️ read_pfm 在 **diffmvs 仓库**里(datasets/data_io.py),不在数据目录。
        #    我第一版把 args.root(数据根)加进 sys.path,当然导不到 —— 实测抓到的。
        if args.repo:
            sys.path.insert(0, str(Path(args.repo).expanduser()))
        try:
            from datasets.data_io import read_pfm  # noqa
        except Exception as e:
            print(f"🔴 导入 read_pfm 失败({type(e).__name__})。"
                  f"请用 --repo <diffmvs 仓库路径>,或在仓库目录下运行。",
                  file=sys.stderr)
            return 3
        didx: dict[str, list[int]] = {}
        doff = 0
        with open(out / "depths.f32", "wb") as fo:
            for i, rel in enumerate(deps):
                d = np.array(read_pfm(str(root / rel))[0], dtype=np.float32)
                fo.write(d.tobytes())
                didx[rel] = [doff, int(d.shape[0]), int(d.shape[1])]
                doff += d.nbytes
                if (i + 1) % 1000 == 0:
                    print(f"  深度 {i+1}/{len(deps)}", flush=True)
        json.dump(didx, open(out / "depths.json", "w"))
        print(f"→ depths.f32  {doff/2**30:.2f} GiB / {len(deps)} 张")

    total = off + (doff if args.depth else 0)
    print(f"\n合计 {total/2**30:.2f} GiB")
    print("🔴 内存要能装下这个数,否则页缓存命中率低,等于白做。")
    print("   核对:free -g 的 available 应明显大于上面这个数。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
