"""Run CasDiffMVS dense + geomcons fusion using SfM (COLMAP/GLOMAP) poses instead
of ARKit poses. Tests whether the cross-platform unified SfM poses (v4/v6/v7)
produce dense geometry as good as the ARKit-pose path.

K (pixel intrinsics) is SCALE-FREE, so we reuse the consistent ARKit per-frame K
(npz, normalized to 504x896) and only swap w2c + co-visibility + depth-range to
the SfM model. Fused cloud comes out in the SfM model's own world frame, then we
similarity-align it to the regular-COLMAP frame (shared camera centers) so all
versions overlay on one page.

Usage: pw_diffmvs_sfm.py MODEL_TXT_DIR OUT_TAG [METHOD] [GEO_MASK] [PHOTO] [NVIEW] [NEIGH]
"""
from __future__ import annotations
import sys, time, os
from pathlib import Path
import numpy as np
import cv2
import open3d as o3d
import pw_diffmvs_common as C
import pw_diffmvs_run as R

sys.path.insert(0, str(Path(__file__).resolve().parent / "diffmvs"))
from filter import check_geometric_consistency  # noqa: E402

NORMAL_COS = 0.5      # inlined from pw_diffmvs_geomcons (avoid its argv-at-import parsing)


def build_kmap():
    """ARKit per-frame K (manifest_idx -> K@512x896), from the npz windows."""
    _, wdef, _ = R._load_meta()
    Kmap = {}
    for win, wd in wdef.items():
        z = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            if mi not in Kmap:
                Kmap[mi] = R.scaled_K(z["K"][j])
    return Kmap


