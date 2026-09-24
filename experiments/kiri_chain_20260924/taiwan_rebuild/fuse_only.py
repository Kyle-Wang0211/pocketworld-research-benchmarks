# -*- coding: utf-8 -*-
"""只跑融合(深度图已存在),用于同一权重下换 geo_mask_thres 出第二个点云。
   逐字复刻 test.py:353-366 的 demo 分支调用:
       pair_folder = args.testpath ; out_folder = args.outdir ; plyfilename = outdir/pc.ply
       filter_depth(pair_folder, out_folder, plyfilename,
                    geo_mask_thres, geo_pixel_thres, geo_depth_thres, photo_thres, method, dataset)
   除 geo_mask_thres 外每个实参都与 infer_arm.sh 完全相同。
   适配代码,必须过阳性对照: thres=2 时点数须与 test.py 一体跑出的 pc.ply 完全一致。"""
import os, sys
os.environ.setdefault("VAR_GATE", "0"); os.environ.setdefault("TEX_GATE", "0")
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth

OUT   = sys.argv[1]                 # 深度图所在目录 (= 推理时的 --outdir)
THRES = int(sys.argv[2])            # geo_mask_thres
PLY   = sys.argv[3]
PAIR  = "/root/mvs_P16k"            # = infer_arm.sh 的 --testpath
print("[fuse] out=%s  geo_mask_thres=%d  ply=%s" % (OUT, THRES, PLY), flush=True)
print("[fuse] VAR_GATE=%s TEX_GATE=%s" % (os.environ["VAR_GATE"], os.environ["TEX_GATE"]), flush=True)
filter_depth(PAIR, OUT, PLY,
             THRES,              # geo_mask_thres  <- 唯一可变
             1.0,                # geo_pixel_thres   test.py argparse 默认
             0.01,               # geo_depth_thres   三份官方脚本一致
             [0.3, 0.5, 0.5],    # photo_thres       test_eth_casdiffmvs.sh:17
             "casdiffmvs",       # method
             "general")          # dataset
print("[fuse] done", flush=True)
