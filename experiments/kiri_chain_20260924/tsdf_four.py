#!/usr/bin/env python3
# [2026-09-23] Four fusion-layer changes on top of the 09-17 ep0 TSDF recipe (/root/tsdf_ep_mesh.py).
# User: 「改这四点,然后跑一遍,出网页跟现在TSDF做对比」.
# Everything before and after integration is the old recipe verbatim: filter.py replay (geo 3 / 1 px / 1 %, photo .3/.5/.5,
# self-check 36,233,053 = pc.ply), 3 mm voxel, 40 mm truncation, block_res 16, colour integrated during fusion,
# extract_triangle_mesh(weight_threshold=1.0), drop clusters < 100 triangles, Taubin x10 + normals.
#
# Integration is a numpy port of Open3D's own kernel (cpp/open3d/t/geometry/kernel/VoxelBlockGridImpl.h:219-302 @b6c5e196),
# laid out like the official custom-integration example (examples/python/t_reconstruction_system/integrate_custom.py),
# with four switches:
#   --round    depth pixel association by rounding. Native kernel :254-255 truncates (static_cast<index_t>(u)); Open3D legacy
#              UniformTSDFVolume.cpp:450-460 adds 0.5 before the cast; integrate_custom.py:91-92 uses .round().
#              Implemented as floor(u + 0.5) (= the legacy form), bounds checked after rounding as in integrate_custom.py:97-98.
#   --dropoff  voxblox behind-surface linear weight drop-off, voxblox tsdf_integrator.cc:163-171 @c8066b04 (on by default,
#              tsdf_integrator.h:66): if sdf < -eps: w *= (trunc + sdf) / (trunc - eps), eps = voxel size, w = max(w, 0).
#   --invsq    voxblox 1/z^2 weight, tsdf_integrator.cc:231-240 (use_const_weight=false by default, tsdf_integrator.h:64);
#              z = camera z of the measured point = the depth reading.
#   --mveconf  MVE depth-map boundary confidence: the depth map is triangulated exactly as mve depthmap.cc:207-298
#              (2x2 blocks, >= 3 valid, shorter diagonal, depth discontinuity if ray-depth jump > 5 x pixel footprint,
#              x sqrt2 on diagonals; DD_FACTOR_DEFAULT depthmap.h:74); MeshInfo border vertices get 0, then 0.25 / 0.5 / 0.75
#              per ring (depthmap.cc:497-545, 4 iterations as scene2pset.cc:328); pixels that are not vertices of that mesh
#              yield no sample. FSSR multiplies the confidence into the value and colour weights (fssr/iso_octree.cc:146-152,
#              183-186); so do we.
# Gate kept identical to the old recipe: the 'weight' attribute is the observation count (+1 per update with w > 0), so
# extract_triangle_mesh(weight_threshold=1.0) still means ">= 2 observations". Weighted averages use a separate 'wsum'.
# With all four switches off, the port must reproduce the native kernel (stage `control` checks this, plus a negative
# control with all four on that must NOT reproduce it).
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import open3d as o3d
import open3d.core as o3c

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=["cache", "unittest", "control", "run"])
ap.add_argument("--repo", default="/root/diffmvs")
ap.add_argument("--pair_folder", default="/root/mvs_P16k")
ap.add_argument("--out_folder", default="/root/arm_full_ep0_tsdf")
ap.add_argument("--cache", default="/root/tsdf_improve/four/cache")
ap.add_argument("--out_dir", default="/root/tsdf_improve/four/out")
ap.add_argument("--tag", default="four")
ap.add_argument("--voxel", type=float, default=0.003)
ap.add_argument("--sdf_trunc", type=float, default=0.04)
ap.add_argument("--depth_scale", type=float, default=5000.0)
ap.add_argument("--depth_max", type=float, default=30.0)
ap.add_argument("--block_count", type=int, default=300000)
ap.add_argument("--block_res", type=int, default=16)
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--photo_thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
ap.add_argument("--dataset", default="general")
ap.add_argument("--expect_points", type=int, default=36233053)
ap.add_argument("--round", action="store_true")
ap.add_argument("--dropoff", action="store_true")
ap.add_argument("--invsq", action="store_true")
ap.add_argument("--mveconf", action="store_true")
ap.add_argument("--control_views", type=int, default=8)
ap.add_argument("--control_blocks", type=int, default=120000)
ap.add_argument("--chunk_blocks", type=int, default=1024)
ap.add_argument("--threads", type=int, default=12)
a = ap.parse_args()

