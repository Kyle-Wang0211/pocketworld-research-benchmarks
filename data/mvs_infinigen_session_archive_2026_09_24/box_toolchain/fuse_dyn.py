# -*- coding: utf-8 -*-
"""用官方【自适应】几何一致性(D2HC-RMVSNet)融合同一份 lg_ep0 深度图。

逐字调用上游 filter.py::filter_depth_dynamic(cd10d5c), 零改动。签名(filter.py:294-301):
    (scan, pair_folder, out_folder, plyfilename, photo_thres, method, dataset)

单变量保证 —— 已逐行核过:
  · 光度闸: 两个函数的 method=='casdiffmvs' 分支【逐字相同】
    (conf0/1/2 三档 > photo_thres[0/1/2] 后相与), 故光度侧零差异。
  · scan 形参在函数体内【只用于查三张几何表】(filter.py:308/315/322), 不做别的。
    传 'Museum' = 取官方【室内】三元组 [N0=2, A=4, B=1300];
    Auditorium/Ballroom/Courtroom/Museum/Palace 五个室内场景这三项完全相同。
  · photo_thres 保持我们现值 [0.3,0.5,0.5], 【不抄】 Museum 的 [0.3,0.3,0.7]
    —— 抄了就是偷带第二变量。
  · dataset 形参在函数体内从未被使用(实测 grep 无命中), 传什么都一样。
  · 天花板 `geo_mask_sum >= 10` 与 range(i,11) 要求每个 ref 有 10 个 src:
    我们 pair.txt 实测 132/132 个 ref 恰好都是 10 个, 完全在射程内。
"""
import os, sys
os.environ.setdefault("VAR_GATE", "0"); os.environ.setdefault("TEX_GATE", "0")
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth_dynamic

OUT = sys.argv[1]; PLY = sys.argv[2]
SCAN = sys.argv[3] if len(sys.argv) > 3 else "Museum"
print("[dyn] out=%s scan=%s(只取几何三元组) ply=%s" % (OUT, SCAN, PLY), flush=True)
print("[dyn] VAR_GATE=%s TEX_GATE=%s" % (os.environ["VAR_GATE"], os.environ["TEX_GATE"]), flush=True)
filter_depth_dynamic(SCAN, "/root/mvs_P16k", OUT, PLY,
                     [0.3, 0.5, 0.5],   # 与 infer_arm.sh 一致, 不动
                     "casdiffmvs",
                     "general")
print("[dyn] done", flush=True)