def world_normals(depth, K, w2c):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K[0, 2]) / K[0, 0] * depth
    y = (vv - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    n = np.cross(du, dv); ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    n[(np.sum(n * P, -1) > 0)] *= -1
    nw = n.reshape(-1, 3) @ w2c[:3, :3]
    return nw.reshape(H, W, 3).astype(np.float32)


def boundary_keep(depth, rel=0.03):
    gx = np.zeros_like(depth); gy = np.zeros_like(depth)
    gx[:, 1:-1] = np.abs(depth[:, 2:] - depth[:, :-2])
    gy[1:-1] = np.abs(depth[2:] - depth[:-2])
    grad = np.maximum(gx, gy)
    return (grad / np.maximum(depth, 1e-6) < rel) & (depth > 0)

MODEL = Path(sys.argv[1])
TAG = sys.argv[2]
METHOD = sys.argv[3] if len(sys.argv) > 3 else "casdiffmvs"
GEO_MASK = int(sys.argv[4]) if len(sys.argv) > 4 else 3
PHOTO = float(sys.argv[5]) if len(sys.argv) > 5 else 0.3
NVIEW = int(sys.argv[6]) if len(sys.argv) > 6 else 5
NEIGH = int(sys.argv[7]) if len(sys.argv) > 7 else 8
GEO_PIX, GEO_DEP = 1.0, 0.01
# --- pass-2 fusion tuning (env-overridable; all reuse the cached pass-1 depths) ---
GEO_PIX = float(os.environ.get("GEO_PIX", GEO_PIX))
GEO_DEP = float(os.environ.get("GEO_DEP", GEO_DEP))
NORMAL_COS = float(os.environ.get("NORMAL_COS", NORMAL_COS))     # ref/neighbor normal agreement
GRAZE_COS = float(os.environ.get("GRAZE_COS", 0.0))             # keep |n·viewray|>this; kills grazing floor curl; 0=off
BOUND_REL = float(os.environ.get("BOUND_REL", 0.03))           # depth-discontinuity boundary mask
CLEANUP = int(os.environ.get("CLEANUP", 1))                    # 1=statistical; 2=+radius; 3=+dbscan small-cluster
CACHE_TAG = os.environ.get("CACHE_TAG", "")                    # reuse another tag's pass-1 cache (skip re-inference)
OUT = R.OUT
P1CACHE = OUT / f"p1cache_sfm_{CACHE_TAG or TAG}.npz"   # CACHE_TAG lets a tuning run reuse another tag's pass-1 depths
SFM_CMP = Path(__file__).resolve().parent / "sfm_cmp"
COLMAP_IMAGES = SFM_CMP / "txt_colmap/images.txt"   # alignment target frame


def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    S, D = src - ms, dst - md
    U, d, Vt = np.linalg.svd(D.T @ S / len(src))
    Rr = U @ Vt
    if np.linalg.det(Rr) < 0:
        U[:, -1] *= -1; Rr = U @ Vt
    s = np.trace(np.diag(d)) / ((S ** 2).sum() / len(src))
    return s, Rr, md - s * Rr @ ms


def parse_colmap(mdir):
    """name -> w2c(4x4), name -> observed point3d ids; point3d id -> xyz."""
    w2c, obs = {}, {}
    L = [l for l in open(mdir / "images.txt") if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        name = p[9]
        Rm = quat_to_R(list(map(float, p[1:5]))); t = np.array(list(map(float, p[5:8])))
        W = np.eye(4); W[:3, :3] = Rm; W[:3, 3] = t
        w2c[name] = W
        toks = L[i + 1].split() if i + 1 < len(L) else []
        ids = toks[2::3]
        obs[name] = np.array([int(x) for x in ids if x != "-1"], dtype=np.int64)
    pid_xyz = {}
    for l in open(mdir / "points3D.txt"):
        if l.startswith("#") or not l.strip():
            continue
        p = l.split(); pid_xyz[int(p[0])] = np.array(list(map(float, p[1:4])))
    return w2c, obs, pid_xyz


def colmap_centers(images_txt):
    out = {}
    L = [l for l in open(images_txt) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        q = list(map(float, p[1:5])); t = np.array(list(map(float, p[5:8])))
        out[p[9]] = -quat_to_R(q).T @ t
    return out


def main():
    man, _, _ = R._load_meta()
    name2mi = {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}
    Kmap = build_kmap()                            # ARKit per-frame K (manifest_idx -> K@512x896)

    w2c_s, obs_s, pid_xyz = parse_colmap(MODEL)
    # use ALL SfM-registered frames (not just the ARKit-K subset). Frames lacking an
    # ARKit npz K reuse the shared phone intrinsics (same camera) -> +coverage, fewer holes.
    ALLFRAMES = int(os.environ.get("ALLFRAMES", 0))
    if ALLFRAMES:
        names = sorted(n for n in w2c_s if n in name2mi)
        Kmed = np.median(np.stack(list(Kmap.values())), axis=0)
        mi_of = {n: name2mi[n] for n in names}
        K_of = {n: (Kmap[mi_of[n]] if mi_of[n] in Kmap else Kmed) for n in names}
        print(f"SfM model {MODEL.name}: {len(w2c_s)} model frames -> {len(names)} (ALL frames, shared-K fallback)", flush=True)
    else:
        names = sorted(n for n in w2c_s if n in name2mi and name2mi[n] in Kmap)
        print(f"SfM model {MODEL.name}: {len(w2c_s)} model frames -> {len(names)} with ARKit-K (fair compare set)", flush=True)
        mi_of = {n: name2mi[n] for n in names}
        K_of = {n: Kmap[mi_of[n]] for n in names}
    w2c_of = {n: w2c_s[n].astype(np.float32) for n in names}
    center_of = {n: (-w2c_s[n][:3, :3].T @ w2c_s[n][:3, 3]) for n in names}

    def drange(n):
        ids = obs_s.get(n, [])
        X = np.array([pid_xyz[i] for i in ids if i in pid_xyz])
        if len(X) < 8:
            return 0.3, 4.0
        W = w2c_s[n]; z = (W[:3, :3] @ X.T + W[:3, 3:4]).T[:, 2]; z = z[z > 0.05]
        if len(z) < 8:
            return 0.3, 4.0
        lo, hi = np.percentile(z, 2), np.percentile(z, 99.5)
        return float(max(0.1, lo * 0.70)), float(hi * 1.5)

    def nearest(n, k, min_base=0.0):
        c0 = center_of[n]
        d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in names if m != n)
        return [m for dist, m in d if dist >= min_base][:k]

    def covis_select(n, k):                          # MVSNet triangulation-angle score on SfM points
        ref = obs_s.get(n)
        if ref is None or len(ref) < 8:
            return None
        ref_set = set(ref.tolist()); c_ref = center_of[n]; t0, s1, s2 = 5.0, 1.0, 10.0
        scored = []
        for m in names:
            if m == n:
                continue
            shared = ref_set & set(obs_s[m].tolist())
            if len(shared) < 5:
                continue
            P = np.array([pid_xyz[i] for i in shared if i in pid_xyz])
            if len(P) < 5:
                continue
            v1 = P - c_ref; v2 = P - center_of[m]
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

    # ---- pass 1: depth+conf per frame (SfM poses) ----
    depth, conf, drng = {}, {}, {}
    if P1CACHE.exists():
        z = np.load(P1CACHE, allow_pickle=True)
        fr = z["frames"].tolist()
        zd, zc, zr = z["depth"], z["conf"], z["drange"]   # materialize once (npz re-decompresses on every access)
        for i, n in enumerate(fr):
            depth[n] = zd[i].astype(np.float32); conf[n] = zc[i]
            drng[n] = tuple(zr[i])
        names = [n for n in names if n in depth]
        print(f"loaded pass1 cache {P1CACHE.name} ({len(names)})", flush=True)
    else:
        dev = C.pick_device("mps")
        model, _ = C.build_model(METHOD, dev)
        t0 = time.time()
        for i, n in enumerate(names):
            src = covis_select(n, NVIEW - 1) or nearest(n, NVIEW - 1, min_base=0.06)
            view = [n] + src
            imgs = [R.load_image(mi_of[m]).transpose(2, 0, 1) for m in view]
            Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
            dmin, dmax = drange(n); drng[n] = (dmin, dmax)
            proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
            d, c, _ = C.run_inference(model, imgs, proj, dv, dev)
            depth[n] = d.astype(np.float32); conf[n] = c.astype(np.float16)
            if i % 50 == 0:
                print(f"  depth {i}/{len(names)} {n} drange=[{dmin:.2f},{dmax:.2f}]", flush=True)
        print(f"pass1 done {time.time()-t0:.1f}s", flush=True)
        np.savez_compressed(P1CACHE,
                            depth=np.stack([depth[n].astype(np.float16) for n in names]),
                            conf=np.stack([conf[n] for n in names]),
                            drange=np.array([drng[n] for n in names], np.float32),
                            frames=np.array(names))

    # ---- pass 2: geomcons fusion (in SfM model frame) ----
    def getnrm(m):
        return world_normals(depth[m], K_of[m].astype(np.float64), w2c_of[m].astype(np.float64))

    pts, cols, kept = [], [], []
    for n in names:
        d_ref = depth[n]; K_ref = K_of[n].astype(np.float64); ext_ref = w2c_of[n].astype(np.float64)
        dmin, dmax = drng[n]; n_ref = getnrm(n)
        geo_sum = np.zeros_like(d_ref, np.int32); depth_acc = d_ref.copy()
        for nb in nearest(n, NEIGH, min_base=0.04):
            mask, depth_reproj, x2d, y2d = check_geometric_consistency(
                d_ref, K_ref, ext_ref, depth[nb], K_of[nb].astype(np.float64),
                w2c_of[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
            nb_n = cv2.remap(getnrm(nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
            mask = mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)
            geo_sum += mask.astype(np.int32); depth_acc += depth_reproj * mask
        img = (R.load_image(mi_of[n]) * 255).astype(np.uint8)
        # grazing-angle gate: drop pixels whose surface faces too obliquely to the
        # camera ray (the curling/floating floor edges at grazing incidence)
        if GRAZE_COS > 0:
            Hh, Ww = d_ref.shape
            uu0, vv0 = np.meshgrid(np.arange(Ww), np.arange(Hh))
            ray = np.stack([(uu0 - K_ref[0, 2]) / K_ref[0, 0],
                            (vv0 - K_ref[1, 2]) / K_ref[1, 1], np.ones_like(d_ref)], -1)
            ray /= np.linalg.norm(ray, axis=2, keepdims=True)
            n_cam = np.einsum('ij,hwj->hwi', ext_ref[:3, :3], n_ref)   # world->cam normal
            graze_mask = np.abs(np.sum(n_cam * ray, axis=2)) > GRAZE_COS
        else:
            graze_mask = np.ones_like(d_ref, bool)
        final = (geo_sum >= GEO_MASK) & (conf[n].astype(np.float32) > PHOTO) & boundary_keep(d_ref, BOUND_REL) & graze_mask
        kept.append(final.mean())
        d_avg = depth_acc / (geo_sum + 1)
        H, W = d_ref.shape
        uu, vv = np.meshgrid(np.arange(W), np.arange(H))
        x = (uu - K_ref[0, 2]) / K_ref[0, 0] * d_avg
        y = (vv - K_ref[1, 2]) / K_ref[1, 1] * d_avg
        cam = np.stack([x, y, d_avg], -1)[final]
        Rr, t = ext_ref[:3, :3], ext_ref[:3, 3]
        pts.append(((Rr.T @ (cam.T - t[:, None])).T).astype(np.float32)); cols.append(img[final])
    P = np.concatenate(pts); Cc = np.concatenate(cols)
    print(f"fused (SfM poses, g={GEO_MASK} p={PHOTO}): {len(P):,} pts kept/frame={np.mean(kept)*100:.1f}%", flush=True)

    # ---- similarity-align SfM-frame cloud -> regular-COLMAP frame ----
    cC = colmap_centers(COLMAP_IMAGES)
    common = [n for n in names if n in cC]
    s, Rm, t = umeyama(np.array([center_of[n] for n in common]), np.array([cC[n] for n in common]))
    resid = np.median(np.linalg.norm((s * (Rm @ np.array([center_of[n] for n in common]).T).T + t)
                                     - np.array([cC[n] for n in common]), axis=1))
    print(f"align->COLMAP: common={len(common)} scale={s:.3f} resid={resid:.4f}", flush=True)
    Pa = (s * (Rm @ P.T).T + t).astype(np.float64)

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(Pa)
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc = pc.voxel_down_sample(0.005)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    if CLEANUP >= 2:                                            # radius outlier: kills isolated floaters
        pc, _ = pc.remove_radius_outlier(nb_points=8, radius=0.02)
        print(f"  after radius-outlier: {len(pc.points):,}", flush=True)
    if CLEANUP >= 3:                                            # drop small floating clusters (DBSCAN)
        lbl = np.array(pc.cluster_dbscan(eps=0.02, min_points=10))
        if lbl.max() >= 0:
            import collections
            big = {k for k, v in collections.Counter(lbl[lbl >= 0]).items() if v >= 300}
            sel = np.where(np.array([l in big for l in lbl]))[0]
            pc = pc.select_by_index(sel)
            print(f"  after cluster-filter: {len(pc.points):,} ({len(big)} clusters kept)", flush=True)
    plyp = OUT / f"fused_sfm_{TAG}.ply"; o3d.io.write_point_cloud(str(plyp), pc)
    print(f"wrote {plyp.name}: {len(pc.points):,} pts (in COLMAP frame)", flush=True)


if __name__ == "__main__":
    main()