CACHE = Path(a.cache)
OUT = Path(a.out_dir)
RES = a.block_res
R3 = RES ** 3
LIN = np.arange(R3, dtype=np.int64)
# voxel_idx -> (x, y, z), x fastest: GeometryIndexer.h:273-276
OFF = np.stack([LIN % RES, (LIN // RES) % RES, LIN // (RES * RES)], 1).astype(np.int64)
TRUNC_MULT = a.sdf_trunc / a.voxel
F32 = np.float32
SDF_TRUNC = F32(F32(TRUNC_MULT) * F32(a.voxel))      # VoxelBlockGrid::Integrate: trunc_voxel_multiplier * voxel_size_ (float)
EPS = F32(a.voxel)                                   # voxblox: dropoff_epsilon = voxel_size_
DS = F32(a.depth_scale)
DMAX = F32(a.depth_max)


def log(*x):
    print(time.strftime("%H:%M:%S"), *x, flush=True)


def rss_gb():
    with open("/proc/self/status") as f:
        for ln in f:
            if ln.startswith("VmRSS"):
                return int(ln.split()[1]) / 1e6
    return -1


# ----------------------------------------------------------------------------------------------------------- stage: cache
def stage_cache():
    """filter.py replay, verbatim from /root/tsdf_ep_mesh.py, written to disk once."""
    sys.path.insert(0, a.repo)
    os.chdir(a.repo)
    from datasets.data_io import read_pfm, read_camera_parameters, read_pair_file, read_img  # noqa: E402
    from filter import check_geometric_consistency  # noqa: E402
    import cv2
    CACHE.mkdir(parents=True, exist_ok=True)
    of = a.out_folder
    pair_data = read_pair_file(os.path.join(a.pair_folder, "pair.txt"), a.dataset)
    kept_total, order = 0, []
    for ref_view, src_views in pair_data:
        ref_intr, ref_extr, depth_max, depth_min = read_camera_parameters(
            os.path.join(of, "cams/{:0>8}_cam.txt".format(ref_view)))
        ref_img = read_img(os.path.join(of, "images/{:0>8}.jpg".format(ref_view)))
        ref_depth = read_pfm(os.path.join(of, "depth_est/{:0>8}.pfm".format(ref_view)))[0]
        c0 = read_pfm(os.path.join(of, "conf0/{:0>8}.pfm".format(ref_view)))[0]
        c1 = read_pfm(os.path.join(of, "conf1/{:0>8}.pfm".format(ref_view)))[0]
        c2 = read_pfm(os.path.join(of, "conf2/{:0>8}.pfm".format(ref_view)))[0]
        photo_mask = (c0 > a.photo_thres[0]) & (c1 > a.photo_thres[1]) & (c2 > a.photo_thres[2])
        acc, gsum = [], 0
        for src_view in src_views:
            src_intr, src_extr, _, _ = read_camera_parameters(
                os.path.join(of, "cams/{:0>8}_cam.txt".format(src_view)))
            src_depth = read_pfm(os.path.join(of, "depth_est/{:0>8}.pfm".format(src_view)))[0]
            geo_mask, depth_reproj, _, _ = check_geometric_consistency(
                ref_depth, ref_intr, ref_extr, src_depth, src_intr, src_extr,
                depth_max, depth_min, a.geo_pixel_thres, a.geo_depth_thres)
            gsum = gsum + geo_mask.astype(np.int32)
            acc.append(depth_reproj)
        depth_avg = (sum(acc) + ref_depth) / (gsum + 1)
        final_mask = np.logical_and(photo_mask, gsum >= a.geo_mask_thres)
        kept_total += int(final_mask.sum())
        if int(final_mask.sum()) == 0:
            log(f"view {ref_view}: no pixel survives the gate, skipped")
            continue
        d = np.where(final_mask, depth_avg, 0.0).astype(np.float64)
        d = np.where(d > a.depth_max, 0.0, d)
        d16 = np.round(d * a.depth_scale).astype(np.uint16)
        col = ref_img
        if col.dtype != np.uint8:
            col = np.clip(col * 255.0, 0, 255).astype(np.uint8)
        if col.shape[:2] != d16.shape:
            col = cv2.resize(col, (d16.shape[1], d16.shape[0]), interpolation=cv2.INTER_AREA)
        np.savez(CACHE / f"{ref_view:08d}.npz", d16=d16, col=np.ascontiguousarray(col),
                 intr=np.asarray(ref_intr, np.float64), extr=np.asarray(ref_extr, np.float64))
        order.append(int(ref_view))
        if ref_view % 20 == 0:
            log(f"view {ref_view}: kept {int(final_mask.sum()):,} running {kept_total:,}  shape {d16.shape}")
    log(f"replayed valid pixels: {kept_total:,}")
    if kept_total != a.expect_points:
        raise SystemExit(f"ABORT: replay kept {kept_total} but pc.ply has {a.expect_points}")
    (CACHE / "order.json").write_text(json.dumps({"order": order, "kept_total": kept_total}))
    log(f"self-check OK: identical to pc.ply ({a.expect_points:,}); {len(order)} views cached")


def load_view(v):
    z = np.load(CACHE / f"{v:08d}.npz")
    return z["d16"], z["col"], z["intr"], z["extr"]


# ------------------------------------------------------------------------------------------------- MVE boundary confidence
SQRT2 = F32(np.sqrt(2.0))
# local 2x2 vertex j -> pixel offset; j: 0=(x,y) 1=(x+1,y) 2=(x,y+1) 3=(x+1,y+1)  (depthmap.cc:171 `i + (j%2) + width*(j/2)`)
TRIS = {1: (0, 2, 1), 2: (0, 3, 1), 3: (0, 2, 3), 4: (1, 2, 3)}      # depthmap.cc:246-248


def mve_conf(z, K, dd_factor=5.0, iterations=4):
    """Per-pixel sample confidence as MVE/FSSR would assign it to this depth map (0 where MVE makes no sample)."""
    H, W = z.shape
    z = z.astype(np.float32)
    Kinv = np.linalg.inv(K.astype(np.float64))
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    rays = Kinv @ np.stack([xs.ravel(), ys.ravel(), np.ones(H * W)])
    nrm = np.linalg.norm(rays, axis=0).reshape(H, W).astype(np.float32)
    r = z * nrm                                   # MVE depth maps store distance along the ray (depthmap_convert_conventions)
    width = np.where(z > 0, r * F32(Kinv[0, 0]) / nrm, 0).astype(np.float32)   # pixel_footprint: invproj[0]*depth/|ray|
    sl = [(slice(0, -1), slice(0, -1)), (slice(0, -1), slice(1, None)), (slice(1, None), slice(0, -1)), (slice(1, None), slice(1, None))]
    D = [r[s] for s in sl]
    Wd = [width[s] for s in sl]
    V = [d > 0 for d in D]
    mask = V[0].astype(np.int32) + 2 * V[1] + 4 * V[2] + 8 * V[3]
    short02 = np.abs(D[0] - D[3]) < np.abs(D[1] - D[2])          # ddiff1 < ddiff2
    use = {1: (mask == 7) | ((mask == 15) & ~short02),
           2: (mask == 11) | ((mask == 15) & short02),
           3: (mask == 13) | ((mask == 15) & short02),
           4: (mask == 14) | ((mask == 15) & ~short02)}

    def disc(i1, i2):                                              # dm_is_depthdisc, depthmap.cc:188-205
        swap = D[i2] < D[i1]
        dmin = np.where(swap, D[i2], D[i1])
        dmax = np.where(swap, D[i1], D[i2])
        wmin = np.where(swap, Wd[i2], Wd[i1])
        f = F32(dd_factor) * (SQRT2 if i1 + i2 == 3 else F32(1.0))
        return (dmax - dmin) > wmin * f

    base = (np.arange(H - 1)[:, None] * W + np.arange(W - 1)[None, :]).astype(np.int64)
    offs = np.array([0, 1, W, W + 1], np.int64)
    faces = []
    for t, (p, q, s) in TRIS.items():
        keep = use[t] & ~disc(p, q) & ~disc(q, s) & ~disc(s, p)
        b = base[keep]
        faces.append(np.stack([b + offs[p], b + offs[q], b + offs[s]], 1))
    faces = np.concatenate(faces, 0)
    conf = np.zeros(H * W, np.float32)
    if len(faces) == 0:
        return conf.reshape(H, W), 0
    verts = np.unique(faces)
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], 0)
    e.sort(axis=1)
    ekey = e[:, 0] * (H * W) + e[:, 1]
    uk, cnt = np.unique(ekey, return_counts=True)
    ea, eb = uk // (H * W), uk % (H * W)
    bnd = cnt == 1
    nb = np.bincount(ea[bnd], minlength=H * W) + np.bincount(eb[bnd], minlength=H * W)
    # MeshInfo: one open fan -> BORDER (2 boundary spokes); several fans -> COMPLEX (>= 4); closed fan -> SIMPLE (0).
    # Depth-map triangulations are planar and consistently oriented (all four TRIS wind the same way), so the fan count is
    # nb / 2 and this equals the chaining in mesh_info.cc update_vertex.
    INF = 1 << 30
    dist = np.full(H * W, INF, np.int64)
    dist[verts[nb[verts] == 2]] = 0
    for k in range(1, iterations):
        fr = dist == k - 1
        nxt = np.zeros(H * W, bool)
        nxt[eb[fr[ea] & (dist[eb] == INF)]] = True
        nxt[ea[fr[eb] & (dist[ea] == INF)]] = True
        dist[nxt] = k
    conf[verts] = 1.0
    ring = verts[dist[verts] < iterations]
    conf[ring] = dist[ring].astype(np.float32) / F32(iterations)
    return conf.reshape(H, W), len(verts)


def stage_unittest():
    K = np.array([[500.0, 0, 50], [0, 500.0, 40], [0, 0, 1]])
    ok = True
    # 1) full plane: only the image-border ring is 0, rings .25/.5/.75, interior 1
    z = np.full((80, 100), 1.0, np.float32)
    c, nv = mve_conf(z, K)
    t1 = c[0, 50] == 0 and c[1, 50] == 0.25 and c[2, 50] == 0.5 and c[3, 50] == 0.75 and c[4, 50] == 1.0 and c[40, 50] == 1.0 and nv == 8000
    print("plane:", c[0:6, 50], "verts", nv, "PASS" if t1 else "FAIL"); ok &= t1
    # 2) single invalid pixel in the middle: it has conf 0 and so do its neighbours (they are border vertices); far away 1
    z2 = z.copy(); z2[40, 50] = 0
    c2, _ = mve_conf(z2, K)
    t2 = (c2[40, 50] == 0 and c2[40, 51] == 0 and c2[40, 49] == 0 and c2[40, 52] == 0.25 and c2[40, 53] == 0.5
          and c2[40, 54] == 0.75 and c2[40, 55] == 1.0)
    print("hole row:", c2[40, 46:56], "PASS" if t2 else "FAIL"); ok &= t2
    # 3) depth step of 0.5 m across a column: triangles across it are cut, a boundary forms on both sides
    z3 = z.copy(); z3[:, 50:] = 1.5
    c3, _ = mve_conf(z3, K)
    t3 = c3[40, 49] == 0 and c3[40, 50] == 0 and c3[40, 46] == 0.75 and c3[40, 45] == 1.0 and c3[40, 53] == 0.75
    print("step row:", c3[40, 44:55], "PASS" if t3 else "FAIL"); ok &= t3
    # 3b/3c) threshold itself: a 6-footprint step (> 5x) is cut, a 4-footprint step is not (footprint = z/fx = 0.002 m)
    z6 = z.copy(); z6[:, 50:] = 1.0 + 6 * 0.002
    z4s = z.copy(); z4s[:, 50:] = 1.0 + 4 * 0.002
    c6, _ = mve_conf(z6, K); c4s, _ = mve_conf(z4s, K)
    t3b = c6[40, 49] == 0 and c6[40, 50] == 0
    t3c = c4s[40, 49] == 1.0 and c4s[40, 50] == 1.0
    print("6x step conf at seam:", c6[40, 48:52], "PASS" if t3b else "FAIL"); ok &= t3b
    print("4x step conf at seam:", c4s[40, 48:52], "PASS" if t3c else "FAIL"); ok &= t3c
    # 4) negative control: a 1-footprint slope (below 5x) must NOT be cut
    z4 = (1.0 + np.arange(100)[None, :] * (1.0 / 500.0) * 1.0).astype(np.float32) * np.ones((80, 1), np.float32)
    c4, _ = mve_conf(z4, K)
    t4 = c4[40, 50] == 1.0
    print("gentle slope centre conf:", c4[40, 50], "PASS" if t4 else "FAIL"); ok &= t4
    # 5) isolated valid pixel makes no triangle -> no sample
    z5 = np.zeros((20, 20), np.float32); z5[10, 10] = 1.0
    c5, nv5 = mve_conf(z5, K)
    t5 = nv5 == 0 and c5[10, 10] == 0
    print("isolated pixel verts", nv5, "PASS" if t5 else "FAIL"); ok &= t5
    # numpy view of an Open3D attribute must share memory with the voxel block grid
    vbg = new_vbg_custom(1000)
    hm = vbg.hashmap()
    hm.activate(o3c.Tensor(np.array([[1, 2, 3]], np.int32)))
    buf, found = hm.find(o3c.Tensor(np.array([[1, 2, 3]], np.int32)))
    b = int(buf.numpy()[0])
    arr = vbg.attribute("tsdf").numpy().reshape(-1)
    arr[b * R3 + 7] = 0.625
    back = float(vbg.attribute("tsdf").numpy().reshape(-1)[b * R3 + 7])
    t6 = back == 0.625
    print("numpy view shares memory:", back, "PASS" if t6 else "FAIL"); ok &= t6
    print("ALL PASS" if ok else "SOME FAIL")
    if not ok:
        raise SystemExit(1)


# -------------------------------------------------------------------------------------------------------- integration
def new_vbg_native(block_count):
    return o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight", "color"),
                                         attr_dtypes=(o3c.float32, o3c.uint16, o3c.uint16),
                                         attr_channels=((1), (1), (3)), voxel_size=a.voxel, block_resolution=RES,
                                         block_count=block_count, device=o3c.Device("CPU:0"))


