#!/usr/bin/env python3
"""调**官方 filter.py 的 filter_depth**融合一条臂,参数照抄生产口径。

  python3.11 fuse_arm.py --pair_folder .../mvs_P16k --out_folder .../out_P16k \
      --ply .../P16k.ply

🔴 这里**不重写任何判据** —— 直接 import 官方 `filter_depth`,调用方式逐字照抄
   test.py:316。08-17 的事故就是有人自写融合、四处偏离官方,排查很久。

生产口径(handoff 已定案,照抄不改):
   geo_mask_thres  = 3
   geo_pixel_thres = 1.0
   geo_depth_thres = 0.01
   photo_thres     = [0.3, 0.5, 0.5]   ← 三阶段 AND
   深度平均         ← 官方 filter_depth 内部就有,不用也不能关
"""
import argparse, os, sys
# ⚠️ 硬编码 Mac 路径会让脚本在别的机器上直接 ModuleNotFoundError
# (2026-08-19 在租的机器上踩到)。允许用 DIFFMVS_REPO 覆盖。
REPO = os.environ.get("DIFFMVS_REPO") or os.path.expanduser(
    "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, REPO)
from filter import filter_depth          # noqa: E402  ← 官方判据,原样调用

ap = argparse.ArgumentParser()
ap.add_argument("--pair_folder", required=True)
ap.add_argument("--out_folder", required=True)
ap.add_argument("--ply", required=True)
a = ap.parse_args()

filter_depth(
    a.pair_folder,
    a.out_folder,
    a.ply,
    3,                      # geo_mask_thres
    1.0,                    # geo_pixel_thres
    0.01,                   # geo_depth_thres
    [0.3, 0.5, 0.5],        # photo_thres —— 三阶段 AND
    "casdiffmvs",           # method
    "general",              # dataset
)
print(f"✅ {a.ply}  {os.path.getsize(a.ply)/1e6:.0f} MB")
