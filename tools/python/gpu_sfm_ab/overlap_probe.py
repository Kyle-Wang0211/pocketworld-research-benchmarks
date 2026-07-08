"""Prototype: does GPU dense inference (MPS) overlap with CPU fusion (fork pool)?
CRITICAL: fork the fusion pool BEFORE initializing MPS/the model (Metal context is
not fork-safe -> forking after MPS init crashes). Workers COW-inherit the depth dict.
Measures t_inf, t_fuse, t_both(concurrent); asserts fusion output byte-identical."""
import sys, time, os
from pathlib import Path
import numpy as np
import multiprocessing as mp

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_sfm_trio as T   # numpy/fusion only — NO torch/MPS touched yet

print("[probe] module load…", flush=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
mn, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
z = np.load(T.OUT / "p1cache_trio_7full.npz", allow_pickle=True)
fr = z["frames"].tolist()
refs = [n for n in fr if n in K_of][:N]
refset = set(refs)
# memory: load depth/conf ONLY for the N refs (neighbors are all ⊂ refs), not all 413
idx_of = {n: i for i, n in enumerate(fr)}
_Zd = z["depth"]; depth = {n: _Zd[idx_of[n]].astype(np.float32) for n in refs}; del _Zd
_Zc = z["conf"];  conf  = {n: _Zc[idx_of[n]] for n in refs}; del _Zc
_Zr = z["drange"]; drng = {n: tuple(_Zr[idx_of[n]]) for n in refs}; del _Zr
z.close()
print(f"[probe] loaded {len(refs)} ref depths", flush=True)
name2mi = T.name2mi_map(); T._name2mi = name2mi
min_base_fuse = T.MIN_BASE_FUSE_M / 0.2168

def _nearest_ctx(n, k, cand, mb):
    c0 = center_of[n]; d = sorted((np.linalg.norm(center_of[m]-c0), m) for m in cand if m != n)
    return [m for dist, m in d if dist >= mb][:k]
T._nearest_ctx = _nearest_ctx

norm_cache = {m: T.world_normals(depth[m], K_of[m].astype(np.float64), w2c_of[m].astype(np.float64)) for m in refs}
T._FUSE_CTX.clear()
T._FUSE_CTX.update(dict(depth=depth, conf=conf, drng=drng, K_of=K_of, w2c_of=w2c_of,
    center_of=center_of, refs=refs, name2mi=name2mi, normals=norm_cache,
    NEIGH=T.NEIGH, min_base_fuse=min_base_fuse, GEO_PIX=T.GEO_PIX, GEO_DEP=T.GEO_DEP,
    NORMAL_COS=0.5, GEO_MASK=T.GEO_MASK, PHOTO=T.PHOTO, BOUND_REL=0.03,
    photo_color=None, photo_color_n=1, erode_kernel=None,
    freespace_n=None, freespace_tau=0.02, reproj_err_max=None))


def pts_hash(results):
    import hashlib
    P = np.concatenate([r[0] for r in results])
    return hashlib.sha256(P.tobytes()).hexdigest()[:16], len(P)


if __name__ == "__main__":
    import cv2; cv2.setNumThreads(1)
    for v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else min(8, (mp.cpu_count() or 4) - 2)
    # fork the pool NOW — before any MPS init (fork-safe: no Metal context yet)
    pool = mp.get_context("fork").Pool(nw, initializer=T._fuse_pool_init, initargs=(None,))
    print("[probe] fusion pool forked (pre-MPS)", flush=True)

    # only NOW touch torch/MPS in the parent
    import torch
    import pw_diffmvs_common as C
    dev = C.pick_device("mps")
    model, _ = C.build_model(T.METHOD, dev)
    print(f"[probe] model on {dev.type}", flush=True)

    def nearest(n, k):
        c0 = center_of[n]; d = sorted((np.linalg.norm(center_of[m]-c0), m) for m in refs if m != n)
        return [m for _, m in d[:k]]

    def infer_all():
        for n in refs:
            view = [n] + nearest(n, T.NVIEW - 1)
            imgs = [T.R.load_image(name2mi[m]).transpose(2, 0, 1) for m in view]
            Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
            dmin, dmax = drng[n]
            proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
            C.run_inference(model, imgs, proj, dv, dev)
        if dev.type == "mps": torch.mps.synchronize()

    infer_all()  # warm graph compile (excluded from timing)
    print("[probe] warmed; timing…", flush=True)

    t0 = time.time(); infer_all(); t_inf = time.time() - t0
    t0 = time.time(); seq = pool.map(T._fuse_one_ref, refs); t_fuse = time.time() - t0
    h_seq = pts_hash(seq)
    t0 = time.time()
    fut = pool.map_async(T._fuse_one_ref, refs)
    infer_all()
    both = fut.get(); t_both = time.time() - t0
    h_both = pts_hash(both)
    pool.close(); pool.join()

    print(f"\nN={N} refs, workers={nw}")
    print(f"t_inf  (GPU MPS)    = {t_inf:6.1f}s")
    print(f"t_fuse (CPU pool)   = {t_fuse:6.1f}s")
    print(f"sum (sequential)    = {t_inf + t_fuse:6.1f}s")
    print(f"t_both (concurrent) = {t_both:6.1f}s   [ideal={max(t_inf, t_fuse):.1f}s]")
    ov = (t_inf + t_fuse) - t_both
    print(f"OVERLAP SAVED       = {ov:6.1f}s  ({100*ov/(t_inf+t_fuse):.0f}% of sum)")
    print(f"fusion byte-identical seq==concurrent: {h_seq == h_both}  ({h_seq} vs {h_both})")