def new_vbg_custom(block_count):
    return o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight", "color", "wsum"),
                                         attr_dtypes=(o3c.float32, o3c.float32, o3c.float32, o3c.float32),
                                         attr_channels=((1), (1), (3), (1)), voxel_size=a.voxel, block_resolution=RES,
                                         block_count=block_count, device=o3c.Device("CPU:0"))


def o3d_inputs(d16, col, intr, extr):
    return (o3d.t.geometry.Image(o3c.Tensor(d16)), o3d.t.geometry.Image(o3c.Tensor(np.ascontiguousarray(col))),
            o3c.Tensor(np.asarray(intr, np.float64), o3c.float64), o3c.Tensor(np.asarray(extr, np.float64), o3c.float64))


def integrate_native(vbg, d16, col, intr, extr):
    dimg, cimg, it, et = o3d_inputs(d16, col, intr, extr)
    coords = vbg.compute_unique_block_coordinates(dimg, it, et, a.depth_scale, a.depth_max, TRUNC_MULT)
    vbg.integrate(coords, dimg, cimg, it, it, et, a.depth_scale, a.depth_max, TRUNC_MULT)


class Sw:
    def __init__(self, rnd, drop, invsq, mve):
        self.round, self.dropoff, self.invsq, self.mveconf = rnd, drop, invsq, mve

    @property
    def any(self):
        return self.round or self.dropoff or self.invsq or self.mveconf

    def __str__(self):
        return f"round={self.round} dropoff={self.dropoff} invsq={self.invsq} mveconf={self.mveconf}"


