#!/usr/bin/env python3
"""@16384 的算子级 profile —— 前面 17 条杠杆全是"猜一条量一条",从没量过时间花在哪个算子。

只测匹配器本体(提取已单独量过)。用**真实两帧的真实特征**,因为剪枝的早退行为依赖数据
分布,拿随机张量测出来的层数是假的。
"""
import argparse
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, "LightGlue")
from lightglue import ALIKED, LightGlue
from lightglue.utils import load_image

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=16384)
ap.add_argument("--depth-conf", type=float, default=0.95)
ap.add_argument("--width-conf", type=float, default=0.99)
ap.add_argument("--fp16", action="store_true")
ap.add_argument("--iters", type=int, default=6)
ap.add_argument("--compile", action="store_true",
                help="torch.compile 融合 elementwise 链(残差 add / qkv 切片的 copy)。\n剪枝有数据依赖控制流会 graph break,但逐层块仍可编译。")
a = ap.parse_args()

dev = "cuda"
frames = sorted(Path("frames").glob("*.jpg"))[:2] or sorted(Path("frames").glob("*.png"))[:2]
print(f"用帧: {[f.name for f in frames]}")

ext = ALIKED(max_num_keypoints=a.n, detection_threshold=0.02).eval().to(dev)
feats = []
for f in frames:
    img = load_image(str(f)).to(dev)
    # 🔴 必须走 extractor.extract(resize=) —— 它内部的 ImagePreprocessor 开了 antialias。
    #    我原来手写 interpolate(antialias 默认关)在 2.5× 降采样下混叠打糊响应图,
    #    16384 的预算只出 7k–11k 点,整个 profile 跑在错误工作点上。
    with torch.no_grad(), torch.autocast("cuda", torch.float16):
        feats.append(ext.extract(img, resize=1600))
print("关键点:", [f["keypoints"].shape[1] for f in feats])

m = LightGlue(features="aliked", depth_confidence=a.depth_conf,
              width_confidence=a.width_conf).eval().to(dev)
if a.fp16:
    m = m.half()
    feats = [{k: (v.half() if v.dtype == torch.float32 else v) for k, v in f.items()}
             for f in feats]

if a.compile:
    # 只编译 transformer 层本体:早退逻辑是数据依赖的,整体编译必然 break
    for i, blk in enumerate(m.transformers):
        m.transformers[i] = torch.compile(blk, dynamic=True)

d = {"image0": feats[0], "image1": feats[1]}
with torch.no_grad():
    for _ in range(8 if a.compile else 3):   # 编译要多预热几轮
        out = m(d)
torch.cuda.synchronize()
t0 = time.perf_counter()
with torch.no_grad():
    for _ in range(a.iters):
        out = m(d)
torch.cuda.synchronize()
print(f"匹配 {(time.perf_counter() - t0) / a.iters * 1000:.1f} ms/对  "
      f"匹配数 {out['matches'][0].shape[0]}")
print("实际执行层数", int(out["stop"]) if "stop" in out else "?", "/ 9")

from torch.profiler import ProfilerActivity, profile

with torch.no_grad(), profile(
        activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as pf:
    for _ in range(3):
        m(d)
    torch.cuda.synchronize()
print()
print(pf.key_averages().table(sort_by="cuda_time_total", row_limit=18,
                              max_name_column_width=45))
