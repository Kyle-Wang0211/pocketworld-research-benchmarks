# -*- coding: utf-8 -*-
"""修 /root/infer_arm.sh 里我自己写的假出处。原注释三处错,逐行核过 test.py(cd10d5c):
   test.py:314-326  dtu  -> filter_depth(..., args.geo_mask_thres, args.geo_pixel_thres, ...)
   test.py:327-337  tank -> filter_depth_dynamic(...)  【是另一个函数】, 只吃 photo_thres_all[scan]
   test.py:338-351  eth3d-> filter_depth(..., geo_mask_thres_all[scan], geo_pixel_thres_all[scan], ...)
   test.py:353-366  general(我们) -> args.*
   只改注释, 不改任何一个参数值。"""
import io, sys

P = "/root/infer_arm.sh"
s = io.open(P, encoding="utf-8").read()

OLD = """#   --geo_mask_thres 2           官方三份脚本的有效值【全是 2】: DTU line20 显式 2;
#                                Tank/ETH3D 不传 -> test.py argparse 默认 2。
#                                filter.py:113 签名里的 3 是死代码: test.py:356-365 调用时
#                                总是显式传 args.geo_mask_thres, 那个 3 永不生效。
#                                (旧臂 off768_true 传的 3 不是官方值, 不照抄)
#   --geo_pixel_thres 1.0        test.py argparse 默认 (ETH3D/Tank 脚本都不覆盖)"""

NEW = """#   --geo_mask_thres 2           🔴 2026-09-22 更正: 原注释写「官方三份脚本的有效值全是 2」,
#                                这是假的, 我没核就写了。逐行核 test.py(cd10d5c) 的实情:
#                                  DTU   test.py:314-326  filter_depth(..., args.geo_mask_thres=2,
#                                                          args.geo_pixel_thres=0.125)  <- 脚本 line20 显式传
#                                  Tank  test.py:327-337  filter_depth_dynamic(...) 【是另一个函数】,
#                                                          只吃 photo_thres_all[scan]; 这两个参数根本不参与
#                                  ETH3D test.py:338-351  filter_depth(..., geo_mask_thres_all[scan],
#                                                          geo_pixel_thres_all[scan])  <- 逐场景表【覆盖 argparse】,
#                                                          官方 test_eth_*.sh 压根不传这两个参数
#                                  表值 test.py:237-263: geo_mask_thres 25 个场景里 24 个是 1(只 bridge=2)
#                                  我们  test.py:353-366  dataset=general -> 用 args.*, 两张表对我们全不生效
#                                ⇒ 官方没有统一值: DTU=2, ETH3D=1, Tank 不适用。
#                                ⇒ 为什么仍然取 2 而不抄 ETH3D 的 1: 见下「闸梯子」一节 —— 抄 1 在我们的
#                                  素材上多层显著变重, 而 ETH3D 用的 F1 会奖励完整度, 我们的判据不会。
#   --geo_pixel_thres 1.0        🔴 同上更正: 不存在「官方默认」这回事。DTU 脚本显式传 0.125;
#                                ETH3D 走逐场景表, 取值 0.5 / 1 / 2 (室内 office/lounge/old_computer 取 2,
#                                living_room/lecture_room/exhibition_hall 取 0.5)。1.0 是表里 9/25 个场景的值,
#                                但绝不是「大家都用的那个数」。官方做法本身就是【逐场景调】。
#
#   闸梯子 (2026-09-22 实测, 同一份 lg_ep0 深度图, 唯一变量 geo_mask_thres, geo_pixel_thres 恒 1.0):
#       thres=3  36,233,955 点 | 厚度中位 69.0mm | 多层(片>=1000) 56.96%
#       thres=2  39,345,336 点 | 厚度中位 83.2mm | 多层(片>=1000) 61.99%   <- 本脚本
#       thres=1  42,007,356 点 | 厚度中位111.0mm | 多层(片>=1000) 70.86%   <- ETH3D 官方表值
#     配对比较(只算三臂【公共像素】, 消掉覆盖面差异)同向: >2cm 多层 43.59 / 49.09 / 56.43%
#     ⇒ 松闸买到的 +16% 点数, 代价是同一批像素上第二层更密更连片。用户肉眼已独立判过
#       「thres=1 比 thres=3 多层和粘连都增加」(/root/holdout.sh)。故【不抄 ETH3D 的 1】。"""

if OLD not in s:
    sys.exit("🔴 没匹配到原文, 不改。")
io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
print("✅ 已改 %s" % P)