def integrate_custom(vbg, d16, col, intr, extr, sw, pool, stats):
    dimg, _, it, et = o3d_inputs(d16, col, intr, extr)
    coords = vbg.compute_unique_block_coordinates(dimg, it, et, a.depth_scale, a.depth_max, TRUNC_MULT)
    hm = vbg.hashmap()
    hm.activate(coords)
    buf, found = hm.find(coords)
    buf = buf.numpy().astype(np.int64)[found.numpy().astype(bool)]
    keys = hm.key_tensor().numpy()[buf].astype(np.int64)
    # views re-fetched after activate (a rehash would move the buffers)
    tsdf = vbg.attribute("tsdf").numpy().reshape(-1)
    wcnt = vbg.attribute("weight").numpy().reshape(-1)
    colr = vbg.attribute("color").numpy().reshape(-1, 3)
    wsum = vbg.attribute("wsum").numpy().reshape(-1)
    H, W = d16.shape
    E = np.asarray(extr, np.float64).astype(F32)                   # TransformIndexer stores float
    fx, fy, cx, cy = (F32(intr[0][0]), F32(intr[1][1]), F32(intr[0][2]), F32(intr[1][2]))
    conf = mve_conf(d16.astype(np.float32) / DS, np.asarray(intr, np.float64))[0] if sw.mveconf else None
    vox = F32(a.voxel)

    def work(sl):
        kb = keys[sl]
        vi = (kb[:, None, :] * RES + OFF[None, :, :]).reshape(-1, 3)
        flat = (buf[sl][:, None] * R3 + LIN[None, :]).reshape(-1)
        X = vi.astype(F32) * vox                                    # RigidTransform: x_in *= scale_
        x, y, z = X[:, 0], X[:, 1], X[:, 2]
        xc = x * E[0, 0] + y * E[0, 1] + z * E[0, 2] + E[0, 3]
        yc = x * E[1, 0] + y * E[1, 1] + z * E[1, 2] + E[1, 3]
        zc = x * E[2, 0] + y * E[2, 1] + z * E[2, 2] + E[2, 3]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            inv_z = F32(1.0) / zc                                   # Project: inv_z = 1/z; u = fx*x*inv_z + cx
            u = fx * xc * inv_z + cx
            v = fy * yc * inv_z + cy
            if sw.round:
                u = np.floor(u + F32(0.5))
                v = np.floor(v + F32(0.5))
            inb = (u >= 0) & (v >= 0) & (u <= F32(W - 1)) & (v <= F32(H - 1))
        idx = np.nonzero(inb)[0]
        ui = u[idx].astype(np.int64)                                # static_cast<index_t>: truncation
        vj = v[idx].astype(np.int64)
        depth = d16[vj, ui].astype(F32) / DS
        zz = zc[idx]
        sdf = depth - zz
        ok = (depth > 0) & (depth <= DMAX) & (zz > 0) & (sdf >= -SDF_TRUNC)
        idx, ui, vj, depth, sdf = idx[ok], ui[ok], vj[ok], depth[ok], sdf[ok]
        n_obs = len(idx)
        if sw.any:
            w = np.ones(len(idx), F32)
            if sw.invsq:
                w = F32(1.0) / (depth * depth)
            if sw.dropoff:
                m = sdf < -EPS
                w[m] = w[m] * (SDF_TRUNC + sdf[m]) / (SDF_TRUNC - EPS)
                w = np.maximum(w, F32(0.0))
            if sw.mveconf:
                w = w * conf[vj, ui]
            k = w > 0
            idx, ui, vj, sdf, w = idx[k], ui[k], vj[k], sdf[k], w[k]
        sdfn = np.minimum(sdf, SDF_TRUNC) / SDF_TRUNC
        f = flat[idx]
        c = col[vj, ui].astype(F32)
        if not sw.any:                                              # native kernel, verbatim arithmetic
            wt = wcnt[f]
            inv = F32(1.0) / (wt + F32(1.0))
            tsdf[f] = (wt * tsdf[f] + sdfn) * inv
            colr[f] = np.trunc((wt[:, None] * colr[f] + c) * inv[:, None])   # stored into uint16 upstream: truncation
            wcnt[f] = wt + F32(1.0)
        else:
            ws = wsum[f]
            wn = ws + w
            tsdf[f] = (tsdf[f] * ws + sdfn * w) / wn
            colr[f] = (colr[f] * ws[:, None] + c * w[:, None]) / wn[:, None]
            wsum[f] = wn
            wcnt[f] = wcnt[f] + F32(1.0)
        return n_obs, len(idx)

    nb = len(buf)
    sls = [slice(i, min(i + a.chunk_blocks, nb)) for i in range(0, nb, a.chunk_blocks)]
    res = list(pool.map(work, sls))
    stats["obs"] += sum(r[0] for r in res)
    stats["kept"] += sum(r[1] for r in res)
    stats["blocks_frame_max"] = max(stats.get("blocks_frame_max", 0), nb)


