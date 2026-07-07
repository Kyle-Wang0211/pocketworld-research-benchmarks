# GPU-extract → SfM → 9-gate validation (2026-07-07)

Proves the **GPU DSP-SIFT extractor** (aether_cpp, persistent-harness + pipeline
cache, 8.4× warm) produces SfM reconstructions of **equal-or-better quality** than
the CPU DSP-SIFT extractor. Clean frontend isolation: same GLOMAP poses, same
matcher, same triangulation options — **only the feature source differs**.

## Result — 9 gates, GPU-extract vs CPU-extract (frontend isolated)

| gate | CPU (base) | GPU | change | verdict |
|---|---|---|---|---|
| reproj_median_px | 1.091 | 1.038 | **-4.9% better** | PASS |
| sv_surface_var | 0.1225 | 0.1229 | +0.3% | dense-only gate¹ |
| tri_angle_deg | 6.693 | 6.943 | **×1.037 better** | PASS |
| weak_track_pct | 34.06 | 33.95 | -0.3% | PASS |
| sphere_fit_mm | 332.1 | 319.2 | **-3.9% better** | PASS |
| floor_thick_mm | 8.724 | 8.502 | **-2.5% better** | PASS |
| arkit_pos_mm | 10.83 | 10.83 | +0.0%² | PASS |
| arkit_orient_deg | 0.6044 | 0.6044 | +0.0%² | PASS |
| point_count | 359,398 | 360,069 | ×1.002 | PASS |

**8/9 pass; GPU is BETTER on 5 metrics, tied on 3.** ¹ SV ≤0.063 is a dense-cloud
threshold; sparse SfM sits at ~0.12 for both arms — GPU vs CPU differ only +0.3%,
not a regression. ² arkit_pos/orient identical by construction (both use the same
fixed GLOMAP poses; only features differ).

**Verdict: GPU extraction is lossless-to-better on SfM quality.** New standard GPU
baseline. Also confirmed via full incremental SfM (both arms registered all 414
frames; GPU 245k pts). Matching: GPU features gave 5.60M inliers vs CPU 5.44M
(+2.9%) on the identical 6159 pairs.

## Timing (host M3)
- GPU batch extract 414 frames: **123 s** (persistent harness; would be ~14 min
  without it — one Dawn init + compiled pipelines shared across all frames).
- Fixed-pose triangulation A/B: 75 s/arm.
- ⚠️ Full pycolmap `incremental_mapping` with DEFAULT options = ~19 min/arm
  (repeated global BA) — a slow validation tool, NOT the production SfM path
  (champion recipe ~7-8 min). Do not confuse extractor speed with SfM-solver speed.

## Reproduce
1. Build the batch extractor (Aether3D repo):
   `cmake --build aether_cpp/third_party/glomap_vendor/build-verify --target gpu_extract_batch_exe`
2. `python3.11 assemble_and_match.py`   # frames.txt → GPU extract → db_gpu/db_cpu2 → match same 6159 pairs
3. `python3.11 fast_tri_9gate.py`        # fixed-pose triangulation A/B + 9-gate table (fast)
   `python3.11 run_full_sfm_9gate.py`    # full incremental SfM A/B (slow, ~40 min both arms)

Large binaries (*.db, *.feat, sfm_*/, tri_*/) are gitignored — regenerable.
