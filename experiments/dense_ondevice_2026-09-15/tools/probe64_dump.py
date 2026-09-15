#!/usr/bin/env python3.11
"""float64-level probe from the numpy side. Lines are copied verbatim from filter.py:20-38 (xy_src before the
float32 cast) and from fuse_ref_dump.py's world back-projection; inputs come from the ref_off dump (pack + davg + masks)."""
import sys, json, numpy as np
REF = sys.argv[1]; NSRC = 3; FR = (0, 1, 2)
NF, W, H, NS = [int(x) for x in open(f"{REF}/pack/meta.txt").read().split()[:4]]
D = np.fromfile(f"{REF}/pack/depth.f32", np.float32).reshape(NF, H, W)
CM = np.fromfile(f"{REF}/pack/cams.f32", np.float32).reshape(NF, 36); NB = np.fromfile(f"{REF}/pack/neighbors.i32", np.int32).reshape(NF, NS)
def cam(f):
    E = np.eye(4, dtype=np.float64); E[:3, :3] = CM[f, 9:18].reshape(3, 3); E[:3, 3] = CM[f, 18:21]
    return CM[f, 0:9].reshape(3, 3).astype(np.float64), E
# --- filter.py:18-38 verbatim (up to xy_src, float64) ---
Kr, Er = cam(0); depth_ref = D[0]
width, height = depth_ref.shape[1], depth_ref.shape[0]
x_ref, y_ref = np.meshgrid(np.arange(0, width), np.arange(0, height))
x_ref, y_ref = x_ref.reshape([-1]), y_ref.reshape([-1])
xyz_ref = np.matmul(np.linalg.inv(Kr), np.vstack((x_ref, y_ref, np.ones_like(x_ref))) * depth_ref.reshape([-1]))
for j, s in enumerate(NB[0][:NSRC]):
    Ks, Es = cam(int(s))
    xyz_src = np.matmul(np.matmul(Es, np.linalg.inv(Er)), np.vstack((xyz_ref, np.ones_like(x_ref))))[:3]
    K_xyz_src = np.matmul(Ks, xyz_src)
    xy_src = K_xyz_src[:2] / K_xyz_src[2:3]
    xy_src[0].astype(np.float64).tofile(f"{REF}/probe/s{j}_x_src64.f64"); xy_src[1].astype(np.float64).tofile(f"{REF}/probe/s{j}_y_src64.f64")
# --- fuse_ref_dump.py world back-projection verbatim, float64 before the cast ---
for f in FR:
    Kr, Er = cam(f)
    final = np.fromfile(f"{REF}/masks/{f:04d}.u8", np.uint8).reshape(H, W).astype(bool)
    d_avg = np.fromfile(f"{REF}/davg/{f:04d}.f64", np.float64).reshape(H, W)
    yy, xx = np.mgrid[0:H, 0:W]; x, y, d = xx[final], yy[final], d_avg[final]
    xyz = np.linalg.inv(Kr) @ (np.vstack([x, y, np.ones_like(x)]) * d)
    Rr, tr = Er[:3, :3], Er[:3, 3]; P64 = ((xyz.T - tr) @ Rr)
    P64.astype(np.float64).tofile(f"{REF}/xyz64_{f:04d}.f64")
print("probe64 written")
