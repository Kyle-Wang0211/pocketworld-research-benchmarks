import os, glob
def count(root, label):
    scans = sorted(d for d in glob.glob(f"{root}/*") if os.path.exists(f"{d}/cams/pair.txt"))
    tot = 0
    for s in scans:
        with open(f"{s}/cams/pair.txt") as f:
            try: tot += int(f.readline())
            except Exception: pass
    print(f"  {label:<18} {len(scans):>5} scans | {tot:>9,} 组")
    return tot
a = count("/root/hs/blendfmt", "Hypersim")
b = count("/root/ta2/blendfmt", "TartanAir V2")
c = count("/root/bmvs/data/BlendedMVS", "BlendedMVS(113)")
t = a + b + c
if t:
    print(f"\n  当前自然比       Hypersim {a/t*100:5.1f}% | TartanAir {b/t*100:5.1f}% | BlendedMVS {c/t*100:5.1f}%")
print(f"  MVSAnywhere 商用子集  Hypersim  19.3% | TartanAir  39.3% | BlendedMVG  41.4%")
