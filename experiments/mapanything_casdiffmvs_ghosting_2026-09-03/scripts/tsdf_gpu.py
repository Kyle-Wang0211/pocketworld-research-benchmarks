#!/usr/bin/env python3
"""3 mm TSDF with Open3D's tensor VoxelBlockGrid on CUDA -- same setup as the archived
tsdf_fuse_gpu.py (block_resolution 16, uint16 depth, colour kept). The legacy CPU
ScalableTSDFVolume cannot hold a 3 mm grid for these clouds: it hit the 64.5 GB cgroup cap
three times. All three engines go through this same path so the panes stay comparable."""
import sys, os, glob, time, numpy as np, cv2, open3d as o3d, open3d.core as o3c

SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
VOX = float(os.environ.get("VOXEL", 0.003))
TRUNC = float(os.environ.get("TRUNC", 0.04))
DSCALE = float(os.environ.get("DEPTH_SCALE", 3200.0))
DMAX = float(os.environ.get("DEPTH_MAX", 20.0))
WTH = float(os.environ.get("WEIGHT_TH", 1.0))
BLOCKS = int(os.environ.get("BLOCK_COUNT", 400000))
os.makedirs(OUT, exist_ok=True)

dev = o3c.Device("CUDA:0")
vbg = o3d.t.geometry.VoxelBlockGrid(
    attr_names=("tsdf", "weight", "color"),
    attr_dtypes=(o3c.float32, o3c.uint16, o3c.uint16),
    attr_channels=((1), (1), (3)),
    voxel_size=VOX, block_resolution=16, block_count=BLOCKS, device=dev)

ids = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{SRC}/depth/*.npy"))
t0 = time.time()
for n, i in enumerate(ids):
    d = np.load(f"{SRC}/depth/{i:08d}.npy").astype(np.float32)
    if not np.isfinite(d).any() or (d > 0).sum() == 0:
        print(f"  skip view {i}: no pixel survived the official gate", flush=True)
        continue
    d16 = np.ascontiguousarray(np.clip(d * DSCALE, 0, 65535).astype(np.uint16))
    rgb = np.ascontiguousarray(cv2.imread(f"{SRC}/color/{i:08d}.png")[:, :, ::-1].copy())
    z = np.load(f"{SRC}/cam/{i:08d}.npz")
    intr = o3c.Tensor(z["K"].astype(np.float64), o3c.float64)
    extr = o3c.Tensor(z["E"].astype(np.float64), o3c.float64)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)).to(dev)
    cimg = o3d.t.geometry.Image(o3c.Tensor(rgb)).to(dev)
    coords = vbg.compute_unique_block_coordinates(dimg, intr, extr, DSCALE, DMAX)
    vbg.integrate(coords, dimg, cimg, intr, intr, extr, DSCALE, DMAX, TRUNC / VOX)
    if n % 40 == 0:
        print(f"  integrated {n}/{len(ids)} blocks={vbg.hashmap().size()} {time.time()-t0:.0f}s", flush=True)
print(f"active blocks {vbg.hashmap().size()} / {BLOCKS}  {time.time()-t0:.0f}s", flush=True)

pcd = vbg.extract_point_cloud(weight_threshold=WTH, estimated_point_number=-1).to_legacy()
o3d.io.write_point_cloud(f"{OUT}/{TAG}_tsdf.ply", pcd)
print(f"{TAG} tsdf points {len(pcd.points)}  {time.time()-t0:.0f}s", flush=True)
mesh = vbg.extract_triangle_mesh(weight_threshold=WTH, estimated_vertex_number=-1).to_legacy()
o3d.io.write_triangle_mesh(f"{OUT}/{TAG}_tsdf_mesh.ply", mesh)
print(f"{TAG} tsdf mesh verts {len(mesh.vertices)} faces {len(mesh.triangles)}  {time.time()-t0:.0f}s", flush=True)
