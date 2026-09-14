import os, glob
def scans(root):
    return sorted(d for d in glob.glob(f"{root}/*") if os.path.exists(f"{d}/cams/pair.txt"))
def tup(ds):
    t=0
    for s in ds:
        with open(f"{s}/cams/pair.txt") as f:
            try: t+=int(f.readline())
            except Exception: pass
    return t
hs=scans("/root/hs/blendfmt"); ta=scans("/root/ta2/blendfmt")
bm1=scans("/root/bmvs/data/BlendedMVS")            # v1.0.0 的 113
bm2=[d for d in scans("/root/bmvs/data") ]         # v1.0.1 直接解在 data/ 下的
th,tt,tb1,tb2 = tup(hs),tup(ta),tup(bm1),tup(bm2)
print(f"  Hypersim            {len(hs):>4} scans | {th:>8,} 组")
print(f"  TartanAir V2        {len(ta):>4} scans | {tt:>8,} 组")
print(f"  BlendedMVS  v1.0.0  {len(bm1):>4} scans | {tb1:>8,} 组")
print(f"  BlendedMVS+ v1.0.1  {len(bm2):>4} scans | {tb2:>8,} 组")
tb=tb1+tb2; tot=th+tt+tb
print(f"  ── BlendedMVG 合计   {len(bm1)+len(bm2):>4} scans | {tb:>8,} 组  (MVSAnywhere 用 494 scans / 97,106 组)")
print(f"\n  当前自然比  Hypersim {th/tot*100:5.1f}% | TartanAir {tt/tot*100:5.1f}% | BlendedMVG {tb/tot*100:5.1f}%")
print(f"  目标(B臂)   Hypersim  19.3% | TartanAir  39.3% | BlendedMVG  41.4%")
# 按目标比例, 谁是瓶颈
for name,have,frac in (("Hypersim",th,0.193),("TartanAir",tt,0.393),("BlendedMVG",tb,0.414)):
    print(f"    以 {name} 为上限时每 epoch 总量 = {have/frac:,.0f} 组")
