# -*- coding: utf-8 -*-
"""每个域一份 held-out 验证集 (Prechelt 1998 §1.2/§3.2: 验证集 = 训练中绝不用于调权重的固定样本, 每若干 epoch 测一次)。
写到 lists/full_v2/:
  train.txt          = 全量 train 去掉所有 held-out scan
  val_<domain>.txt   = 各域验证 scan
  val.txt            = 六份合并 (train.py 每 epoch 自带的 test 用它)
规则(全部沿用已有口径, 不新造数字):
  - 已有的快档 val (lists/ab/val.txt: sp 98 / ta 6 / tg 4 scan) 原样保留
  - BlendedMVS 官方 val 7 scene (lists/blend/val.txt, 本来就不在 train 里) 作为 blendedmvg 验证
  - gso / arkitscenes 没有 held-out: 按快档同一规则 VAL_FRAC=0.10, seed=0 按 scan 抽 (build_final_lists.py:7 同)
    但每 epoch 评测预算按快档 val 的量级 (~3.3K 元组) 控制: arkitscenes 只评测抽出集合里前 K 个视频 (其余仍从 train 剔除, 保持干净)
"""
import os, sys, random, collections
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
from datasets.domain_sampler import domain_of

ROOT, NV, SEED, VAL_FRAC = "/root/monotrain", 8, 0, 0.10
AK_EVAL_VIDEOS = 4          # 评测预算: 4 个视频 ≈ 650 元组 (与 tg 4 scan / 558 元组 同量级)
old_val = [l.strip() for l in open("/root/diffmvs/lists/ab/val.txt") if l.strip()]
bm_val = [l.strip() for l in open("/root/diffmvs/lists/blend/val.txt") if l.strip()]
scans = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "cams", "pair.txt")))
by = collections.defaultdict(list)
for s in scans:
    by[domain_of(s)].append(s)

def pick(lst, frac, seed_off):
    r = random.Random(SEED + seed_off); sh = sorted(lst); r.shuffle(sh)
    return sorted(sh[:max(1, int(round(frac * len(sh))))])

val = {}
val["simpleproc"] = [s for s in old_val if s.startswith("sp_scene_")]
val["tartanair"] = [s for s in old_val if s.startswith("ta_")]
val["tartanground"] = [s for s in old_val if s.startswith("tg_")]
val["blendedmvg"] = [s for s in bm_val if s in set(scans)]
gso_hold = pick(by["gso"], VAL_FRAC, 3)
ak_hold = pick(by["arkitscenes"], VAL_FRAC, 4)
val["gso"] = gso_hold
val["arkitscenes"] = ak_hold[:AK_EVAL_VIDEOS]
holdout = set(sum(val.values(), [])) | set(gso_hold) | set(ak_hold)
train = [s for s in scans if s not in holdout]
os.makedirs("lists/full_v2", exist_ok=True)
open("lists/full_v2/train.txt", "w").write("\n".join(train) + "\n")
allval = []
for d in sorted(val):
    open("lists/full_v2/val_%s.txt" % d, "w").write("\n".join(val[d]) + "\n")
    allval += val[d]
open("lists/full_v2/val.txt", "w").write("\n".join(allval) + "\n")
assert not (set(train) & set(allval))

def tuples(listfile):
    return len(MVSDataset(ROOT, listfile, "train", NV, 384).metas)
print("\n=== lists/full_v2 ===")
tot = 0
for d in sorted(val):
    n = tuples("lists/full_v2/val_%s.txt" % d); tot += n
    extra = "" if d not in ("gso", "arkitscenes") else "  (从 train 剔除 %d scan)" % (len(gso_hold) if d == "gso" else len(ak_hold))
    print("val_%-13s %4d scan %6d 元组  ≈ %4.1f min/epoch 评测%s" % (d, len(val[d]), n, n / 4 * 1.46 / 60, extra))
print("val 合计 %d 元组 ≈ %.0f min/epoch (与训练共卡)" % (tot, tot / 4 * 1.46 / 60))
ct = collections.Counter(domain_of(m[0]) for m in MVSDataset(ROOT, "lists/full_v2/train.txt", "train", NV, 384).metas)
print("train: %d scan, 各域元组 %s" % (len(train), dict(ct)))
