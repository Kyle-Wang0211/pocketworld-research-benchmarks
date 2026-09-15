#!/usr/bin/env python3.11
"""Math-free packer for the on-device dense chain bench. Copies: session pack, the photos the run needs
(refs a..b, their sources, and their sources' sources — read from fx_official/neighbors.i32, which the C++
session table reproduces byte-for-byte), the reference run's noise (npz n2/n3 -> NF blocks) and depths (NF×H×W)."""
import os, shutil, sys, numpy as np
CAP, FX, REF, SP, OUT = sys.argv[1:6]; a, b = [int(x) for x in sys.argv[6].split("-")]
NF, W, H, NS = 97, 768, 576, 9
nb = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, NS)
names = [l.strip() for l in open(f"{SP}/names.txt") if l.strip()]
infer = set(range(a, b + 1)) | {int(s) for f in range(a, b + 1) for s in nb[f]}
imgs = set(infer) | {int(s) for v in infer for s in nb[v]}
os.makedirs(f"{OUT}/photos", exist_ok=True); os.makedirs(f"{OUT}/session_pack", exist_ok=True)
for f in ("frames.f64", "points.f32", "names.txt"): shutil.copy(f"{SP}/{f}", f"{OUT}/session_pack/{f}")
for v in sorted(imgs): shutil.copy(f"{CAP}/photos_jpg/{names[v]}", f"{OUT}/photos/{names[v]}")
n2, n3 = (H // 4) * (W // 4), (H // 2) * (W // 2)
noise = np.zeros((NF, n2 + n3), np.float32); depth = np.zeros((NF, H * W), np.float32)
for v in sorted(infer):
    z = np.load(f"{REF}/noise/{v:04d}.npz"); noise[v, :n2] = z["n2"].reshape(-1); noise[v, n2:] = z["n3"].reshape(-1)
    depth[v] = np.load(f"{REF}/depth/{v:04d}.npy").astype(np.float32).reshape(-1)
noise.tofile(f"{OUT}/noise.f32"); depth.tofile(f"{OUT}/refdepth.f32")
sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
print(f"refs {a}-{b}: infer {len(infer)} views, photos {len(imgs)}, bundle {sz/1e6:.0f} MB -> {OUT}")
