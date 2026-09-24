#!/usr/bin/env python3
"""Geometry three metrics ONLY (the double-layer number comes from /root/layer2.py, not here).
  geo3.py <mesh> <name>
reports: total area m2, longest-edge median/p95/max in mm, and the fraction of triangles
needed to cover 50% of the total area."""
import sys, numpy as np, open3d as o3d
P, NAME = sys.argv[1], sys.argv[2]
me = o3d.io.read_triangle_mesh(P)
V = np.asarray(me.vertices); T = np.asarray(me.triangles)
a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
ar = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
tot = ar.sum()
e = np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], 1).max(1) * 1000.0
srt = np.sort(ar)[::-1]; cs = np.cumsum(srt)
k = int(np.searchsorted(cs, 0.5 * tot) + 1)
print("%-22s area %7.3f m2 | longest-edge med %6.1f p95 %7.1f max %7.1f mm | tri for 50%% area %6.2f%% (%d/%d) | %dv %df"
      % (NAME, tot, np.median(e), np.percentile(e, 95), e.max(), 100.0 * k / len(T), k, len(T), len(V), len(T)))
