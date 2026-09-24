#!/usr/bin/env python3
"""Order-insensitive exact comparison of two point PLYs (xyz + rgb): sorted rows must be identical."""
import sys, numpy as np
from plyfile import PlyData
def rows(p):
    v = PlyData.read(p)["vertex"]
    a = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64); c = np.stack([v["red"], v["green"], v["blue"]], 1).astype(np.float64)
    r = np.concatenate([a, c], 1); return r[np.lexsort(r.T[::-1])]
A, B = rows(sys.argv[1]), rows(sys.argv[2])
print(f"A {len(A):,} rows  B {len(B):,} rows")
if A.shape != B.shape: print("DIFFERENT (row count)"); sys.exit(1)
eq = np.array_equal(A, B); print("IDENTICAL (sorted rows)" if eq else f"DIFFERENT: {int((A != B).any(1).sum()):,} rows differ"); sys.exit(0 if eq else 1)
