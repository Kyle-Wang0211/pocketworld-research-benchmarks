"""Production-identical TSDF (3mm / 40mm / br16, exact /root/tsdf_ep_mesh.py inputs) restricted to one planar region.
Per view: coords = compute_unique_block_coordinates(this view depth) exactly as production, then INTERSECTED with the
region block set, then integrate(coords) -> every voxel in the region gets exactly the production tsdf/weight."""
import numpy as np, open3d as o3d, open3d.core as o3c, json, sys, time
from scipy import ndimage as ndi
from replay_lib import *
REG = sys.argv[1]            # wall | floorpatch
VOX = float(sys.argv[2]) if len(sys.argv) > 2 else 0.003
TRUNC = float(sys.argv[3]) if len(sys.argv) > 3 else 0.04
VIEWSET = sys.argv[4] if len(sys.argv) > 4 else "all"   # all | even | odd
TAG = f"{REG}_v{VOX:g}_t{TRUNC:g}_{VIEWSET}"
BR = 16; DS = 5000.0; DMAX = 30.0
R = json.load(open("regions_planes.json")); PL = np.load("polygons.npz")
nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"])
nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]; e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"])
CELL = 0.02
if REG == "wall":
    mask = PL["wall"].copy(); u0, v0 = PL["wall_meta"]
    A = np.stack([nw, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -dw), u - df, v], 1); n_ = nw
elif REG == "white":
    nW = np.array(R["white"]["n"]); dW = R["white"]["d"]
    mask = PL["white"].copy(); u0, v0 = PL["white_meta"]
    A = np.stack([nW, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -dW), u - df, v], 1); n_ = nW
else:
    mask = PL["floor"].copy(); u0, v0 = PL["floor_meta"]
    A = np.stack([nf, e1f, e2f]); rhs = lambda u, v: np.stack([np.full_like(u, -df), u, v], 1); n_ = nf
    best = None
    for i0 in range(0, mask.shape[0] - 60, 10):
        for j0 in range(0, mask.shape[1] - 60, 10):
            f = mask[i0:i0 + 60, j0:j0 + 60].mean()
            if best is None or f > best[0]: best = (f, i0, j0)
    _, i0, j0 = best; m2 = np.zeros_like(mask); m2[i0:i0 + 60, j0:j0 + 60] = mask[i0:i0 + 60, j0:j0 + 60]; mask = m2
    print("floor patch window", i0, j0, "cells", int(mask.sum()), flush=True)
Ainv = np.linalg.inv(A)
def to3d(u, v): return (Ainv @ rhs(u, v).T).T
md = ndi.binary_dilation(mask, iterations=3); du, dv = np.nonzero(md)
g = np.arange(0, CELL, VOX * 4)
uu = (u0 + du * CELL)[:, None] + np.repeat(g, len(g))[None, :]; vv = (v0 + dv * CELL)[:, None] + np.tile(g, len(g))[None, :]
Xs = to3d(uu.ravel(), vv.ravel())
bs = VOX * BR; keys = []
for t in np.arange(-0.15, 0.1501, bs / 2):
    keys.append(np.unique(np.floor((Xs + t * n_) / bs).astype(np.int64), axis=0))
K_reg = np.unique(np.concatenate(keys), axis=0); print(TAG, "region blocks", len(K_reg), flush=True)
def kv(a): a = np.ascontiguousarray(a.astype(np.int64)); return a.view([("x", np.int64), ("y", np.int64), ("z", np.int64)]).ravel()
regv = kv(K_reg)
vbg = o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight"), attr_dtypes=(o3c.float32, o3c.float32), attr_channels=((1), (1)),
    voxel_size=VOX, block_resolution=BR, block_count=int(len(K_reg) * 1.2) + 1000, device=o3c.Device("CPU:0"))
t0 = time.time(); tm = TRUNC / VOX; used = 0
for rv, sv in PAIR_DATA:
    if VIEWSET == "even" and rv % 2: continue
    if VIEWSET == "odd" and rv % 2 == 0: continue
    o = replay(rv, sv)
    d = np.where(o["final"], o["davg"], 0.0).astype(np.float64); d = np.where(d > DMAX, 0.0, d); d16 = np.round(d * DS).astype(np.uint16)
    dimg = o3d.t.geometry.Image(o3c.Tensor(d16)); Kt = o3c.Tensor(np.asarray(o["K"], np.float64)); Et = o3c.Tensor(np.asarray(o["E"], np.float64))
    coords = vbg.compute_unique_block_coordinates(dimg, Kt, Et, DS, DMAX, tm).numpy().astype(np.int64)
    if len(coords) == 0: continue
    sel = np.isin(kv(coords), regv)
    if sel.sum() == 0: continue
    vbg.integrate(o3c.Tensor(coords[sel].astype(np.int32)), dimg, Kt, Et, DS, DMAX, tm); used += 1
print(TAG, "integrated views", used, "active blocks", vbg.hashmap().size(), f"{time.time()-t0:.0f}s", flush=True)
hm = vbg.hashmap(); ai = hm.active_buf_indices().numpy().astype(np.int64); kt = hm.key_tensor().numpy()[ai].astype(np.int64)
T = vbg.attribute("tsdf").numpy().reshape(-1, BR, BR, BR)[ai]; W = vbg.attribute("weight").numpy().reshape(-1, BR, BR, BR)[ai]
np.savez_compressed(f"vbg_{TAG}.npz", keys=kt, tsdf=T.astype(np.float32), weight=W.astype(np.uint16), vox=VOX, br=BR)
for thr in (1.0, 0.0):
    m = vbg.extract_triangle_mesh(weight_threshold=thr).to_legacy()
    o3d.io.write_triangle_mesh(f"mesh_{TAG}_thr{thr:g}_raw.ply", m)
    print(TAG, "thr", thr, "MC", len(m.vertices), "v", len(m.triangles), "t", flush=True)
np.save(f"regionmask_{REG}.npy", mask)
json.dump(dict(u0=float(u0), v0=float(v0), cells=int(mask.sum())), open(f"regionmeta_{REG}.json", "w"))
