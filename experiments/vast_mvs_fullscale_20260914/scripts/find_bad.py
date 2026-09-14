import os, sys, glob, numpy as np
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
ROOT = "/root/monotrain"
names = [l.strip() for l in open("/root/MonoMVSNet/lists/ours/train.txt") if l.strip()]
bad = []
for si, s in enumerate(names):
    for c in sorted(glob.glob(f"{ROOT}/{s}/cams/*_cam.txt")):
        idx = os.path.basename(c).split("_")[0]
        p = f"{ROOT}/{s}/rendered_depth_maps/{idx}.pfm"
        if not os.path.exists(p): bad.append((s, idx, "缺 pfm", 0, 0, 0)); continue
        L = open(c).read().rstrip("\n").split("\n"); a = L[-1].split()
        lo, hi = float(a[0]), float(a[-1])
        d = np.array(read_pfm(p)[0], dtype=np.float32)
        n = int(((d >= lo) & (d <= hi)).sum())
        if n == 0: bad.append((s, idx, "掩码为空", lo, hi, float(np.nanmax(d))))
    if si % 200 == 0: print(f"  ...{si}/{len(names)} 已发现 {len(bad)}", flush=True)
print(f"\n有问题的帧 {len(bad)} 个:")
for b in bad[:15]: print("  ", b)
