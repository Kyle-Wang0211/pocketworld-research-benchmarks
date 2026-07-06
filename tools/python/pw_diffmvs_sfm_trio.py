"""Controlled 3-way dense run: same CasDiffMVS pipeline, three SfM pose sources.

For each of three COLMAP binary models (base / p4354 / ftol) of the SAME 414-frame
capture, run the exact casdiffmvs + geomcons(g3 p0.3) recipe with poses+intrinsics+
depth-ranges read from THAT model (pycolmap). Everything else is held fixed:
  - identical reference subset: every 4th frame of the sorted intersection of
    frames registered in ALL THREE models (413 -> 104 refs), spatial-manifest order
  - identical source-view selection LOGIC (covis MVSNet score, fallback nearest
    with metric min-baseline 6cm), identical fusion params (NVIEW=5, NEIGH=8,
    GEO_PIX=1.0, GEO_DEP=0.01, geo>=3, conf>0.3, NORMAL_COS=0.5, BOUND_REL=0.03)
  - identical images (896x512), device (MPS), cleanup (voxel 5mm + stat outlier)
    -- cleanup and export are done AFTER robust-umeyama alignment into the ARKit
    metric frame, so thresholds are physically identical across models.
  - baseline gates (0.06 / 0.04 m) are converted into each model's own units via
    its umeyama scale so they are metrically identical too.

Usage: KMP_DUPLICATE_LIB_OK=TRUE python3.11 pw_diffmvs_sfm_trio.py TAG [REF_LIMIT]
  TAG in {base, p4354, ftol};  REF_LIMIT (int) = only first N refs (smoke test).
"""
from __future__ import annotations
import os, sys, json, time
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from pathlib import Path
import numpy as np
import cv2
import open3d as o3d
import pw_diffmvs_common as C
import pw_diffmvs_run as R
# NOTE: pycolmap is NOT imported here -- it cannot share a process with torch on
# this Mac (duplicate libomp -> SIGSEGV). Run pw_diffmvs_sfm_trio_dump.py first.

sys.path.insert(0, str(Path(__file__).resolve().parent / "diffmvs"))
from filter import check_geometric_consistency  # noqa: E402

SCRATCH = Path("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/"
               "7fc69efe-e09c-4359-8afb-04378874d3a1/scratchpad")
sys.path.insert(0, str(SCRATCH))
import geom_metrics as g  # noqa: E402  (arkit_centers_and_R + umeyama, proven)

