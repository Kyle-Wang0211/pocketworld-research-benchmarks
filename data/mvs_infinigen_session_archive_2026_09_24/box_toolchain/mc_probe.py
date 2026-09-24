import sys, numpy as np, open3d as o3d, open3d.core as o3c, time, resource
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm, read_camera_parameters, read_img, read_pair_file
of="/root/arm_full_ep0_tsdf"; res=int(sys.argv[1]); voxel=float(sys.argv[2]); nviews=int(sys.argv[3])
vbg=o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf","weight","color"),attr_dtypes=(o3c.float32,o3c.uint16,o3c.uint16),attr_channels=((1),(1),(3)),voxel_size=voxel,block_resolution=res,block_count=int(sys.argv[4]),device=o3c.Device("CPU:0"))
tm=0.04/voxel
for v in range(nviews):
    intr, extr, dmin, dint = read_camera_parameters(f"{of}/cams/{v:08d}_cam.txt")
    d = read_pfm(f"{of}/depth_est/{v:08d}.pfm")[0].astype(np.float32); d16=np.round(d*5000).astype(np.uint16)
    col=np.clip(np.asarray(read_img(f"{of}/images/{v:08d}.jpg"))*255,0,255).astype(np.uint8)
    dimg=o3d.t.geometry.Image(o3c.Tensor(d16)); cimg=o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(col)))
    ti=o3c.Tensor(np.asarray(intr,dtype=np.float64)); te=o3c.Tensor(np.asarray(extr,dtype=np.float64))
    co=vbg.compute_unique_block_coordinates(dimg,ti,te,5000.0,30.0,tm); vbg.integrate(co,dimg,cimg,ti,ti,te,5000.0,30.0,tm)
print("integrated", nviews, "views, blocks", vbg.hashmap().size(), "rss MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, flush=True)
t=time.time(); m=vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy(); print("mesh", len(m.vertices), "v", len(m.triangles), "t", f"{time.time()-t:.0f}s", "rss MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, flush=True)
