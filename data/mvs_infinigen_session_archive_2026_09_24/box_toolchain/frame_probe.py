"""Decide the AliceVision mesh's display transform by measurement, not by eye: for each candidate sign flip, how far
is a sample of mesh vertices from the TSDF cloud (same scene, known-good frame)? The right transform is the one with
millimetre-scale distances."""
import numpy as np, open3d as o3d
V = []
for l in open("/root/av_ep0_hi/meshfilt/mesh.obj", errors="ignore"):
    if l.startswith("v "): V.append(l[2:])
m = np.fromstring("".join(V), sep=" ", dtype=np.float32).reshape(-1, 3)
P = np.asarray(o3d.io.read_point_cloud("/root/tsdf_full_ep0_fix/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r16.ply").points)
print(f"mesh {len(m):,} vertices, tsdf {len(P):,} points (both RAW, i.e. as written by their own tool)")
pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P[::7]))
kd = o3d.geometry.KDTreeFlann(pc)
rng = np.random.default_rng(0); S = m[rng.choice(len(m), 4000, replace=False)]
for name, sgn in (("identity (x,y,z)", (1, 1, 1)), ("180 deg about x (x,-y,-z)", (1, -1, -1)),
                  ("flip z only", (1, 1, -1)), ("flip y only", (1, -1, 1))):
    Q = S * np.array(sgn, np.float32)
    d = []
    for q in Q:
        k, _, dist = kd.search_knn_vector_3d(q.astype(np.float64), 1)
        d.append(np.sqrt(dist[0]))
    d = np.array(d)
    print(f"  {name:28s}: mesh->tsdf distance  p50 {d.min() if False else np.percentile(d,50)*1000:9.1f} mm   p90 {np.percentile(d,90)*1000:9.1f} mm")
