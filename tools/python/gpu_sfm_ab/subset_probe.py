"""subset_probe.py — coverage/redundancy-aware REF-SUBSET selection for the dome
dense pipeline, and the speed×quality trade-off of fusing only the subset.

Premise: the 413-frame dome is highly redundant; fusion already dedups across
views. If we compute depth maps for only a coverage-preserving SUBSET of refs, the
number of MPS forwards drops LINEARLY (one forward per ref) -> inference speedup is
EXACTLY subset_frac. That is an external, exact extrapolation; this probe does NOT
re-infer. It reuses the FROZEN p1cache_trio_7full.npz depths (the exact depths the
certified `ofull` deliverable was fused from) and measures the two things that are
NOT free: (a) the fusion-side wall (also ~linear in ref count), and (b) the QUALITY
COST — how much of the full-413 baseline surface the sparser fusion still covers.

Selector: deterministic greedy Farthest-Point-Sampling (FPS) on camera CENTRES
(center_of, known from SfM — no inference). FPS maximises the minimum spacing of
the chosen cameras, i.e. it spreads them evenly over the dome so coverage degrades
as slowly as possible. Fully reproducible: sorted-name order, fixed seed (first
name), argmax ties broken by lowest index.

Fusion-neighbour confinement: _fuse_one_ref(n) picks its geometric-consistency
neighbours via _nearest_ctx(n, NEIGH, ctx["refs"], min_base_fuse). We set
ctx["refs"] = the subset, so dep(n) is drawn ONLY from the subset (no subset ref
ever reads a non-subset depth — the depth dict only contains subset frames anyway).

Config = the certified `ofull` deliverable (identical to pw_diffmvs_stream.py):
PHOTO=0.5, GEO_MASK=3, NEIGH=8, NORMAL_COS=0.5, GEO_PIX=1.0, GEO_DEP=0.01,
BOUND_REL=0.03, all cleanup (free-space / reproj-err / colour / erode) OFF.

Quality proxy vs ~/Desktop/tiled_414_viewer/mvs_ofull.ply (3.62M pts, the full-413
fusion of the SAME frozen depths):
  completeness(t) = fraction of BASELINE points within t mm of the subset cloud
                    (open3d compute_point_cloud_distance, source=baseline,
                     target=subset -> nearest-neighbour distance per baseline pt)
  + subset point count and its ratio to baseline
  + median / p90 one-sided distance baseline->subset (mm)
The frac=1.0 pass re-fuses all 413 and MUST reproduce the baseline point count
(frozen depths + deterministic CPU fusion) — a built-in pipeline self-check.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE python3.11 gpu_sfm_ab/subset_probe.py [frac,frac,...]
  (default fracs: 1.0,0.75,0.5 ; workers via AETHER_FUSE_WORKERS, default 8)
"""
import os, sys, time, json, hashlib
from pathlib import Path
import numpy as np
import multiprocessing as mp

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_sfm_trio as T
import pw_diffmvs_run as R          # noqa: F401  (imported for side-effect parity + used by fusion body)
import geom_metrics as g
import cv2

BASELINE = Path(os.path.expanduser("~/Desktop/tiled_414_viewer/mvs_ofull.ply"))
CACHE = T.OUT / "p1cache_trio_7full.npz"
WORKERS = int(os.environ.get("AETHER_FUSE_WORKERS", "8"))
FRACS = [float(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["1.0", "0.75", "0.5"])]

# ofull config (byte-for-byte the certified deliverable, mirrors stream.py)
PHOTO, GEO_MASK = 0.5, 3
NORMAL_COS, BOUND_REL, GEO_PIX, GEO_DEP = 0.5, 0.03, 1.0, 0.01
NEIGH = T.NEIGH


# ── deterministic coverage selector: greedy farthest-point sampling on centres ──
def fps_subset(names, center_of, frac):
    """Greedy FPS on camera centres. Deterministic: sorted names, seed=first name,
    argmax ties -> lowest index. Returns a coverage-spread subset of size
    round(frac*N) (>=1). frac>=1 returns every name."""
    order = sorted(names)                                  # stable, name-sorted
    C = np.array([center_of[n] for n in order], dtype=np.float64)
    N = len(order)
    k = max(1, int(round(frac * N)))
    if k >= N:
        return list(order)
    sel = [0]                                              # seed = first sorted name
    dmin = np.linalg.norm(C - C[0], axis=1)                # min dist to selected set
    for _ in range(k - 1):
        i = int(np.argmax(dmin))                           # farthest; first-max => deterministic
        sel.append(i)
        dmin = np.minimum(dmin, np.linalg.norm(C - C[i], axis=1))
    sel.sort()
    return [order[i] for i in sel]


def subset_min_spacing(names, center_of):
    """Coverage diagnostic: min & median nearest-neighbour camera spacing (model
    units). Higher min-spacing = more even dome coverage."""
    C = np.array([center_of[n] for n in names], dtype=np.float64)
    if len(C) < 2:
        return 0.0, 0.0
    nn = []
    for i in range(len(C)):
        d = np.linalg.norm(C - C[i], axis=1); d[i] = np.inf
        nn.append(d.min())
    nn = np.array(nn)
    return float(nn.min()), float(np.median(nn))


