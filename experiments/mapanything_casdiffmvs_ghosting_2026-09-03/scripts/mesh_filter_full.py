#!/usr/bin/env python3
"""Graph-cut mesh as ARBITER, full-resolution official cloud as DELIVERABLE.

The Delaunay/graph-cut mesh says where the free space ends. Every one of the official CasDiffMVS fused points is
kept or deleted by its signed distance to that surface: points that lie in free space (outside the closed surface,
or farther than TOL from it) are the ghost/sticking mass; the rest are returned UNCHANGED at full resolution.
Nothing is resampled, interpolated or recoloured, so the delivered geometry is exactly the official one minus the
points visibility voting rejected.

  mesh_filter_full.py <mesh.ply> <official.ply> <out_bin_dir> <tag> [tol_m]
"""
import sys, json, numpy as np, open3d as o3d
MESH, CLOUD, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
TOL = float(sys.argv[5]) if len(sys.argv) > 5 else 0.01
from pathlib import Path
Path(OUT).mkdir(parents=True, exist_ok=True)
m = o3d.io.read_triangle_mesh(MESH)
m.remove_degenerate_triangles(); m.remove_duplicated_vertices(); m.remove_unreferenced_vertices()
print("mesh %d verts %d tris" % (len(m.vertices), len(m.triangles)), flush=True)
pc = o3d.io.read_point_cloud(CLOUD)
P = np.asarray(pc.points).astype(np.float32); C = (np.asarray(pc.colors) * 255).astype(np.uint8)
print("official cloud", len(P), flush=True)
scene = o3d.t.geometry.RaycastingScene()
scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m))
keep = np.zeros(len(P), bool); dist_all = np.empty(len(P), np.float32); occ_all = np.empty(len(P), np.float32)
CH = 2_000_000
for i in range(0, len(P), CH):
    q = o3d.core.Tensor(P[i:i+CH], dtype=o3d.core.Dtype.Float32)
    d = scene.compute_distance(q).numpy(); o = scene.compute_occupancy(q).numpy()
    dist_all[i:i+CH] = d; occ_all[i:i+CH] = o
    print("  %d/%d" % (min(i+CH, len(P)), len(P)), flush=True)
keep = (dist_all <= TOL) | (occ_all > 0)          # on the surface, or inside solid space
print("kept %d / %d (%.1f%%); deleted %.1f%% as free-space" % (keep.sum(), len(P), 100*keep.mean(), 100*(1-keep.mean())), flush=True)
print("distance to surface: p50 %.1f mm p90 %.1f mm; occupancy inside %.1f%%" % (np.median(dist_all)*1000, np.percentile(dist_all,90)*1000, 100*(occ_all>0).mean()), flush=True)
pos = P[keep].copy(); pos[:,1] *= -1; pos[:,2] *= -1; pos = np.ascontiguousarray(pos.astype("<f4"))
col = np.ascontiguousarray(C[keep])
pos.tofile(f"{OUT}/{TAG}.pos"); col.tofile(f"{OUT}/{TAG}.col")
lo, hi = np.percentile(pos,1,0), np.percentile(pos,99,0); med = np.median(pos,0)
rad = float(np.percentile(np.linalg.norm(pos-med,axis=1),95))
json.dump({TAG: {"n": int(len(pos)), "center": ((lo+hi)/2).tolist(), "ext": (hi-lo).tolist(), "med": med.astype(float).tolist(), "radius": rad}}, open(f"{OUT}/meta_{TAG}.json","w"))
print("wrote", TAG, len(pos), "med", np.round(med,3).tolist(), flush=True)