def dump(vbg, names):
    hm = vbg.hashmap()
    act = hm.active_buf_indices().numpy().astype(np.int64)
    keys = hm.key_tensor().numpy()[act]
    o = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    d = {"keys": keys[o]}
    for n in names:
        d[n] = vbg.attribute(n).numpy()[act[o]].astype(np.float32)
    return d


def stage_control():
    order = json.loads((CACHE / "order.json").read_text())["order"][: a.control_views]
    log(f"control on views {order}")
    pool = ThreadPoolExecutor(a.threads)
    vn = new_vbg_native(a.control_blocks)
    t = time.time()
    for v in order:
        integrate_native(vn, *load_view(v))
    log(f"native {time.time()-t:.1f}s blocks {vn.hashmap().size():,}")
    runs = {}
    for name, sw in (("port_all_off", Sw(False, False, False, False)), ("port_all_on", Sw(True, True, True, True))):
        vc = new_vbg_custom(a.control_blocks)
        st = {"obs": 0, "kept": 0}
        t = time.time()
        for v in order:
            integrate_custom(vc, *load_view(v), sw, pool, st)
        log(f"{name} ({sw}) {time.time()-t:.1f}s blocks {vc.hashmap().size():,} obs {st['obs']:,} kept {st['kept']:,}")
        runs[name] = vc
    A = dump(vn, ("tsdf", "weight", "color"))
    rep = {"views": order}
    for name, vc in runs.items():
        B = dump(vc, ("tsdf", "weight", "color"))
        same_keys = A["keys"].shape == B["keys"].shape and bool(np.array_equal(A["keys"], B["keys"]))
        r = {"same_block_set": same_keys}
        if same_keys:
            obs = A["weight"] > 0
            r["observed_voxels_native"] = int(obs.sum())
            r["observed_voxels_port"] = int((B["weight"] > 0).sum())
            r["weight_identical_frac"] = float((A["weight"] == B["weight"]).mean())
            both = obs & (B["weight"] > 0)
            dt = np.abs(A["tsdf"] - B["tsdf"])[both]
            r["tsdf_bit_identical_frac_on_observed"] = float((dt == 0).mean())
            r["tsdf_absdiff_p99_on_observed"] = float(np.percentile(dt, 99))
            r["tsdf_absdiff_max_on_observed"] = float(dt.max())
            r["color_identical_frac_on_observed"] = float((np.abs(A["color"] - B["color"]).max(axis=-1) == 0)[both[..., 0]].mean())
        rep[name] = r
        log(name, json.dumps(r))
    for name, vb in (("native", vn), ("port_all_off", runs["port_all_off"]), ("port_all_on", runs["port_all_on"])):
        m = vb.extract_triangle_mesh(weight_threshold=1.0)
        rep[f"mesh_{name}"] = [int(m.vertex.positions.shape[0]), int(m.triangle.indices.shape[0])]
        log(f"mesh {name}: {rep[f'mesh_{name}'][0]:,} v / {rep[f'mesh_{name}'][1]:,} t")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "control.json").write_text(json.dumps(rep, indent=2))
    log("control written", OUT / "control.json")


