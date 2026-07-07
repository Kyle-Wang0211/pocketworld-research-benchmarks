"""FAST frontend A/B: fixed GLOMAP poses, triangulate GPU-feature matches vs
CPU-feature matches (identical poses + matcher + tri options; ONLY the extractor
differs). Seconds per arm — isolates the extractor cleanly, no slow incremental
registration. Then 9-gate degradation table GPU vs CPU."""
import sys, time, json
from pathlib import Path
import numpy as np
import pycolmap

WD = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/gpu_sfm_ab")
BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks")
IMG = BR / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/photos_highres"
GLOMAP = BR / "tools/python/sfm_cmp/sfm_v7/sparse_glomap/0"
FP = BR / "fixtures_persist"
sys.path.insert(0, str(FP)); sys.path.insert(0, str(BR / "tools/python"))
import score_gates as SG


def tri_opts():
    o = pycolmap.IncrementalPipelineOptions()
    o.triangulation.min_angle = 0.5
    o.triangulation.ignore_two_view_tracks = False
    return o


def triangulate(db, tag):
    recon = pycolmap.Reconstruction(str(GLOMAP))     # fixed GLOMAP poses
    out = WD / f"tri_{tag}"; out.mkdir(exist_ok=True)
    t0 = time.time()
    r = pycolmap.triangulate_points(recon, str(db), str(IMG), str(out),
                                    clear_points=True, options=tri_opts(),
                                    refine_intrinsics=False)
    dt = time.time() - t0
    print(f"[{tag}] triangulate {dt:.1f}s: {r.num_reg_images()} imgs / {r.num_points3D()} pts", flush=True)
    return out


def main():
    res = {}
    for tag, db in (("GPU", WD / "db_gpu.db"), ("CPU", WD / "db_cpu2.db")):
        mp = triangulate(db, tag)
        res[tag] = SG.score(mp, tag)
    (WD / "gate_scores_fast_tri.json").write_text(json.dumps(res, indent=2))

    g, c = res["GPU"], res["CPU"]
    GATES = [("reproj_median_px","lower",3.0),("sv_surface_var","sv",0.0630),
             ("tri_angle_deg","higher",0.97),("weak_track_pct","lower",3.0),
             ("sphere_fit_mm","lower",3.0),("floor_thick_mm","lower",3.0),
             ("arkit_pos_mm","lower",3.0),("arkit_orient_deg","lower",3.0),
             ("point_count","higher",0.97)]
    print("\n" + "=" * 92)
    print("9-GATE: GPU-extract vs CPU-extract  (SAME GLOMAP poses + matcher + tri opts)")
    print(f"{'gate':<20}{'CPU(base)':>13}{'GPU':>13}{'change':>13}{'rule':>10}  verdict")
    npass = 0
    for name, kind, thr in GATES:
        cv, gv = c[name], g[name]
        if kind == "sv":
            ok = gv <= thr; chg = f"abs {gv:.4f}"; rule = f"<={thr}"
        elif kind == "higher":
            rr = gv / cv if cv else 0; ok = rr >= thr; chg = f"x{rr:.3f}"; rule = f">={thr}"
        else:
            d = (gv - cv) / cv * 100 if cv else 0; ok = d <= thr; chg = f"{d:+.1f}%"; rule = f"<=+{thr}%"
        npass += ok
        print(f"{name:<20}{cv:>13.4g}{gv:>13.4g}{chg:>13}{rule:>10}  {'PASS' if ok else 'FAIL'}")
    print(f"  --> {npass}/9 gates pass  (GPU extractor vs CPU extractor, frontend isolated)")


if __name__ == "__main__":
    main()
