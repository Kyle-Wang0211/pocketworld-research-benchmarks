# -*- coding: utf-8 -*-
"""完全版 A+B 的 train/val 列表。

与快档(lists/ab/)的【唯一区别是规模】, 比例/口径/随机种子全部不动:
  比例   SimpleProc : 室内 = 33 : 67   (快档实测 33.0% : 67.0%, 已验证有效)
         🔴 保持这个比例是【单变量原则】: 若同时放大规模又改比例(全量直接混会变成 10:90),
            结果好坏都无法归因, 而 SimpleProc 正是「粘连消失」的来源与防遗忘的全部依靠。
  室内   TartanAir室内14env + TartanGround 【全量】, 两域不重新加权
         [MVSAnywhere: "the original dataset proportions are preserved"]
  nviews 8  (SimpleProc 每场景仅 8 张, add_cameras.py:71 写死)
  VAL_FRAC 0.10, seed 0  (与快档、与 A 臂 build_final_lists.py:7 同)
"""
import os, random

ROOT = "/root/monotrain"
NV, SEED, VAL_FRAC = 8, 0, 0.10
SP_SHARE = 33.0 / 67.0          # SimpleProc 相对室内的比例(快档实测值)
INDOOR_ENVS = ["AmericanDiner", "ArchVizTinyHouseDay", "ArchVizTinyHouseNight", "CarWelding",
               "CountryHouse", "Hospital", "House", "ModularNeighborhoodIntExt", "Office",
               "OldBrickHouseDay", "OldBrickHouseNight", "Restaurant", "RetroOffice", "Supermarket"]

def tup(scan):
    p = os.path.join(ROOT, scan, "cams", "pair.txt")
    if not os.path.isfile(p):
        return 0
    k = 0
    with open(p) as f:
        try:
            n = int(f.readline())
        except Exception:
            return 0
        for _ in range(n):
            f.readline()
            if len(f.readline().split()[1::2]) >= NV - 1:
                k += 1
    return k

ta = [d for d in os.listdir(ROOT) if d.startswith("ta_")]
indoor_ta = sorted([d for d in ta if any(d[3:].startswith(e + "_") for e in INDOOR_ENVS)])
indoor_tg = sorted([d for d in os.listdir(ROOT) if d.startswith("tg_")])
sp_all = sorted([d for d in os.listdir(ROOT) if d.startswith("sp_scene_")],
                key=lambda s: int(s.split("_")[-1]))

n_ta = sum(tup(s) for s in indoor_ta)
n_tg = sum(tup(s) for s in indoor_tg)
n_indoor = n_ta + n_tg
print("室内全量: TA室内 %d scans/%d 元组 + TG %d scans/%d 元组 = %d 元组"
      % (len(indoor_ta), n_ta, len(indoor_tg), n_tg, n_indoor))

# SimpleProc 取够 33:67 所需的量, 按场景号顺序取(确定性, 与①段同一批在前)
need_sp = int(round(n_indoor * SP_SHARE))
rng = random.Random(SEED)
sel_sp, acc = [], 0
for s in sp_all:
    if acc >= need_sp:
        break
    t = tup(s)
    if t == 0:
        continue
    sel_sp.append(s)
    acc += t
print("SimpleProc: 需要 %d 元组 -> 取 %d 场景 = %d 元组 (盘上共 %d 场景)"
      % (need_sp, len(sel_sp), acc, len(sp_all)))
if acc < need_sp * 0.95:
    print("🔴 警告: SimpleProc 不足目标的 95%%, 实际比例会偏离 33:67")

indoor_all = indoor_ta + indoor_tg
# val: 两边各抽 10%, 按 scan 划分(不切 scan 内部, 避免同场景跨 train/val)
def split(lst, seed_off):
    r = random.Random(SEED + seed_off)
    sh = lst[:]
    r.shuffle(sh)
    k = max(1, int(round(VAL_FRAC * len(sh))))
    return sorted(sh[k:]), sorted(sh[:k])

sp_tr, sp_va = split(sel_sp, 1)
in_tr, in_va = split(indoor_all, 2)
train = sorted(sp_tr + in_tr)
val = sorted(sp_va + in_va)
assert not (set(train) & set(val)), "train/val 有交集"

os.makedirs("/root/diffmvs/lists/abfull", exist_ok=True)
open("/root/diffmvs/lists/abfull/train.txt", "w").write("\n".join(train) + "\n")
open("/root/diffmvs/lists/abfull/val.txt", "w").write("\n".join(val) + "\n")

n_sptr = sum(tup(s) for s in sp_tr)
n_intr = sum(tup(s) for s in in_tr)
n_spva = sum(tup(s) for s in sp_va)
n_inva = sum(tup(s) for s in in_va)
tot = n_sptr + n_intr
print()
print("=== 完全版 list (nviews=%d) ===" % NV)
print("  train %4d scans = %6d 元组  [SimpleProc %d (%.1f%%) + 室内 %d (%.1f%%)]"
      % (len(train), tot, n_sptr, 100.0 * n_sptr / tot, n_intr, 100.0 * n_intr / tot))
print("  val   %4d scans = %6d 元组   train∩val = 0" % (len(val), n_spva + n_inva))
print("  每 epoch %d 步(batch4) -> %.2f h -> 16 epochs = %.1f h"
      % (tot // 4, tot / 4 * 0.322 / 3600, tot / 4 * 0.322 / 3600 * 16))
print()
print("  对照 —— 快档: 21,466 元组 (SimpleProc 33.0%% + 室内 67.0%%), 8.3 h")
sp_pct = 100.0 * n_sptr / tot
dev = abs(sp_pct - 33.0)
print("  完全版放大 %.2f 倍" % (tot / 21466.0))
if dev <= 2.0:
    print("  比例 %.1f%% vs 快档 33.0%% (偏离 %.1fpp) => 单变量成立, 唯一变量 = 数据量" % (sp_pct, dev))
else:
    print("  🔴 比例 %.1f%% vs 快档 33.0%% (偏离 %.1fpp) => 【单变量不成立】" % (sp_pct, dev))
    print("     规模与比例同时变, 结果好坏无法归因。需先把 SimpleProc 扩到足量。")
    raise SystemExit(2)
