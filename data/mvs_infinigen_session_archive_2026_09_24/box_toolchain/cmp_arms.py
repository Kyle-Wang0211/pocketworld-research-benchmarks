import numpy as np, cv2, glob, os, datetime
for A in ("av_ep0", "av_ep0_hi"):
    d = f"/root/{A}/out_native"
    ms = sorted(glob.glob(f"{d}/mask/*_final.png"))
    fr = []
    for p in ms[:8]:
        m = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        fr.append((round(float((m > 0).mean()), 3), m.shape))
    tot = 0
    for p in ms:
        tot += int((cv2.imread(p, cv2.IMREAD_GRAYSCALE) > 0).sum())
    with open(f"{d}/depth_est/00000000.pfm", "rb") as f:
        f.readline(); size = f.readline().decode().strip()
    print(f"{A}: {len(ms)} masks {fr[0][1]}, depth {size}, total valid mask px {tot:,}")
    print(f"   per-view valid frac (first 8): {[x for x, _ in fr]}")
    print(f"   depth mtime {datetime.datetime.fromtimestamp(os.path.getmtime(d+'/depth_est/00000000.pfm')):%H:%M}"
          f"  mask mtime {datetime.datetime.fromtimestamp(os.path.getmtime(ms[0])):%H:%M}")
