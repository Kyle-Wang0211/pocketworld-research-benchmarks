"""Streaming (overlapped inference+fusion) driver for the trio dense pipeline.

Reuses pw_diffmvs_sfm_trio's fusion body VERBATIM (T._fuse_one_ref) so output is
byte-identical to the two-pass path — only the SCHEDULE changes. Instead of
"infer all refs, then fuse all refs", we infer refs in order and, after each
block, fork a fusion pool for the newly-READY refs so CPU fusion overlaps the
next block's GPU (MPS) inference. A ref is ready once every member of its fusion
dependency dep(n) = {n} ∪ nearest(n, NEIGH, refs, min_base_fuse) has been
inferred. dep(n) is fixed by camera centres (known upfront), so the schedule is
deterministic and provably never fuses a ref before its neighbour depths exist.

Modes:
  verify : cache-only. Run monolithic AND streamed fusion on the SAME cached
           depths; assert bitwise-identical (the lossless guarantee). No MPS.
  seq    : fresh MPS inference, then fuse-all (two-pass). Baseline wall-clock.
  stream : fresh MPS inference OVERLAPPED with fusion. Measured wall-clock.

ofull config (the certified deliverable): PHOTO=0.5, GEO_MASK=3, cleanup off,
reusing the frozen 7full stride1 cache.
"""
import os, sys, time, hashlib
from pathlib import Path
import numpy as np
import multiprocessing as mp

BR = Path(__file__).resolve().parent
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_sfm_trio as T
import pw_diffmvs_run as R
import pw_diffmvs_common as C
import geom_metrics as g
import cv2

MODE = sys.argv[1] if len(sys.argv) > 1 else "verify"
BLK = int(os.environ.get("AETHER_STREAM_BLK", "40"))
KW = int(os.environ.get("AETHER_STREAM_WORKERS", "5"))
SEQ_W = int(os.environ.get("AETHER_SEQ_WORKERS", "8"))
CACHE = T.OUT / "p1cache_trio_7full.npz"

# ofull config (deliverable)
PHOTO, GEO_MASK = 0.5, 3
NORMAL_COS, BOUND_REL, GEO_PIX, GEO_DEP = 0.5, 0.03, 1.0, 0.01
NEIGH, NVIEW = T.NEIGH, T.NVIEW


def _pin_threads():
    for v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    cv2.setNumThreads(1)


def setup():
    name2mi = T.name2mi_map()
    pool, refs = T.build_refs()
    mn, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
    pool = [n for n in pool if n in K_of]
    refs = [n for n in refs if n in K_of]
    ark = g.arkit_centers_and_R()
    s_al, R_al, t_al = T.robust_align(center_of, ark)
    return dict(name2mi=name2mi, pool=pool, refs=refs, K_of=K_of, w2c_of=w2c_of,
                center_of=center_of, obs=obs, pts_arr=pts_arr, s_al=s_al, R_al=R_al,
                t_al=t_al, min_base_fuse=T.MIN_BASE_FUSE_M / s_al,
                min_base_src=T.MIN_BASE_SRC_M / s_al)


def nearest(center_of, n, k, cand, mb):
    c0 = center_of[n]
    d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
    return [m for dist, m in d if dist >= mb][:k]


def dep_graph(S):
    """dep(n) = exactly the frames T._fuse_one_ref(n) reads a depth of."""
    co, refs, mbf = S["center_of"], S["refs"], S["min_base_fuse"]
    return {n: set([n]) | set(nearest(co, n, NEIGH, refs, mbf)) for n in refs}


def build_ctx(S, depth, conf, drng, normals):
    T._FUSE_CTX.clear()
    T._FUSE_CTX.update(dict(
        depth=depth, conf=conf, drng=drng, K_of=S["K_of"], w2c_of=S["w2c_of"],
        center_of=S["center_of"], refs=S["refs"], name2mi=S["name2mi"], normals=normals,
        NEIGH=NEIGH, min_base_fuse=S["min_base_fuse"], GEO_PIX=GEO_PIX, GEO_DEP=GEO_DEP,
        NORMAL_COS=NORMAL_COS, GEO_MASK=GEO_MASK, PHOTO=PHOTO, BOUND_REL=BOUND_REL,
        photo_color=None, photo_color_n=1, erode_kernel=None,
        freespace_n=None, freespace_tau=0.02, reproj_err_max=None))


