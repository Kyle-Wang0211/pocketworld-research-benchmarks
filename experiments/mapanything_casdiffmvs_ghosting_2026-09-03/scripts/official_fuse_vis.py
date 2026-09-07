#!/usr/bin/env python3.11
"""Official CasDiffMVS fusion (filter.py functions, unchanged criteria: photo [0.3,0.5,0.5], geo >=3 views, 1 px, 1%,
depth averaged) + per-point VISIBILITY (ref + the source views whose official geometric check passed at that pixel).
Then a voxel merge to a Delaunay-input budget (Meshroom's Meshing feeds ~5M points by default) with visibility = union,
and COLMAP dense-workspace outputs: fused.ply + fused.ply.vis (uint64 n; per point uint32 count, uint32 image_idx...).
image_idx = order of images in sparse/images.bin = view id."""
import sys, os, numpy as np
from pathlib import Path
DIFFMVS = os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, DIFFMVS)
from filter import read_pfm, read_camera_parameters, read_img, read_pair_file, check_geometric_consistency
OUT = Path(sys.argv[1]); PAIR = sys.argv[2]; WS = Path(sys.argv[3]); VOX = float(sys.argv[4])
pair = read_pair_file(PAIR, "general")
NIMG = len(pair); P = []; C = []; V = []; KEYS = []
for ref, srcs in pair:
    Kr, Er, dmax, dmin = read_camera_parameters(str(OUT/f"cams/{ref:08d}_cam.txt"))
    img = read_img(str(OUT/f"images/{ref:08d}.jpg")); dref = read_pfm(str(OUT/f"depth_est/{ref:08d}.pfm"))[0]
    c0 = read_pfm(str(OUT/f"conf0/{ref:08d}.pfm"))[0]; c1 = read_pfm(str(OUT/f"conf1/{ref:08d}.pfm"))[0]; c2 = read_pfm(str(OUT/f"conf2/{ref:08d}.pfm"))[0]
    photo = (c0 > 0.3) & (c1 > 0.5) & (c2 > 0.5)
    geo_sum = 0; reproj_sum = 0; masks = []
    for s in srcs:
        Ks, Es, _, _ = read_camera_parameters(str(OUT/f"cams/{s:08d}_cam.txt")); ds = read_pfm(str(OUT/f"depth_est/{s:08d}.pfm"))[0]
        gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, ds, Ks, Es, dmax, dmin, 1.0, 0.01)
        geo_sum = geo_sum + gm.astype(np.int32); reproj_sum = reproj_sum + dr; masks.append(gm)
    davg = (reproj_sum + dref) / (geo_sum + 1)
    final = photo & (geo_sum >= 3)
    h, w = dref.shape; x, y = np.meshgrid(np.arange(w), np.arange(h)); x, y, d = x[final], y[final], davg[final]
    xyz_ref = np.linalg.inv(Kr) @ (np.vstack((x, y, np.ones_like(x))) * d)
    xyz = (np.linalg.inv(Er) @ np.vstack((xyz_ref, np.ones_like(x))))[:3].T.astype(np.float32)
    col = (img[final] * 255).astype(np.uint8)
    vis = np.full((len(x), 1 + len(srcs)), -1, np.int16); vis[:, 0] = ref
    for j, (s, gm) in enumerate(zip(srcs, masks)): vis[gm[final], 1 + j] = s
    P.append(xyz); C.append(col); V.append(vis)
    print(f"ref {ref:3d} final {final.mean():.3f} pts {len(x)}", flush=True)
P = np.concatenate(P); C = np.concatenate(C); V = np.concatenate(V); print("official fused points", len(P), flush=True)
# ---- voxel merge with visibility union
lo = P.min(0); ijk = np.floor((P - lo) / VOX).astype(np.int64); dims = ijk.max(0) + 1
key = (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]
uk, inv = np.unique(key, return_inverse=True); M = len(uk); print(f"voxel {VOX*1000:.0f} mm -> {M} points", flush=True)
sumP = np.zeros((M, 3)); np.add.at(sumP, inv, P.astype(np.float64)); cnt = np.bincount(inv, minlength=M)
sumC = np.zeros((M, 3)); np.add.at(sumC, inv, C.astype(np.float64))
Pm = (sumP / cnt[:, None]).astype(np.float32); Cm = np.clip(sumC / cnt[:, None], 0, 255).astype(np.uint8)
nw = (NIMG + 63) // 64; bits = np.zeros((M, nw), np.uint64)
for j in range(V.shape[1]):
    col = V[:, j]; ok = col >= 0; idx = inv[ok]; im = col[ok].astype(np.int64)
    for wi in range(nw):
        sel = (im // 64) == wi
        np.bitwise_or.at(bits[:, wi], idx[sel], (np.uint64(1) << (im[sel] % 64).astype(np.uint64)))
vis_lists = []; counts = np.zeros(M, np.int64)
for wi in range(nw):
    for b in range(64):
        i = wi * 64 + b
        if i >= NIMG: break
        has = (bits[:, wi] >> np.uint64(b)) & np.uint64(1) == 1
        vis_lists.append((i, has)); counts += has
print("visibility per merged point: median", np.median(counts), "p10", np.percentile(counts, 10), "p90", np.percentile(counts, 90), flush=True)
# ---- write fused.ply (x y z nx ny nz r g b) + fused.ply.vis
WS.mkdir(parents=True, exist_ok=True)
with open(WS/"fused.ply", "wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\n"
             "property float nx\nproperty float ny\nproperty float nz\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % M).encode())
    rec = np.zeros(M, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("nx","<f4"),("ny","<f4"),("nz","<f4"),("r","u1"),("g","u1"),("b","u1")])
    rec["x"], rec["y"], rec["z"] = Pm[:,0], Pm[:,1], Pm[:,2]; rec["r"], rec["g"], rec["b"] = Cm[:,0], Cm[:,1], Cm[:,2]
    rec.tofile(f)
# per-point lists: build via sorting (point, image) pairs
pairs = np.concatenate([np.stack([np.nonzero(has)[0], np.full(int(has.sum()), i)], 1) for i, has in vis_lists])
pairs = pairs[np.argsort(pairs[:, 0], kind="stable")]
starts = np.searchsorted(pairs[:, 0], np.arange(M)); ends = np.searchsorted(pairs[:, 0], np.arange(M), side="right")
with open(WS/"fused.ply.vis", "wb") as f:
    f.write(np.uint64(M).tobytes())
    buf = np.empty(M + len(pairs), np.uint32); pos = 0; out_idx = 0
    # interleave: count then ids
    cnts = (ends - starts).astype(np.uint32); ids = pairs[:, 1].astype(np.uint32)
    # vectorized interleave
    total = M + len(pairs); marks = np.zeros(total, bool); cpos = np.concatenate([[0], np.cumsum((cnts + 1).astype(np.int64))[:-1]]).astype(np.int64); marks[cpos] = True
    buf[marks] = cnts; buf[~marks] = ids; buf.tofile(f)
np.save(WS/"merged_xyz.npy", Pm); np.save(WS/"merged_rgb.npy", Cm)
print("wrote", WS/"fused.ply", "and .vis;", M, "points", flush=True)
