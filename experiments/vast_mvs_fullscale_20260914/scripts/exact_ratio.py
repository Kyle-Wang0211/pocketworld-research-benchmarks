#!/usr/bin/env python3
"""按 tuple 级精确比例 19.3/41.4/39.3 重建 train.txt。
   贪心:先算在该比例下能撑起的最大总量,再逐桶挑 scan 逼近目标 tuple 数。"""
import os, glob, collections, random
ROOT="/root/monotrain"; L="/root/MonoMVSNet/lists/ours"
TARGET={"Hypersim":0.193,"BlendedMVG":0.414,"TartanAir":0.393}
def bucket(s): return "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
val=set(l.strip() for l in open(f"{L}/val.txt") if l.strip())
bad=set()
if os.path.exists("/root/pruned_scans.txt"):
    bad=set(l.strip() for l in open("/root/pruned_scans.txt") if l.strip())
prev=set(l.strip() for l in open(f"{L}/train.txt") if l.strip())     # 已剪过坏 scan 的池
pool=collections.defaultdict(list); tot=collections.Counter()
for s in sorted(os.listdir(ROOT)):
    if s in val or s in bad or not os.path.isdir(os.path.join(ROOT,s)): continue
    if s not in prev: continue          # 只用已验证可训练的 scan(21 个坏的已剔除)
    p=f"{ROOT}/{s}/cams/pair.txt"
    if not os.path.exists(p): p=f"{ROOT}/{s}/pair.txt"
    if not os.path.exists(p): continue
    try:
        with open(p) as f: n=int(f.readline())
    except Exception: continue
    if n<=0: continue
    b=bucket(s); pool[b].append((s,n)); tot[b]+=n
print("可用 tuple:", dict(tot))
T=min(tot[k]/TARGET[k] for k in TARGET)
print(f"该比例下最大总量 T = {T:,.0f}  (瓶颈桶 = {min(TARGET,key=lambda k: tot[k]/TARGET[k])})")
rng=random.Random(0); out=[]; got=collections.Counter()
for b in TARGET:
    want=TARGET[b]*T
    lst=pool[b][:]; rng.shuffle(lst)
    lst.sort(key=lambda x:-x[1])          # 先放大的,再用小的补尾差
    acc=0; take=[]
    for s,n in lst:
        if acc+n<=want: take.append(s); acc+=n
    for s,n in lst:
        if s in take: continue
        if abs(want-(acc+n))<abs(want-acc): take.append(s); acc+=n
    out+=take; got[b]=acc
G=sum(got.values())
print(f"选中 {len(out)} scans / {G:,} tuples")
for b in ("Hypersim","BlendedMVG","TartanAir"):
    print(f"   {b:12s} {got[b]:7,}  {100.0*got[b]/G:5.2f}%   目标 {100*TARGET[b]:.1f}%")
open(f"{L}/train_exact.txt","w").write("\n".join(sorted(out))+"\n")
print("写出", f"{L}/train_exact.txt")
