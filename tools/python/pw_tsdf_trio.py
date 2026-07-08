"""Depth-frame TSDF volumetric reconstruction (o3d ScalableTSDFVolume).

Replaces the Poisson mesher: integrate every masked depth frame into a voxel
grid; each voxel is a multi-ray weighted running average -> naturally smooth,
NO reliance on (jittery re-estimated KNN) normals. Marching-cubes surface.

The ONLY difference between the 'ofull' (o baseline) and 'ofsxq' (cleaned final)
meshes is the pass-2 per-ref `final` boolean mask (same depth cache, different
fusion gates). We recompute exactly the pipeline's `final` mask per ref, apply it
to the depth, integrate the masked depth into a per-tag TSDF volume, extract the
mesh, then transform vertices into the ARKit metric frame with (s_al,R_al,t_al)
so the output overlays the existing point clouds / Poisson meshes.

Usage: KMP_DUPLICATE_LIB_OK=TRUE python3.11 pw_tsdf_trio.py TAG [VOXEL_MM] [REF_LIMIT]
  TAG in {ofull, ofsxq};  VOXEL_MM (float, ARKit metres*1000, default 6);
  REF_LIMIT (int) = only first N refs (smoke test).
"""
from __future__ import annotations
import os, sys, time
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from pathlib import Path
import numpy as np
import cv2
import open3d as o3d

# Reuse the exact fusion pipeline (loaders, alignment, gates, geom-cons).
import pw_diffmvs_sfm_trio as T
import pw_diffmvs_run as R

SCRATCH = Path("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/"
               "7fc69efe-e09c-4359-8afb-04378874d3a1/scratchpad")
sys.path.insert(0, str(SCRATCH))
import geom_metrics as g  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "diffmvs"))
from filter import check_geometric_consistency  # noqa: E402

OUTDIR = Path(os.path.expanduser("~/Desktop/tiled_414_viewer"))
OUT = R.OUT
# Base viewer filenames at the DEFAULT 6mm voxel. Non-6mm voxels get a suffix
# (e.g. mesh_o_tsdf.ply @6mm vs mesh_o_tsdf4.ply @4mm) so finer-voxel runs never
# clobber the certified 6mm meshes. See viewer_ply_name().
VIEWER_PLY = {"ofull": "mesh_o_tsdf.ply", "ofsxq": "mesh_ofsxq_tsdf.ply",
              "7full": "mesh_7full_tsdf.ply", "blend": "mesh_blend_tsdf.ply",
              "ofsonly": "mesh_ofsonly_tsdf.ply"}

# Which frozen p1cache each tag reads, and the pass-2 fusion config.
# blend has its OWN stride1 MPS cache (casdiffmvs_blend.ckpt) + a blend-scale gate
# (blend conf << DTU, so a matched-low PHOTO is required; see BLEND_CFG below).
CACHE_FILE = {"ofull": "p1cache_trio_7full.npz", "ofsxq": "p1cache_trio_7full.npz",
              "7full": "p1cache_trio_7full.npz", "blend": "p1cache_trio_blend.npz",
              "ofsonly": "p1cache_trio_7full.npz"}
# Calibrated blend fusion gate (src=lapa, blend ckpt @896x512). PHOTO is set to the
# blend-scale value chosen from the conf-distribution probe (matched to o coverage).
BLEND_CFG = {"src": "lapa", "PHOTO": 0.20, "GEO_MASK": 3}


def viewer_ply_name(tag: str, voxel_mm: float) -> str:
    """6mm keeps the base name; any other voxel appends the mm as an int suffix
    (4.0 -> '4', 4.5 -> '4p5'). Guarantees the certified 6mm meshes are never
    overwritten by a finer-voxel experiment."""
    base = VIEWER_PLY[tag]
    if abs(voxel_mm - 6.0) < 1e-6:
        return base
    if abs(voxel_mm - round(voxel_mm)) < 1e-6:
        suf = str(int(round(voxel_mm)))
    else:
        suf = ("%g" % voxel_mm).replace(".", "p")
    stem, ext = os.path.splitext(base)
    return f"{stem}{suf}{ext}"


