#!/usr/bin/env python3
# [2026-09-23] KIRI chain from the TSDF step on, copied from GauStudio gaustudio/scripts/extract_mesh.py @132d749d (MIT):
#   :86  vdb_volume = vdbfusion.VDBVolume(voxel_size=0.01, sdf_trunc=0.04, space_carving=False)
#   :115 vdb_volume.integrate(points_world, extrinsic=cam_center)
#   :145 vertices, faces = vdb_volume.extract_triangle_mesh(min_weight=min_w)
#   :146 geo_mesh = trimesh.Trimesh(vertices, faces); geo_mesh.export(...)
# User: 「3DGS 和 CasDiffMVS 做出来的都是稠密点云,所以就从 TSDF 的步骤开始抄」. Depth fed in = the same CasDiffMVS
# filter.py replay used for mesh A (cache, 132 views, 36,233,053 valid pixels); all 132 views are used (the cameras[::3]
# stride in GauStudio belongs to its 3DGS-rendering loop, whose rendered depth is hole-free). Only knob changed between
# the two versions: voxel_size (0.01 = verbatim, 0.003 = our A voxel). README default: no --clean.
import sys, json, time
import numpy as np
import vdbfusion
import trimesh
voxel, out = float(sys.argv[1]), sys.argv[2]
min_w = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0   # GauStudio :145 uses 5; user-approved scaled variant passes 5*(voxel/0.01)^2
C = "/root/tsdf_improve/four/cache"
order = json.load(open(f"{C}/order.json"))["order"]
t0 = time.time()
vdb_volume = vdbfusion.VDBVolume(voxel_size=voxel, sdf_trunc=0.04, space_carving=False)
npts = 0
for i, v in enumerate(order):
    z = np.load(f"{C}/{v:08d}.npz"); d = z["d16"].astype(np.float64) / 5000.0; K = z["intr"]; E = z["extr"]
    vs, us = np.nonzero(d > 0); dd = d[vs, us]
    Xc = np.stack([(us - K[0, 2]) / K[0, 0] * dd, (vs - K[1, 2]) / K[1, 1] * dd, dd], 1)
    R, t = E[:3, :3], E[:3, 3]
    Xw = (Xc - t) @ R                       # world = R^T (Xc - t)
    cam_center = -R.T @ t
    vdb_volume.integrate(np.ascontiguousarray(Xw), extrinsic=cam_center)
    npts += len(dd)
    if i % 20 == 0: print(f"  [{i+1}/{len(order)}] points {npts:,}  {time.time()-t0:.0f}s", flush=True)
print(f"integrated points {npts:,} (mesh A valid pixels 36,233,053)  {time.time()-t0:.0f}s", flush=True)
vertices, faces = vdb_volume.extract_triangle_mesh(min_weight=min_w)
print(f"extract_triangle_mesh(min_weight={min_w}): {len(vertices):,} v / {len(faces):,} f  {time.time()-t0:.0f}s", flush=True)
geo_mesh = trimesh.Trimesh(vertices, faces)
geo_mesh.export(out)
print(f"trimesh: {len(geo_mesh.vertices):,} v / {len(geo_mesh.faces):,} f -> {out}  {time.time()-t0:.0f}s", flush=True)
