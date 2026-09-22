#!/usr/bin/env python3
"""Arm C: mesh the ep0 dense cloud the user actually judges by, with the classic point-cloud-to-mesh method.

Poisson is the standard answer to 'I have a good dense cloud, give me a surface': it solves for an implicit
function whose gradient matches the oriented normals, so it produces a watertight manifold mesh by construction --
the property our TSDF marching-cubes output does not have. The price is that it closes everything, including space
the cameras never saw, so the low-density parts are trimmed afterwards with Open3D's own density output.

Normals are oriented toward the cameras that observed the scene (a normal pointing the wrong way flips the implicit
function locally and produces inside-out blobs).
  poisson_ep0.py <cloud.ply> <sfm.sfm> <out.ply> [depth=11] [trim_quantile=0.02]
"""
import sys, json, time, numpy as np, open3d as o3d
CLOUD, SFM, OUT = sys.argv[1:4]
DEPTH = int(sys.argv[4]) if len(sys.argv) > 4 else 11
TRIM = float(sys.argv[5]) if len(sys.argv) > 5 else 0.02
t0 = time.time()
pcd = o3d.io.read_point_cloud(CLOUD)
print(f"cloud: {len(pcd.points):,} points, colours={pcd.has_colors()}, normals={pcd.has_normals()}  ({time.time()-t0:.0f}s)", flush=True)
if not pcd.has_normals():
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.02, max_nn=30))
    print(f"estimated normals ({time.time()-t0:.0f}s)", flush=True)
# orient toward the cameras: for each point take the nearest camera centre and flip the normal to face it
d = json.load(open(SFM))
C = np.array([[float(x) for x in p["pose"]["transform"]["center"]] for p in d["poses"]])
P = np.asarray(pcd.points); N = np.asarray(pcd.normals)
from scipy.spatial import cKDTree
_, ci = cKDTree(C).query(P, k=1)
flip = np.einsum('ij,ij->i', C[ci] - P, N) < 0
N[flip] *= -1
pcd.normals = o3d.utility.Vector3dVector(N)
print(f"oriented normals toward the nearest camera ({flip.mean():.1%} flipped)  ({time.time()-t0:.0f}s)", flush=True)
mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=DEPTH, linear_fit=False)
dens = np.asarray(dens)
print(f"poisson depth={DEPTH}: {len(mesh.vertices):,} v / {len(mesh.triangles):,} t  ({time.time()-t0:.0f}s)", flush=True)
thr = np.quantile(dens, TRIM)
mesh.remove_vertices_by_mask(dens < thr)
print(f"trim lowest {TRIM:.0%} density: {len(mesh.vertices):,} v / {len(mesh.triangles):,} t", flush=True)
nme = len(mesh.get_non_manifold_edges(allow_boundary_edges=True))
print(f"非流形边 {nme:,}  (对照: 官方 Delaunay 115, 我们的 TSDF 56,640)", flush=True)
mesh.compute_vertex_normals()
o3d.io.write_triangle_mesh(OUT, mesh, write_ascii=False, write_vertex_normals=True, write_vertex_colors=True)
print(f"wrote {OUT}  ({time.time()-t0:.0f}s)", flush=True)
