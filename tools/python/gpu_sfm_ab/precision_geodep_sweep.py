"""Confirm the mechanism + quantify a rescue lever: sweep the fusion geometric-
consistency depth tolerance GEO_DEP and watch fp16's geo>=3 kept-fraction. If fp16's
loss is really "2.8% depth noise > 1% geo tolerance", then loosening GEO_DEP toward
~3% should let fp16 recover toward fp32's baseline (measured at the shipped 1%)."""
import os, sys
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from pathlib import Path
import numpy as np, cv2
BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "gpu_sfm_ab")); sys.path.insert(0, str(BR / "diffmvs"))
import precision_quality_probe as P
import pw_diffmvs_sfm_trio as T
from filter import check_geometric_consistency

GEO_MASK, GEO_PIX, NORMAL_COS = 3, 1.0, 0.5
GEODEPS = [0.01, 0.02, 0.03, 0.04, 0.06]
NDIAG = int(sys.argv[1]) if len(sys.argv) > 1 else 12


def geo_kept(S, depth, n, nbrs, geo_dep, geo_pix=GEO_PIX):
    d_ref = depth[n]; K_ref = S["K_of"][n].astype(np.float64); ext_ref = S["w2c_of"][n].astype(np.float64)
    dmin, dmax = S["_drng"][n]; n_ref = P.norm_of(S, depth, n)
    geo_sum = np.zeros_like(d_ref, np.int32)
    for nb in nbrs:
        mask, dreproj, x2d, y2d = check_geometric_consistency(
            d_ref, K_ref, ext_ref, depth[nb], S["K_of"][nb].astype(np.float64),
            S["w2c_of"][nb].astype(np.float64), dmax, dmin, geo_pix, geo_dep)
        nb_n = cv2.remap(P.norm_of(S, depth, nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
        geo_sum += (mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)).astype(np.int32)
    return float((geo_sum >= GEO_MASK).mean())


def main():
    S = P.setup()
    subset = P.fps_subset(S["refs"], S["center_of"], 130)
    diag = subset[::max(1, len(subset) // NDIAG)][:NDIAG]
    need = set(diag)
    for n in diag:
        need |= set(P.nearest(S["center_of"], n, T.NEIGH, subset, S["min_base_fuse"]))
    m16, dk16, ck16 = P.load_coreml(P.FP16_PKG); m32, dk32, ck32 = P.load_coreml(P.FP32_PKG)
    drange = P.make_drange(S); d16, d32, drng = {}, {}, {}
    for n in sorted(need):
        feed, dr = P.build_feed(S, P.select_view(S, n), drange, n); drng[n] = dr
        d16[n] = np.asarray(m16.predict(feed)[dk16]).squeeze().astype(np.float32)
        d32[n] = np.asarray(m32.predict(feed)[dk32]).squeeze().astype(np.float32)
    S["_drng"] = drng
    nb_of = {n: P.nearest(S["center_of"], n, T.NEIGH, subset, S["min_base_fuse"]) for n in diag}
    print(f"GEO_DEP sweep (GEO_PIX=1.0 shipped; geo>=3 kept %, mean over {len(diag)} diag refs):")
    print(f"{'GEO_DEP':>8} | {'fp16':>7} | {'fp32':>7} | {'fp16/fp32':>9}")
    for gd in GEODEPS:
        k16 = np.mean([geo_kept(S, d16, n, nb_of[n], gd, 1.0) for n in diag])
        k32 = np.mean([geo_kept(S, d32, n, nb_of[n], gd, 1.0) for n in diag])
        star = "  <- shipped" if abs(gd - 0.01) < 1e-9 else ""
        print(f"{gd:>8.2f} | {100*k16:6.1f}% | {100*k32:6.1f}% | {k16/max(k32,1e-9):>8.2f}{star}")
    print(f"\nGEO_PIX sweep (GEO_DEP=0.03; geo>=3 kept %):")
    print(f"{'GEO_PIX':>8} | {'fp16':>7} | {'fp32':>7} | {'fp16/fp32':>9}")
    for gp in (1.0, 2.0, 3.0, 5.0):
        k16 = np.mean([geo_kept(S, d16, n, nb_of[n], 0.03, gp) for n in diag])
        k32 = np.mean([geo_kept(S, d32, n, nb_of[n], 0.03, gp) for n in diag])
        print(f"{gp:>8.1f} | {100*k16:6.1f}% | {100*k32:6.1f}% | {k16/max(k32,1e-9):>8.2f}")


if __name__ == "__main__":
    main()
