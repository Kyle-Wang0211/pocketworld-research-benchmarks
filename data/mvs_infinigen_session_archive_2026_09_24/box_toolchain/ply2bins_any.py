#!/usr/bin/env python3
"""PLY (any float type for x,y,z; optional normals; uchar red/green/blue) -> verdict-page .pos/.col, flipped into the
display frame exactly as /root/ply2bins.py does (y,z negated). Parser = plyfile (the official PLY reader), not a hand-rolled
struct layout, because Open3D's writer emits `property double x` + nx/ny/nz which broke ply2bins' fixed x,y,z,r,g,b dtype."""
import sys, os, numpy as np
from plyfile import PlyData
SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
v = PlyData.read(SRC)["vertex"]
P = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float32)
C = np.stack([v["red"], v["green"], v["blue"]], 1).astype(np.uint8)
n = len(P); assert n == v.count
print(f"{n:,} 点  COLMAP帧中位 {np.round(np.median(P, 0), 3).tolist()}  (props: {[p.name for p in v.properties]})")
P[:, 1] *= -1; P[:, 2] *= -1
print(f"展示帧中位 {np.median(P, 0).tolist()}   写出 {OUT}/{TAG}")
P.tofile(os.path.join(OUT, TAG + ".pos")); C.tofile(os.path.join(OUT, TAG + ".col"))
assert os.path.getsize(os.path.join(OUT, TAG + ".pos")) == n * 12 and os.path.getsize(os.path.join(OUT, TAG + ".col")) == n * 3