MODELS = {
    "base":  SCRATCH / "jfix/recon_gc",
    "p4354": Path("/private/tmp/knife4354/C4354/0"),
    "ftol":  Path("/private/tmp/knifeFTOL/FT2b/0"),
    "f0b":   Path("/private/tmp/knifeFTOL/F0b/0"),   # 现行认证配置(归因A)
    "ft0":   Path("/private/tmp/knifeFT0/FT0/0"),    # 内部ftol1e-4+收尾满BA(归因B)
    "r3":    Path("/private/tmp/knifeR3/R3/0"),      # FT2快配置+rounds=3(归因C)
    "lapa":  Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 新认证+DENSE_SCHUR/LAPACK收尾
    "r3b":   Path("/private/tmp/knifeR3cert/R3b/0"),    # 新认证复跑 rounds3+ftol
    "g1":    Path("/private/tmp/knifeG12/G1/0"),     # 冠军组合+收尾ftol1e-7深收敛
    "g2":    Path("/private/tmp/knifeG12/G2/0"),     # G1+内部ftol1e-5金级
    "piter": Path("/private/tmp/knifePITER/PITER/0"),  # 冠军组合+内部换回金时代ITER+SJ
    "r4":    Path("/private/tmp/knifeR3cert/R4/0"),  # rounds=4
    "r5":    Path("/private/tmp/knifeR3cert/R5/0"),  # rounds=5
    "lapatight": Path("/private/tmp/lapa_tight"),    # LAPa后置紧过滤(151k稀疏点)
    "ss":    Path("/private/tmp/knifeSS/SS/0"),      # 冠军配方+CHOLMOD/SuiteSparse收尾(金指纹)
    "grav":  Path("/private/tmp/knifeGRAV/GRAV/0"),  # 冠军配方+ARKit重力RA+flip修复
    "ann":   Path("/private/tmp/knifeNIGHT/ANN/0"),  # 冠军配方+逐轮loss退火2→1→0.5
    "champrot5": Path("/private/tmp/knifeTH/CHAMP_ROT5/0"),  # 阈值标定保守:旋转过滤10°→5°
    "combora3":  Path("/private/tmp/knifeTH/COMBO_RA3/0"),   # 阈值标定激进:旋转5°+track角度门×0.66
    "fingold":   Path("/private/tmp/knifeFIN/FIN_GOLD/0"),   # 金收尾复刻:金B0+CHOLMOD/SuiteSparse+ftol0+3x100
    "finlapdeep":Path("/private/tmp/knifeFIN/FIN_LAPDEEP/0"),# 金B0+DENSE_SCHUR/LAPACK+ftol0+3x100(隔离深度)
    "baseredense": SCRATCH / "jfix/recon_gc",               # 对照1:今日管线重稠密化EXACT金稀疏recon_gc(应≈mvs_base)
    "baseredense2": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第2次独立稠密(MPS推理+融合抽样非确定性)
    "baseredense3": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第3次独立稠密(MPS推理+融合抽样非确定性)
    # ---- 稠密融合严格度扫描(唯一变量=融合门;复用金/冠军 p1cache 跳过 MPS 重推理)----
    "strictgoldp5":    SCRATCH / "jfix/recon_gc",          # 金 recon_gc + PHOTO0.5(其余同金)
    "strictgoldg4p4":  SCRATCH / "jfix/recon_gc",          # 金 recon_gc + PHOTO0.4 + GEO_MASK4
    "strictchampp5":   Path("/private/tmp/knifeLAPcert/LAPa/0"),   # 冠军 lapa + PHOTO0.5
    "strictchampg4p4": Path("/private/tmp/knifeLAPcert/LAPa/0"),   # 冠军 lapa + PHOTO0.4 + GEO_MASK4
}
# 严格度扫描的每档融合门(源自复用 base/lapa 的 p1cache,推理冻结;仅 pass2 变)
STRICT = {
    "strictgoldp5":    {"src": "base", "PHOTO": 0.5, "GEO_MASK": 3},
    "strictgoldg4p4":  {"src": "base", "PHOTO": 0.4, "GEO_MASK": 4},
    "strictchampp5":   {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3},
    "strictchampg4p4": {"src": "lapa", "PHOTO": 0.4, "GEO_MASK": 4},
}
VIEWER_PLY = {"base": "mvs_base.ply", "p4354": "mvs_4354.ply", "ftol": "mvs_ftol.ply",
              "f0b": "mvs_f0b.ply", "ft0": "mvs_ft0.ply", "r3": "mvs_r3.ply",
              "lapa": "mvs_lapa.ply", "r3b": "mvs_r3b.ply",
              "g1": "mvs_g1.ply", "g2": "mvs_g2.ply", "piter": "mvs_piter.ply",
              "r4": "mvs_r4.ply", "r5": "mvs_r5.ply", "lapatight": "mvs_lapatight.ply",
              "ss": "mvs_ss.ply", "grav": "mvs_grav.ply", "ann": "mvs_ann.ply",
              "champrot5": "mvs_champrot5.ply", "combora3": "mvs_combora3.ply",
              "fingold": "mvs_fingold.ply", "finlapdeep": "mvs_finlapdeep.ply",
              "baseredense": "mvs_baseredense.ply",
              "baseredense2": "mvs_baseredense2.ply",
              "baseredense3": "mvs_baseredense3.ply",
              "strictgoldp5": "mvs_strictgoldp5.ply",
              "strictgoldg4p4": "mvs_strictgoldg4p4.ply",
              "strictchampp5": "mvs_strictchampp5.ply",
              "strictchampg4p4": "mvs_strictchampg4p4.ply"}
OUTDIR = Path(os.path.expanduser("~/Desktop/tiled_414_viewer"))
OUT = R.OUT
FULL_W, FULL_H = 4224, 2376
PROC_W, PROC_H = R.PROC_W, R.PROC_H            # 896 x 512
METHOD = "casdiffmvs"
NVIEW, NEIGH = 5, 8
GEO_MASK, PHOTO, GEO_PIX, GEO_DEP = 3, 0.3, 1.0, 0.01
NORMAL_COS, BOUND_REL = 0.5, 0.03
MIN_BASE_SRC_M, MIN_BASE_FUSE_M = 0.06, 0.04   # metres (converted to model units)
REF_STRIDE = 4
REFS_JSON = OUT / "trio_refs.json"


