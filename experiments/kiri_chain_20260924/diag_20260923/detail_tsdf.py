"""Production-identical TSDF (exact /root/tsdf_ep_mesh.py inputs) restricted to a 3D box (floor coordinates), any voxel size /
view subset. Saves thr1 raw MC and the production post-processing (cluster<100 removal + Taubin x10) of it."""
import numpy as np, open3d as o3d, open3d.core as o3c, json, sys, time
from replay_lib import *
BOX = sys.argv[1]; VOX = float(sys.argv[2]); TRUNC = float(sys.argv[3]); VIEWSET = sys.argv[4]
TAG = f"{BOX}_v{VOX:g}_t{TRUNC:g}_{VIEWSET}"; BR = 16; DS = 5000.0; DMAX = 30.0
# "oddshift": odd views integrated in a world translated by DELTA (non-integer voxel fractions) so the voxel lattice / MC
# discretisation pattern differs from the even half; vertices are shifted back afterwards. Grid-aligned artefacts then decorrelate.
DELTA = np.array([0.37, 0.61, 0.53]) * VOX if VIEWSET.endswith("shift") else np.zeros(3)
R = json.load(open("regions_planes.json")); nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]; e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"]); gf = R["floor"]["grid"]
BOXES = {"suitcase": ((gf["a0"] + 1.5, gf["a0"] + 3.9), (gf["b0"] + 3.3, gf["b0"] + 6.9), (0.03, 2.0)),
         "floorbox": None}
if BOX == "floorbox":
    PL = np.load("polygons.npz"); m = np.load("regionmask_floorpatch.npy"); iu, iv = np.nonzero(m); u0, v0 = PL["floor_meta"]
    BOXES["floorbox"] = ((u0 + iu.min() * 0.02, u0 + (iu.max() + 1) * 0.02), (v0 + iv.min() * 0.02, v0 + (iv.max() + 1) * 0.02), (-0.15, 0.15))
(a0, a1), (b0, b1), (h0, h1) = BOXES[BOX]
def inbox(P):
    a = P @ e1f; b = P @ e2f; h = P @ nf + df
    return (a > a0) & (a < a1) & (b > b0) & (b < b1) & (h > h0) & (h < h1)
bs = VOX * BR
vbg = o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight"), attr_dtypes=(o3c.float32, o3c.float32), attr_channels=((1), (1)),
    voxel_size=VOX, block_resolution=BR, block_count=400000, device=o3c.Device("CPU:0"))
t0 = time.time(); used = 0
for rv, sv in PAIR_DATA:
    if VIEWSET == "even" and rv % 2: continue
    if VIEWSET.startswith("odd") and rv % 2 == 0: continue
    o = replay(rv, sv)
    d = np.where(o["final"], o["davg"], 0.0).astype(np.float64); d = np.where(d > DMAX, 0.0, d); d16 = np.round(d * DS).astype(np.uint16)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)); Kt = o3c.Tensor(np.asarray(o["K"], np.float64)); Ev = np.asarray(o["E"], np.float64).copy(); Ev[:3, 3] = Ev[:3, 3] - Ev[:3, :3] @ DELTA; Et = o3c.Tensor(Ev)
    c = vbg.compute_unique_block_coordinates(dimg, Kt, Et, DS, DMAX, TRUNC / VOX).numpy().astype(np.int64)
    if len(c) == 0: continue
    sel = inbox((c + 0.5) * bs - DELTA)       # block centre inside the box (true world coords)
    if sel.sum() == 0: continue
    vbg.integrate(o3c.Tensor(c[sel].astype(np.int32)), dimg, Kt, Et, DS, DMAX, TRUNC / VOX); used += 1
print(TAG, "views", used, "blocks", vbg.hashmap().size(), f"{time.time()-t0:.0f}s", flush=True)
m = vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy(); del vbg
m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(m.vertices) - DELTA), m.triangles)
o3d.io.write_triangle_mesh(f"det_{TAG}_raw.ply", m)
tc, cn, _ = m.cluster_connected_triangles(); tc = np.asarray(tc); cn = np.asarray(cn)
m.remove_triangles_by_mask(cn[tc] < 100); m2 = m.filter_smooth_taubin(number_of_iterations=10)
o3d.io.write_triangle_mesh(f"det_{TAG}_post.ply", m2)
print(TAG, "raw/post", len(m.vertices), len(m.triangles), flush=True)
