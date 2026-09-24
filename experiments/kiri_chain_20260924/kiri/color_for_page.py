# Display-only colours for the KIRI-chain meshes (they carry no colour; texrecon comes last):
# nearest vertex of mesh A. Geometry untouched; vertex normals computed for the lit view.
import sys, time, numpy as np, open3d as o3d
from scipy.spatial import cKDTree
A = "/root/tsdf_mesh_ep0/tsdf_mesh_full_ep0_v0.003_t0.04_nofill.ply"
t0 = time.time()
ma = o3d.io.read_triangle_mesh(A); VA = np.asarray(ma.vertices); CA = np.asarray(ma.vertex_colors)
tree = cKDTree(VA); print(f"KD-tree on A {len(VA):,} v  {time.time()-t0:.0f}s", flush=True)
for src, dst in zip(sys.argv[1::2], sys.argv[2::2]):
    m = o3d.io.read_triangle_mesh(src); V = np.asarray(m.vertices)
    d, i = tree.query(V, k=1, workers=-1)
    m.vertex_colors = o3d.utility.Vector3dVector(CA[i]); m.compute_vertex_normals()
    o3d.io.write_triangle_mesh(dst, m, write_ascii=False, compressed=False, write_vertex_normals=True, write_vertex_colors=True)
    print(f"{src}: {len(V):,} v / {len(m.triangles):,} f; NN distance to A p50 {np.median(d)*1000:.2f} mm p90 {np.percentile(d,90)*1000:.1f} mm -> {dst}  {time.time()-t0:.0f}s", flush=True)