# ── setup: model dump, ARKit alignment scale, frozen cache ──────────────────────
def setup():
    names, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
    _pool, refs = T.build_refs()
    refs = [n for n in refs if n in K_of]                  # all 413 (REF_STRIDE=1)
    ark = g.arkit_centers_and_R()
    s_al, R_al, t_al = T.robust_align(center_of, ark)      # model -> ARKit metres
    return dict(refs=refs, K_of=K_of, w2c_of=w2c_of, center_of=center_of,
                name2mi=T.name2mi_map(), s_al=s_al, R_al=R_al, t_al=t_al,
                min_base_fuse=T.MIN_BASE_FUSE_M / s_al)


def load_cache_for(frames):
    """Load depth(f32)/conf(f16)/drange ONLY for `frames` (read each big array once
    then index — never z['depth'][i] in a loop)."""
    z = np.load(CACHE, allow_pickle=True)
    fr = z["frames"].tolist(); idx = {n: i for i, n in enumerate(fr)}
    _zd = z["depth"]; depth = {n: _zd[idx[n]].astype(np.float32) for n in frames}; del _zd
    _zc = z["conf"];  conf = {n: _zc[idx[n]] for n in frames}; del _zc
    _zr = z["drange"]; drng = {n: (float(_zr[idx[n]][0]), float(_zr[idx[n]][1])) for n in frames}; del _zr
    z.close()
    return depth, conf, drng


def build_ctx(S, subset, depth, conf, drng, normals):
    """Populate the module-global fusion context. ctx['refs']=subset confines every
    ref's fusion neighbours to the subset."""
    T._FUSE_CTX.clear()
    T._FUSE_CTX.update(dict(
        depth=depth, conf=conf, drng=drng, K_of=S["K_of"], w2c_of=S["w2c_of"],
        center_of=S["center_of"], refs=subset, name2mi=S["name2mi"], normals=normals,
        NEIGH=NEIGH, min_base_fuse=S["min_base_fuse"], GEO_PIX=GEO_PIX, GEO_DEP=GEO_DEP,
        NORMAL_COS=NORMAL_COS, GEO_MASK=GEO_MASK, PHOTO=PHOTO, BOUND_REL=BOUND_REL,
        photo_color=None, photo_color_n=1, erode_kernel=None,
        freespace_n=None, freespace_tau=0.02, reproj_err_max=None))


def norm_of(S, depth, n):
    return T.world_normals(depth[n], S["K_of"][n].astype(np.float64),
                           S["w2c_of"][n].astype(np.float64))


def postprocess(S, P):
    """EXACT deliverable post-fusion path (pw_diffmvs_sfm_trio.main lines 809-817):
    transform model-frame points into ARKit METRES, then voxel_down_sample(5mm) +
    remove_statistical_outlier(20, 2.0). Point positions are attribute-independent
    (voxel centroid / SOR use positions only), so points-only is byte-identical to
    the full delivered cloud's positions. Returns metric points (Nx3, metres)."""
    import open3d as o3d
    Pa = (S["s_al"] * (S["R_al"] @ P.astype(np.float64).T).T + S["t_al"])
    pc = o3d.geometry.PointCloud(); pc.points = o3d.utility.Vector3dVector(Pa)
    pc = pc.voxel_down_sample(0.005)                       # 5 mm (metres)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    return np.asarray(pc.points)


def fuse_subset(S, subset, depth, conf, drng):
    """Fuse only `subset` (neighbours confined to subset), then run the deliverable
    post-process. Returns (metric_pts, raw_pts_count, fusion_wall_s, kept_frac_mean).
    Normals precomputed for the subset only, then dropped."""
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
    P = np.concatenate([r[0] for r in res]) if res else np.zeros((0, 3), np.float32)
    kept = float(np.mean([r[3] for r in res])) if res else 0.0
    del normals
    T._FUSE_CTX.clear()
    pts = postprocess(S, P)                                # -> ARKit metres, voxel+SOR
    return pts, len(P), wall, kept


# ── quality proxy: completeness of subset vs full-413 baseline ──────────────────
def completeness(baseline_pts, subset_pts, thr_mm=(2.0, 5.0, 10.0)):
    """Both clouds are in ARKit METRES. For each baseline point, distance to nearest
    subset point -> mm. completeness(t) = frac(baseline pts within t mm of subset)."""
    import open3d as o3d
    b = o3d.geometry.PointCloud(); b.points = o3d.utility.Vector3dVector(baseline_pts.astype(np.float64))
    x = o3d.geometry.PointCloud(); x.points = o3d.utility.Vector3dVector(subset_pts.astype(np.float64))
    d_mm = np.asarray(b.compute_point_cloud_distance(x)) * 1000.0    # source=baseline, target=subset
    comp = {t: float((d_mm <= t).mean()) for t in thr_mm}
    return comp, float(np.median(d_mm)), float(np.percentile(d_mm, 90))


