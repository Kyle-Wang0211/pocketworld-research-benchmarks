#!/usr/bin/env python3
"""Open3D ScalableTSDFVolume on the gated depths. Settings are Open3D own ReconstructionSystem
indoor defaults: voxel_length = 4.0/512 m (7.8 mm), sdf_trunc = 0.04 m, RGB8 colour.
Outputs the TSDF own coloured point cloud (extract_point_cloud) and mesh (extract_triangle_mesh)."""
import sys, os, glob, numpy as np, open3d as o3d, cv2, time
SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
VOX = float(os.environ.get("VOXEL", 4.0/512.0)); TRUNC = float(os.environ.get("TRUNC", 0.04))
DMAX = float(os.environ.get("DMAX", 30.0))
os.makedirs(OUT, exist_ok=True)
vol = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=VOX, sdf_trunc=TRUNC,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
ids = sorted(int(os.path.basename(f)[:8]) for f in glob.glob(f"{SRC}/depth/*.npy"))
t0 = time.time()
for i in ids:
    d = np.load(f"{SRC}/depth/{i:08d}.npy").astype(np.float32)
    c = cv2.imread(f"{SRC}/color/{i:08d}.png")[:, :, ::-1].copy()
    z = np.load(f"{SRC}/cam/{i:08d}.npz"); K = z["K"]; E = z["E"]
    h, w = d.shape
    intr = o3d.camera.PinholeCameraIntrinsic(w, h, K[0,0], K[1,1], K[0,2], K[1,2])
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(np.ascontiguousarray(c)),
        o3d.geometry.Image(d),
        depth_scale=1.0, depth_trunc=DMAX, convert_rgb_to_intensity=False)
    vol.integrate(rgbd, intr, E)
    if i % 40 == 0: print(f"  integrated {i} {time.time()-t0:.1f}s", flush=True)
pc = vol.extract_point_cloud()
o3d.io.write_point_cloud(f"{OUT}/{TAG}_tsdf.ply", pc)
print("tsdf point cloud", len(pc.points), flush=True)
me = vol.extract_triangle_mesh(); me.compute_vertex_normals()
o3d.io.write_triangle_mesh(f"{OUT}/{TAG}_tsdf_mesh.ply", me)
print("tsdf mesh verts", len(me.vertices), "faces", len(me.triangles), f"{time.time()-t0:.1f}s", flush=True)
