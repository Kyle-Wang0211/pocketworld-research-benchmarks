"""Offline capture-review probe on the real 317-frame set: per-frame blur,
overexposure, and DiffMVS conf-median (from the pass-1 cache). Question: would a
simple blur/overexposure gate flag the frames that produce bad depth (low conf)?
If flagged frames cluster at low conf -> the review metric works upstream.
"""
import numpy as np
import cv2
import pw_diffmvs_run as R

cache = R.OUT / "p1cache_diffmvs.npz"
z = np.load(cache, allow_pickle=True)
conf = z["conf"]; frames = z["frames"].tolist()
print(f"frames={len(frames)} (from pass-1 cache)\n", flush=True)

rows = []
for i, mi in enumerate(frames):
    rgb = (R.load_image(mi) * 255).astype(np.uint8)          # 512x896, what DiffMVS sees
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(g, cv2.CV_64F).var())          # low = blurry
    luma = g.astype(np.float32)
    overexp = float((luma > 245).mean()) * 100                # % saturated
    dark = float((luma < 12).mean()) * 100
    cmed = float(np.median(conf[i].astype(np.float32)))        # DiffMVS conf median (low = bad depth)
    rows.append((mi, blur, overexp, dark, cmed))

blur = np.array([r[1] for r in rows]); oe = np.array([r[2] for r in rows])
cmed = np.array([r[4] for r in rows])

def pct(a, p): return float(np.percentile(a, p))
print("metric distributions (p10 / p50 / p90):")
print(f"  blur(LapVar): {pct(blur,10):.0f} / {pct(blur,50):.0f} / {pct(blur,90):.0f}")
print(f"  overexp %:    {pct(oe,10):.1f} / {pct(oe,50):.1f} / {pct(oe,90):.1f}")
print(f"  conf median:  {pct(cmed,10):.2f} / {pct(cmed,50):.2f} / {pct(cmed,90):.2f}")

print(f"\ncorrelation with DiffMVS conf-median (does the metric predict bad depth?):")
print(f"  r(blur, conf)    = {np.corrcoef(blur, cmed)[0,1]:+.3f}  (want +: sharper->more confident)")
print(f"  r(overexp, conf) = {np.corrcoef(oe, cmed)[0,1]:+.3f}  (want -: more overexposed->less confident)")

# would a gate catch the worst-depth frames? take bottom-20% conf frames, see their blur/oe rank
order = np.argsort(cmed)
worst = order[:len(order)//5]               # bottom 20% by conf = worst depth
best = order[-len(order)//5:]
print(f"\nbottom-20%-conf frames (worst depth) vs top-20%:")
print(f"  median blur:    worst={np.median(blur[worst]):.0f}  vs best={np.median(blur[best]):.0f}")
print(f"  median overexp: worst={np.median(oe[worst]):.1f}%  vs best={np.median(oe[best]):.1f}%")

# example gate: blur < p20 OR overexp > p80
bt, ot = pct(blur, 20), pct(oe, 80)
flagged = (blur < bt) | (oe > ot)
print(f"\nexample gate [blur<{bt:.0f} OR overexp>{ot:.1f}%]: flags {flagged.sum()}/{len(rows)} frames "
      f"({100*flagged.mean():.0f}%)")
print(f"  flagged frames' median conf = {np.median(cmed[flagged]):.2f}  vs kept = {np.median(cmed[~flagged]):.2f}")

print("\nworst-8 by blur (mi, blur, overexp%, conf):")
for mi, b, o, d, c in sorted(rows, key=lambda r: r[1])[:8]:
    print(f"  mi={mi:3d} blur={b:6.0f} oe={o:4.1f}% conf={c:.2f}")
print("worst-6 by overexposure:")
for mi, b, o, d, c in sorted(rows, key=lambda r: -r[2])[:6]:
    print(f"  mi={mi:3d} oe={o:4.1f}% blur={b:6.0f} conf={c:.2f}")
