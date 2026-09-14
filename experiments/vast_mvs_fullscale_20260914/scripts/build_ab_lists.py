# -*- coding: utf-8 -*-
"""A+B 第②段的 train/val 列表。
   组成: SimpleProc(与①段【完全同一批】scan) + 室内(TartanAir室内14env + TartanGround)
   规模: 室内部分对齐【官方一段】的规模 16,873 元组 [lists/blend/train.txt 实测]
   比例: 两个室内域按各自实际元组数的【原始比例】抽,不重新加权
         [MVSAnywhere: "the original dataset proportions are preserved"]
   nviews=8: SimpleProc 每场景仅 8 张(add_cameras.py:71 写死),混合训练必须统一;
             官方自己也在不同段用不同值(DTU段=5, BlendedMVS段=9)。
   随机: 固定 seed 0, 按 scan 抽(不切 scan 内部),避免同场景跨 train/val。"""
import os, random, sys
ROOT="/root/monotrain"; NV=8; SEED=0
TARGET_INDOOR=16873          # = 官方 lists/blend/train.txt 在我们盘上的 nviews=9 元组数
INDOOR_ENVS=["AmericanDiner","ArchVizTinyHouseDay","ArchVizTinyHouseNight","CarWelding","CountryHouse",
        "Hospital","House","ModularNeighborhoodIntExt","Office","OldBrickHouseDay","OldBrickHouseNight",
        "Restaurant","RetroOffice","Supermarket"]
def tup(scan):
    p=os.path.join(ROOT,scan,"cams","pair.txt")
    if not os.path.isfile(p): return 0
    k=0
    with open(p) as f:
        try: n=int(f.readline())
        except: return 0
        for _ in range(n):
            f.readline()
            if len(f.readline().split()[1::2])>=NV-1: k+=1
    return k
ta=[d for d in os.listdir(ROOT) if d.startswith("ta_")]
ind=sorted([d for d in ta if any(d[3:].startswith(e+"_") for e in INDOOR_ENVS)])
tg =sorted([d for d in os.listdir(ROOT) if d.startswith("tg_")])
n_ind=sum(tup(s) for s in ind); n_tg=sum(tup(s) for s in tg)
tot=n_ind+n_tg
share_ind=n_ind/tot
print("室内两域实际元组: TA室内 %d (%.4f)  TG %d (%.4f)" % (n_ind,share_ind,n_tg,1-share_ind))
quota={"ta":int(round(TARGET_INDOOR*share_ind)), "tg":TARGET_INDOOR-int(round(TARGET_INDOOR*share_ind))}
print("按原始比例分配:  TA室内 %d  TG %d  (合计 %d)" % (quota["ta"],quota["tg"],TARGET_INDOOR))
rng=random.Random(SEED)
picked={}
for key,lst in (("ta",ind),("tg",tg)):
    pool=lst[:]; rng.shuffle(pool)
    acc=0; sel=[]
    for s in pool:
        if acc>=quota[key]: break
        t=tup(s)
        if t==0: continue
        sel.append(s); acc+=t
    picked[key]=(sel,acc)
    print("  %s: 抽 %d scans -> %d 元组 (目标 %d)" % (key,len(sel),acc,quota[key]))
sp=[l.strip() for l in open("/root/diffmvs/lists/sp/train.txt") if l.strip()]
spv=[l.strip() for l in open("/root/diffmvs/lists/sp/val.txt") if l.strip()]
n_sp=sum(tup(s) for s in sp)
indoor_all=picked["ta"][0]+picked["tg"][0]
rng2=random.Random(SEED)
sh=indoor_all[:]; rng2.shuffle(sh)
nval=max(1,int(round(0.10*len(sh))))
iv=sorted(sh[:nval]); it=sorted(sh[nval:])
train=sorted(sp+it); val=sorted(spv+iv)
os.makedirs("/root/diffmvs/lists/ab",exist_ok=True)
open("/root/diffmvs/lists/ab/train.txt","w").write("\n".join(train)+"\n")
open("/root/diffmvs/lists/ab/val.txt","w").write("\n".join(val)+"\n")
assert not (set(train)&set(val)), "train/val 有交集"
n_it=sum(tup(s) for s in it); n_iv=sum(tup(s) for s in iv); n_spv=sum(tup(s) for s in spv)
print()
print("=== 第②段 list (nviews=%d) ===" % NV)
print("  train %4d scans = %6d 元组   [SimpleProc %d (%.1f%%) + 室内 %d (%.1f%%)]" %
      (len(train), n_sp+n_it, n_sp, 100*n_sp/(n_sp+n_it), n_it, 100*n_it/(n_sp+n_it)))
print("  val   %4d scans = %6d 元组   train∩val=0" % (len(val), n_spv+n_iv))
print("  每 epoch %d 步(batch4) -> %.2f 小时 -> 16 epochs = %.1f 小时" %
      ((n_sp+n_it)//4, (n_sp+n_it)/4*0.89/3600, (n_sp+n_it)/4*0.89/3600*16))
