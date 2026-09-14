#!/usr/bin/env python3
"""fuseCut(Jancosek-Pajdla 可见性图割)网格当裁判, 全分辨率官方云当交付。
只判去留, 留下的点坐标颜色一字不改(mesh_filter_full.py 的设计, 用户 09-07 定的)。

坐标:裁判网格在旧约定(y,z 为负), official_full.ply 在新约定(y,z 为正)。
先做 y,z 反号对齐, 再判。阳性对照:档案记载删除率 3.11%(93 万/2995 万) —— 对不上就是没对齐。
"""
import sys, numpy as np, open3d as o3d
MESH = "/root/av/mesh_avdense.obj"
CLOUD = "/root/ws_gc8/official_full.ply"
TOL = 0.01

me = o3d.io.read_triangle_mesh(MESH)
V = np.asarray(me.vertices)
print(f"网格 {len(V):,} 顶点  中心 {np.round(V.mean(0),2)}")

with open(CLOUD, "rb") as f:
    hdr = b""
    while b"end_header" not in hdr: hdr += f.readline()
    n = int([l for l in hdr.split(b"\n") if l.startswith(b"element vertex")][0].split()[-1])
    a = np.frombuffer(f.read(n * 15), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
P = np.stack([a["x"], a["y"], a["z"]], 1).astype(np.float32)
C = np.stack([a["r"], a["g"], a["b"]], 1)
print(f"官方云 {n:,} 点  中心 {np.round(P.mean(0),2)}")

sc = o3d.t.geometry.RaycastingScene()
sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(me))

for name, Q in (("原样", P), ("y,z 反号", P * np.array([1, -1, -1], np.float32))):
    print(f"\n── {name}  中心 {np.round(Q.mean(0),2)}")
    keep = np.zeros(len(Q), bool)
    B = 2_000_000
    for i in range(0, len(Q), B):
        q = o3d.core.Tensor(Q[i:i+B], dtype=o3d.core.Dtype.Float32)
        d = sc.compute_distance(q).numpy()
        occ = sc.compute_occupancy(q).numpy().astype(bool)
        keep[i:i+B] = occ | (d <= TOL)
    dele = (~keep).mean()
    print(f"   删除 {(~keep).sum():,} / {len(Q):,} = {dele*100:.2f}%   (档案记载 3.11%)")
    if abs(dele - 0.0311) < 0.02:
        print("   ✅ 与档案吻合 —— 这是对的对齐")
        np.save("/root/fusecut_keep.npy", keep)
        with open("/root/av/fusecut_kept.ply", "wb") as f:
            k = keep.sum()
            f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % k).encode())
            r = np.zeros(k, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
            r["x"],r["y"],r["z"] = P[keep,0],P[keep,1],P[keep,2]     # 交付用原坐标, 不用翻过的
            r["r"],r["g"],r["b"] = C[keep,0],C[keep,1],C[keep,2]; r.tofile(f)
        with open("/root/av/fusecut_deleted.ply", "wb") as f:
            k = (~keep).sum()
            f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % k).encode())
            r = np.zeros(k, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
            r["x"],r["y"],r["z"] = P[~keep,0],P[~keep,1],P[~keep,2]
            r["r"],r["g"],r["b"] = C[~keep,0],C[~keep,1],C[~keep,2]; r.tofile(f)
        print(f"   写出 kept {keep.sum():,} / deleted {(~keep).sum():,}")
        break
