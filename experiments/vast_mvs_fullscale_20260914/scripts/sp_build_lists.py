# -*- coding: utf-8 -*-
"""B 臂 train/val 列表。VAL_FRAC=0.10 —— 官方无规定,沿用 A 臂 build_final_lists.py:7 的口径,标明是我们定的。"""
import os, random, sys
ROOT="/root/monotrain"; VAL_FRAC=0.10; SEED=0
scans=sorted([d for d in os.listdir(ROOT) if d.startswith("sp_scene_")], key=lambda s:int(s.split("_")[-1]))
rng=random.Random(SEED); lst=scans[:]; rng.shuffle(lst)
nval=int(round(VAL_FRAC*len(lst)))
val=sorted(lst[:nval], key=lambda s:int(s.split("_")[-1]))
tr =sorted(lst[nval:], key=lambda s:int(s.split("_")[-1]))
os.makedirs("/root/diffmvs/lists/sp", exist_ok=True)
open("/root/diffmvs/lists/sp/train.txt","w").write("\n".join(tr)+"\n")
open("/root/diffmvs/lists/sp/val.txt","w").write("\n".join(val)+"\n")
assert not (set(tr)&set(val)), "train/val 有交集"
print("场景总数 %d" % len(scans))
print("  train %4d 场景 = %6d 組 (每场景 8)   口径: 场景级划分" % (len(tr), len(tr)*8))
print("  val   %4d 场景 = %6d 組               train∩val = %d" % (len(val), len(val)*8, len(set(tr)&set(val))))
print("  val 占场景 %.4f  占組 %.4f   (VAL_FRAC=%.2f, 我们定的)" % (len(val)/len(scans), len(val)*8/(len(scans)*8), VAL_FRAC))