def main():
    import open3d as o3d
    S = setup()
    N = len(S["refs"])
    print(f"[subset] N_full={N} workers={WORKERS} min_base_fuse={S['min_base_fuse']:.3f} "
          f"s_al={S['s_al']:.4f} (1 model unit = {S['s_al']*1000:.1f} mm)", flush=True)

    # load baseline once
    bpc = o3d.io.read_point_cloud(str(BASELINE))
    baseline_pts = np.asarray(bpc.points)
    n_base = len(baseline_pts)
    print(f"[subset] baseline mvs_ofull.ply: {n_base:,} pts", flush=True)

    # depths for the UNION of all subsets = the largest frac's subset. Since FPS(1.0)
    # or the max frac drives the union, just load every frame the runs will touch.
    all_needed = set()
    subsets = {}
    for frac in FRACS:
        sub = fps_subset(S["refs"], S["center_of"], frac)
        subsets[frac] = sub
        all_needed |= set(sub)
    depth, conf, drng = load_cache_for(sorted(all_needed))
    print(f"[subset] loaded frozen depths for {len(all_needed)} frames (union)", flush=True)

    rows = []
    for frac in FRACS:
        sub = subsets[frac]
        # subset-selection determinism fingerprint
        sig = hashlib.sha256("|".join(sub).encode()).hexdigest()[:12]
        mn_sp, md_sp = subset_min_spacing(sub, S["center_of"])
        pts, raw_pts, wall, kept = fuse_subset(S, sub, depth, conf, drng)
        comp, med_mm, p90_mm = completeness(baseline_pts, pts)
        rows.append(dict(frac=frac, n_refs=len(sub), fuse_wall=wall, n_pts=len(pts),
                         raw_pts=raw_pts, pts_ratio=len(pts) / n_base, kept=kept, sel_sig=sig,
                         min_spacing=mn_sp, med_spacing=md_sp,
                         comp=comp, med_mm=med_mm, p90_mm=p90_mm))
        print(f"\n[frac {frac:.2f}] refs={len(sub)} sel_sig={sig} "
              f"min/med cam-spacing={mn_sp:.3f}/{md_sp:.3f} u", flush=True)
        print(f"  fusion wall={wall:.1f}s  raw_pts={raw_pts:,} -> voxel5mm+SOR pts={len(pts):,} "
              f"({100*len(pts)/n_base:.1f}% of baseline)  kept/ref={100*kept:.1f}%", flush=True)
        print(f"  completeness: " + "  ".join(f"@{t:g}mm={100*comp[t]:.2f}%" for t in sorted(comp)), flush=True)
        print(f"  baseline->subset dist: median={med_mm:.2f}mm  p90={p90_mm:.2f}mm", flush=True)

    del depth, conf, drng

    # ── trade-off table ─────────────────────────────────────────────────────────
    full = next((r for r in rows if abs(r["frac"] - 1.0) < 1e-9), None)
    print("\n================ SPEED × QUALITY TRADE-OFF ================", flush=True)
    print(f"{'frac':>5} {'refs':>5} {'infer×':>7} {'fuse×':>7} {'pts':>10} {'pts%':>6} "
          f"{'cmp@2':>7} {'cmp@5':>7} {'cmp@10':>7} {'medmm':>6}", flush=True)
    for r in rows:
        infer_x = 1.0 / r["frac"]                                  # EXACT: one forward per ref
        fuse_x = (full["fuse_wall"] / r["fuse_wall"]) if full else float("nan")
        c = r["comp"]
        print(f"{r['frac']:>5.2f} {r['n_refs']:>5} {infer_x:>6.2f}x {fuse_x:>6.2f}x "
              f"{r['n_pts']:>10,} {100*r['pts_ratio']:>5.1f}% "
              f"{100*c[2.0]:>6.2f}% {100*c[5.0]:>6.2f}% {100*c[10.0]:>6.2f}% {r['med_mm']:>5.2f}",
              flush=True)
    print("\ninfer× = EXACT linear extrapolation (subset_frac = #MPS forwards); "
          "fuse× = measured this run (±30% wall noise).", flush=True)
    if full:
        print(f"frac=1.00 self-check: re-fused {full['n_pts']:,} pts vs baseline "
              f"{n_base:,}  (delta {full['n_pts']-n_base:+,}, "
              f"{'MATCH' if abs(full['n_pts']-n_base) < 0.005*n_base else 'MISMATCH'})", flush=True)

    out = dict(N_full=N, workers=WORKERS, s_al=S["s_al"], n_baseline=n_base,
               fracs=FRACS, rows=rows)
    outp = BR / "gpu_sfm_ab" / "subset_probe_result.json"
    json.dump(out, open(outp, "w"), indent=2, default=float)
    print(f"\n[subset] wrote {outp}", flush=True)


if __name__ == "__main__":
    main()
