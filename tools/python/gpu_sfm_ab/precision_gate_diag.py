"""Diagnostic: WHICH fusion gate decimates fp16? Reuses precision_quality_probe's
proven setup. For a handful of refs, run BOTH models and report, per model:
  - confidence gate:  %(conf > PHOTO=0.5)
  - boundary gate:    %(boundary_keep)
  - geometric gate:   %(geo_sum >= GEO_MASK=3) using the SAME subset neighbours + the
                      SAME check_geometric_consistency the deliverable fusion uses
  - combined final:   %(all three)
So we can attribute fp16's point loss to conf-head fp16 quirk vs depth-noise breaking
multi-view geometric consistency (GEO_DEP=1% tolerance vs ~2.8% fp16 depth noise).
"""
import os, sys
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from pathlib import Path
import numpy as np
BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "gpu_sfm_ab")); sys.path.insert(0, str(BR / "diffmvs"))
import precision_quality_probe as P
import pw_diffmvs_sfm_trio as T
from filter import check_geometric_consistency

PHOTO, GEO_MASK, GEO_PIX, GEO_DEP, NORMAL_COS, BOUND_REL = 0.5, 3, 1.0, 0.01, 0.5, 0.03
NDIAG = int(sys.argv[1]) if len(sys.argv) > 1 else 12


def geo_pass(S, depth, n, neighbors):
    """%(geo_sum>=GEO_MASK) for ref n against its subset neighbours — same CGC the
    fusion uses (incl. the normal-agreement term)."""
    d_ref = depth[n]; K_ref = S["K_of"][n].astype(np.float64); ext_ref = S["w2c_of"][n].astype(np.float64)
    dmin, dmax = S["_drng"][n]
    n_ref = P.norm_of(S, depth, n)
    geo_sum = np.zeros_like(d_ref, np.int32)
    import cv2
    for nb in neighbors:
        mask, depth_reproj, x2d, y2d = check_geometric_consistency(
            d_ref, K_ref, ext_ref, depth[nb], S["K_of"][nb].astype(np.float64),
            S["w2c_of"][nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
        nb_n = cv2.remap(P.norm_of(S, depth, nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
        mask = mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)
        geo_sum += mask.astype(np.int32)
    return (geo_sum >= GEO_MASK)


def main():
    S = P.setup()
    subset = P.fps_subset(S["refs"], S["center_of"], 130)
    diag = subset[::max(1, len(subset) // NDIAG)][:NDIAG]
    # neighbours (subset-confined) for each diag ref
    need = set(diag)
    for n in diag:
        need |= set(P.nearest(S["center_of"], n, T.NEIGH, subset, S["min_base_fuse"]))
    m16, dk16, ck16 = P.load_coreml(P.FP16_PKG)
    m32, dk32, ck32 = P.load_coreml(P.FP32_PKG)
    drange = P.make_drange(S)
    d16, c16, d32, c32, drng = {}, {}, {}, {}, {}
    for n in sorted(need):
        view = P.select_view(S, n)
        feed, dr = P.build_feed(S, view, drange, n)
        drng[n] = dr
        o16 = m16.predict(feed); o32 = m32.predict(feed)
        d16[n] = np.asarray(o16[dk16]).squeeze().astype(np.float32)
        c16[n] = np.asarray(o16[ck16]).squeeze().astype(np.float32)
        d32[n] = np.asarray(o32[dk32]).squeeze().astype(np.float32)
        c32[n] = np.asarray(o32[ck32]).squeeze().astype(np.float32)
    S["_drng"] = drng
    print(f"{'ref':<20} | {'conf>0.5':>18} | {'bound':>13} | {'geo>=3':>15} | {'FINAL':>15}")
    print(f"{'':<20} | {'fp16   fp32':>18} | {'fp16 fp32':>13} | {'fp16   fp32':>15} | {'fp16   fp32':>15}")
    agg = {k: [] for k in ("cf16", "cf32", "b16", "b32", "g16", "g32", "f16", "f32", "cm16", "cm32")}
    for n in diag:
        nbrs = P.nearest(S["center_of"], n, T.NEIGH, subset, S["min_base_fuse"])
        cf16 = float((c16[n] > PHOTO).mean()); cf32 = float((c32[n] > PHOTO).mean())
        b16 = float(T.boundary_keep(d16[n], BOUND_REL).mean()); b32 = float(T.boundary_keep(d32[n], BOUND_REL).mean())
        g16m = geo_pass(S, d16, n, nbrs); g32m = geo_pass(S, d32, n, nbrs)
        g16 = float(g16m.mean()); g32 = float(g32m.mean())
        fin16 = float((g16m & (c16[n] > PHOTO) & T.boundary_keep(d16[n], BOUND_REL)).mean())
        fin32 = float((g32m & (c32[n] > PHOTO) & T.boundary_keep(d32[n], BOUND_REL)).mean())
        agg["cf16"].append(cf16); agg["cf32"].append(cf32); agg["b16"].append(b16); agg["b32"].append(b32)
        agg["g16"].append(g16); agg["g32"].append(g32); agg["f16"].append(fin16); agg["f32"].append(fin32)
        agg["cm16"].append(float(np.median(c16[n]))); agg["cm32"].append(float(np.median(c32[n])))
        print(f"{n:<20} | {100*cf16:6.1f} {100*cf32:6.1f}%    | {100*b16:5.1f}{100*b32:5.1f}% | "
              f"{100*g16:6.1f} {100*g32:6.1f}% | {100*fin16:6.1f} {100*fin32:6.1f}%")
    A = {k: float(np.mean(v)) for k, v in agg.items()}
    print("\n=== MEANS over diag refs ===")
    print(f"conf median:  fp16={A['cm16']:.3f}  fp32={A['cm32']:.3f}")
    print(f"conf>0.5:     fp16={100*A['cf16']:.1f}%  fp32={100*A['cf32']:.1f}%   (ratio {A['cf16']/max(A['cf32'],1e-9):.2f})")
    print(f"boundary:     fp16={100*A['b16']:.1f}%  fp32={100*A['b32']:.1f}%")
    print(f"geo>=3:       fp16={100*A['g16']:.1f}%  fp32={100*A['g32']:.1f}%   (ratio {A['g16']/max(A['g32'],1e-9):.2f})")
    print(f"FINAL kept:   fp16={100*A['f16']:.1f}%  fp32={100*A['f32']:.1f}%   (ratio {A['f16']/max(A['f32'],1e-9):.2f})")


if __name__ == "__main__":
    main()
