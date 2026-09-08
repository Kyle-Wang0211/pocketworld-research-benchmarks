#!/usr/bin/env python3
"""Back-project the already-gated per-view depths into one true-colour cloud.
No re-gating, no averaging, no downsampling: these are exactly the pixels that survived
each engine's official gate, at native depth-map resolution."""
import sys, os, glob, numpy as np, cv2
SRC, OUT = sys.argv[1], sys.argv[2]
V = []; C = []
for f in sorted(glob.glob(f"{SRC}/depth/*.npy")):
    i = int(os.path.basename(f)[:8])
    d = np.load(f); z = np.load(f"{SRC}/cam/{i:08d}.npz"); K = z["K"]; E = z["E"]
    img = cv2.imread(f"{SRC}/color/{i:08d}.png")[:, :, ::-1]
    keep = d > 0
    h, w = d.shape; x, y = np.meshgrid(np.arange(w), np.arange(h))
    x, y, dd = x[keep], y[keep], d[keep]
    xyz = np.linalg.inv(K) @ (np.vstack((x, y, np.ones_like(x))) * dd)
    V.append((np.linalg.inv(E) @ np.vstack((xyz, np.ones_like(x))))[:3].T.astype(np.float32))
    C.append(img[keep].astype(np.uint8))
V = np.concatenate(V); C = np.concatenate(C)
print("points", len(V), flush=True)
with open(OUT, "wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % len(V)).encode())
    r = np.zeros(len(V), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    r["x"],r["y"],r["z"] = V[:,0],V[:,1],V[:,2]; r["r"],r["g"],r["b"] = C[:,0],C[:,1],C[:,2]; r.tofile(f)
print("wrote", OUT, flush=True)