def stage_run():
    sw = Sw(a.round, a.dropoff, a.invsq, a.mveconf)
    OUT.mkdir(parents=True, exist_ok=True)
    order = json.loads((CACHE / "order.json").read_text())["order"]
    log(f"run {a.tag}: {sw}  views {len(order)}  voxel {a.voxel} trunc {a.sdf_trunc} (float32 trunc {SDF_TRUNC!r})")
    pool = ThreadPoolExecutor(a.threads)
    vbg = new_vbg_custom(a.block_count)
    st = {"obs": 0, "kept": 0}
    t0 = time.time()
    for i, v in enumerate(order):
        integrate_custom(vbg, *load_view(v), sw, pool, st)
        if i % 10 == 0 or i == len(order) - 1:
            log(f"  [{i+1}/{len(order)}] view {v} blocks {vbg.hashmap().size():,} obs {st['obs']:,} kept {st['kept']:,}"
                f"  {time.time()-t0:.0f}s  rss {rss_gb():.1f}GB")
    def counts(m): return f"{len(m.vertices):,} v / {len(m.triangles):,} t"
    t = time.time()
    mesh = vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy()
    log(f"[mc] {counts(mesh)} colours={mesh.has_vertex_colors()} {time.time()-t:.0f}s rss {rss_gb():.1f}GB")
    t = time.time()
    tc, cn, _ = mesh.cluster_connected_triangles()
    tc = np.asarray(tc); cn = np.asarray(cn)
    rm = cn[tc] < 100
    mesh.remove_triangles_by_mask(rm)
    log(f"[cc] clusters={len(cn):,} largest={cn.max():,} removed tris={int(rm.sum()):,} -> {counts(mesh)} {time.time()-t:.0f}s")
    t = time.time()
    mesh = mesh.filter_smooth_taubin(number_of_iterations=10)
    mesh.compute_vertex_normals()
    log(f"[taubin10+normals] {counts(mesh)} {time.time()-t:.0f}s")
    ply = OUT / f"tsdf_mesh_{a.tag}_v{a.voxel:g}_t{a.sdf_trunc:g}_nofill.ply"
    o3d.io.write_triangle_mesh(str(ply), mesh, write_ascii=False, compressed=False, write_vertex_normals=True, write_vertex_colors=True)
    res = {"purpose": "old ep0 TSDF recipe + four fusion changes", "switches": str(sw), "views": len(order),
           "voxel": a.voxel, "sdf_trunc": a.sdf_trunc, "block_res": RES, "open3d": o3d.__version__,
           "observations_in_band": st["obs"], "observations_integrated": st["kept"], "active_blocks": int(vbg.hashmap().size()),
           "vertices": len(mesh.vertices), "triangles": len(mesh.triangles), "ply": str(ply), "bytes": ply.stat().st_size,
           "seconds": round(time.time() - t0)}
    (OUT / f"result_{a.tag}.json").write_text(json.dumps(res, indent=2))
    log(json.dumps(res, indent=2))


if __name__ == "__main__":
    {"cache": stage_cache, "unittest": stage_unittest, "control": stage_control, "run": stage_run}[a.stage]()
