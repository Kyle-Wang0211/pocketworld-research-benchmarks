"""precision_quality_probe.py — fp16 vs fp32 CoreML CasDiffMVS on the FINAL fused
cloud.

Question this answers: the fp16 CoreML CasDiffMVS depth has ~6% mean-rel error vs
PyTorch (fp32 CoreML is ~1.88%). Does that ~4% extra depth error SURVIVE the fusion
stage — i.e. on the delivered fused point cloud, does fp16 give visibly fewer points
/ worse coverage / more holes, or does geometric-consistency fusion wash it out?

Method (fully self-contained; reuses the PROVEN trio/stream setup + fusion body,
never modifies them):
  1. setup() exactly like subset_probe/stream: load_model("lapa") -> poses/K/sparse,
     build_refs() -> 413 refs, robust_align -> ARKit-metric scale.
  2. Pick a coverage-preserving REF SUBSET (deterministic FPS on camera centres,
     default 130 frames ≈ 31% of the dome) — enough to see the effect, fast enough
     that two CoreML passes finish in minutes (~127 ms/frame CPU+GPU).
  3. For EACH ref, build the input feed ONCE (5 imgs + 4 proj + dv from the SAME
     view-selection + drange the certified pipeline uses) and feed it to BOTH the
     fp16 and fp32 CoreML models. Identical inputs -> the only difference between the
     two depth maps is model precision (+ the one diffusion-noise realisation each
     model's trace baked in; see caveat below). Predictions are deterministic
     run-to-run (verified), so there is NO extra sampling noise on top.
  4. Fuse each depth set through the EXACT `ofull` deliverable fusion (T._fuse_one_ref
     + _FUSE_CTX; PHOTO=0.5, GEO_MASK=3, all cleanup OFF), with fusion neighbours
     CONFINED to the subset (ctx['refs']=subset), then the exact export post-process
     (ARKit-metre align -> voxel 5mm -> statistical-outlier). -> fp16 cloud, fp32 cloud.
  5. Quantify (open3d compute_point_cloud_distance / KDTree):
       (a) fp16 vs fp32: point-count delta, completeness (frac of fp32 pts within
           X mm of fp16, X=2/5/10), one-sided distance median/p90 (both directions).
       (b) each vs the gold mvs_ofull.ply (full-413 fp32 PyTorch production): point
           count + completeness — which precision lands closer to production.
  6. Write fp16_fused.ply / fp32_fused.ply to ~/Desktop for eyeball comparison.

⚠️ HONESTY CAVEAT (baked noise): CasDiffMVS's stage-2/3 DDIM sampling has ddim_eta>0
(stochastic). torch.jit.trace bakes whatever noise realisation it drew at trace time
into each exported model as constants. The fp16 and fp32 packages were traced
separately, so their depths differ by (precision) + (one different noise draw). The
run-to-run "~2% MPS/diffusion noise" band therefore lives INSIDE this comparison. Read
the result as: is fp16 SYSTEMATICALLY worse (point loss / coverage drop clearly beyond
the ~2% noise band), or is the fp16-vs-fp32 gap within noise?

IRON RULES honoured: python3.11 + KMP_DUPLICATE_LIB_OK=TRUE; CoreML loaded with
compute_units=CPU_AND_GPU (NEVER ANE — ANE garbages 3D-conv -> 64%); only subset
depths held in RAM. No proven source touched (read-only import of T/R/C).

Run:
  KMP_DUPLICATE_LIB_OK=TRUE python3.11 gpu_sfm_ab/precision_quality_probe.py [N_REFS]
  env: AETHER_PROBE_REFS (default 130), AETHER_FUSE_WORKERS (default 8)
"""
import os, sys, time, json, gc, hashlib
# objc/Metal fork-safety: CoreML inits a Metal context in this process; we run ALL
# predictions BEFORE any fork and free the models, but disable the abort-on-fork guard
# so the (numpy/cv2-only) fusion workers fork cleanly. libomp/BLAS threads are pinned.
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from pathlib import Path
import numpy as np
import multiprocessing as mp

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_sfm_trio as T
import pw_diffmvs_run as R          # noqa: F401 (fusion body + image loader use it)
import pw_diffmvs_common as C
import geom_metrics as g
import cv2
import coremltools as ct

