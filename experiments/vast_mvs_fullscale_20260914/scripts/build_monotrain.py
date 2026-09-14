#!/usr/bin/env python3
"""搭 MonoMVSNet 的室内微调数据根。
假设:MonoMVSNet 只在 DTU(转台物件)+BlendedMVS(物体/户外)上训过, 从没见过室内房间。
最小检验 = 只加房间:
  - Hypersim  官方 train split 的 scan(纯室内)
  - TartanAir V2 的 11 个 Domes(家居)环境, 全部 Indoor
  - BlendedMVS 官方 106 train scan 作 replay, 防止把它已有的能力训丢
   (replay 的依据: MVSFormer++ 混 DTU 回来就是这个目的; 我们起点权重 bld_best 训在 BlendedMVS 上)
输出: /root/monotrain/<scan> 软链 + lists/ours/{train,val}.txt
"""
import os, glob, csv, collections

ROOT = "/root/monotrain"
os.makedirs(ROOT, exist_ok=True)
DOMES = ["AmericanDiner","ArchVizTinyHouseDay","ArchVizTinyHouseNight","CountryHouse","House",
         "Office","OldBrickHouseDay","OldBrickHouseNight","Restaurant","RetroOffice","Supermarket"]

# Hypersim: 按 Apple 官方 split 只取 train / val
scene2part = {}
for r in csv.DictReader(open("/root/hs/split.csv")):
    if r["split_partition_name"]:
        scene2part[r["scene_name"]] = r["split_partition_name"]

def link(src, name):
    d = os.path.join(ROOT, name)
    if not os.path.islink(d) and not os.path.isdir(d):
        os.symlink(src, d)
    return name

train, val = [], []
n = collections.Counter()

for d in sorted(glob.glob("/root/hs/blendfmt/*")):
    if not os.path.exists(f"{d}/cams/pair.txt"): continue
    scene = "_".join(os.path.basename(d).split("_")[:3])
    p = scene2part.get(scene)
    if p == "train": train.append(link(d, "hs_" + os.path.basename(d))); n["hypersim_train"] += 1
    elif p == "val": val.append(link(d, "hs_" + os.path.basename(d))); n["hypersim_val"] += 1

for d in sorted(glob.glob("/root/ta2/blendfmt/*")):
    if not os.path.exists(f"{d}/cams/pair.txt"): continue
    b = os.path.basename(d)
    if not any(b.startswith(e + "_") for e in DOMES): continue
    # 每个环境的 P000 留作 val, 其余训练(按轨迹切, 不跨轨迹泄漏)
    if b.endswith("_P000"): val.append(link(d, "ta_" + b)); n["tartan_val"] += 1
    else: train.append(link(d, "ta_" + b)); n["tartan_train"] += 1

bm_train = [l.strip() for l in open("/root/MonoMVSNet/lists/blendedmvs/train.txt") if l.strip()]
bm_val   = [l.strip() for l in open("/root/MonoMVSNet/lists/blendedmvs/val.txt") if l.strip()]
for s in bm_train:
    d = f"/root/bmvs/data/BlendedMVS/{s}"
    if os.path.exists(f"{d}/cams/pair.txt"): train.append(link(d, s)); n["blend_train"] += 1
for s in bm_val:
    d = f"/root/bmvs/data/BlendedMVS/{s}"
    if os.path.exists(f"{d}/cams/pair.txt"): val.append(link(d, s)); n["blend_val"] += 1

os.makedirs("/root/MonoMVSNet/lists/ours", exist_ok=True)
open("/root/MonoMVSNet/lists/ours/train.txt", "w").write("\n".join(train) + "\n")
open("/root/MonoMVSNet/lists/ours/val.txt", "w").write("\n".join(val) + "\n")

def tuples(names):
    t = 0
    for s in names:
        with open(f"{ROOT}/{s}/cams/pair.txt") as f:
            try: t += int(f.readline())
            except Exception: pass
    return t

print("组成:", dict(n))
for lbl, names in (("train", train), ("val", val)):
    print(f"  {lbl}: {len(names)} scans | {tuples(names):,} 组")
hs = [s for s in train if s.startswith("hs_")]; ta = [s for s in train if s.startswith("ta_")]
bm = [s for s in train if not s.startswith(("hs_", "ta_"))]
th, tt, tb = tuples(hs), tuples(ta), tuples(bm); tot = th + tt + tb
print(f"  train 自然比: Hypersim {th/tot*100:.1f}% | TartanAir室内 {tt/tot*100:.1f}% | BlendedMVS {tb/tot*100:.1f}%")
# 阳性对照: train / val 场景不能相交
tr_sc = set(s.rsplit("_P", 1)[0] if s.startswith("ta_") else s for s in train)
va_sc = set(s.rsplit("_P", 1)[0] if s.startswith("ta_") else s for s in val)
inter = {s for s in va_sc if s in tr_sc and not s.startswith("ta_")}
print(f"  阳性对照 train∩val(非TartanAir) = {len(inter)} (必须 0);TartanAir 按轨迹切,环境允许重叠")
