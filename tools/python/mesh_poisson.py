"""Screened-Poisson mesh a point cloud (Open3D). Point-cloud -> watertight-ish
colored mesh. n_threads=1 (Open3D Poisson segfaults otherwise on this box).
usage: mesh_poisson.py in.ply out.ply [voxel=0.012] [depth=10] [trim_q=0.04]"""
import sys, numpy as np, open3d as o3d
inp, outp = sys.argv[1], sys.argv[2]
voxel = float(sys.argv[3]) if len(sys.argv) > 3 else 0.012
depth = int(sys.argv[4]) if len(sys.argv) > 4 else 10
trim_q = float(sys.argv[5]) if len(sys.argv) > 5 else 0.04

pc = o3d.io.read_point_cloud(inp)
n0 = len(pc.points)
pc = pc.voxel_down_sample(voxel)
print(f"{inp}: {n0:,} -> voxel {len(pc.points):,}", flush=True)
pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 3, max_nn=30))
pc.orient_normals_consistent_tangent_plane(15)            # consistent orientation for Poisson
print("normals oriented; running Poisson…", flush=True)
mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pc, depth=depth, n_threads=1)
dens = np.asarray(dens)
mesh.remove_vertices_by_mask(dens < np.quantile(dens, trim_q))   # trim low-density balloon artifacts
mesh.remove_unreferenced_vertices()
mesh.compute_vertex_normals()
o3d.io.write_triangle_mesh(outp, mesh)
print(f"wrote {outp}: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris", flush=True)
