#!/usr/bin/env python3
"""Carved TSDF as arbiter: keep original full-resolution coloured points that survive space carving.
Same pattern as the mesh-as-arbiter filter already in this repo -- the original points and colours
are untouched, the carved surface only decides which ones are deleted."""
import sys, numpy as np, open3d as o3d
RAW, VERTS_CARVE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
TOL = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0045      # 1.5 voxels at 3 mm
pc = o3d.io.read_point_cloud(RAW)
P = np.asarray(pc.points); C = (np.asarray(pc.colors) * 255).astype(np.uint8)
V = np.load(VERTS_CARVE).astype(np.float64)
ref = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(V))
d = np.asarray(pc.compute_point_cloud_distance(ref))
keep = d < TOL
print(f"raw {len(P)}  carved-surface verts {len(V)}  kept {keep.sum()} ({keep.mean()*100:.1f}%)", flush=True)
P, C = P[keep], C[keep]
with open(OUT, "wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % len(P)).encode())
    r = np.zeros(len(P), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    r["x"],r["y"],r["z"] = P[:,0],P[:,1],P[:,2]; r["r"],r["g"],r["b"] = C[:,0],C[:,1],C[:,2]; r.tofile(f)
print("wrote", OUT, flush=True)
