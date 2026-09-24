# texrecon (MVE) scene for the 132 full-res photos: <name>.jpg symlink + <name>.cam, cameras = /root/mvs_P16k/cams
# (the same cameras that fused the depth; full-res 4032x3024 intrinsics). MVE .cam format (mvs-texturing README):
#   line 1: tx ty tz R00 R01 R02 R10 R11 R12 R20 R21 R22   (world -> camera)
#   line 2: f d0 d1 paspect ppx ppy                          (f = fx / max(W, H), ppx/ppy normalised, paspect = fy / fx)
# Principal point convention as validated on 2026-09-23 by a shift sweep (colour error minimum at 0 +- 1 px):
#   ppx = (cx + 0.5) / W, ppy = (cy + 0.5) / H.
import os, sys
import numpy as np

SRC, OUT, W, H = "/root/mvs_P16k", "/root/tsdf_improve/tex_A/scene", 4032, 3024
os.makedirs(OUT, exist_ok=True)
names = sorted(f[:-4] for f in os.listdir(f"{SRC}/images") if f.endswith(".jpg"))
for n in names:
    L = open(f"{SRC}/cams/{n}_cam.txt").read().split()
    E = np.array(L[1:17], float).reshape(4, 4)
    K = np.array(L[18:27], float).reshape(3, 3)
    R, t = E[:3, :3], E[:3, 3]
    f = K[0, 0] / max(W, H)
    ppx, ppy = (K[0, 2] + 0.5) / W, (K[1, 2] + 0.5) / H
    with open(f"{OUT}/{n}.cam", "w") as fo:
        fo.write(" ".join(f"{v:.17g}" for v in list(t) + list(R.ravel())) + "\n")
        fo.write(" ".join(f"{v:.17g}" for v in (f, 0.0, 0.0, K[1, 1] / K[0, 0], ppx, ppy)) + "\n")
    dst = f"{OUT}/{n}.jpg"
    if not os.path.lexists(dst):
        os.symlink(f"{SRC}/images/{n}.jpg", dst)
print(f"{len(names)} views -> {OUT}; first cam:")
print(open(f"{OUT}/{names[0]}.cam").read())
