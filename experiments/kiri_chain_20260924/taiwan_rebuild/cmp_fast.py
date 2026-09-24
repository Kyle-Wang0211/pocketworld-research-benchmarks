# Fast point-cloud agreement: quantize xyz to a grid cell of size s, count points whose cell also holds a point of the
# other cloud (sorted-key membership, no KD-tree). Cell-boundary effects make this a slight under-count; it is only
# used to put several clouds (old box runs vs new box runs) on the same footing.
import sys, numpy as np
from plyfile import PlyData

def load(p):
    if p.endswith(".pos"):
        # page bins store the cloud in the viewer frame: y and z negated (OpenCV -> OpenGL); undo it
        return np.fromfile(p, "<f4").reshape(-1, 3).astype(np.float64) * np.array([1.0, -1.0, -1.0])
    v = PlyData.read(p)["vertex"]
    return np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)

def keys(P, s):
    q = np.floor(P / s).astype(np.int64) + (1 << 20)
    return (q[:, 0] << 42) | (q[:, 1] << 21) | q[:, 2]

names = sys.argv[1:]
C = {n: load(n) for n in names}
for n in names:
    print(f"{n}: {len(C[n]):,}", flush=True)
for s in (1e-4, 1e-3):
    K = {n: np.unique(keys(C[n], s)) for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ka = keys(C[a], s)
            hit = np.isin(ka, K[b], assume_unique=False)
            print(f"cell {s*1e3:g} mm: {a.split('/')[-2] if '/' in a else a} points with a {b.split('/')[-2]} point in the same cell: {hit.mean()*100:.3f}%  (miss {np.sum(~hit):,})", flush=True)
