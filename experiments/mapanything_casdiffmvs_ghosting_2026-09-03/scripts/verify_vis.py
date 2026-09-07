#!/usr/bin/env python3
"""Positive control for the fused.ply.vis index mapping: for random points, take the image indices the .vis file
claims see them, project the point with THAT image's camera, and check it lands in frame near the stored depth.
A correct mapping gives a high in-frame + depth-agreement rate; an off-by-one or shuffled mapping gives chance."""
import sys, struct, glob, numpy as np, os
WS = sys.argv[1]; SRC = sys.argv[2]
# read fused.ply (x y z nx ny nz r g b)
with open(f"{WS}/fused.ply","rb") as f:
    hdr = b""
    while b"end_header" not in hdr: hdr += f.readline()
    n = int([l for l in hdr.split(b"\n") if l.startswith(b"element vertex")][0].split()[-1])
    rec = np.fromfile(f, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("nx","<f4"),("ny","<f4"),("nz","<f4"),("r","u1"),("g","u1"),("b","u1")], count=n)
P = np.stack([rec["x"],rec["y"],rec["z"]],1).astype(np.float64)
b = open(f"{WS}/fused.ply.vis","rb").read(); N = int(np.frombuffer(b[:8],"<u8")[0]); a = np.frombuffer(b[8:],"<u4")
assert N == n, (N, n)
# per-point visibility lists
starts = np.empty(N, np.int64); cnts = np.empty(N, np.int64); off = 0
for k in range(N):
    cnts[k] = a[off]; starts[k] = off+1; off += 1+cnts[k]
def read_cam(i):
    L=[l.rstrip() for l in open(f"{SRC}/cams/{i:08d}_cam.txt")]
    return np.fromstring(" ".join(L[1:5]),sep=" ").reshape(4,4), np.fromstring(" ".join(L[7:10]),sep=" ").reshape(3,3)
def read_pfm(p):
    with open(p,"rb") as f:
        f.readline(); w,h=map(int,f.readline().split()); s=float(f.readline())
        d=np.fromfile(f,"<f4" if s<0 else ">f4").reshape(h,w)
    return np.flipud(d)
cams = {i: read_cam(i) for i in range(132)}
deps = {i: read_pfm(f"{SRC}/depth_est/{i:08d}.pfm") for i in range(132)}
rng = np.random.default_rng(0); idx = rng.choice(N, 20000, replace=False)
for shift in (0, 1, -1):
    inframe = 0; agree = 0; tot = 0
    for k in idx:
        ids = a[starts[k]:starts[k]+cnts[k]]
        for v in ids:
            vi = int(v) + shift
            if not (0 <= vi < 132): continue
            E, K = cams[vi]; X = E @ np.append(P[k], 1.0); z = X[2]
            if z <= 0: tot += 1; continue
            u = K[0,0]*X[0]/z + K[0,2]; vv = K[1,1]*X[1]/z + K[1,2]
            tot += 1
            if 0 <= u < 767 and 0 <= vv < 575:
                inframe += 1
                d = deps[vi][int(round(vv)), int(round(u))]
                if d > 0 and abs(d - z)/z < 0.02: agree += 1
    print(f"shift {shift:+d}: in-frame {inframe/tot:.3f}  depth-agree {agree/tot:.3f}  (n={tot})", flush=True)
