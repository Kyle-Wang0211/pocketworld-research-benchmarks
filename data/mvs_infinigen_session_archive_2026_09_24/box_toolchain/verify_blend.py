# -*- coding: utf-8 -*-
"""用【训练本尊】datasets/blend.py 的 MVSDataset 读一遍产物, 报 mask 覆盖率。
   这是最终判据: 不是我自己解析 cam.txt, 是训练 dataloader 自己读。"""
import sys, os, numpy as np
sys.path.insert(0, "/root/diffmvs_full")
os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset

root, scan, nviews = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5
lst = "/tmp/_verify_list.txt"
open(lst, "w").write(scan + "\n")
ds = MVSDataset(root, lst, mode="train", nviews=nviews, ndepths=384)
print("metas =", len(ds))
assert len(ds) > 0, "🔴 blend.py 一条 meta 都没建出来 (pair.txt 的 src 数 < nviews-1)"
cov = []
for i in range(min(len(ds), 8)):
    s = ds[i]
    m = s["mask"]["stage4"]; d = s["depth"]["stage4"]
    cov.append(m.mean())
    if i == 0:
        print("imgs", np.asarray(s["imgs"]).shape, "depth", d.shape,
              "depth_values[0,-1]", s["depth_values"][0], s["depth_values"][-1])
        print("proj stage4[0]:\n", s["proj_matrices"]["stage4"][0])
print("mask(stage4) 进 loss 的像素占比: mean=%.4f min=%.4f max=%.4f"
      % (float(np.mean(cov)), float(np.min(cov)), float(np.max(cov))))
