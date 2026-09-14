import os, glob, numpy as np, collections
ROOT = "/root/monotrain"
names = [l.strip() for l in open("/root/MonoMVSNet/lists/ours/train.txt") if l.strip()]
by = collections.defaultdict(list)
for s in names:
    src = "Hypersim" if s.startswith("hs_") else ("TartanAir" if s.startswith("ta_") else "BlendedMVG")
    for c in sorted(glob.glob(f"{ROOT}/{s}/cams/*_cam.txt"))[:60]:
        try:
            L = open(c).read().rstrip("\n").split("\n"); p = L[-1].split()
            lo, hi = float(p[0]), float(p[-1])
            if hi > lo > 0: by[src].append(hi / lo)
        except Exception: pass
print(f"{'来源':<12} {'样本':>7} {'比值 p50':>9} {'p90':>9} {'p99':>10} {'max':>12}")
for k in ("BlendedMVG", "Hypersim", "TartanAir"):
    a = np.array(by[k])
    if not len(a): continue
    print(f"{k:<12} {len(a):>7,} {np.median(a):>9.2f} {np.percentile(a,90):>9.2f} {np.percentile(a,99):>10.2f} {a.max():>12.1f}")
print("\n384 个深度假设下, 比值越大每档覆盖的相对深度越粗:")
for k in ("BlendedMVG", "Hypersim", "TartanAir"):
    a = np.array(by[k])
    if not len(a): continue
    # 反深度均匀采样时, 每档的相对分辨率 ~ (1 - 1/ratio)/384
    print(f"  {k:<12} p50 比值 {np.median(a):6.2f}  => 反深度空间每档跨 {(1-1/np.median(a))/384*100:.4f}% 的视差全程")
