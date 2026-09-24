# -*- coding: utf-8 -*-
"""融合(深度图已存在), pair 目录可指定 => 可对比 10 src vs 20 src。
用法: fuse2.py <out_folder> <pair_folder> <ply> <mode>
      mode = "2" / "3"  -> filter_depth 固定闸
      mode = "dyn"      -> filter_depth_dynamic 官方自适应(室内三元组 Museum=[2,4,1300])
其余每个实参都与 infer_arm.sh 一致, 不动。"""
import os, sys
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth, filter_depth_dynamic
OUT, PAIR, PLY, MODE = sys.argv[1:5]
ns = int(open(os.path.join(PAIR,"pair.txt")).read().split("\n")[2].split()[0])
print("[fuse] out=%s pair=%s(src/ref=%d) mode=%s" % (OUT, PAIR, ns, MODE), flush=True)
if MODE == "dyn":
    filter_depth_dynamic("Museum", PAIR, OUT, PLY, [0.3,0.5,0.5], "casdiffmvs", "general")
else:
    filter_depth(PAIR, OUT, PLY, int(MODE), 1.0, 0.01, [0.3,0.5,0.5], "casdiffmvs", "general")
print("[fuse] done", flush=True)
