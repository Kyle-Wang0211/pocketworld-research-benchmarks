#!/usr/bin/env python3
"""Fuse COLMAP's classical PatchMatch depth maps with the SAME gate CasDiffMVS got (official filter.py's
check_geometric_consistency: >=3 views, 1 px reprojection, 1% relative depth, depth averaged). COLMAP has already
applied its own photometric/geometric filtering inside patch_match_stereo, so there is no separate photo mask here.
Result: the only remaining difference from the CasDiffMVS cloud is the depth algorithm itself."""
import sys, os, glob, numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency
WS, SRC, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
def read_colmap_map(p):
    b = open(p, "rb").read(); i = 0; h = []
    for _ in range(3):
        j = b.index(b"&", i); h.append(int(b[i:j])); i = j + 1
    w, hh, c = h
    return np.frombuffer(b[i:], "<f4").reshape(c, hh, w)[0].astype(np.float32)
DMW = None   # depth-map width, set after the first map is read; K is rescaled to it
def read_cam(i):
    L = [l.rstrip() for l in open(f"{SRC}/cams/{i:08d}_cam.txt")]
    E = np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4)
    K = np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3)
    if DMW is not None:
        s = DMW / float(CAMW); K = K.copy(); K[0, :] *= s; K[1, :] *= s
    return (E, K, *[float(x) for x in L[11].split()[:2]])
lines = [l.strip() for l in open(os.environ.get("PAIR_TXT", f"{SRC}/../mvs_P16k/pair.txt")) if l.strip()]
n = int(lines[0]); pairs = []; i = 1
for _ in range(n):
    ref = int(lines[i]); t = lines[i+1].split(); m = int(t[0]); pairs.append((ref, [int(t[1+2*j]) for j in range(m)][:10])); i += 2
D = {}
for f in glob.glob(f"{WS}/stereo/depth_maps/*.geometric.bin"):
    D[int(os.path.basename(f)[:8])] = read_colmap_map(f)
CAMW = float(os.environ.get("CAM_WIDTH", "768"))
DMW = float(next(iter(D.values())).shape[1])
print(f"cam width {CAMW:.0f} -> depth-map width {DMW:.0f}; K scaled by {DMW/CAMW:.4f}", flush=True)
print("loaded", len(D), "COLMAP depth maps; valid frac mean %.3f" % np.mean([(d>0).mean() for d in D.values()]), flush=True)
V = []; C = []
for ref, srcs in pairs:
    if ref not in D: continue
    Er, Kr, dmax, dmin = read_cam(ref)
    dmin = float(os.environ.get("DEPTH_MIN", dmin)); dmax = float(os.environ.get("DEPTH_MAX", dmax))          # cam.txt line 11 is "depth_max depth_min" (CasDiffMVS convention)
    dref = D[ref]; dref_shape = dref.shape; gsum = 0; rsum = 0
    img = cv2.imread(f"{SRC}/images/{ref:08d}.jpg")[:, :, ::-1].astype(np.float32) / 255.0
    if img.shape[:2] != dref_shape: img = cv2.resize(img, (dref_shape[1], dref_shape[0]), interpolation=cv2.INTER_AREA)
    for s in srcs:
        if s not in D: continue
        Es, Ks = read_cam(s)[0], read_cam(s)[1]
        gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, D[s], Ks, Es, dmax, dmin, 1.0, 0.01)
        gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
    davg = (rsum + dref) / (gsum + 1)
    keep = (gsum >= 3) & (dref > 0)
    h, w = dref.shape; x, y = np.meshgrid(np.arange(w), np.arange(h))
    x, y, d = x[keep], y[keep], davg[keep]
    xyz = np.linalg.inv(Kr) @ (np.vstack((x, y, np.ones_like(x))) * d)
    V.append((np.linalg.inv(Er) @ np.vstack((xyz, np.ones_like(x))))[:3].T.astype(np.float32))
    C.append((img[keep] * 255).astype(np.uint8))
    if ref % 40 == 0: print(f"  ref {ref} keep {keep.mean():.3f}", flush=True)
V = np.concatenate(V); C = np.concatenate(C)
print("fused", len(V), "points", flush=True)
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % len(V)).encode())
    r = np.zeros(len(V), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    r["x"],r["y"],r["z"] = V[:,0],V[:,1],V[:,2]; r["r"],r["g"],r["b"] = C[:,0],C[:,1],C[:,2]; r.tofile(f)
print("wrote", OUT, flush=True)