def name2mi_map():
    man, _, _ = R._load_meta()
    return {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}


def load_model(tag: str):
    """Read the torch-free dump produced by pw_diffmvs_sfm_trio_dump.py."""
    z = np.load(OUT / f"trio_model_{tag}.npz", allow_pickle=False)
    names = z["names"].tolist()
    K_of = {n: z["K"][i] for i, n in enumerate(names)}
    w2c_of = {n: z["w2c"][i] for i, n in enumerate(names)}
    center_of = {n: z["centers"][i] for i, n in enumerate(names)}
    off = z["obs_off"]; idx = z["obs_idx"]
    obs = {n: idx[off[i]:off[i + 1]] for i, n in enumerate(names)}
    pts = z["pts"]                                 # (P,3): obs are indices into pts
    return names, K_of, w2c_of, center_of, obs, pts


def robust_align(center_of, ark):
    """Trimmed umeyama model camera centers -> ARKit centers (align_export_ab logic)."""
    common = sorted(set(center_of) & set(ark))
    src = np.array([center_of[n] for n in common])
    dst = np.array([ark[n][0] for n in common])
    keep = np.ones(len(src), bool)
    for _ in range(8):
        s, Rm, t = g.umeyama(src[keep], dst[keep])
        res = np.linalg.norm((s * (Rm @ src.T).T + t) - dst, axis=1)
        thr = np.median(res[keep]) * 3 + 1e-9
        nk = res < thr
        if nk.sum() == keep.sum() or nk.sum() < 50:
            keep = nk; break
        keep = nk
    s, Rm, t = g.umeyama(src[keep], dst[keep])
    res = np.linalg.norm((s * (Rm @ src.T).T + t) - dst, axis=1)
    print(f"align->ARKit: common={len(common)} inliers={int(keep.sum())} "
          f"scale={s:.4f} med_resid={np.median(res)*1000:.1f}mm", flush=True)
    return s, Rm, t


def build_refs():
    """Fixed ref subset shared by all three runs (written by the dump script)."""
    assert REFS_JSON.exists(), "run pw_diffmvs_sfm_trio_dump.py first"
    d = json.load(open(REFS_JSON))
    return d["pool"], d["refs"]


def covis_select(n, pool, center_of, obs_set, obs, pts_arr, k):
    """MVSNet triangulation-angle view score on the model's own sparse points
    (verbatim logic from pw_diffmvs_sfm.py)."""
    ref = obs.get(n)
    if ref is None or len(ref) < 8:
        return None
    ref_set = obs_set[n]; c_ref = center_of[n]; t0, s1, s2 = 5.0, 1.0, 10.0
    scored = []
    for m in pool:
        if m == n:
            continue
        shared = ref_set & obs_set[m]
        if len(shared) < 5:
            continue
        P = pts_arr[np.fromiter(shared, np.int64, len(shared))]
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


def world_normals(depth, K, w2c):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K[0, 2]) / K[0, 0] * depth
    y = (vv - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    nrm = np.cross(du, dv); ln = np.linalg.norm(nrm, axis=-1, keepdims=True)
    nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 1e-9)
    nrm[(np.sum(nrm * P, -1) > 0)] *= -1
    nw = nrm.reshape(-1, 3) @ w2c[:3, :3]
    return nw.reshape(H, W, 3).astype(np.float32)


def boundary_keep(depth, rel=BOUND_REL):
    gx = np.zeros_like(depth); gy = np.zeros_like(depth)
    gx[:, 1:-1] = np.abs(depth[:, 2:] - depth[:, :-2])
    gy[1:-1] = np.abs(depth[2:] - depth[:-2])
    grad = np.maximum(gx, gy)
    return (grad / np.maximum(depth, 1e-6) < rel) & (depth > 0)


