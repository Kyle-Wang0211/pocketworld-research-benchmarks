# -*- coding: utf-8 -*-
"""充分条件测试原型: 让 geo_depth_thres 逐像素随不确定度【放宽】。

🔴 这是【机制探针】不是候选算法。`secmass` 的出处还在查(agent F),
   函数形式和系数 k 是我定的、没有出处 ⇒ 所以我扫 k 而不是挑一个值,
   问的是「**存不存在任何单调放宽能跳出那条取舍前沿**」,不是「k 该取多少」。

为什么是【放宽】不是收紧(机制,已在 D2HC 那轮实证过同构现象):
  `filter_depth` 里阈值决定两件事 ——
   ① 哪些 src 算「同意」(决定该像素保不保留)
   ② `depth_est_averaged = (Σ 同意的 src 深度 + ref) / (同意数+1)` 的【平均池】
  在低纹理歧义处放宽 ⇒ 近层和远层的 src 【都算同意】⇒ 两层被平均成【一个面】
  ⇒ 层数减少,而且点数/覆盖【不减反增】。这正是 D2HC 三项全赢的同一个机制
  (接受走曲线、平均走最松档),只是驱动量换成逐像素的。
"""
import os, sys, numpy as np, cv2

SRC = "/root/diffmvs/filter.py"
DST = "/root/filter_adapt.py"
s = open(SRC).read()

OLD = """    mask = np.logical_and(dist < geo_pixel_thres, 
                            relative_depth_diff < geo_depth_thres)"""
NEW = """    # ★ 机制探针: geo_depth_thres 可以是【逐像素的数组】(与 depth_ref 同形)
    #   放宽发生在不确定度高处 => 近/远两层的 src 都算同意 => 被平均成一个面
    mask = np.logical_and(dist < geo_pixel_thres, 
                            relative_depth_diff < geo_depth_thres)"""
assert s.count(OLD) == 1, "锚点未命中"
s = s.replace(OLD, NEW)

# filter_depth 里读一张逐像素阈值图
OLD2 = """        ref_depth_est = read_pfm(
            os.path.join(out_folder, 'depth_est/{:0>8}.pfm'.format(ref_view)))[0]"""
NEW2 = """        ref_depth_est = read_pfm(
            os.path.join(out_folder, 'depth_est/{:0>8}.pfm'.format(ref_view)))[0]

        # ★ 机制探针: 若 out_folder/dthres/ 下有同名 pfm, 就把它当逐像素 geo_depth_thres
        _dt = os.path.join(out_folder, 'dthres/{:0>8}.pfm'.format(ref_view))
        _geo_depth_thres = geo_depth_thres
        if os.path.exists(_dt):
            _geo_depth_thres = read_pfm(_dt)[0]"""
assert s.count(OLD2) == 1, "锚点2未命中"
s = s.replace(OLD2, NEW2)

# 把调用处的 geo_depth_thres 换成逐像素版
OLD3 = """                geo_pixel_thres,
                geo_depth_thres
            )"""
n3 = s.count(OLD3)
assert n3 >= 1, "锚点3未命中 (found %d)" % n3
s = s.replace(OLD3, """                geo_pixel_thres,
                _geo_depth_thres
            )""")
open(DST, "w").write(s)
print("✅ 写出 %s (逐像素阈值图入口 = out_folder/dthres/*.pfm)" % DST)
