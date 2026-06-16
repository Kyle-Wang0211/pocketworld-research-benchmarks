"""DiffMVS depth + DiffMVS's OWN geometric-consistency fusion (filter.py).

Pipeline (the standard learned-MVS -> point cloud path):
  1. compute a DiffMVS depth+conf for EVERY unique frame (ref = frame, N nearest
     min-baseline sources), on MPS.
  2. for each ref frame, cross-check its depth against its M nearest neighbors'
     depths via filter.check_geometric_consistency (reproj<geo_pixel_thres &
     rel-depth<geo_depth_thres). Keep pixels confirmed by >= geo_mask_thres views
     AND conf > photo_thres. Average the confirmed depths (filter.py behaviour).
  3. backproject kept pixels -> world cloud (color from ref image).

Usage: pw_diffmvs_geomcons.py GEO_MASK_THRES PHOTO_THRES GEO_PIX GEO_DEPTH NVIEW NEIGH
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
import open3d as o3d
import pw_diffmvs_common as C
import pw_diffmvs_run as R

sys.path.insert(0, str(Path(__file__).resolve().parent / "diffmvs"))
from filter import check_geometric_consistency  # noqa: E402

GEO_MASK = int(sys.argv[1]) if len(sys.argv) > 1 else 3      # views that must confirm
PHOTO = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3
GEO_PIX = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
GEO_DEP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
NVIEW = int(sys.argv[5]) if len(sys.argv) > 5 else 5
NEIGH = int(sys.argv[6]) if len(sys.argv) > 6 else 8
METHOD = sys.argv[7] if len(sys.argv) > 7 else "diffmvs"
OVEREXP = int(sys.argv[8]) if len(sys.argv) > 8 else 0   # 1 = drop near-saturated (overexposed) pixels
OVEREXP_THR = 245                                        # luma 0-255; above => overexposed
OUT = R.OUT
TAG = f"{METHOD}_geocons_g{GEO_MASK}_p{PHOTO}" + (f"_oe" if OVEREXP else "")
P1CACHE = OUT / f"p1cache_{METHOD}.npz"                  # pass-1 depths cached for fast threshold sweeps


def build_frame_table():
    man, wdef, _ = R._load_meta()
    Kmap, wmap, srcimg = {}, {}, {}
    for win, wd in wdef.items():
        z = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            if mi not in Kmap:
                Kmap[mi] = R.scaled_K(z["K"][j]); wmap[mi] = z["w2c"][j].astype(np.float32)
    frames = sorted(Kmap)
    centers = {mi: R.cam_center(wmap[mi]) for mi in frames}
    return frames, Kmap, wmap, centers


def nearest(frames, centers, ref, k, min_base=0.0):
    c0 = centers[ref]
    d = sorted(((np.linalg.norm(centers[m] - c0), m) for m in frames if m != ref))
    out = [m for dist, m in d if dist >= min_base]
    return out[:k]


_ANCH = None
def _load_anchors():
    """per-frame set of observed SfM anchor ids + anchor world points (co-visibility)."""
    global _ANCH
    if _ANCH is None:
        from collections import defaultdict
        A = np.load(R.ANCH)
        pts, obsf, obsa = A["pts"], A["obs_frame"], A["obs_aidx"]
        f2a = defaultdict(set)
        for f, a in zip(obsf.tolist(), obsa.tolist()):
            f2a[f].add(a)
        _ANCH = (pts, {k: np.array(sorted(v)) for k, v in f2a.items()})
    return _ANCH


def covis_select(ref_mi, frames, centers, k):
    """MVSNet view-selection: rank src frames by sum over shared SfM points of a
    piecewise-Gaussian on triangulation angle (peak ~5deg). Returns None if too few
    anchors (caller falls back to nearest)."""
    pts, f2a = _load_anchors()
    ref_set = f2a.get(ref_mi)
    if ref_set is None or len(ref_set) < 8:
        return None
    c_ref = centers[ref_mi]; t0, s1, s2 = 5.0, 1.0, 10.0
    scored = []
    for m in frames:
        if m == ref_mi or m not in f2a:
            continue
        shared = np.intersect1d(ref_set, f2a[m], assume_unique=True)
        if len(shared) < 5:
            continue
        P = pts[shared]
        v1 = P - c_ref; v2 = P - centers[m]
        v1 /= np.linalg.norm(v1, axis=1, keepdims=True) + 1e-9
        v2 /= np.linalg.norm(v2, axis=1, keepdims=True) + 1e-9
        ang = np.degrees(np.arccos(np.clip((v1 * v2).sum(1), -1, 1)))
        sc = np.where(ang <= t0, np.exp(-(ang - t0) ** 2 / (2 * s1 ** 2)),
                      np.exp(-(ang - t0) ** 2 / (2 * s2 ** 2)))
        scored.append((float(sc.sum()), m))
    if len(scored) < k:
        return None
    scored.sort(reverse=True)
    return [m for _, m in scored[:k]]


NORMAL_COS = 0.5    # cross-view world-normal agreement (cos60deg); below => reject
BOUND_REL = 0.03    # depth jump >3%/2px => occlusion boundary => drop (kills flying pixels)


def world_normals(depth, K, w2c):
    """per-pixel world-space normal from a depth map (camera normal -> world via R^T)."""
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K[0, 2]) / K[0, 0] * depth
    y = (vv - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    n = np.cross(du, dv); ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    n[(np.sum(n * P, -1) > 0)] *= -1                      # face the camera
    nw = n.reshape(-1, 3) @ w2c[:3, :3]                   # n_cam @ R == R^T n_cam == world
    return nw.reshape(H, W, 3).astype(np.float32)


def boundary_keep(depth, rel=BOUND_REL):
    """True = keep; drop occlusion-boundary pixels (large relative depth gradient)."""
    gx = np.zeros_like(depth); gy = np.zeros_like(depth)
    gx[:, 1:-1] = np.abs(depth[:, 2:] - depth[:, :-2])
    gy[1:-1] = np.abs(depth[2:] - depth[:-2])
    grad = np.maximum(gx, gy)
    return (grad / np.maximum(depth, 1e-6) < rel) & (depth > 0)


def main():
    frames, Kmap, wmap, centers = build_frame_table()
    print(f"frames={len(frames)} method={METHOD}", flush=True)

    # ---- pass 1: depth+conf for every frame (cached for fast threshold sweeps) ----
    depth, conf, drange = {}, {}, {}
    if P1CACHE.exists():
        z = np.load(P1CACHE, allow_pickle=True)
        D, Cf, fr = z["depth"], z["conf"], z["frames"].tolist()
        dr = z["drange"]
        for i, mi in enumerate(fr):
            depth[mi] = D[i].astype(np.float32); conf[mi] = Cf[i]; drange[mi] = tuple(dr[i])
        frames = fr
        print(f"loaded pass1 cache {P1CACHE.name} ({len(frames)} frames)", flush=True)
    else:
        dev = C.pick_device("mps")
        model, _ = C.build_model(METHOD, dev)
        t0 = time.time()
        for i, mi in enumerate(frames):
            src = covis_select(mi, frames, centers, NVIEW - 1) \
                or nearest(frames, centers, mi, NVIEW - 1, min_base=0.06)
            view = [mi] + src
            imgs = [R.load_image(m).transpose(2, 0, 1) for m in view]
            Ks = np.stack([Kmap[m] for m in view]); w2cs = np.stack([wmap[m] for m in view])
            dmin, dmax = R.metric_depth_range(mi, w2cs[0]); drange[mi] = (dmin, dmax)
            proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
            d, c, _ = C.run_inference(model, imgs, proj, dv, dev)
            depth[mi] = d.astype(np.float32); conf[mi] = c.astype(np.float16)
            if i % 50 == 0:
                print(f"  depth {i}/{len(frames)}", flush=True)
        print(f"pass1 depths done {time.time()-t0:.1f}s", flush=True)
        np.savez_compressed(P1CACHE,
                            depth=np.stack([depth[m].astype(np.float16) for m in frames]),
                            conf=np.stack([conf[m] for m in frames]),
                            drange=np.array([drange[m] for m in frames], np.float32),
                            frames=np.array(frames))
        print(f"saved pass1 cache {P1CACHE.name}", flush=True)

    # ---- pass 2: geometric-consistency fusion (+ normal gate + boundary mask) ----
    import cv2
    def getnrm(m):  # recompute (cheap) to keep memory bounded vs caching all 317
        return world_normals(depth[m], Kmap[m].astype(np.float64), wmap[m].astype(np.float64))

    pts, cols = [], []
    kept_frac = []
    for mi in frames:
        d_ref = depth[mi]; K_ref = Kmap[mi].astype(np.float64)
        ext_ref = wmap[mi].astype(np.float64)
        dmin, dmax = drange[mi]
        n_ref = getnrm(mi)
        geo_sum = np.zeros_like(d_ref, np.int32)
        depth_acc = d_ref.copy()
        for nb in nearest(frames, centers, mi, NEIGH, min_base=0.04):
            mask, depth_reproj, x2d_src, y2d_src = check_geometric_consistency(
                d_ref, K_ref, ext_ref, depth[nb], Kmap[nb].astype(np.float64),
                wmap[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
            # normal-consistency: sample src world-normal at the reprojected pixel,
            # require agreement with ref normal (COLMAP's 3rd fusion criterion)
            nb_n = cv2.remap(getnrm(nb), x2d_src, y2d_src, interpolation=cv2.INTER_LINEAR)
            ndot = np.sum(n_ref * nb_n, axis=2)
            mask = mask & (ndot > NORMAL_COS)
            geo_sum += mask.astype(np.int32)
            depth_acc += depth_reproj * mask
        img = (R.load_image(mi) * 255).astype(np.uint8)
        photo_mask = conf[mi].astype(np.float32) > PHOTO
        final = (geo_sum >= GEO_MASK) & photo_mask & boundary_keep(d_ref)
        if OVEREXP:
            luma = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114])
            final = final & (luma < OVEREXP_THR)        # drop near-saturated (overexposed) pixels
        kept_frac.append(final.mean())
        d_avg = depth_acc / (geo_sum + 1)
        H, W = d_ref.shape
        uu, vv = np.meshgrid(np.arange(W), np.arange(H))
        x = (uu - K_ref[0, 2]) / K_ref[0, 0] * d_avg
        y = (vv - K_ref[1, 2]) / K_ref[1, 1] * d_avg
        cam = np.stack([x, y, d_avg], -1)[final]
        Rr, t = ext_ref[:3, :3], ext_ref[:3, 3]
        world = (Rr.T @ (cam.T - t[:, None])).T
        pts.append(world.astype(np.float32)); cols.append(img[final])
    P = np.concatenate(pts); Cc = np.concatenate(cols)
    print(f"fused (geomcons g={GEO_MASK} p={PHOTO}): {len(P):,} pts  mean-kept/frame={np.mean(kept_frac)*100:.1f}%",
          flush=True)

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(P.astype(np.float64))
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc = pc.voxel_down_sample(0.005)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"after voxel5mm+outlier: {len(pc.points):,}", flush=True)

    # floor flatness
    m, inl = pc.segment_plane(0.01, 3, 2000)
    n = np.array(m[:3]); n /= np.linalg.norm(n)
    xyz = np.asarray(pc.points); dist = np.abs(xyz @ n + m[3])
    print(f"floor normal={n.round(3)} RMS={np.sqrt(np.mean(dist[inl]**2))*1000:.1f}mm inliers={len(inl):,}",
          flush=True)

    plyp = OUT / f"fused_{TAG}.ply"; o3d.io.write_point_cloud(str(plyp), pc)
    cc = np.mean([centers[m] for m in frames], axis=0)
    pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30))
    pc.orient_normals_towards_camera_location(cc.astype(np.float64))
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pc, depth=10, scale=1.1, linear_fit=True, n_threads=1)
    dens = np.asarray(dens); mesh.remove_vertices_by_mask(dens < np.quantile(dens, 0.05))
    mp = OUT / f"mesh_{TAG}.ply"; o3d.io.write_triangle_mesh(str(mp), mesh)
    print(f"OK mesh verts={len(mesh.vertices):,} tris={len(mesh.triangles):,} -> {mp.name}", flush=True)


if __name__ == "__main__":
    main()
