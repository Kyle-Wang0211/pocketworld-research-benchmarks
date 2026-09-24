# -*- coding: utf-8 -*-
"""全量 list v3 —— 每个数字都指到出处:
  hold-out 比例  = BlendedMVS 官方划分 7/113 = 6.19% (diffmvs lists/blend/val.txt 7 scene / train.txt 106 scene), 按 scan 抽
  随机种子       = 123 (官方 train.py argparse --seed 默认)
  评测子集大小   = 官方 BlendedMVS val 的元组数 (lists/blend/val.txt 在 nviews=8 下的元组数), 每域取够这个数的 scan 做每 epoch 评测
                   (hold-out 其余部分照样剔出 train, 只是不每 epoch 评)
  BlendedMVS 域直接用官方 val 7 scene; 其余五域按上面规则抽。
输出 lists/full_v3/{train.txt, val.txt, val_<domain>.txt}
"""
import os, sys, random, collections
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
from datasets.domain_sampler import domain_of

ROOT, NV, SEED = "/root/monotrain", 8, 123
BM_TRAIN = [l.strip() for l in open("/root/diffmvs/lists/blend/train.txt") if l.strip()]
BM_VAL = [l.strip() for l in open("/root/diffmvs/lists/blend/val.txt") if l.strip()]
FRAC = len(BM_VAL) / float(len(BM_VAL) + len(BM_TRAIN))          # 7/113
scans = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "cams", "pair.txt")))
by = collections.defaultdict(list)
for s in scans: by[domain_of(s)].append(s)
def tuples_of(lst):
    tmp = "/tmp/_cnt.txt"; open(tmp, "w").write("\n".join(lst) + "\n")
    return len(MVSDataset(ROOT, tmp, "train", NV, 384).metas)
bm_val_present = [s for s in BM_VAL if s in set(scans)]
EVAL_BUDGET = tuples_of(bm_val_present)                          # 官方 val 的元组数 = 每域评测预算
print("hold-out 比例 %.4f (7/113); 评测预算 = 官方 BlendedMVS val %d scene 的 %d 元组" % (FRAC, len(bm_val_present), EVAL_BUDGET))
rng = random.Random(SEED)
hold, evalset = {}, {}
for d in sorted(by):
    if d == "blendedmvg":
        hold[d] = bm_val_present
    else:
        lst = by[d][:]; rng.shuffle(lst)
        hold[d] = sorted(lst[:max(1, int(round(FRAC * len(lst))))])
    # 评测子集: 按名字顺序累加 scan 直到元组数 >= 预算
    sel, n = [], 0
    for s in hold[d]:
        sel.append(s); n = tuples_of(sel)
        if n >= EVAL_BUDGET: break
    evalset[d] = sel
holdall = set(sum(hold.values(), []))
train = [s for s in scans if s not in holdall]
os.makedirs("lists/full_v3", exist_ok=True)
open("lists/full_v3/train.txt", "w").write("\n".join(train) + "\n")
allval = []
for d in sorted(evalset):
    open("lists/full_v3/val_%s.txt" % d, "w").write("\n".join(evalset[d]) + "\n"); allval += evalset[d]
open("lists/full_v3/val.txt", "w").write("\n".join(allval) + "\n")
assert not (set(train) & set(allval))
print("\n=== lists/full_v3 (nviews=%d, seed %d) ===" % (NV, SEED))
for d in sorted(by):
    print("%-13s 总 %5d scan | hold-out %4d scan (剔出 train) | 每 epoch 评测 %3d scan %5d 元组" % (d, len(by[d]), len(hold[d]), len(evalset[d]), tuples_of(evalset[d])))
ct = collections.Counter(domain_of(m[0]) for m in MVSDataset(ROOT, "lists/full_v3/train.txt", "train", NV, 384).metas)
print("train: %d scan, 各域元组 %s, 合计 %d" % (len(train), dict(ct), sum(ct.values())))
print("val 合计 %d 元组" % tuples_of(allval))
