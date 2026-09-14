import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
D = "/root/out_official"
res = {c: {"w": [], "r": []} for c in ("conf0", "conf1", "conf2")}
frac = []
for f in sorted(glob.glob(f"{D}/depth_est/*.pfm")):
    i = int(os.path.basename(f)[:8])
    d = np.array(read_pfm(f)[0], dtype=np.float32)
    img = cv2.resize(cv2.imread(f"{D}/images/{i:08d}.jpg"), (d.shape[1], d.shape[0]), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    wall = (g > 150) & (np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3)) < 4) & (d > 0)
    rest = (~wall) & (d > 0)
    frac.append(wall.mean())
    for c in res:
        p = f"{D}/{c}/{i:08d}.pfm"
        if not os.path.exists(p): continue
        v = np.array(read_pfm(p)[0], dtype=np.float32)
        if v.shape != d.shape:
            v = cv2.resize(v, (d.shape[1], d.shape[0]), interpolation=cv2.INTER_LINEAR)
        if wall.sum() > 500: res[c]["w"].append(float(np.median(v[wall])))
        if rest.sum() > 500: res[c]["r"].append(float(np.median(v[rest])))
print(f"132 帧, 白墙像素平均占 {np.mean(frac)*100:.1f}%\n")
print(f"{'置信度':>7} {'白墙中位':>9} {'非白墙中位':>11} {'差距':>8}")
for c in ("conf0", "conf1", "conf2"):
    if not res[c]["w"]: print(f"{c:>7}  (无数据)"); continue
    a, b = np.mean(res[c]["w"]), np.mean(res[c]["r"])
    print(f"{c:>7} {a:>9.4f} {b:>11.4f} {b-a:>8.4f}")
# 若某档能分开, 看按分位切能切多干净
best = "conf2"
for c in ("conf0","conf1","conf2"):
    if res[c]["w"] and (np.mean(res[c]["r"]) - np.mean(res[c]["w"])) > (np.mean(res[best]["r"]) - np.mean(res[best]["w"])):
        best = c
print(f"\n差距最大的是 {best}, 按阈值扫:")
W, R = [], []
for f in sorted(glob.glob(f"{D}/depth_est/*.pfm")):
    i = int(os.path.basename(f)[:8])
    d = np.array(read_pfm(f)[0], dtype=np.float32)
    p = f"{D}/{best}/{i:08d}.pfm"
    if not os.path.exists(p): continue
    v = np.array(read_pfm(p)[0], dtype=np.float32)
    if v.shape != d.shape: v = cv2.resize(v, (d.shape[1], d.shape[0]), interpolation=cv2.INTER_LINEAR)
    img = cv2.resize(cv2.imread(f"{D}/images/{i:08d}.jpg"), (d.shape[1], d.shape[0]), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    wall = (g > 150) & (np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3)) < 4) & (d > 0)
    rest = (~wall) & (d > 0)
    W.append(v[wall]); R.append(v[rest])
W = np.concatenate(W); R = np.concatenate(R)
print(f"{'阈值':>6} {'白墙存活':>9} {'非白墙存活':>11} {'比值':>8}")
for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
    a, b = (W >= t).mean(), (R >= t).mean()
    print(f"{t:>6.1f} {a*100:>8.1f}% {b*100:>10.1f}% {a/max(b,1e-9):>8.3f}")
