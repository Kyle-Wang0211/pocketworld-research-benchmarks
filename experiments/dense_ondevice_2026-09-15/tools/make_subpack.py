#!/usr/bin/env python3.11
"""Sub-pack for the on-device run: reference frames 0..n-1 plus every source view they need, indices remapped.
Per-frame results are independent, so the sub-pack's outputs for those frames must equal the full pack's bit-for-bit."""
import sys, os, numpy as np
SRC, DST, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
NF, W, H, NS = [int(x) for x in open(f"{SRC}/meta.txt").read().split()[:4]]
rest = open(f"{SRC}/meta.txt").read().split()[4:]
NB = np.fromfile(f"{SRC}/neighbors.i32", np.int32).reshape(NF, NS)
uniq = sorted({f for f in range(n)} | {int(s) for f in range(n) for s in NB[f]})
idx = {g: i for i, g in enumerate(uniq)}; assert [idx[f] for f in range(n)] == list(range(n)), "ref frames must keep indices 0..n-1"
NF2 = len(uniq); os.makedirs(DST, exist_ok=True)
N = W * H
for name, elem in (("depth.f32", 4), ("conf0.f32", 4), ("conf1.f32", 4), ("conf2.f32", 4)):
    a = np.memmap(f"{SRC}/{name}", np.float32, "r", shape=(NF, N)); a[uniq].tofile(f"{DST}/{name}")
rgb = np.memmap(f"{SRC}/rgb.u8", np.uint8, "r", shape=(NF, N * 3)); rgb[uniq].tofile(f"{DST}/rgb.u8")
cams = np.fromfile(f"{SRC}/cams.f32", np.float32).reshape(NF, 36); cams[uniq].tofile(f"{DST}/cams.f32")
nb2 = np.zeros((NF2, NS), np.int32)
for f in range(n): nb2[f] = [idx[int(s)] for s in NB[f]]
nb2.tofile(f"{DST}/neighbors.i32")
open(f"{DST}/meta.txt", "w").write(" ".join([str(NF2), str(W), str(H), str(NS)] + rest) + "\n")
sz = sum(os.path.getsize(f"{DST}/{x}") for x in os.listdir(DST))
print(f"subpack: {n} ref frames, {NF2} unique views, {sz/1e6:.0f} MB -> {DST}")
