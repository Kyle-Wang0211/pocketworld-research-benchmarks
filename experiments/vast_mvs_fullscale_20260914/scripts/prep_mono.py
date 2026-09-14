#!/usr/bin/env python3
"""把我们的 132 张(mvs_P16k, BlendedMVS 约定 line11 = "dmin dmax")转成 MonoMVSNet
general_eval_vit.py 期望的 DTU 约定 line11 = "depth_min depth_interval num_depth depth_max"。

不自定任何常数 —— 用它自己的算术反推:
  read_cam_file 里若 line11 有 >=3 项, 它会做
      depth_max = depth_min + num_depth * depth_interval
      depth_interval = (depth_max - depth_min) / self.ndepths      # ndepths = 192 硬编码
  所以只要写 num_depth=192, depth_interval=(dmax-dmin)/192,
  它算回来的 depth_max 正好 = dmax, depth_interval 正好 = (dmax-dmin)/192。
  第四项 depth_max 是 MVSNet 标准格式的第四列(colmap2mvsnet.py 也写四列), 它不读但留着。
"""
import os, sys, glob, shutil

SRC = "/root/mvs_P16k"
DST = "/root/mono_data/scene0"
NDEPTHS = 192          # datasets/general_eval_vit.py:20  self.ndepths = 192  # Hardcode

os.makedirs(f"{DST}/cams", exist_ok=True)
if not os.path.islink(f"{DST}/images") and not os.path.isdir(f"{DST}/images"):
    os.symlink(f"{SRC}/images", f"{DST}/images")
shutil.copy(f"{SRC}/pair.txt", f"{DST}/pair.txt")

n = 0; rng = []
for f in sorted(glob.glob(f"{SRC}/cams/*_cam.txt")):
    lines = open(f).read().rstrip("\n").split("\n")
    parts = lines[-1].split()
    assert len(parts) == 2, f"{f} line11 不是两项: {parts}"
    dmin, dmax = float(parts[0]), float(parts[1])
    assert dmax > dmin > 0, f"{f} 深度范围异常 {dmin} {dmax}"
    interval = (dmax - dmin) / NDEPTHS
    lines[-1] = f"{dmin:.6f} {interval:.9f} {NDEPTHS} {dmax:.6f}"
    open(f"{DST}/cams/{os.path.basename(f)}", "w").write("\n".join(lines) + "\n")
    rng.append((dmin, dmax)); n += 1

import statistics as st
print(f"写了 {n} 个 cam 文件 -> {DST}/cams")
print(f"深度范围 dmin 中位 {st.median(a for a,_ in rng):.3f} m | dmax 中位 {st.median(b for _,b in rng):.3f} m")
# 阳性对照: 用它的公式反算, 必须还原出原始 dmax
d0, d1 = rng[0]
iv = (d1 - d0) / NDEPTHS
back = d0 + NDEPTHS * iv
print(f"阳性对照 反算 depth_max = {back:.6f}, 原始 dmax = {d1:.6f}, 差 {abs(back-d1):.2e}  (必须 ~0)")
print(f"图 {len(os.listdir(DST + '/images'))} 张 | pair.txt {open(DST+'/pair.txt').readline().strip()} 个视点")
