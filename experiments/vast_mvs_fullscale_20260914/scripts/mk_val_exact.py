#!/usr/bin/env python3
"""按 tuple 级精确 19.3/41.4/39.3 重建验证集,只用「当前val + 闲置」池,不动训练集。
   与 train_exact 同一套贪心:先放大的,再用小的补尾差。"""
import os, collections, random
ROOT="/root/monotrain"; L="/root/MonoMVSNet/lists/ours"
T={"Hypersim":0.193,"BlendedMVG":0.414,"TartanAir":0.393}
def bucket(s): return "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
def ntup(s):
    for p in (f"{ROOT}/{s}/cams/pair.txt", f"{ROOT}/{s}/pair.txt"):
        if os.path.exists(p):
            with open(p) as f: return int(f.readline())
    return 0
train=set(l.strip() for l in open(f"{L}/train_exact.txt") if l.strip())
val  =set(l.strip() for l in open(f"{L}/val.txt") if l.strip())
bad  =set(l.strip() for l in open("/root/bad_val_scans.txt") if l.strip())
allsc=set(d for d in os.listdir(ROOT) if os.path.isdir(f"{ROOT}/{d}"))
pool=sorted((val | (allsc - train - val - bad)) - bad)
by=collections.defaultdict(list)
for s in pool:
    k=ntup(s)
    if k>0: by[bucket(s)].append((s,k))
tot={b:sum(k for _,k in v) for b,v in by.items()}
CAP=min(tot[b]/T[b] for b in T)
print(f"池 {len(pool)} scans, 按比例最大 {CAP:,.0f} 组 (瓶颈 {min(T,key=lambda b: tot[b]/T[b])})")
rng=random.Random(7); out=[]; got=collections.Counter()
for b in T:
    want=T[b]*CAP; lst=by[b][:]; rng.shuffle(lst); lst.sort(key=lambda x:-x[1])
    acc=0; take=[]
    for s,k in lst:
        if acc+k<=want: take.append(s); acc+=k
    for s,k in lst:
        if s in take: continue
        if abs(want-(acc+k))<abs(want-acc): take.append(s); acc+=k
    out+=take; got[b]=acc
G=sum(got.values())
print(f"选中 {len(out)} scans / {G:,} 组")
for b in ("Hypersim","BlendedMVG","TartanAir"):
    print(f"   {b:12s} {got[b]:7,}  {100.0*got[b]/G:5.2f}%   目标 {100*T[b]:.1f}%")
open(f"{L}/val_exact.txt","w").write("\n".join(sorted(out))+"\n")
print("写出", f"{L}/val_exact.txt")
# 与训练集零交叠自证
print("train∩val_exact =", len(train & set(out)))
