# -*- coding: utf-8 -*-
"""全域全量 list (做法①: 每数据集等量采样由 train.py --domain_balance 负责, list 本身不配比)。
  train = /root/monotrain 下六个域的全部 scan(有 cams/pair.txt 的)
          - 快档 val (lists/ab/val.txt, 108 scan, 沿用 => 曲线可与快档对照)
          - BlendedMVS 官方 val (lists/blend/val.txt, 官方划分, 不进 train)
  val   = lists/ab/val.txt
  元组数用官方 MVSDataset(blend.py) 数, 不自己复刻解析。
"""
import os, sys, collections
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
from datasets.domain_sampler import domain_of

ROOT, NV, N_PER = "/root/monotrain", 8, 100000
VAL = [l.strip() for l in open("/root/diffmvs/lists/ab/val.txt") if l.strip()]
BMVS_VAL = set(l.strip() for l in open("/root/diffmvs/lists/blend/val.txt") if l.strip())
scans = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "cams", "pair.txt")))
missing_val = [v for v in VAL if v not in set(scans)]
assert not missing_val, "val scan 不在盘上: %s" % missing_val[:5]
train = [s for s in scans if s not in set(VAL) and s not in BMVS_VAL]
os.makedirs("lists/full", exist_ok=True)
open("lists/full/train.txt", "w").write("\n".join(train) + "\n")
open("lists/full/val.txt", "w").write("\n".join(VAL) + "\n")
assert not (set(train) & set(VAL))

def count(listfile):
    ds = MVSDataset(ROOT, listfile, "train", NV, 384)
    c = collections.Counter(domain_of(m[0]) for m in ds.metas)
    sc = collections.Counter(domain_of(s) for s in [l.strip() for l in open(listfile) if l.strip()])
    return c, sc

ct, st = count("lists/full/train.txt")
cv, sv = count("lists/full/val.txt")
tot = sum(ct.values())
print("\n=== lists/full (nviews=%d) ===" % NV)
print("%-13s %8s %10s %9s %12s %s" % ("域", "scan", "元组", "拼接占比", "①每epoch", "整个训练被看遍数(16ep×10万)"))
for d in sorted(ct):
    print("%-13s %8d %10d %8.1f%% %12d %8.1f" % (d, st[d], ct[d], 100.0 * ct[d] / tot, N_PER, 16.0 * N_PER / ct[d]))
print("%-13s %8d %10d" % ("合计", len(train), tot))
print("val: %d scan %d 元组 %s" % (len(VAL), sum(cv.values()), dict(cv)))
print("每 epoch = %d 样本 = %d 步(batch 4) ≈ %.1f h; 16 epochs ≈ %.1f 天" % (
    N_PER * len(ct), N_PER * len(ct) // 4, N_PER * len(ct) / 4 * 0.331 / 3600, N_PER * len(ct) / 4 * 0.331 / 3600 * 16 / 24))
