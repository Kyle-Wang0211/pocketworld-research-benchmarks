"""GPU-extract -> FULL incremental SfM -> 9-gate, vs CPU-extract baseline.
Both arms: identical matcher (already done, same 6159 pairs) + identical
pycolmap incremental_mapping options. ONLY the feature source differs. Also
scores the existing A_glomap (champion GLOMAP-pose triangulation) for context.
"""
import sys, time, json, shutil
from pathlib import Path
import numpy as np
import pycolmap

WD = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/gpu_sfm_ab")
BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks")
IMG = BR / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/photos_highres"
FP = BR / "fixtures_persist"
sys.path.insert(0, str(FP))            # score_gates.py
sys.path.insert(0, str(BR / "tools/python"))
import score_gates as SG


def run_sfm(db, out, tag):
    out.mkdir(parents=True, exist_ok=True)
    opts = pycolmap.IncrementalPipelineOptions()
    opts.num_threads = 8
    t0 = time.time()
    recs = pycolmap.incremental_mapping(str(db), str(IMG), str(out), options=opts)
    dt = time.time() - t0
    if not recs:
        print(f"[{tag}] NO reconstruction produced ({dt:.1f}s)", flush=True)
        return None
    # pick the reconstruction with the most registered images
    best = max(recs.values(), key=lambda r: r.num_reg_images())
    print(f"[{tag}] SfM {dt:.1f}s: {len(recs)} model(s), best="
          f"{best.num_reg_images()} imgs / {best.num_points3D()} pts", flush=True)
    return best


def main():
    results = {}
    for tag, db in (("GPU_incremental", WD / "db_gpu.db"),
                    ("CPU_incremental", WD / "db_cpu2.db")):
        print(f"\n===== {tag} =====", flush=True)
        best = run_sfm(db, WD / f"sfm_{tag}", tag)
        if best is None:
            continue
        mp = WD / f"sfm_{tag}" / "best_model"
        mp.mkdir(exist_ok=True)
        best.write(str(mp))
        print(f"[{tag}] scoring 9 gates...", flush=True)
        results[tag] = SG.score(mp, tag)

    # context: champion A_glomap (CPU features + GLOMAP poses + triangulation)
    ag = FP / "arms" / "A_glomap" / "model"
    if not ag.exists():
        ag = FP / "arms" / "A_glomap"
    try:
        print(f"\n===== A_glomap (champion reference) =====", flush=True)
        results["A_glomap"] = SG.score(ag, "A_glomap")
    except Exception as e:
        print(f"[A_glomap] score failed: {e}", flush=True)

    (WD / "gate_scores_gpu_ab.json").write_text(json.dumps(results, indent=2))
    print("\n" + "=" * 96, flush=True)
    print(json.dumps(results, indent=2), flush=True)

    # degradation table: GPU vs CPU (both full incremental — the fair A/B)
    if "GPU_incremental" in results and "CPU_incremental" in results:
        g, c = results["GPU_incremental"], results["CPU_incremental"]
        GATES = [("reproj_median_px","lower",3.0),("sv_surface_var","sv",0.0630),
                 ("tri_angle_deg","higher",0.97),("weak_track_pct","lower",3.0),
                 ("sphere_fit_mm","lower",3.0),("floor_thick_mm","lower",3.0),
                 ("arkit_pos_mm","lower",3.0),("arkit_orient_deg","lower",3.0),
                 ("point_count","higher",0.97)]
        print("\n" + "=" * 96)
        print(f"9-GATE: GPU-extract vs CPU-extract (both full incremental SfM, same matcher)")
        print(f"{'gate':<20}{'CPU(base)':>14}{'GPU':>14}{'change':>14}{'rule':>10}  verdict")
        npass = 0
        for name, kind, thr in GATES:
            cv, gv = c[name], g[name]
            if kind == "sv":
                ok = gv <= thr; chg = f"abs {gv:.4f}"; rule = f"<={thr}"
            elif kind == "higher":
                r = gv / cv if cv else 0; ok = r >= thr; chg = f"x{r:.3f}"; rule = f">={thr}"
            else:
                d = (gv - cv) / cv * 100 if cv else 0; ok = d <= thr; chg = f"{d:+.1f}%"; rule = f"<=+{thr}%"
            npass += ok
            print(f"{name:<20}{cv:>14.4g}{gv:>14.4g}{chg:>14}{rule:>10}  {'PASS' if ok else 'FAIL'}")
        print(f"  --> {npass}/9 gates pass")


if __name__ == "__main__":
    main()
