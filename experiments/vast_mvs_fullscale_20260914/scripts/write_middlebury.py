#!/usr/bin/env python3
"""MVSNet cams/*_cam.txt -> Middlebury *_par.txt so the OFFICIAL aliceVision_importMiddlebury builds the SfMData
(views + per-image intrinsics + poses) instead of me hand-writing AliceVision's JSON schema.
Middlebury convention: one line per image `name K(9, row-major) R(9, row-major) t(3)` with x = K [R|t] X — the same
world-to-camera convention as the MVSNet extrinsic."""
import sys, glob, os, numpy as np
SRC, OUT = sys.argv[1], sys.argv[2]
cams = sorted(glob.glob(f"{SRC}/cams/*_cam.txt"))
lines = [str(len(cams))]
for p in cams:
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4)
    K = np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3)
    R, t = E[:3, :3], E[:3, 3]
    name = os.path.basename(p)[:8] + ".jpg"
    lines.append(" ".join([name] + ["%.10g" % v for v in list(K.ravel()) + list(R.ravel()) + list(t)]))
open(OUT, "w").write("\n".join(lines) + "\n")
print("wrote", OUT, len(cams), "cameras; first line:", lines[1][:110])