def compute_final_mask(n, refs, depth, conf, drng, K_of, w2c_of, center_of,
                       cfg, min_base_fuse):
    """Recompute the pipeline pass-2 `final` boolean mask for ref `n`, plus the
    geo-consistency-averaged depth d_avg. Verbatim gate logic from
    pw_diffmvs_sfm_trio.main (STRICT cfg dict controls which gates are active)."""
    GEO_MASK = cfg["GEO_MASK"]; PHOTO = cfg["PHOTO"]
    GEO_PIX, GEO_DEP = T.GEO_PIX, T.GEO_DEP
    NORMAL_COS = cfg.get("NORMAL_COS", 0.5)
    BOUND_REL = cfg.get("BOUND_REL", 0.03)
    photo_color = cfg.get("PHOTO_COLOR", None)
    photo_color_n = cfg.get("PHOTO_COLOR_N", 1)
    erode_px = cfg.get("ERODE_PX", 0)
    freespace_n = cfg.get("FREESPACE_N", None)
    freespace_tau = cfg.get("FREESPACE_TAU", 0.02)
    reproj_err_max = cfg.get("REPROJ_ERR_MAX", None)

    d_ref = depth[n]; K_ref = K_of[n].astype(np.float64)
    ext_ref = w2c_of[n].astype(np.float64)
    dmin, dmax = drng[n]

    def getnrm(m):
        return T.world_normals(depth[m], K_of[m].astype(np.float64),
                               w2c_of[m].astype(np.float64))

    n_ref = getnrm(n)
    ref_rgb01 = R.load_image(T._name2mi[n]) if photo_color is not None else None
    geo_sum = np.zeros_like(d_ref, np.int32); depth_acc = d_ref.copy()
    color_agree_sum = np.zeros_like(d_ref, np.int32)
    freespace_sum = np.zeros_like(d_ref, np.int32)
    rerr_acc = np.zeros_like(d_ref, np.float32)

    for nb in T.__dict__["_nearest"](n, T.NEIGH, refs, min_base_fuse):
        mask, depth_reproj, x2d, y2d = check_geometric_consistency(
            d_ref, K_ref, ext_ref, depth[nb], K_of[nb].astype(np.float64),
            w2c_of[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
        nb_n = cv2.remap(getnrm(nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
        mask = mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)
        geo_sum += mask.astype(np.int32); depth_acc += depth_reproj * mask
        if reproj_err_max is not None:
            rerr_acc += (np.abs(depth_reproj - d_ref) / np.maximum(d_ref, 1e-6)) * mask
        if photo_color is not None:
            nb_rgb01 = cv2.remap(R.load_image(T._name2mi[nb]), x2d, y2d,
                                 interpolation=cv2.INTER_LINEAR)
            col_diff = np.abs(nb_rgb01 - ref_rgb01).mean(axis=2)
            color_agree_sum += (mask & (col_diff < photo_color)).astype(np.int32)
        if freespace_n is not None:
            samp_src = cv2.remap(depth[nb], x2d, y2d, interpolation=cv2.INTER_LINEAR)
            d_ref_in_nb = T.ref_depth_in_src(d_ref, K_ref, ext_ref,
                                             w2c_of[nb].astype(np.float64))
            seen_through = (samp_src > 0) & (d_ref > 0) & \
                (samp_src - d_ref_in_nb > freespace_tau * np.maximum(d_ref_in_nb, 1e-6))
            freespace_sum += seen_through.astype(np.int32)

    final = (geo_sum >= GEO_MASK) & (conf[n].astype(np.float32) > PHOTO) \
        & T.boundary_keep(d_ref, rel=BOUND_REL)
    if photo_color is not None:
        final = final & (color_agree_sum >= photo_color_n)
    if freespace_n is not None:
        final = final & (freespace_sum < freespace_n)
    if reproj_err_max is not None:
        rerr_mean = rerr_acc / np.maximum(geo_sum, 1)
        final = final & (rerr_mean < reproj_err_max)
    if erode_px and erode_px > 0:
        k = 2 * int(erode_px) + 1
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        final = cv2.erode(final.astype(np.uint8), ker).astype(bool)
    d_avg = depth_acc / (geo_sum + 1)
    return final, d_avg


# ─── Parallel per-ref prep for TSDF (2026-07-07) ───
# The heavy part of the integrate loop is compute_final_mask (per-ref geometric-
# consistency over NEIGH neighbors) + image load — both fully independent per
# ref. Parallelize THAT; keep vol.integrate serial in main, called in refs order
# (a single ScalableTSDFVolume is not thread-safe, and same-order integrate keeps
# the weighted-average FP accumulation bit-identical to the serial baseline).
# Workers return numpy arrays only (picklable); main builds the o3d objects.
_TSDF_CTX: dict = {}
# dm-cache: pw_diffmvs_sfm_trio's fusion writes the exact same masked depth this
# stage would recompute. When a validated cache is loaded (main), skip the entire
# compute_final_mask geometric-consistency pass — byte-identical, big TSDF win.
_DM_CACHE: dict = {}


def _tsdf_prep_one(n):
    c = _TSDF_CTX
    dm = _DM_CACHE.get(n)
    if dm is not None:                                   # cache hit: no recompute
        kf = float((dm > 0).mean())                      # dm>0 <=> final (d_avg>0 where kept)
    else:
        final, d_avg = compute_final_mask(n, c["refs"], c["depth"], c["conf"], c["drng"],
                                          c["K_of"], c["w2c_of"], c["center_of"],
                                          c["cfg"], c["min_base_fuse"])
        kf = float(final.mean())
        dm = np.where(final, d_avg, 0.0).astype(np.float32)
    if not np.any(dm > 0):
        return (n, None, None, kf)
    rgb = (R.load_image(T._name2mi[n]) * 255).astype(np.uint8)
    return (n, dm, np.ascontiguousarray(rgb), kf)


def _tsdf_pool_init(ctx):
    if ctx is not None:                 # spawn fallback: receive pickled ctx
        _TSDF_CTX.update(ctx)
    cv2.setNumThreads(1)                # no thread oversubscription in workers


def main():
    tag = sys.argv[1]
    voxel_mm = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
    ref_limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    assert tag in ("ofull","ofsxq","7full","blend","ofsonly"), \
        "tag must be ofull/ofsxq/7full/blend"
    cfg = BLEND_CFG if tag == "blend" else T.STRICT[tag]
    print(f"[{tag}] TSDF cfg={cfg} voxel={voxel_mm}mm(ARKit)", flush=True)

    # ---- load model dump, refs, ARKit alignment (same as pipeline) ----
    name2mi = T.name2mi_map()
    T._name2mi = name2mi
    T._nearest = None  # placeholder; real nearest is a closure below
    pool, refs = T.build_refs()
    if ref_limit:
        refs = refs[:ref_limit]
    ark = g.arkit_centers_and_R()
    model_tag = cfg["src"]  # 'lapa'
    mnames, K_of, w2c_of, center_of, obs, pts_arr = T.load_model(model_tag)
    missing = [n for n in pool if n not in K_of]
    if missing:
        pool = [n for n in pool if n in K_of]
        refs = [n for n in refs if n in K_of]
    s_al, R_al, t_al = T.robust_align(center_of, ark)
    min_base_fuse = T.MIN_BASE_FUSE_M / s_al

    def _nearest(n, k, cand, min_base):
        c0 = center_of[n]
        d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
        return [m for dist, m in d if dist >= min_base][:k]
    T._nearest = _nearest

    # ---- load frozen depth+conf cache (7full for o-family; blend's own cache) ----
    p1cache = OUT / CACHE_FILE[tag]
    assert p1cache.exists(), f"missing {p1cache}"
    z = np.load(p1cache, allow_pickle=True)
    fr = z["frames"].tolist(); zd, zc, zr = z["depth"], z["conf"], z["drange"]
    depth, conf, drng = {}, {}, {}
    for i, nm in enumerate(fr):
        depth[nm] = zd[i].astype(np.float32); conf[nm] = zc[i]; drng[nm] = tuple(zr[i])
    refs = [n for n in refs if n in depth]
    print(f"[{tag}] loaded cache {len(refs)} refs; align scale={s_al:.4f}", flush=True)

    # ---- dm-cache: reuse fusion's masked depth (byte-identical) → skip the whole
    # compute_final_mask geometric-consistency pass. Sig-guarded: mismatch = recompute.
    _dmc = OUT / f"dmcache_trio_{tag}.npz"
    _my_sig = (f"g{cfg['GEO_MASK']}_p{cfg['PHOTO']}_bnd{cfg.get('BOUND_REL', 0.03)}_"
               f"nrm{cfg.get('NORMAL_COS', 0.5)}_pc{cfg.get('PHOTO_COLOR', None)}_"
               f"pcn{cfg.get('PHOTO_COLOR_N', 1)}_fs{cfg.get('FREESPACE_N', None)}_"
               f"fst{cfg.get('FREESPACE_TAU', 0.02)}_re{cfg.get('REPROJ_ERR_MAX', None)}_"
               f"er{cfg.get('ERODE_PX', 0)}")
    if not os.environ.get("AETHER_NO_DMCACHE") and _dmc.exists():
        dz = np.load(_dmc, allow_pickle=True)
        if str(dz["sig"]) == _my_sig:
            dfr = [str(x) for x in dz["frames"].tolist()]
            ddm = dz["dm"]
            for i, nm in enumerate(dfr):
                _DM_CACHE[nm] = ddm[i].astype(np.float32)
            print(f"[{tag}] dm-cache HIT ({len(_DM_CACHE)} refs) — skip compute_final_mask", flush=True)
        else:
            print(f"[{tag}] dm-cache sig MISMATCH -> recompute ({str(dz['sig'])} != {_my_sig})", flush=True)
    else:
        print(f"[{tag}] dm-cache absent/disabled -> recompute", flush=True)

    # ---- TSDF setup (GLOMAP/camera metric frame; convert ARKit voxel by 1/s_al) ----
    voxel_len = (voxel_mm / 1000.0) / s_al          # GLOMAP units
    sdf_trunc = voxel_len * 4.0                     # ~24mm ARKit at 6mm voxel
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel_len, sdf_trunc=sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    print(f"[{tag}] TSDF voxel_len={voxel_len:.5f} sdf_trunc={sdf_trunc:.5f} "
          f"(GLOMAP units; ARKit voxel={voxel_mm}mm trunc={voxel_mm*4:.0f}mm)", flush=True)

    W, H = T.PROC_W, T.PROC_H
    t0 = time.time(); n_int = 0; kept_frac = []

    # Integrate one prepped frame. Called in refs order (serial path AND the
    # ordered imap below) -> the single-volume weighted-average FP accumulation
    # is bit-identical to the pre-parallel baseline.
    def _integrate(item, i):
        nonlocal n_int
        n, dm, rgb, kf = item
        kept_frac.append(kf)
        if dm is None:                                  # nothing kept this frame
            return
        color_o3d = o3d.geometry.Image(np.ascontiguousarray(rgb))
        depth_o3d = o3d.geometry.Image(np.ascontiguousarray(dm))
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color_o3d, depth_o3d, depth_scale=1.0,      # depth already in metric units
            depth_trunc=float(max(drng[n]) * 1.5), convert_rgb_to_intensity=False)
        K = K_of[n].astype(np.float64)
        intr = o3d.camera.PinholeCameraIntrinsic(
            W, H, K[0, 0], K[1, 1], K[0, 2], K[1, 2])
        extr = w2c_of[n].astype(np.float64)             # world->camera == o3d extrinsic
        vol.integrate(rgbd, intr, extr)
        n_int += 1
        if i % 40 == 0 or ref_limit:
            print(f"  [{tag}] {i}/{len(refs)} {n} kept={kf*100:.0f}% "
                  f"integrated={n_int}", flush=True)

    # [2026-07-07] Parallelize the heavy independent prep (compute_final_mask +
    # image load); integrate stays serial. Default parallel; AETHER_TSDF_WORKERS=1
    # forces serial (debug / bit-exact A/B).
    _TSDF_CTX.clear()
    _TSDF_CTX.update(dict(refs=refs, depth=depth, conf=conf, drng=drng, K_of=K_of,
                          w2c_of=w2c_of, center_of=center_of, cfg=cfg,
                          min_base_fuse=min_base_fuse))
    _tsdf_default = str(min(8, max(1, (os.cpu_count() or 4) - 2)))
    n_workers = int(os.environ.get("AETHER_TSDF_WORKERS", _tsdf_default))
    if n_workers <= 1:
        for i, n in enumerate(refs):                    # serial (env=1 explicit fallback)
            _integrate(_tsdf_prep_one(n), i)
    else:
        import multiprocessing as _mp
        n_workers = min(n_workers, max(1, (os.cpu_count() or 2) - 2), len(refs))
        # OMP/BLAS pinned to 1 BEFORE forking so no multi-thread pool is live at
        # fork (classic macOS libomp fork-hang guard); workers are single-thread.
        for v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
            os.environ.setdefault(v, "1")
        cv2.setNumThreads(1)
        try:
            _ctx = _mp.get_context("fork"); _init = None      # COW-inherit cache + T/R
        except ValueError:
            _ctx = _mp.get_context("spawn"); _init = dict(_TSDF_CTX)
        print(f"[{tag}] tsdf prep: parallel {n_workers} workers "
              f"({_ctx.get_start_method()}) over {len(refs)} refs; integrate serial",
              flush=True)
        with _ctx.Pool(processes=n_workers, initializer=_tsdf_pool_init,
                       initargs=(_init,)) as _pool:
            # imap preserves refs order -> integrate order == serial -> bit-identical
            for i, item in enumerate(_pool.imap(
                    _tsdf_prep_one, refs,
                    chunksize=max(1, len(refs) // (n_workers * 4)))):
                _integrate(item, i)
        cv2.setNumThreads(0)
    print(f"[{tag}] integrated {n_int} frames kept/frame={np.mean(kept_frac)*100:.1f}% "
          f"pass2+integrate={time.time()-t0:.1f}s", flush=True)

    # ---- extract mesh, then transform into ARKit metric frame ----
    mesh = vol.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    V = np.asarray(mesh.vertices)
    Va = (s_al * (R_al @ V.T).T + t_al)             # GLOMAP -> ARKit metric
    mesh.vertices = o3d.utility.Vector3dVector(Va)
    mesh.compute_vertex_normals()                    # recompute after transform
    nv, nt = len(mesh.vertices), len(mesh.triangles)
    print(f"[{tag}] TSDF mesh: {nv:,} verts {nt:,} tris "
          f"(has_color={mesh.has_vertex_colors()})", flush=True)

    print(f"[{tag}] ALIGNED bbox: min={Va.min(0)} max={Va.max(0)} "
          f"median={np.median(Va, 0)}", flush=True)
    if ref_limit and os.environ.get("TSDF_SMOKE_WRITE"):
        sp = Path(os.environ["TSDF_SMOKE_WRITE"])
        o3d.io.write_triangle_mesh(str(sp), mesh, write_vertex_normals=True,
                                   write_vertex_colors=True)
        print(f"[smoke] wrote {sp}", flush=True)
    if not ref_limit:
        OUTDIR.mkdir(exist_ok=True)
        outp = OUTDIR / viewer_ply_name(tag, voxel_mm)
        o3d.io.write_triangle_mesh(str(outp), mesh, write_vertex_normals=True,
                                   write_vertex_colors=True, write_ascii=False)
        print(f"wrote {outp}  {os.path.getsize(outp)/1e6:.1f}MB", flush=True)
        # also stash a copy next to the fused ply for provenance (voxel-suffixed)
        prov_stem = os.path.splitext(viewer_ply_name(tag, voxel_mm))[0]
        o3d.io.write_triangle_mesh(str(OUT / f"tsdf_trio_{prov_stem}.ply"), mesh,
                                   write_vertex_normals=True, write_vertex_colors=True)


if __name__ == "__main__":
    main()