BENCH = BR.parent / "ios_diffmvs_bench/DiffMVSBench"
FP16_PKG = BENCH / "CasDiffMVS_fp16.mlpackage"
FP32_PKG = BENCH / "CasDiffMVS_fp32.mlpackage"
BASELINE = Path(os.path.expanduser("~/Desktop/tiled_414_viewer/mvs_ofull.ply"))
DESKTOP = Path(os.path.expanduser("~/Desktop"))
RESULT_JSON = BR / "gpu_sfm_ab" / "precision_quality_probe_result.json"

TARGET_REFS = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("AETHER_PROBE_REFS", "130"))
WORKERS = int(os.environ.get("AETHER_FUSE_WORKERS", "8"))

# ── ofull config (byte-for-byte the certified deliverable, mirrors stream/subset) ──
PHOTO, GEO_MASK = 0.5, 3
NORMAL_COS, BOUND_REL, GEO_PIX, GEO_DEP = 0.5, 0.03, 1.0, 0.01
NEIGH, NVIEW = T.NEIGH, T.NVIEW

IN_NAMES = ["i0", "i1", "i2", "i3", "i4", "p1", "p2", "p3", "p4", "dv"]


# ── deterministic coverage selector: greedy farthest-point sampling on centres ──
def fps_subset(names, center_of, k):
    """Greedy FPS on camera centres -> k coverage-spread frames. Deterministic:
    sorted names, seed=first name, argmax ties -> lowest index."""
    order = sorted(names)
    Cc = np.array([center_of[n] for n in order], dtype=np.float64)
    N = len(order)
    k = max(1, min(k, N))
    if k >= N:
        return list(order)
    sel = [0]
    dmin = np.linalg.norm(Cc - Cc[0], axis=1)
    for _ in range(k - 1):
        i = int(np.argmax(dmin))
        sel.append(i)
        dmin = np.minimum(dmin, np.linalg.norm(Cc - Cc[i], axis=1))
    sel.sort()
    return [order[i] for i in sel]


def setup():
    names, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
    pool, refs = T.build_refs()
    pool = [n for n in pool if n in K_of]
    refs = [n for n in refs if n in K_of]
    ark = g.arkit_centers_and_R()
    s_al, R_al, t_al = T.robust_align(center_of, ark)
    obs_set = {n: set(v.tolist()) for n, v in obs.items() if n in set(pool)}
    for n in pool:
        obs_set.setdefault(n, set())
    return dict(names=names, pool=pool, refs=refs, K_of=K_of, w2c_of=w2c_of,
                center_of=center_of, obs=obs, pts_arr=pts_arr, obs_set=obs_set,
                name2mi=T.name2mi_map(), s_al=s_al, R_al=R_al, t_al=t_al,
                min_base_src=T.MIN_BASE_SRC_M / s_al,
                min_base_fuse=T.MIN_BASE_FUSE_M / s_al)


def make_drange(S):
    obs, pts_arr, w2c_of, s_al = S["obs"], S["pts_arr"], S["w2c_of"], S["s_al"]

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
    return drange


def nearest(center_of, n, k, cand, mb):
    c0 = center_of[n]
    d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
    return [m for dist, m in d if dist >= mb][:k]


def select_view(S, n):
    """ref + NVIEW-1 source frames — identical logic to trio/stream pass1:
    covis MVSNet triangulation-angle score over the model's sparse points, falling
    back to nearest-with-min-baseline. Sources are drawn from the FULL pool (only
    fusion neighbours are subset-confined)."""
    src = T.covis_select(n, S["pool"], S["center_of"], S["obs_set"], S["obs"],
                         S["pts_arr"], NVIEW - 1) \
        or nearest(S["center_of"], n, NVIEW - 1, S["pool"], S["min_base_src"])
    return [n] + src