def write_ply(path, xyz, rgb):
    n = len(xyz)
    hdr = (f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n"
           "property float x\nproperty float y\nproperty float z\n"
           "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    rec = np.zeros(n, dtype=[('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                             ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
    rec['x'], rec['y'], rec['z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rec['r'], rec['g'], rec['b'] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, 'wb') as f:
        f.write(hdr.encode()); f.write(rec.tobytes())
    print(f"wrote {path}  {n:,} pts  {os.path.getsize(path)/1e6:.1f}MB", flush=True)


def main():
    global PHOTO, GEO_MASK
    tag = sys.argv[1]
    ref_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    assert tag in MODELS, f"tag must be one of {list(MODELS)}"
    if tag in STRICT:
        PHOTO = STRICT[tag]["PHOTO"]
        GEO_MASK = STRICT[tag]["GEO_MASK"]
        print(f"[{tag}] STRICT fusion sweep: src={STRICT[tag]['src']} "
              f"PHOTO={PHOTO} GEO_MASK={GEO_MASK} (reusing frozen p1cache; "
              f"NO MPS re-inference)", flush=True)
    name2mi = name2mi_map()
    pool, refs = build_refs()
    if ref_limit:
        refs = refs[:ref_limit]
    ark = g.arkit_centers_and_R()

    mnames, K_of, w2c_of, center_of, obs, pts_arr = load_model(tag)
    missing = [n for n in pool if n not in K_of]
    if missing:  # model did not register some pool frames -> drop them (DECLARE in report)
        print(f"[{tag}] WARNING: {len(missing)} pool frame(s) not in model, dropped: "
              f"{missing} (refs affected: {[n for n in missing if n in refs]})", flush=True)
        pool = [n for n in pool if n in K_of]
        refs = [n for n in refs if n in K_of]
    print(f"[{tag}] model {MODELS[tag]}: {len(mnames)} imgs {len(pts_arr)} sparse pts; "
          f"pool={len(pool)} refs={len(refs)}", flush=True)
    s_al, R_al, t_al = robust_align(center_of, ark)
    min_base_src = MIN_BASE_SRC_M / s_al
    min_base_fuse = MIN_BASE_FUSE_M / s_al
    obs_set = {n: set(v.tolist()) for n, v in obs.items() if n in set(pool)}
    for n in pool:
        obs_set.setdefault(n, set())

    def drange(n):
        ids = obs.get(n)
        X = pts_arr[ids] if ids is not None and len(ids) else np.empty((0, 3))
        if len(X) < 8:
            return 0.3 / s_al, 4.0 / s_al
        W = w2c_of[n].astype(np.float64)
        z = (W[:3, :3] @ X.T + W[:3, 3:4]).T[:, 2]; z = z[z > 0.05 / s_al]
        if len(z) < 8:
            return 0.3 / s_al, 4.0 / s_al
        lo, hi = np.percentile(z, 2), np.percentile(z, 99.5)
        return float(max(0.1 / s_al, lo * 0.70)), float(hi * 1.5)

    def nearest(n, k, cand, min_base):
        c0 = center_of[n]
        d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
        return [m for dist, m in d if dist >= min_base][:k]

    # ---- pass 1: casdiffmvs depth+conf for each ref (poses/K/drange from this model) ----
    p1cache = OUT / f"p1cache_trio_{tag}.npz"
    depth, conf, drng = {}, {}, {}
    t_inf = 0.0
    if p1cache.exists():
        z = np.load(p1cache, allow_pickle=True)
        fr = z["frames"].tolist(); zd, zc, zr = z["depth"], z["conf"], z["drange"]
        for i, n in enumerate(fr):
            depth[n] = zd[i].astype(np.float32); conf[n] = zc[i]; drng[n] = tuple(zr[i])
        refs = [n for n in refs if n in depth]
        print(f"loaded {p1cache.name} ({len(refs)} refs)", flush=True)
    else:
        dev = C.pick_device("mps")
        model, _ = C.build_model(METHOD, dev)
        t0 = time.time()
        for i, n in enumerate(refs):
            src = covis_select(n, pool, center_of, obs_set, obs, pts_arr, NVIEW - 1) \
                or nearest(n, NVIEW - 1, pool, min_base_src)
            view = [n] + src
            imgs = [R.load_image(name2mi[m]).transpose(2, 0, 1) for m in view]
            Ks = np.stack([K_of[m] for m in view])
            w2cs = np.stack([w2c_of[m] for m in view])
            dmin, dmax = drange(n); drng[n] = (dmin, dmax)
            proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
            d, c, dt = C.run_inference(model, imgs, proj, dv, dev)
            t_inf += dt
            depth[n] = d.astype(np.float32); conf[n] = c.astype(np.float16)
            if i % 20 == 0 or ref_limit:
                dd = d[d > 0]
                print(f"  [{tag}] {i}/{len(refs)} {n} src={src} drange=[{dmin:.2f},{dmax:.2f}] "
                      f"depth[med={np.median(dd):.2f} p5={np.percentile(dd,5):.2f} "
                      f"p95={np.percentile(dd,95):.2f}] conf%>{PHOTO}="
                      f"{100*(c>PHOTO).mean():.0f} {dt:.2f}s", flush=True)
        print(f"[{tag}] pass1 done wall={time.time()-t0:.1f}s infer_sum={t_inf:.1f}s", flush=True)
        if not ref_limit:  # never poison the full-run cache with a smoke subset
            np.savez_compressed(p1cache,
                                depth=np.stack([depth[n].astype(np.float16) for n in refs]),
                                conf=np.stack([conf[n] for n in refs]),
                                drange=np.array([drng[n] for n in refs], np.float32),
                                frames=np.array(refs))

    # ---- pass 2: geomcons fusion g3 p0.3 among the ref set (identical recipe) ----
    t0 = time.time()
    def getnrm(m):
        return world_normals(depth[m], K_of[m].astype(np.float64), w2c_of[m].astype(np.float64))

    pts, cols, kept = [], [], []
    for n in refs:
        d_ref = depth[n]; K_ref = K_of[n].astype(np.float64)
        ext_ref = w2c_of[n].astype(np.float64)
        dmin, dmax = drng[n]; n_ref = getnrm(n)
        geo_sum = np.zeros_like(d_ref, np.int32); depth_acc = d_ref.copy()
        for nb in nearest(n, NEIGH, refs, min_base_fuse):
            mask, depth_reproj, x2d, y2d = check_geometric_consistency(
                d_ref, K_ref, ext_ref, depth[nb], K_of[nb].astype(np.float64),
                w2c_of[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
            nb_n = cv2.remap(getnrm(nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
            mask = mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)
            geo_sum += mask.astype(np.int32); depth_acc += depth_reproj * mask
        img = (R.load_image(name2mi[n]) * 255).astype(np.uint8)
        final = (geo_sum >= GEO_MASK) & (conf[n].astype(np.float32) > PHOTO) \
            & boundary_keep(d_ref)
        kept.append(final.mean())
        d_avg = depth_acc / (geo_sum + 1)
        H, W = d_ref.shape
        uu, vv = np.meshgrid(np.arange(W), np.arange(H))
        x = (uu - K_ref[0, 2]) / K_ref[0, 0] * d_avg
        y = (vv - K_ref[1, 2]) / K_ref[1, 1] * d_avg
        cam = np.stack([x, y, d_avg], -1)[final]
        Rr, t = ext_ref[:3, :3], ext_ref[:3, 3]
        pts.append(((Rr.T @ (cam.T - t[:, None])).T).astype(np.float32))
        cols.append(img[final])
    P = np.concatenate(pts); Cc = np.concatenate(cols)
    print(f"[{tag}] fused g{GEO_MASK} p{PHOTO}: {len(P):,} raw pts "
          f"kept/frame={np.mean(kept)*100:.1f}% fuse={time.time()-t0:.1f}s", flush=True)

    # ---- align into ARKit metric frame, THEN metric cleanup (identical across models) ----
    Pa = (s_al * (R_al @ P.astype(np.float64).T).T + t_al)
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(Pa)
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc = pc.voxel_down_sample(0.005)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"[{tag}] after voxel5mm+outlier: {len(pc.points):,}", flush=True)

    fp = OUT / f"fused_trio_{tag}.ply"
    o3d.io.write_point_cloud(str(fp), pc)
    print(f"wrote {fp}", flush=True)
    if not ref_limit:
        OUTDIR.mkdir(exist_ok=True)
        xyz = np.asarray(pc.points, np.float64).astype(np.float32)
        rgb = np.clip(np.asarray(pc.colors) * 255 + 0.5, 0, 255).astype(np.uint8)
        write_ply(OUTDIR / VIEWER_PLY[tag], xyz, rgb)


if __name__ == "__main__":
    main()
