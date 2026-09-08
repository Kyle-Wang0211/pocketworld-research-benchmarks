#!/usr/bin/env python3
"""Textured OpenMVS mesh -> per-vertex-coloured point set for the existing viewer, with the mesh's own shading.
The viewer draws points, so each mesh VERTEX becomes one point; its colour is the texture sampled at its UV,
multiplied by simple Lambert shading from the vertex normal so the surface reads as a surface, not a fog of dots.
Nothing is resampled: one point per mesh vertex, exactly the geometry OpenMVS produced."""
import sys, json, os, numpy as np, open3d as o3d, cv2
PLY, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
m = o3d.io.read_triangle_mesh(PLY, True)
V = np.asarray(m.vertices); T = np.asarray(m.triangles)
print("mesh %d verts %d tris; has_uv=%s textures=%d" % (len(V), len(T),
      m.has_triangle_uvs(), len(m.textures)), flush=True)
m.compute_vertex_normals()
N = np.asarray(m.vertex_normals)
# colour: prefer the texture via triangle UVs; fall back to vertex colours
C = np.full((len(V), 3), 200, np.float64)
if m.has_triangle_uvs() and len(m.textures):
    uv = np.asarray(m.triangle_uvs).reshape(-1, 3, 2)
    tid = np.asarray(m.triangle_material_ids) if len(np.asarray(m.triangle_material_ids)) else np.zeros(len(T), int)
    texs = [np.asarray(t) for t in m.textures]
    acc = np.zeros((len(V), 3)); cnt = np.zeros(len(V))
    for k in range(3):
        for ti, tex in enumerate(texs):
            sel = tid == ti
            if not sel.any() or tex.size == 0: continue
            h, w = tex.shape[:2]
            u = np.clip((uv[sel, k, 0] * w).astype(int), 0, w - 1)
            v = np.clip(((1 - uv[sel, k, 1]) * h).astype(int), 0, h - 1)
            col = tex[v, u][:, :3].astype(np.float64)
            idx = T[sel][:, k]
            np.add.at(acc, idx, col); np.add.at(cnt, idx, 1)
    ok = cnt > 0
    C[ok] = acc[ok] / cnt[ok, None]
    print("textured vertices: %.1f%%" % (100 * ok.mean()), flush=True)
elif m.has_vertex_colors():
    C = np.asarray(m.vertex_colors) * 255
    print("using vertex colours", flush=True)
L = np.array([0.4, -0.8, 0.45]); L = L / np.linalg.norm(L)
sh = 0.55 + 0.45 * np.abs(N @ L)
C = np.clip(C * sh[:, None], 0, 255).astype(np.uint8)
pos = V.astype(np.float32).copy(); pos[:, 1] *= -1; pos[:, 2] *= -1
pos = np.ascontiguousarray(pos.astype("<f4")); pos.tofile(f"{OUT}/{TAG}.pos")
np.ascontiguousarray(C).tofile(f"{OUT}/{TAG}.col")
lo, hi = np.percentile(pos, 1, 0), np.percentile(pos, 99, 0); med = np.median(pos, 0)
json.dump({TAG: {"n": int(len(pos)), "center": ((lo + hi) / 2).tolist(), "ext": (hi - lo).tolist(),
                 "med": med.astype(float).tolist(),
                 "radius": float(np.percentile(np.linalg.norm(pos - med, axis=1), 95))}},
          open(f"{OUT}/meta_{TAG}.json", "w"))
print("wrote", TAG, len(pos), "med", np.round(med, 3).tolist(), flush=True)
