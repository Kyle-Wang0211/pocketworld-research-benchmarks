#!/usr/bin/env python3.11
"""用**官方** datasets/blend.py 的 MVSDataset 真实 __getitem__ 抽验转换产物。

不自己写读取逻辑 —— 直接 import 官方 dataloader,按训练时一模一样的方式
(mode='train', nviews=trainviews, ndepths=384)取样本,检查:
  * imgs   : nviews 张,每张 (3,H,W),值域 [0,1]
  * proj   : 四个 stage 的 (nviews,2,4,4);stage 间内参恰好差 8/4/2/1 倍
  * depth  : 四个 stage,stage4 == (H,W);深度有限、>0
  * mask   : stage4 有效像素占比不能太低(全 0 的样本训练时是白喂)
  * depth_values: 长度 ndepths 的**视差**等距序列,单调递增,首尾 = 1/depth_max, ~1/depth_min

用法:
  python3.11 verify_with_official_loader.py --root <tg_mvs> --list <lists_all_scans.txt> \
      --nviews 9 --n 20
"""
import argparse
import os
import random
import sys

import numpy as np

import os as _os
DIFFMVS = _os.environ.get("DIFFMVS_REPO",
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, DIFFMVS)
from datasets import find_dataset_def  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--nviews", type=int, default=9)
    ap.add_argument("--ndepths", type=int, default=384)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    MVSDataset = find_dataset_def("blend")
    ds = MVSDataset(a.root, a.list, "train", a.nviews, a.ndepths)
    n_meta = len(ds)
    print(f"[info] 官方 dataloader 建表成功: {n_meta} 个样本 "
          f"(root={a.root}, nviews={a.nviews})")
    if n_meta == 0:
        sys.exit("[fatal] 0 个样本 —— pair.txt 的 src 数不足 nviews-1?")

    rng = random.Random(a.seed)
    idxs = rng.sample(range(n_meta), min(a.n, n_meta))
    shapes, dmins, dmaxs, valid_fracs = set(), [], [], []
    bad = 0
    for k, i in enumerate(idxs):
        s = ds[i]
        imgs = s["imgs"]
        assert len(imgs) == a.nviews, (len(imgs), a.nviews)
        for im in imgs:
            assert im.shape[0] == 3, im.shape
            assert 0.0 <= float(im.min()) and float(im.max()) <= 1.0, (im.min(), im.max())
        C, H, W = imgs[0].shape
        shapes.add((H, W))

        d4 = s["depth"]["stage4"]
        assert d4.shape == (H, W), (d4.shape, H, W)
        for st, div in (("stage1", 8), ("stage2", 4), ("stage3", 2), ("stage4", 1)):
            assert s["depth"][st].shape == (H // div, W // div), (st, s["depth"][st].shape)
            pm = s["proj_matrices"][st]
            assert pm.shape == (a.nviews, 2, 4, 4), pm.shape
            # 内参按 stage 缩放:stage4 的 fx / stageX 的 fx == div
            r = s["proj_matrices"]["stage4"][0, 1, 0, 0] / pm[0, 1, 0, 0]
            assert abs(r - div) < 1e-4, (st, r, div)

        fin = np.isfinite(d4)
        assert fin.all(), "深度里有 NaN/Inf"
        m4 = s["mask"]["stage4"]
        vf = float(m4.mean())
        valid_fracs.append(vf)
        if vf < 0.5:
            bad += 1

        dv = s["depth_values"]
        assert dv.shape == (a.ndepths,), dv.shape
        assert np.all(np.diff(dv) > 0), "depth_values 不单调"
        dmin_from_dv, dmax_from_dv = 1.0 / dv[-1], 1.0 / dv[0]
        dmins.append(float(dmin_from_dv)); dmaxs.append(float(dmax_from_dv))
        pos = d4[d4 > 0]
        print(f"  [{k+1:>2}/{len(idxs)}] meta#{i:<6} {H}x{W} "
              f"depth {pos.min():.3f}~{pos.max():.3f} m  "
              f"range[{dmin_from_dv:.3f},{dmax_from_dv:.3f}]  "
              f"mask 有效 {vf*100:.1f}%")

    print()
    print(f"[ok] 分辨率集合 = {shapes}  (必须只有一个,否则同 batch collate 会崩)")
    print(f"[ok] depth_min 区间 {min(dmins):.3f}~{max(dmins):.3f} m,"
          f"depth_max 区间 {min(dmaxs):.3f}~{max(dmaxs):.3f} m")
    print(f"[ok] stage4 mask 有效占比 中位 {np.median(valid_fracs)*100:.1f}% "
          f"最低 {min(valid_fracs)*100:.1f}%")
    if len(shapes) != 1:
        sys.exit("[fatal] 分辨率不唯一")
    if bad:
        print(f"[warn] {bad}/{len(idxs)} 个样本的 stage4 有效像素 < 50%")
    print("[done] 官方 dataloader 抽验通过")


if __name__ == "__main__":
    main()
