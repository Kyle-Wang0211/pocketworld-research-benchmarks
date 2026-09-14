#!/usr/bin/env python3
"""按 B 臂比例(Hypersim 19.3 : BlendedMVG 41.4 : TartanAir 39.3)建 MonoMVSNet 训练表。

比例出处:MVSAnywhere 论文 Table 1 的组数 / 其 data_splits 的 tuple 文件行数(两处独立对账一致),
取其中**商用可用**的三家再归一。它的架构因 Patent Pending + non-commercial 不能抄,
但数据配方是独立产物 —— 它的全部贡献就是跨域泛化,配方照抄有依据。

实现上不写新采样器:MVSAnywhere 的机制是 ConcatDataset 按自然大小混合,
所以只要**挑 scan 让三家的自然组数落在目标比例上**, MonoMVSNet 原生的单列表加载
就等价于那个机制。零新代码,零自定阈值。

🔴 全量参与 —— 不做"只留室内"的裁剪。C 端用户拍什么的都有,为修白墙砍户外是拿泛化换单点。
"""
import os, glob, csv, random, sys

ROOT = "/root/monotrain"
RATIO = {"hypersim": 0.193, "blendedmvg": 0.414, "tartanair": 0.393}
SEED = 0

def scan_tuples(d):
    try:
        with open(f"{d}/cams/pair.txt") as f: return int(f.readline())
    except Exception: return 0

def collect(root, pred=None):
    out = []
    for d in sorted(glob.glob(f"{root}/*")):
        if not os.path.exists(f"{d}/cams/pair.txt"): continue
        if pred and not pred(os.path.basename(d)): continue
        n = scan_tuples(d)
        if n > 0: out.append((d, n))
    return out

# ---- Hypersim: 按 Apple 官方 split 分 train/val ----
part = {}
for r in csv.DictReader(open("/root/hs/split.csv")):
    if r["split_partition_name"]: part[r["scene_name"]] = r["split_partition_name"]
def hs_part(name): return part.get("_".join(name.split("_")[:3]))
hs_tr = collect("/root/hs/blendfmt", lambda n: hs_part(n) == "train")
hs_va = collect("/root/hs/blendfmt", lambda n: hs_part(n) == "val")

# ---- TartanAir V2: 每个环境的 P000 留 val, 其余训练(按轨迹切) ----
ta_tr = collect("/root/ta2/blendfmt", lambda n: not n.endswith("_P000"))
ta_va = collect("/root/ta2/blendfmt", lambda n: n.endswith("_P000"))

# ---- BlendedMVG: v1.0.0 的 BlendedMVS/ + v1.0.1/v1.0.2 直接解在 data/ 下的 ----
bm_all = collect("/root/bmvs/data/BlendedMVS") + collect("/root/bmvs/data")
bm_val_names = {l.strip() for l in open("/root/MonoMVSNet/lists/blendedmvs/val.txt") if l.strip()}
bm_tr = [(d, n) for d, n in bm_all if os.path.basename(d) not in bm_val_names]
bm_va = [(d, n) for d, n in bm_all if os.path.basename(d) in bm_val_names]

pools = {"hypersim": hs_tr, "blendedmvg": bm_tr, "tartanair": ta_tr}
have = {k: sum(n for _, n in v) for k, v in pools.items()}
print("可用组数:", {k: f"{v:,}" for k, v in have.items()})

# 谁是瓶颈 -> 决定每 epoch 总量
total = min(have[k] / RATIO[k] for k in RATIO)
binder = min(RATIO, key=lambda k: have[k] / RATIO[k])
quota = {k: int(total * RATIO[k]) for k in RATIO}
print(f"瓶颈 = {binder}  =>  每 epoch 总量 {int(total):,} 组")
print("配额:", {k: f"{v:,}" for k, v in quota.items()})

rng = random.Random(SEED)
picked = {}
for k, pool in pools.items():
    p = pool[:]; rng.shuffle(p)
    got, sel = 0, []
    for d, n in p:
        if got >= quota[k]: break
        sel.append(d); got += n
    picked[k] = (sel, got)
    print(f"  {k:<11} 选 {len(sel):>4}/{len(pool)} scans -> {got:,} 组 (配额 {quota[k]:,})")

os.makedirs(ROOT, exist_ok=True)
def link(src):
    pre = {"/root/hs/": "hs_", "/root/ta2/": "ta_"}
    name = next((v + os.path.basename(src) for k, v in pre.items() if src.startswith(k)), os.path.basename(src))
    dst = os.path.join(ROOT, name)
    if not os.path.islink(dst) and not os.path.isdir(dst): os.symlink(src, dst)
    return name

train = [link(d) for k in ("hypersim", "blendedmvg", "tartanair") for d in picked[k][0]]
val   = [link(d) for d, _ in hs_va + bm_va + ta_va]
os.makedirs("/root/MonoMVSNet/lists/ours", exist_ok=True)
open("/root/MonoMVSNet/lists/ours/train.txt", "w").write("\n".join(train) + "\n")
open("/root/MonoMVSNet/lists/ours/val.txt", "w").write("\n".join(val) + "\n")

got_tot = sum(picked[k][1] for k in picked)
print(f"\n阳性对照 —— 实际达成比例(目标 19.3/41.4/39.3):")
for k in ("hypersim", "blendedmvg", "tartanair"):
    print(f"  {k:<11} {picked[k][1]/got_tot*100:5.1f}%   (目标 {RATIO[k]*100:4.1f}%)")
tr, va = set(train), set(val)
print(f"  train {len(train)} scans / {got_tot:,} 组 | val {len(val)} scans")
print(f"  train∩val = {len(tr & va)}  (必须 0)")
