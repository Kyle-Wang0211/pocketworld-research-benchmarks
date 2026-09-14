#!/usr/bin/env python3.11
"""Graph-cut mesh -> point cloud at the official CasDiffMVS point count, colours from the nearest official (merged) point.
Sampled points farther than FILL_DIST from any input point lie on interpolated (hole-filling) triangles and are
counted (statistic only, NOT recoloured; user wants original colours). Writes viewer bins (ply2bin
convention: x,-y,-z baked; meta n/center/ext/med/radius)."""
import sys, json, numpy as np, open3d as o3d
from scipy.spatial import cKDTree
from pathlib import Path
MESH, WSDIR, OUTBIN, TAG, N = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5])
FILL_DIST = float(sys.argv[6]) if len(sys.argv) > 6 else 0.02
m = o3d.io.read_triangle_mesh(MESH); print("mesh: %d vertices, %d triangles" % (len(m.vertices), len(m.triangles)), flush=True)
m.remove_degenerate_triangles(); m.remove_duplicated_vertices(); m.remove_unreferenced_vertices()
tri = np.asarray(m.triangles); V = np.asarray(m.vertices)
# triangle area stats: mesh from Delaunay graph-cut may contain huge triangles bridging holes
a = np.linalg.norm(np.cross(V[tri[:,1]]-V[tri[:,0]], V[tri[:,2]]-V[tri[:,0]]), axis=1)/2
print("triangle area p50 %.2e p99 %.2e max %.2e m^2; total %.2f m^2" % (np.median(a), np.percentile(a,99), a.max(), a.sum()), flush=True)
pc = m.sample_points_uniformly(number_of_points=N, use_triangle_normal=False)
P = np.asarray(pc.points).astype(np.float32); print("sampled", len(P), flush=True)
ref = np.load(WSDIR/"merged_xyz.npy"); rgb = np.load(WSDIR/"merged_rgb.npy")
d, idx = cKDTree(ref).query(P, k=1, workers=-1)
col = rgb[idx].astype(np.uint8); fill = d > FILL_DIST   # statistic only; colours stay original (user: no marking)
print("fill points (>%.0f mm from any observed point): %.2f%%" % (FILL_DIST*1000, fill.mean()*100), flush=True)
OUTBIN.mkdir(parents=True, exist_ok=True)
pos = P.copy(); pos[:,1] *= -1; pos[:,2] *= -1; pos = np.ascontiguousarray(pos.astype("<f4")); pos.tofile(OUTBIN/f"{TAG}.pos"); np.ascontiguousarray(col).tofile(OUTBIN/f"{TAG}.col")
lo, hi = np.percentile(pos, 1, 0), np.percentile(pos, 99, 0); med = np.median(pos, 0); rad = float(np.percentile(np.linalg.norm(pos-med, axis=1), 95))
json.dump({TAG: {"n": int(len(pos)), "center": ((lo+hi)/2).tolist(), "ext": (hi-lo).tolist(), "med": med.astype(float).tolist(), "radius": rad}}, open(OUTBIN/f"meta_{TAG}.json", "w"))
print("wrote", TAG, len(pos), "med", np.round(med,3).tolist(), flush=True)
