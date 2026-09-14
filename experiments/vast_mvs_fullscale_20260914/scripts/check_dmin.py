import os, glob, numpy as np
ROOT = "/root/monotrain"
names = [l.strip() for l in open("/root/MonoMVSNet/lists/ours/train.txt") if l.strip()]
bad = []
rows = []
for s in names:
    cams = sorted(glob.glob(f"{ROOT}/{s}/cams/*_cam.txt"))
    if not cams: continue
    dmins = []
    for c in cams[:200]:
        try:
            L = open(c).read().rstrip("\n").split("\n")
            p = L[-1].split()
            dmins.append(float(p[0]))
        except Exception: pass
    if not dmins: continue
    lo = min(dmins)
    rows.append((lo, s, len(cams)))
rows.sort()
print(f"{len(rows)} 个 scan 的最小 dmin 分布:")
a = np.array([r[0] for r in rows])
for q in (0, 1, 5, 50, 95, 100):
    print(f"   p{q:<3} {np.percentile(a,q):.6f} m   -> scale = 100/dmin = {100/max(np.percentile(a,q),1e-9):,.0f}")
print("\n最危险的 12 个 scan(dmin 最小 => scale 最大):")
for lo, s, n in rows[:12]:
    src = "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
    print(f"   {s:<44} {src:<11} dmin {lo:.6f}  scale {100/max(lo,1e-9):>12,.0f}")
