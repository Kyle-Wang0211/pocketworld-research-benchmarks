#!/usr/bin/env python3
"""Fuse region-merge depth maps (SfM prior + monocular completion) with the SAME official gate every other
engine got: CasDiffMVS filter.py check_geometric_consistency, >=3 views, 1 px reprojection, 1% relative depth.
Only the depth source changes."""
import sys, os, glob, numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency

DEPTH_DIR = sys.argv[1]          # dir of {stem}.npy depth maps
OUT       = sys.argv[2]
CAM_DIR   = os.environ.get("CAM_DIR", "/root/regionmerge/sfm768")
RGB_DIR   = os.environ.get("RGB_DIR", "/root/regionmerge/rgb768")
PAIR_TXT  = os.environ.get("PAIR_TXT", "/root/mvs_P16k/pair.txt")
DMIN      = float(os.environ.get("DEPTH_MIN", "0.5"))
DMAX      = float(os.environ.get("DEPTH_MAX", "30.0"))
NVIEW     = int(os.environ.get("NVIEW", "3"))

def read_cam(i):
    K = np.loadtxt(f"{CAM_DIR}/intrinsic/{i:08d}.txt").astype(np.float32)
    E = np.loadtxt(f"{CAM_DIR}/pose/{i:08d}.txt").astype(np.float32)
    return E, K

lines = [l.strip() for l in open(PAIR_TXT) if l.strip()]
n = int(lines[0]); pairs = []; i = 1
for _ in range(n):
    ref = int(lines[i]); t = lines[i+1].split(); m = int(t[0])
    pairs.append((ref, [int(t[1+2*j]) for j in range(m)][:10])); i += 2

D = {}
for f in glob.glob(f"{DEPTH_DIR}/*.npy"):
    D[int(os.path.basename(f)[:8])] = np.load(f).astype(np.float32)
print("loaded", len(D), "depth maps", flush=True)

V = []; C = []
for ref, srcs in pairs:
    if ref not in D: continue
    Er, Kr = read_cam(ref)
    dref = D[ref]; gsum = 0; rsum = 0
    img = cv2.imread(f"{RGB_DIR}/{ref:08d}.jpg")[:, :, ::-1].astype(np.float32) / 255.0
    if img.shape[:2] != dref.shape:
        img = cv2.resize(img, (dref.shape[1], dref.shape[0]), interpolation=cv2.INTER_AREA)
    for s in srcs:
        if s not in D: continue
        Es, Ks = read_cam(s)
        gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, D[s], Ks, Es, DMAX, DMIN, 1.0, 0.01)
        gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
    davg = (rsum + dref) / (gsum + 1)
    keep = (gsum >= NVIEW) & (dref > 0)
    h, w = dref.shape; x, y = np.meshgrid(np.arange(w), np.arange(h))
    x, y, d = x[keep], y[keep], davg[keep]
    xyz = np.linalg.inv(Kr) @ (np.vstack((x, y, np.ones_like(x))) * d)
    V.append((np.linalg.inv(Er) @ np.vstack((xyz, np.ones_like(x))))[:3].T.astype(np.float32))
    C.append((img[keep] * 255).astype(np.uint8))
    if ref % 40 == 0: print(f"  ref {ref} keep {keep.mean():.3f}", flush=True)
V = np.concatenate(V); C = np.concatenate(C)
print("fused", len(V), "points", flush=True)
with open(OUT, "wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % len(V)).encode())
    r = np.zeros(len(V), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    r["x"],r["y"],r["z"] = V[:,0],V[:,1],V[:,2]; r["r"],r["g"],r["b"] = C[:,0],C[:,1],C[:,2]; r.tofile(f)
print("wrote", OUT, flush=True)