def build_feed(S, view, drange, n):
    imgs = [R.load_image(S["name2mi"][m]).transpose(2, 0, 1)[None].astype(np.float32)
            for m in view]
    Ks = np.stack([S["K_of"][m] for m in view])
    w2cs = np.stack([S["w2c_of"][m] for m in view])
    dmin, dmax = drange(n)
    proj = C.make_proj_matrices(Ks, w2cs)      # dict stage1..4, each torch (1,5,2,4,4)
    dv = C.depth_values_tensor(dmin, dmax)     # torch (1,384)
    feed = {"i0": imgs[0], "i1": imgs[1], "i2": imgs[2], "i3": imgs[3], "i4": imgs[4],
            "p1": proj["stage1"].numpy().astype(np.float32),
            "p2": proj["stage2"].numpy().astype(np.float32),
            "p3": proj["stage3"].numpy().astype(np.float32),
            "p4": proj["stage4"].numpy().astype(np.float32),
            "dv": dv.numpy().astype(np.float32)}
    return feed, (dmin, dmax)


def load_coreml(pkg):
    m = ct.models.MLModel(str(pkg), compute_units=ct.ComputeUnit.CPU_AND_GPU)
    spec = m.get_spec()
    in_names = [i.name for i in spec.description.input]
    out_names = [o.name for o in spec.description.output]     # tuple order = (depth, conf)
    assert set(in_names) == set(IN_NAMES), f"{pkg.name} inputs {in_names} != {IN_NAMES}"
    assert len(out_names) == 2, f"{pkg.name} expected 2 outputs, got {out_names}"
    return m, out_names[0], out_names[1]      # depth_key, conf_key


def infer_both(S, subset, m16, dk16, ck16, m32, dk32, ck32):
    """One feed per ref, fed to BOTH models. Returns per-model depth(f32)/conf(f16)
    dicts + shared drng, plus median predict ms per model."""
    drange = make_drange(S)
    d16, c16, d32, c32, drng = {}, {}, {}, {}, {}
    t16, t32 = [], []
    checked_det = False
    for i, n in enumerate(subset):
        view = select_view(S, n)
        feed, dr = build_feed(S, view, drange, n)
        drng[n] = dr
        s = time.time(); o16 = m16.predict(feed); t16.append((time.time() - s) * 1000)
        s = time.time(); o32 = m32.predict(feed); t32.append((time.time() - s) * 1000)
        dm16 = np.asarray(o16[dk16]).squeeze(); cf16 = np.asarray(o16[ck16]).squeeze()
        dm32 = np.asarray(o32[dk32]).squeeze(); cf32 = np.asarray(o32[ck32]).squeeze()
        # sanity: conf ∈ [0,1], depth clearly metric (spec-order + value cross-check)
        if not checked_det:
            assert cf32.max() <= 1.05 and cf16.max() <= 1.05, \
                f"conf key looks wrong (max16={cf16.max():.3f} max32={cf32.max():.3f})"
            o32b = m32.predict(feed)
            det = np.array_equal(np.asarray(o32b[dk32]).squeeze(), dm32)
            print(f"[infer] determinism self-check (fp32, same feed x2): "
                  f"{'BIT-IDENTICAL' if det else 'NON-DETERMINISTIC!'}", flush=True)
            checked_det = True
        d16[n] = dm16.astype(np.float32); c16[n] = cf16.astype(np.float16)
        d32[n] = dm32.astype(np.float32); c32[n] = cf32.astype(np.float16)
        if i % 20 == 0 or i == len(subset) - 1:
            rel = np.mean(np.abs(dm16 - dm32) / (dm32 + 1e-6))
            print(f"  [{i + 1}/{len(subset)}] {n} drange=[{dr[0]:.2f},{dr[1]:.2f}] "
                  f"fp16-vs-fp32 depth mean|rel|={rel:.4f} "
                  f"med16={np.median(dm16):.3f} med32={np.median(dm32):.3f}", flush=True)
    return d16, c16, d32, c32, drng, float(np.median(t16)), float(np.median(t32))


def norm_of(S, depth, n):
    return T.world_normals(depth[n], S["K_of"][n].astype(np.float64),
                           S["w2c_of"][n].astype(np.float64))


