"""Full-scene production-identical TSDF (no colour: tsdf/weight updates are independent of colour), MC at thr 1.0 and 0.0.
Self-checks: replayed pixel count == 36,233,053 and thr1 MC counts == production run.log '[mc] 45,228,456 v / 87,573,228 t'."""
import numpy as np, open3d as o3d, open3d.core as o3c, time, json
from replay_lib import *
VOX = 0.003; TR = 0.04; DS = 5000.0; DMAX = 30.0
vbg = o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight"), attr_dtypes=(o3c.float32, o3c.float32), attr_channels=((1), (1)),
    voxel_size=VOX, block_resolution=16, block_count=300000, device=o3c.Device("CPU:0"))
t0 = time.time(); tot = 0
for rv, sv in PAIR_DATA:
    o = replay(rv, sv); tot += int(o["final"].sum())
    if o["final"].sum() == 0: continue
    d = np.where(o["final"], o["davg"], 0.0).astype(np.float64); d = np.where(d > DMAX, 0.0, d); d16 = np.round(d * DS).astype(np.uint16)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)); K = o3c.Tensor(np.asarray(o["K"], np.float64)); E = o3c.Tensor(np.asarray(o["E"], np.float64))
    c = vbg.compute_unique_block_coordinates(dimg, K, E, DS, DMAX, TR / VOX); vbg.integrate(c, dimg, K, E, DS, DMAX, TR / VOX)
print("replayed", tot, "blocks", vbg.hashmap().size(), f"{time.time()-t0:.0f}s", flush=True)
res = dict(replayed=tot, blocks=int(vbg.hashmap().size()))
for thr in (1.0, 0.0):
    t0 = time.time(); m = vbg.extract_triangle_mesh(weight_threshold=thr).to_legacy()
    res[f"thr{thr:g}"] = [len(m.vertices), len(m.triangles)]
    print(f"thr {thr}: {len(m.vertices):,} v / {len(m.triangles):,} t  {time.time()-t0:.0f}s", flush=True)
    m2 = o3d.geometry.TriangleMesh(m.vertices, m.triangles); del m
    o3d.io.write_triangle_mesh(f"global_thr{thr:g}_raw.ply", m2); del m2
json.dump(res, open("global_tsdf.json", "w"), indent=1)
