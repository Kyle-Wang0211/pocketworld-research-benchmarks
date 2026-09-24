# -*- coding: utf-8 -*-
"""重训前的运行期自证: 证明 dataloader 真的吃到【修好的】深度范围。

规矩(记忆 feedback_swap_arm_experiments_need_runtime_self_proof):
  换臂实验必须能在运行期证明跑的是哪条臂。这里直接用官方 dataloader 取样,
  把它实际读到的 depth_min/depth_max 打出来, 并与 skyfix 备份里的【旧值】对照。
"""
import os, sys, random
import numpy as np
sys.path.insert(0, "/root/diffmvs_full")
from datasets.blend import MVSDataset

MONO = "/root/monotrain"
BACKUP = "/root/skyfix_backup.tsv"

old = {}
for ln in open(BACKUP):
    p, o, n = ln.rstrip("\n").split("\t")
    old[p] = (tuple(float(x) for x in o.split()), tuple(float(x) for x in n.split()))
print("skyfix 备份记录 %d 条" % len(old))

ds = MVSDataset(MONO, "/root/diffmvs_full/lists/full_v3/train.txt", "train", 8, 384)
print("训练集元组数: %s" % format(len(ds.metas), ","))

# 只看 TartanAir 的元组(ta_ 前缀), 它们才是被修的
ta = [i for i, m in enumerate(ds.metas) if m[0].startswith("ta_")]
print("其中 TartanAir: %s (%.1f%%)" % (format(len(ta), ","), 100 * len(ta) / len(ds.metas)))

random.seed(20260922)
sel = random.sample(ta, 400)
now_max, was_max, hit = [], [], 0
for i in sel:
    scan, ref, _ = ds.metas[i]
    cf = os.path.join(MONO, scan, "cams", "%08d_cam.txt" % ref)
    if not os.path.exists(cf):
        continue
    t = open(cf).read().strip().split("\n")[-1].split()
    dm = float(t[-1])
    now_max.append(dm)
    if cf in old:
        hit += 1
        was_max.append(old[cf][0][1])
        # 自证: 磁盘上的值必须等于备份记录的【新值】
        assert abs(dm - old[cf][1][1]) < 1e-3, "🔴 磁盘值与备份的新值不符: %s" % cf
    else:
        was_max.append(dm)

n = np.array(now_max); w = np.array(was_max)
print()
print("dataloader 会读到的 depth_max (n=%d 个 TartanAir 参考视图, 其中 %d 个被 skyfix 改过)" % (len(n), hit))
print("  修前: 中位 %9.2f   p90 %9.2f   >1000 占 %5.1f%%" % (np.median(w), np.percentile(w, 90), 100 * (w > 1000).mean()))
print("  修后: 中位 %9.2f   p90 %9.2f   >1000 占 %5.1f%%" % (np.median(n), np.percentile(n, 90), 100 * (n > 1000).mean()))
print()
print("✅ 运行期自证通过: 官方 dataloader 的元组表指向的 cam 文件, 磁盘上就是修好的值"
      if hit > 0 and (n > 1000).mean() < (w > 1000).mean() else "🔴 自证失败")