def build_ctx(S, subset, depth, conf, drng, normals):
    T._FUSE_CTX.clear()
    T._FUSE_CTX.update(dict(
        depth=depth, conf=conf, drng=drng, K_of=S["K_of"], w2c_of=S["w2c_of"],
        center_of=S["center_of"], refs=subset, name2mi=S["name2mi"], normals=normals,
        NEIGH=NEIGH, min_base_fuse=S["min_base_fuse"], GEO_PIX=GEO_PIX, GEO_DEP=GEO_DEP,
        NORMAL_COS=NORMAL_COS, GEO_MASK=GEO_MASK, PHOTO=PHOTO, BOUND_REL=BOUND_REL,
        photo_color=None, photo_color_n=1, erode_kernel=None,
        freespace_n=None, freespace_tau=0.02, reproj_err_max=None))


def fuse(S, subset, depth, conf, drng):
    """Fuse `subset` (neighbours confined to subset) via the verbatim ofull fusion
    body, then the exact export post-process (ARKit-metre align -> voxel5mm -> SOR).
    Returns (o3d PointCloud in metres w/ colour+normals, raw_pt_count, wall, kept)."""
    import open3d as o3d
    normals = {m: norm_of(S, depth, m) for m in subset}
    build_ctx(S, subset, depth, conf, drng, normals)
    cv2.setNumThreads(1)
    fork = mp.get_context("fork")
    t0 = time.time()
    with fork.Pool(processes=min(WORKERS, len(subset)),
                   initializer=T._fuse_pool_init, initargs=(None,)) as pl:
        res = list(pl.imap(T._fuse_one_ref, subset,
                           chunksize=max(1, len(subset) // (WORKERS * 4))))
    wall = time.time() - t0
    cv2.setNumThreads(0)
    del normals; T._FUSE_CTX.clear()
    P = np.concatenate([r[0] for r in res])
    Cc = np.concatenate([r[1] for r in res])
    Nn = np.concatenate([r[2] for r in res])
    kept = float(np.mean([r[3] for r in res]))
    Pa = (S["s_al"] * (S["R_al"] @ P.astype(np.float64).T).T + S["t_al"])
    Na = (S["R_al"] @ Nn.astype(np.float64).T).T
    Na /= np.maximum(np.linalg.norm(Na, axis=1, keepdims=True), 1e-9)
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(Pa)
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc.normals = o3d.utility.Vector3dVector(Na)
    pc = pc.voxel_down_sample(0.005)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    return pc, len(P), wall, kept


def one_sided(src_pts, tgt_pts, thr_mm=(2.0, 5.0, 10.0)):
    """For each src point: distance to nearest tgt point (mm). completeness(t) =
    frac of src within t mm of tgt. Both clouds in ARKit metres."""
    import open3d as o3d
    a = o3d.geometry.PointCloud(); a.points = o3d.utility.Vector3dVector(src_pts.astype(np.float64))
    b = o3d.geometry.PointCloud(); b.points = o3d.utility.Vector3dVector(tgt_pts.astype(np.float64))
    d_mm = np.asarray(a.compute_point_cloud_distance(b)) * 1000.0
    comp = {t: float((d_mm <= t).mean()) for t in thr_mm}
    return comp, float(np.median(d_mm)), float(np.percentile(d_mm, 90))


def fmt_comp(c):
    return "  ".join(f"@{t:g}mm={100 * c[t]:.2f}%" for t in sorted(c))


def main():
    import open3d as o3d
    print(f"[probe] TARGET_REFS={TARGET_REFS} WORKERS={WORKERS}", flush=True)
    S = setup()
    N = len(S["refs"])
    subset = fps_subset(S["refs"], S["center_of"], TARGET_REFS)
    sig = hashlib.sha256("|".join(subset).encode()).hexdigest()[:12]
    print(f"[probe] N_full={N} subset={len(subset)} ({100 * len(subset) / N:.1f}%) "
          f"sel_sig={sig} s_al={S['s_al']:.4f} (1 unit={S['s_al'] * 1000:.1f}mm)", flush=True)

    # ---- load both CoreML models (CPU+GPU, never ANE) ----
    m16, dk16, ck16 = load_coreml(FP16_PKG)
    m32, dk32, ck32 = load_coreml(FP32_PKG)
    print(f"[probe] fp16 out: depth={dk16} conf={ck16} | fp32 out: depth={dk32} conf={ck32}", flush=True)

    # ---- inference: one feed per ref -> both models ----
    t_inf = time.time()
    d16, c16, d32, c32, drng, ms16, ms32 = infer_both(S, subset, m16, dk16, ck16, m32, dk32, ck32)
    print(f"[probe] inference done ({time.time() - t_inf:.1f}s wall)  "
          f"fp16 median={ms16:.0f}ms/frame  fp32 median={ms32:.0f}ms/frame", flush=True)

    # depth-map-level fp16-vs-fp32 stats (before fusion), for context
    rels = np.array([np.mean(np.abs(d16[n] - d32[n]) / (d32[n] + 1e-6)) for n in subset])
    print(f"[probe] per-ref depth mean|rel| fp16-vs-fp32: "
          f"median={np.median(rels):.4f} mean={rels.mean():.4f} p90={np.percentile(rels, 90):.4f}", flush=True)

    del m16, m32; gc.collect()      # free CoreML/Metal BEFORE any fork

    # ---- fuse each depth set through the identical ofull fusion ----
    pc16, raw16, w16, k16 = fuse(S, subset, d16, c16, drng)
    print(f"[fp16] fused raw={raw16:,} -> voxel5mm+SOR {len(pc16.points):,} pts  "
          f"kept/ref={100 * k16:.1f}%  fuse={w16:.1f}s", flush=True)
    del d16, c16; gc.collect()
    pc32, raw32, w32, k32 = fuse(S, subset, d32, c32, drng)
    print(f"[fp32] fused raw={raw32:,} -> voxel5mm+SOR {len(pc32.points):,} pts  "
          f"kept/ref={100 * k32:.1f}%  fuse={w32:.1f}s", flush=True)
    del d32, c32; gc.collect()

    p16 = np.asarray(pc16.points); p32 = np.asarray(pc32.points)
    n16, n32 = len(p16), len(p32)

    # ---- write plys for eyeball ----
    f16p = DESKTOP / "fp16_fused.ply"; f32p = DESKTOP / "fp32_fused.ply"
    o3d.io.write_point_cloud(str(f16p), pc16)
    o3d.io.write_point_cloud(str(f32p), pc32)
    print(f"[probe] wrote {f16p} ({n16:,} pts) and {f32p} ({n32:,} pts)", flush=True)

    # ---- (a) fp16 vs fp32 ----
    comp_32to16, med_32to16, p90_32to16 = one_sided(p32, p16)   # fp32 pts within X of fp16
    comp_16to32, med_16to32, p90_16to32 = one_sided(p16, p32)   # symmetric
    print("\n================ (a) fp16 cloud vs fp32 cloud ================", flush=True)
    print(f"  points:  fp16={n16:,}  fp32={n32:,}  delta={n16 - n32:+,} "
          f"({100 * (n16 - n32) / n32:+.2f}% vs fp32)  raw fp16/fp32={raw16:,}/{raw32:,}", flush=True)
    print(f"  completeness fp32->fp16 (frac of fp32 pts near fp16): {fmt_comp(comp_32to16)}", flush=True)
    print(f"  one-sided dist fp32->fp16: median={med_32to16:.2f}mm  p90={p90_32to16:.2f}mm", flush=True)
    print(f"  completeness fp16->fp32 (frac of fp16 pts near fp32): {fmt_comp(comp_16to32)}", flush=True)
    print(f"  one-sided dist fp16->fp32: median={med_16to32:.2f}mm  p90={p90_16to32:.2f}mm", flush=True)

    # ---- (b) each vs gold mvs_ofull.ply (full-413 fp32 PyTorch production) ----
    bpc = o3d.io.read_point_cloud(str(BASELINE))
    gold = np.asarray(bpc.points); n_gold = len(gold)
    comp_g16, med_g16, p90_g16 = one_sided(gold, p16)   # frac of gold covered by fp16
    comp_g32, med_g32, p90_g32 = one_sided(gold, p32)   # frac of gold covered by fp32
    # own points' agreement with production surface (subset->gold)
    comp_16g, med_16g, p90_16g = one_sided(p16, gold)
    comp_32g, med_32g, p90_32g = one_sided(p32, gold)
    print("\n========= (b) vs gold mvs_ofull.ply (full-413 fp32 PyTorch) =========", flush=True)
    print(f"  gold: {n_gold:,} pts  |  fp16 subset: {n16:,} ({100 * n16 / n_gold:.1f}% of gold)  "
          f"fp32 subset: {n32:,} ({100 * n32 / n_gold:.1f}% of gold)", flush=True)
    print(f"  gold coverage BY fp16 (frac gold near fp16): {fmt_comp(comp_g16)}  "
          f"med={med_g16:.2f}mm p90={p90_g16:.2f}mm", flush=True)
    print(f"  gold coverage BY fp32 (frac gold near fp32): {fmt_comp(comp_g32)}  "
          f"med={med_g32:.2f}mm p90={p90_g32:.2f}mm", flush=True)
    print(f"  fp16 pts ON gold surface (frac fp16 near gold): {fmt_comp(comp_16g)}  "
          f"med={med_16g:.2f}mm p90={p90_16g:.2f}mm", flush=True)
    print(f"  fp32 pts ON gold surface (frac fp32 near gold): {fmt_comp(comp_32g)}  "
          f"med={med_32g:.2f}mm p90={p90_32g:.2f}mm", flush=True)

    # ---- verdict line ----
    dpts = 100 * (n16 - n32) / n32
    print("\n================ VERDICT ================", flush=True)
    print(f"  fp16 point count is {dpts:+.2f}% vs fp32 on the FINAL fused cloud.", flush=True)
    print(f"  fp32 surface reproduced by fp16 within 5mm: {100 * comp_32to16[5.0]:.2f}% "
          f"(within 10mm: {100 * comp_32to16[10.0]:.2f}%); median cl-to-cl dist "
          f"{med_32to16:.2f}mm.", flush=True)
    print(f"  gold-coverage gap (fp32 - fp16) @5mm = "
          f"{100 * (comp_g32[5.0] - comp_g16[5.0]):+.2f} pts, @10mm = "
          f"{100 * (comp_g32[10.0] - comp_g16[10.0]):+.2f} pts.", flush=True)
    print("  ⚠️ This gap includes ONE diffusion-noise realisation per model (traces baked "
          "separate eta noise); read >~2% only as SYSTEMATIC precision loss.", flush=True)

    out = dict(
        target_refs=TARGET_REFS, n_full=N, n_subset=len(subset), sel_sig=sig,
        s_al=S["s_al"], workers=WORKERS,
        fp16_ms=ms16, fp32_ms=ms32,
        depth_rel_fp16_vs_fp32=dict(median=float(np.median(rels)), mean=float(rels.mean()),
                                    p90=float(np.percentile(rels, 90))),
        n_pts=dict(fp16=n16, fp32=n32, gold=n_gold, raw_fp16=raw16, raw_fp32=raw32),
        kept_ref=dict(fp16=k16, fp32=k32),
        pts_delta_pct_fp16_vs_fp32=dpts,
        a_fp16_vs_fp32=dict(
            comp_fp32_to_fp16=comp_32to16, med_fp32_to_fp16_mm=med_32to16, p90_fp32_to_fp16_mm=p90_32to16,
            comp_fp16_to_fp32=comp_16to32, med_fp16_to_fp32_mm=med_16to32, p90_fp16_to_fp32_mm=p90_16to32),
        b_vs_gold=dict(
            gold_cov_by_fp16=comp_g16, med_gold_to_fp16_mm=med_g16, p90_gold_to_fp16_mm=p90_g16,
            gold_cov_by_fp32=comp_g32, med_gold_to_fp32_mm=med_g32, p90_gold_to_fp32_mm=p90_g32,
            fp16_on_gold=comp_16g, med_fp16_to_gold_mm=med_16g,
            fp32_on_gold=comp_32g, med_fp32_to_gold_mm=med_32g),
        plys=dict(fp16=str(f16p), fp32=str(f32p), gold=str(BASELINE)),
    )
    json.dump(out, open(RESULT_JSON, "w"), indent=2, default=float)
    print(f"\n[probe] wrote {RESULT_JSON}", flush=True)


if __name__ == "__main__":
    main()
