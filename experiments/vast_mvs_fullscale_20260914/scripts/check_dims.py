import os, glob, collections
from PIL import Image
ROOT = "/root/monotrain"
def bucket(s):
    return "TartanAir" if s.startswith("ta_") else ("Hypersim" if s.startswith("hs_") else "BlendedMVG")
dims = collections.defaultdict(collections.Counter)
dep = collections.defaultdict(collections.Counter)
import numpy as np, re, struct
def pfm_shape(p):
    with open(p, "rb") as f:
        f.readline(); wh = f.readline().split()
        return (int(wh[1]), int(wh[0]))
scans = sorted(os.listdir(ROOT))
per = collections.defaultdict(int)
for s in scans:
    b = bucket(s)
    if per[b] >= 40: continue          # 每桶抽 40 个 scan 足够暴露不一致
    g = sorted(glob.glob(f"{ROOT}/{s}/blended_images/*.jpg"))
    if not g: continue
    try: dims[b][Image.open(g[0]).size] += 1
    except Exception: continue
    d = sorted(glob.glob(f"{ROOT}/{s}/rendered_depth_maps/*.pfm"))
    if d:
        try: dep[b][pfm_shape(d[0])] += 1
        except Exception: pass
    per[b] += 1
for b in sorted(dims):
    print(f"{b}:")
    print("   图像 (W,H):", dict(dims[b]))
    print("   深度 (H,W):", dict(dep[b]))
