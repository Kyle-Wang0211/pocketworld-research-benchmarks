"""Isolated meshing from the cached fused cloud. ONE Poisson attempt per process
so Open3D's process-level "Failed to close loop" crash can't take down a loop.

Usage: pw_mesh.py CONF_THR VOXEL_MM DEPTH OUTLIER_STD METHOD
"""
import sys
from pathlib import Path
import numpy as np
import open3d as o3d

OUT = Path(__file__).resolve().parent / "diffmvs_out"
conf_thr = float(sys.argv[1]) if len(sys.argv) > 1 else 0.6
voxel = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.008
depth = int(sys.argv[3]) if len(sys.argv) > 3 else 9
ostd = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
method = sys.argv[5] if len(sys.argv) > 5 else "diffmvs"

d = np.load(OUT / f"rawfused_{method}.npz")
P, Cc, Cf, cc = d["xyz"], d["rgb"], d["conf"], d["cam_centroid"]
keep = (Cf >= conf_thr) & np.isfinite(P).all(1)
P, Cc = P[keep], Cc[keep]
pc = o3d.geometry.PointCloud()
pc.points = o3d.utility.Vector3dVector(P.astype(np.float64))
pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
pc = pc.voxel_down_sample(voxel)
pc = pc.remove_non_finite_points()
pc, _ = pc.remove_statistical_outlier(nb_neighbors=30, std_ratio=ostd)
print(f"conf>={conf_thr} voxel={voxel*1000:.0f}mm -> {len(pc.points):,} pts (outlier std {ostd})",
      flush=True)
pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.06, max_nn=30))
pc.orient_normals_towards_camera_location(cc.astype(np.float64))

print(f"poisson depth={depth} starting (n_threads=1)...", flush=True)
mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    pc, depth=depth, scale=1.1, linear_fit=True, n_threads=1)
dens = np.asarray(dens)
mesh.remove_vertices_by_mask(dens < np.quantile(dens, 0.05))
mesh.compute_vertex_normals()
mp = OUT / f"mesh_{method}_d{depth}_c{conf_thr}.ply"
o3d.io.write_triangle_mesh(str(mp), mesh)
print(f"OK poisson(depth={depth}) verts={len(mesh.vertices):,} tris={len(mesh.triangles):,} -> {mp.name}",
      flush=True)
