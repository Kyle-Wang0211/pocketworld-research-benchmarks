#!/usr/bin/env python3
"""Open3D triangle-mesh PLY -> verdict-page mesh bins, in the same display frame as ply2bins (y,z negated = 180° about x, so
triangle winding is unchanged):
  <tag>.pos   f32 xyz per vertex        <tag>.col  u8 rgb per vertex        <tag>.nrm  i8 xyz per vertex (unit normal * 127)
  <tag>.idx.k u32 vertex indices, 40,000,000 triangles per part (the page's http.server ignores Range, same split rule as points)
  meta.json[tag] = {kind:"mesh", n:<vertices>, tris:<triangles>, center/ext/med/radius as gen_meta.py (1%/99% percentiles, median, p95 radius)}
"""
import sys, os, json, numpy as np, open3d as o3d
SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]; CH_TRI = 40_000_000
os.makedirs(OUT, exist_ok=True)
m = o3d.io.read_triangle_mesh(SRC)
V = np.asarray(m.vertices, dtype=np.float32); T = np.asarray(m.triangles, dtype=np.uint32)
C = (np.clip(np.asarray(m.vertex_colors), 0, 1) * 255 + 0.5).astype(np.uint8) if m.has_vertex_colors() else np.full((len(V), 3), 200, np.uint8)
if not m.has_vertex_normals(): m.compute_vertex_normals()
N = np.asarray(m.vertex_normals, dtype=np.float32)
print(f"{TAG}: {len(V):,} vertices  {len(T):,} triangles  colours={m.has_vertex_colors()}  COLMAP帧中位 {np.round(np.median(V,0),3).tolist()}")
V[:, 1] *= -1; V[:, 2] *= -1; N[:, 1] *= -1; N[:, 2] *= -1
N8 = np.clip(np.round(N * 127), -127, 127).astype(np.int8)
V.tofile(f"{OUT}/{TAG}.pos"); C.tofile(f"{OUT}/{TAG}.col"); N8.tofile(f"{OUT}/{TAG}.nrm")
for k, off in enumerate(range(0, len(T), CH_TRI)):
    T[off:off + CH_TRI].astype("<u4").tofile(f"{OUT}/{TAG}.idx.{k}")
    print(f"  {TAG}.idx.{k}: {min(CH_TRI, len(T)-off):,} triangles")
lo = np.percentile(V, 1, axis=0); hi = np.percentile(V, 99, axis=0); med = np.median(V, 0)
rad = float(np.percentile(np.linalg.norm(V - med, axis=1), 95))
mp = f"{OUT}/meta.json"; meta = json.load(open(mp)) if os.path.exists(mp) else {}
meta[TAG] = {"kind": "mesh", "n": int(len(V)), "tris": int(len(T)), "center": ((lo + hi) / 2).tolist(), "ext": (hi - lo).tolist(),
             "med": med.astype(float).tolist(), "radius": rad, "idx_parts": int((len(T) + CH_TRI - 1) // CH_TRI)}
json.dump(meta, open(mp, "w"), ensure_ascii=False, indent=1)
print(f"展示帧中位 {med.tolist()}  radius {rad:.3f}  写出 {OUT}/{TAG}.*  (meta 现有 {len(meta)} 臂)")
