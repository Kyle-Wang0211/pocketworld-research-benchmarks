# -*- coding: utf-8 -*-
"""两条一行级的改动,都有出处,都从没试过。老 ep0 + 20src,其余逐字不变。

A) geo_pixel_thres = 0.125
   出处: 上游官方 `scripts/test/test_dtu_casdiffmvs.sh:20` 显式传 0.125。
   我们一直用 1.0 —— 那只是 `filter.py` 的【函数默认值】,不是官方值。
   我们量过 1.0→0.5 近似死键(只 0.73pp),但 0.125 是再紧 8 倍, 从没试过。

B) 对称归一化(★ 机制上与「整体收紧」不同, 最值得试的一条)
   上游写的是   relative_depth_diff = |d_reproj − d_ref| / d_ref          <- 分母只有 ref
   Vis-MVSNet   `fusion.py:114`  < max(ref_depth, reproj_d) * depth_thresh <- 对称
   MVSFormer    `misc/fusion.py:103-104` 抄的也是对称版。两者均 MIT。
   🔑 差别的方向正好对口双层: 源视图【幻觉出一个更近的面】时 d_reproj < d_ref,
      上游那个分母偏大 ⇒ 闸更松 ⇒ 假的近层活下来。对称版把分母换成两者中的大者,
      在这个方向上收紧,而在「源视图给出更远的面」方向上保持不变。
   ⇒ 这不是整体收紧, 是把一个【不对称的偏袒】改掉。所以它有可能不付均匀的覆盖代价。
"""
import os, sys, re, shutil
SRC = "/root/diffmvs/filter.py"
DST = "/root/filter_sym.py"
s = open(SRC).read()
OLD = "    relative_depth_diff = depth_diff / depth_ref"
NEW = ("    # ★ 对称归一化: 抄 Vis-MVSNet fusion.py:114 / MVSFormer misc/fusion.py:103-104 (均 MIT)\n"
       "    #   上游: / depth_ref        <- 源视图幻觉出更近的面时分母偏大 => 闸更松 => 假近层活下来\n"
       "    #   对称: / max(ref, reproj) <- 只在那个方向收紧, 另一方向不变\n"
       "    relative_depth_diff = depth_diff / np.maximum(depth_ref, depth_reproj)")
n = s.count(OLD)
print("匹配到 %d 处 `relative_depth_diff = depth_diff / depth_ref`" % n, flush=True)
assert n >= 1, "没匹配到, 停"
open(DST, "w").write(s.replace(OLD, NEW))
print("写出 %s" % DST, flush=True)
