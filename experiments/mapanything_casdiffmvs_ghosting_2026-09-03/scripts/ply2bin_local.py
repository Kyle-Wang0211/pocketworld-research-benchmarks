#!/usr/bin/env python3
"""PLY -> viewer bins (same convention as everything else: x,-y,-z baked; meta n/center/ext/med/radius)."""
import sys, json, os, numpy as np, open3d as o3d
SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
pc = o3d.io.read_point_cloud(SRC)
P = np.asarray(pc.points).astype(np.float32); C = (np.asarray(pc.colors) * 255).astype(np.uint8)
pos = P.copy(); pos[:, 1] *= -1; pos[:, 2] *= -1; pos = np.ascontiguousarray(pos.astype("<f4"))
pos.tofile(f"{OUT}/{TAG}.pos"); np.ascontiguousarray(C).tofile(f"{OUT}/{TAG}.col")
lo, hi = np.percentile(pos, 1, 0), np.percentile(pos, 99, 0); med = np.median(pos, 0)
json.dump({TAG: {"n": int(len(pos)), "center": ((lo + hi) / 2).tolist(), "ext": (hi - lo).tolist(),
                 "med": med.astype(float).tolist(),
                 "radius": float(np.percentile(np.linalg.norm(pos - med, axis=1), 95))}},
          open(f"{OUT}/meta_{TAG}.json", "w"))
print("wrote", TAG, len(pos), "med", np.round(med, 3).tolist(), flush=True)