def load_cache(S):
    z = np.load(CACHE, allow_pickle=True)
    fr = z["frames"].tolist(); idx = {n: i for i, n in enumerate(fr)}
    zd, zc, zr = z["depth"], z["conf"], z["drange"]
    depth = {n: zd[idx[n]].astype(np.float32) for n in S["refs"]}
    conf = {n: zc[idx[n]] for n in S["refs"]}
    drng = {n: tuple(zr[idx[n]]) for n in S["refs"]}
    z.close()
    return depth, conf, drng


def make_infer(S, depth, conf, drng):
    """Fresh-MPS per-ref inference closure (identical recipe to trio pass1)."""
    dev = C.pick_device("mps")
    model, _ = C.build_model(T.METHOD, dev)
    if dev.type == "mps" and hasattr(__import__("torch").mps, "empty_cache"):
        __import__("torch").mps.empty_cache()
    obs, pool = S["obs"], S["pool"]
    obs_set = {n: set(v.tolist()) for n, v in obs.items() if n in set(pool)}
    for n in pool:
        obs_set.setdefault(n, set())
    s_al = S["s_al"]; pts_arr = S["pts_arr"]; w2c_of = S["w2c_of"]

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

    def infer(n):
        src = T.covis_select(n, pool, S["center_of"], obs_set, obs, pts_arr, NVIEW - 1) \
            or nearest(S["center_of"], n, NVIEW - 1, pool, S["min_base_src"])
        view = [n] + src
        imgs = [R.load_image(S["name2mi"][m]).transpose(2, 0, 1) for m in view]
        Ks = np.stack([S["K_of"][m] for m in view])
        w2cs = np.stack([w2c_of[m] for m in view])
        dmin, dmax = drange(n); drng[n] = (dmin, dmax)
        proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
        d, c, dt = C.run_inference(model, imgs, proj, dv, dev, view_names=view, feat_cache=None)
        depth[n] = d.astype(np.float32); conf[n] = c.astype(np.float16)
        return dt
    return infer


def norm_of(S, depth, n):
    return T.world_normals(depth[n], S["K_of"][n].astype(np.float64),
                           S["w2c_of"][n].astype(np.float64))


def stream_run(S, dep, infer_or_load, depth, conf, drng, normals):
    """Block-streamed: infer a block, then fork a pool for the newly-ready refs
    (overlapping the NEXT block's inference). Returns (results_in_refs_order,
    wall, infer_block_sum)."""
    refs = S["refs"]; _pin_threads()
    fork = mp.get_context("fork")
    inferred, dispatched, results, prev = set(), set(), {}, None
    t0 = time.time(); t_inf = 0.0
    for bstart in range(0, len(refs), BLK):
        block = refs[bstart:bstart + BLK]
        ti = time.time()
        for n in block:
            infer_or_load(n)
            normals[n] = norm_of(S, depth, n)
            inferred.add(n)
        t_inf += time.time() - ti
        if prev is not None:                       # harvest pool that overlapped this block
            pl, ar, batch = prev
            for n, r in zip(batch, ar.get()):
                results[n] = r
            pl.close(); pl.join(); prev = None
        ready = [n for n in refs if n not in dispatched and dep[n] <= inferred]
        if ready:
            dispatched |= set(ready)
            pl = fork.Pool(processes=min(KW, len(ready)),
                           initializer=T._fuse_pool_init, initargs=(None,))
            prev = (pl, pl.map_async(T._fuse_one_ref, ready), ready)
    if prev is not None:
        pl, ar, batch = prev
        for n, r in zip(batch, ar.get()):
            results[n] = r
        pl.close(); pl.join()
    assert len(results) == len(refs), f"stream fused {len(results)}/{len(refs)}"
    cv2.setNumThreads(0)
    return [results[n] for n in refs], time.time() - t0, t_inf


