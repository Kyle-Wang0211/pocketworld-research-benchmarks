#!/opt/homebrew/bin/python3.11
"""
expAZ v2 — Poisson 清晰度扫描(正解版):高 octree depth 抓细节,成面后 QEM 减面到顶点预算。
v1 的错: depth↑ + 细降采样 → 顶点炸到 30M(纯 bloat)。
v2 正解: 输入降采样保持适中(不放开),靠 depth 抓地板微起伏,再 simplify_quadric_decimation 压到 ~150 万面。
   QEM 会优先保高曲率(细节/薄结构),塌平冗余平面 → 既清晰又不 bloat。

用法: expAZ_poisson_depth_sweep.py  KEPT_CLOUD_TAG
读 ~/Desktop/expF2_.../tsdf/kept_cloud_<TAG>.ply
写 ~/Desktop/expF2_.../poisson/colored_mesh_poi_<name>.ply
"""
import sys, numpy as np, open3d as o3d
from pathlib import Path

TAG = sys.argv[1] if len(sys.argv) > 1 else "fixb93sweep"
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
SRC = DELIVER / "tsdf" / f"kept_cloud_{TAG}.ply"
POI = DELIVER / "poisson"; POI.mkdir(exist_ok=True)
TARGET_TRIS = 1_500_000   # 减面目标(≈75万顶点,贴图就绪,无 bloat)

pcd0 = o3d.io.read_point_cloud(str(SRC))
print(f"loaded {len(pcd0.points):,} pts from {SRC.name}", flush=True)

# (depth, 输入降采样, scale, 名字) — 输入降采样保持 0.003 适中,靠 depth 抓细节
CONFIGS = [
    (10, 0.003, 1.10, "d10_dec"),   # 基线深度,减面后(对照)
    (11, 0.003, 1.05, "d11_dec"),   # +1 深度
    (12, 0.003, 1.00, "d12_dec"),   # +2 深度(最清晰候选)
    (12, 0.002, 1.00, "d12f_dec"),  # 深度12 + 略细输入
]

def floater_cull(mesh):
    ids, n, _ = mesh.cluster_connected_triangles()
    ids = np.asarray(ids); n = np.asarray(n)
    small = n[ids] < max(200, int(0.001 * len(mesh.triangles)))
    mesh.remove_triangles_by_mask(small); mesh.remove_unreferenced_vertices()
    return mesh

for depth, ds, scale, name in CONFIGS:
    pcd = pcd0.voxel_down_sample(ds)
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=depth, scale=scale, linear_fit=True, n_threads=1)
    dens = np.asarray(dens)
    mesh.remove_vertices_by_mask(dens <= np.quantile(dens, 0.04))
    mesh = floater_cull(mesh)
    raw_v = len(mesh.vertices)
    # QEM 减面到预算(保高曲率细节/薄结构,塌平冗余平面)
    if len(mesh.triangles) > TARGET_TRIS:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=TARGET_TRIS)
    mesh.compute_vertex_normals()
    out = POI / f"colored_mesh_poi_{name}.ply"
    o3d.io.write_triangle_mesh(str(out), mesh)
    print(f"[{name}] depth={depth} ds={ds} scale={scale} | raw {raw_v:,}v "
          f"-> dec {len(mesh.vertices):,}v {len(mesh.triangles):,}t  {out.name}", flush=True)
print("EXPAZ-DONE", flush=True)
