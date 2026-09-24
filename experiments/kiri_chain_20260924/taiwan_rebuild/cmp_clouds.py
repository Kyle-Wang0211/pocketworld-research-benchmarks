# Compare two fused CasDiffMVS clouds point by point (same cameras, same frame): how many points coincide, how many
# exist only in one of them. Used to judge a rebuild on another box against the old box's ep0 cloud.
import sys, numpy as np
from plyfile import PlyData
from scipy.spatial import cKDTree

def load(p):
    if p.endswith(".pos"):
        return np.fromfile(p, "<f4").reshape(-1, 3)
    v = PlyData.read(p)["vertex"]
    return np.stack([v["x"], v["y"], v["z"]], 1).astype("<f4")

A, B = load(sys.argv[1]), load(sys.argv[2])
print(f"A {sys.argv[1]}: {len(A):,}\nB {sys.argv[2]}: {len(B):,}  (B-A = {len(B)-len(A):+,})", flush=True)
for name, P, Q in (("B->A", B, A), ("A->B", A, B)):
    d, _ = cKDTree(Q).query(P, k=1, workers=32)
    tot = len(P)
    row = [f"{name}: exact(0) {np.sum(d == 0):,}"]
    for t in (1e-6, 1e-5, 1e-4, 1e-3, 1e-2):
        row.append(f"<{t:g} {np.sum(d < t)/tot*100:.4f}%")
    row.append(f"no partner within 1 mm: {np.sum(d >= 1e-3):,}  (p50 of those {np.median(d[d >= 1e-3])*1e3 if np.any(d >= 1e-3) else 0:.1f} mm)")
    print("  ".join(row), flush=True)