def results_sig(res):
    """Bitwise signature of a list of (pts,cols,nrms,kept,dm) in ref order."""
    P = np.concatenate([r[0] for r in res])
    Cc = np.concatenate([r[1] for r in res])
    Nn = np.concatenate([r[2] for r in res])
    DM = np.stack([r[4] for r in res]).astype(np.float32)
    kept = np.array([r[3] for r in res], np.float64)
    h = hashlib.sha256()
    for a in (P, Cc, Nn, DM, kept):
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()[:16], len(P)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    S = setup()
    dep = dep_graph(S)
    print(f"[stream] mode={MODE} N={len(S['refs'])} BLK={BLK} KW={KW} "
          f"min_base_fuse={S['min_base_fuse']:.3f}", flush=True)

    if MODE == "verify":
        depth, conf, drng = load_cache(S)
        # (A) monolithic reference: precompute all normals, serial fuse-all
        normM = {m: norm_of(S, depth, m) for m in S["refs"]}
        build_ctx(S, depth, conf, drng, normM)
        t0 = time.time()
        mono = [T._fuse_one_ref(n) for n in S["refs"]]
        sig_m, np_m = results_sig(mono)
        print(f"[verify] monolithic: {np_m:,} pts sig={sig_m} ({time.time()-t0:.1f}s)", flush=True)
        # (B) streamed schedule (normals filled incrementally); depths already present
        normS = {}
        build_ctx(S, depth, conf, drng, normS)
        strm, wall, _ = stream_run(S, dep, lambda n: None, depth, conf, drng, normS)
        sig_s, np_s = results_sig(strm)
        print(f"[verify] streamed:   {np_s:,} pts sig={sig_s} ({wall:.1f}s)", flush=True)
        # per-ref bitwise diff (localise any mismatch)
        bad = None
        for i, n in enumerate(S["refs"]):
            a, b = mono[i], strm[i]
            same = (np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
                    and np.array_equal(a[2], b[2]) and a[3] == b[3]
                    and np.array_equal(a[4], b[4]))
            if not same:
                bad = n; break
        print(f"\n{'✅ BYTE-IDENTICAL' if sig_m == sig_s and bad is None else '❌ MISMATCH'}"
              f"  monolithic==streamed  (first bad ref={bad})", flush=True)

    elif MODE in ("seq", "stream"):
        depth, conf, drng = {}, {}, {}
        infer = make_infer(S, depth, conf, drng)
        if MODE == "stream":
            normS = {}
            build_ctx(S, depth, conf, drng, normS)
            res, wall, t_inf = stream_run(S, dep, lambda n: infer(n), depth, conf, drng, normS)
            sig, npts = results_sig(res)
            print(f"\n[stream] OVERLAPPED wall={wall:.1f}s  infer_block_sum={t_inf:.1f}s  "
                  f"{npts:,} pts sig={sig}", flush=True)
        else:  # seq: two-pass baseline (infer all -> fuse all), same fresh inference
            _pin_threads()
            t0 = time.time()
            for n in S["refs"]:
                infer(n)
            t_infer = time.time() - t0
            normM = {m: norm_of(S, depth, m) for m in S["refs"]}
            build_ctx(S, depth, conf, drng, normM)
            fork = mp.get_context("fork")
            t1 = time.time()
            with fork.Pool(processes=SEQ_W, initializer=T._fuse_pool_init, initargs=(None,)) as pl:
                res = list(pl.imap(T._fuse_one_ref, S["refs"],
                                   chunksize=max(1, len(S["refs"]) // (SEQ_W * 4))))
            t_fuse = time.time() - t1
            cv2.setNumThreads(0)
            sig, npts = results_sig(res)
            print(f"\n[seq] TWO-PASS infer={t_infer:.1f}s + fuse({SEQ_W}w)={t_fuse:.1f}s "
                  f"= {t_infer + t_fuse:.1f}s  {npts:,} pts sig={sig}", flush=True)
    elif MODE == "contend":
        # THERMAL-CONTROLLED contention measurement. One fresh-inference run;
        # alternate blocks: EVEN blocks run inference with NO fusion pool active
        # (clean), ODD blocks run inference WHILE a fusion pool works (contended).
        # Even/odd blocks interleave across the whole thermal ramp, so the mean
        # per-ref inference delta (contended − clean) isolates memory-bandwidth
        # contention from slow thermal drift. Fusion of all refs still happens
        # (dispatch is just batched onto even-block boundaries), correctness kept.
        depth, conf, drng = {}, {}, {}
        infer = make_infer(S, depth, conf, drng)
        normS = {}; build_ctx(S, depth, conf, drng, normS)
        refs = S["refs"]; _pin_threads(); fork = mp.get_context("fork")
        inferred, dispatched, results, prev = set(), set(), {}, None
        clean_t, cont_t = [], []   # per-ref inference seconds
        t0 = time.time()
        blocks = [refs[i:i + BLK] for i in range(0, len(refs), BLK)]
        for bi, block in enumerate(blocks):
            active = prev is not None            # is a fusion pool running now?
            ti = time.time()
            for n in block:
                infer(n); normS[n] = norm_of(S, depth, n); inferred.add(n)
            per_ref = (time.time() - ti) / len(block)
            (cont_t if active else clean_t).append(per_ref)
            if prev is not None:                 # harvest whatever overlapped this block
                pl, ar, batch = prev
                for n, r in zip(batch, ar.get()):
                    results[n] = r
                pl.close(); pl.join(); prev = None
            ready = [n for n in refs if n not in dispatched and dep[n] <= inferred]
            # dispatch only at the END of EVEN blocks -> the NEXT (odd) block is contended,
            # the block after (even) runs clean. First block (bi=0) has no prior pool -> clean.
            if ready and bi % 2 == 0:
                dispatched |= set(ready)
                pl = fork.Pool(processes=min(KW, len(ready)),
                               initializer=T._fuse_pool_init, initargs=(None,))
                prev = (pl, pl.map_async(T._fuse_one_ref, ready), ready)
        # drain: fuse any remaining undispatched refs
        rem = [n for n in refs if n not in dispatched]
        if prev is not None:
            pl, ar, batch = prev
            for n, r in zip(batch, ar.get()):
                results[n] = r
            pl.close(); pl.join()
        if rem:
            with fork.Pool(processes=KW, initializer=T._fuse_pool_init, initargs=(None,)) as pl:
                for n, r in zip(rem, pl.map(T._fuse_one_ref, rem)):
                    results[n] = r
        cv2.setNumThreads(0)
        assert len(results) == len(refs)
        sig, npts = results_sig([results[n] for n in refs])
        cln = float(np.median(clean_t)); con = float(np.median(cont_t))
        print(f"\n[contend] clean-inference   median = {cln*1000:.0f} ms/ref  (n={len(clean_t)} blocks)")
        print(f"[contend] contended-inference median = {con*1000:.0f} ms/ref  (n={len(cont_t)} blocks)")
        print(f"[contend] contention slowdown = {100*(con-cln)/cln:+.0f}%  "
              f"(thermal-controlled: even/odd blocks interleaved)")
        # net-benefit model at full scale
        n_ref = len(refs)
        infer_clean = cln * n_ref
        penalty = (con - cln) * n_ref                    # extra inference cost when overlapping
        fuse_hidden = 28.9                               # measured seq fusion(8w); hidden if overlapped
        print(f"[contend] full-run model: inference≈{infer_clean:.0f}s, overlap penalty≈{penalty:+.0f}s, "
              f"fusion hideable≈{fuse_hidden:.0f}s -> NET {fuse_hidden - penalty:+.0f}s "
              f"({'WIN' if penalty < fuse_hidden else 'LOSS'})")
        print(f"[contend] total wall={time.time()-t0:.1f}s  {npts:,} pts sig={sig}", flush=True)

    else:
        sys.exit(f"unknown mode {MODE!r} (verify|seq|stream|contend)")
