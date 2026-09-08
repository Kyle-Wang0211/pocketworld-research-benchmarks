#!/usr/bin/env python3
"""VDBFusion (PRBonn, Sensors 2022, MIT) on the gated depths.
Two volumes differing in ONE flag: space_carving. sdf_trunc = 3 x voxel follows VDBFusion's own config.
STRIDE subsamples the pixels used as carving rays (delivery is never subsampled -- the arbiter step
filters the FULL-resolution original cloud). The paper itself notes carving costs a lot of time."""
import sys, os, glob, time, numpy as np, open3d as o3d, vdbfusion

SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
VOX = float(os.environ.get("VOXEL", 0.01))
TRUNC = float(os.environ.get("TRUNC", 3 * VOX))
MINW = float(os.environ.get("MIN_WEIGHT", 3.0))    # the official gate is >= 3 views; same number here
STRIDE = int(os.environ.get("STRIDE", 2))
os.makedirs(OUT, exist_ok=True)

ids = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{SRC}/depth/*.npy"))
scans = []
for i in ids:
    d = np.load(f"{SRC}/depth/{i:08d}.npy")
    z = np.load(f"{SRC}/cam/{i:08d}.npz"); K = z["K"]; E = z["E"]
    if STRIDE > 1:
        m = np.zeros_like(d, bool); m[::STRIDE, ::STRIDE] = True; d = np.where(m, d, 0)
    keep = d > 0
    h, w = d.shape; x, y = np.meshgrid(np.arange(w), np.arange(h))
    x, y, dd = x[keep], y[keep], d[keep]
    xyz = np.linalg.inv(K) @ (np.vstack((x, y, np.ones_like(x))) * dd)
    pw = (np.linalg.inv(E) @ np.vstack((xyz, np.ones_like(x))))[:3].T
    org = (-E[:3, :3].T @ E[:3, 3])
    scans.append((np.ascontiguousarray(pw.astype(np.float64)), np.ascontiguousarray(org.astype(np.float64))))
print(f"{TAG}: {len(scans)} scans, {sum(len(p) for p,_ in scans)} carving rays "
      f"(stride {STRIDE}), voxel {VOX} trunc {TRUNC} min_weight {MINW}", flush=True)

for carve in (False, True):
    t0 = time.time()
    vol = vdbfusion.VDBVolume(voxel_size=VOX, sdf_trunc=TRUNC, space_carving=carve)
    for k, (pw, org) in enumerate(scans):
        vol.integrate(pw, org)
        if k % 20 == 0: print(f"   carve={carve} scan {k}/{len(scans)} {time.time()-t0:.0f}s", flush=True)
    vert, tri = vol.extract_triangle_mesh(fill_holes=False, min_weight=MINW)
    name = f"{TAG}_vdb_carve{int(carve)}"
    m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vert), o3d.utility.Vector3iVector(tri))
    m.compute_vertex_normals(); o3d.io.write_triangle_mesh(f"{OUT}/{name}_mesh.ply", m)
    np.save(f"{OUT}/{name}_verts.npy", np.asarray(vert, dtype=np.float32))
    print(f"{name}: verts {len(vert)} tris {len(tri)}  {time.time()-t0:.1f}s", flush=True)
print("VDB_DONE", TAG, flush=True)
