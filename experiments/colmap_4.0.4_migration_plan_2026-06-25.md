# COLMAP 3.14 → 4.0.4 vendored migration plan

Date: 2026-06-25. Goal: re-vendor COLMAP 4.0.4 (latest stable, 2026-04-27) into
`aether_cpp/third_party/glomap_vendor/colmap-src` to get the ~15% BA speedup (single pose
parameter block + analytical Jacobians for SIMPLE_RADIAL+trivial frames — we ARE SIMPLE_RADIAL
model_id=2 + single-camera trivial frames, so we qualify) + the AdjustGlobalBundle crash fix.

## Foundation (DONE)
- Version verified: **4.0.4** (2026-04-27, latest stable; 4.1.0 is unreleased dev). Recent, not stale.
- Worktree: `git worktree add /tmp/aether-colmap40 -b colmap-4.0-migration` (isolates from working 3.14).
- 4.0.4 source: `/tmp/colmap404` (`git clone --branch 4.0.4 --depth 1 https://github.com/colmap/colmap`).
- BA refactor mapped: `bundle_adjustment.cc` (1248→374 lines) split into abstract `bundle_adjustment.cc`
  + **`bundle_adjustment_ceres.cc/.h`** (Ceres backend = where solver routing now lives).

## Our [AETHER] patches → 4.0.4 new home (patch mapping table)
| Patch | 3.14 location | 4.0.4 new home | Difficulty |
|---|---|---|---|
| Force EIGEN_SPARSE (CPU sparse path, !use_gpu) | bundle_adjustment.cc:360 | **bundle_adjustment_ceres.cc** (CreateSolverOptions) | HARD |
| A1 CLUSTER_JACOBI preconditioner (ITERATIVE branch) | bundle_adjustment.cc:375 | bundle_adjustment_ceres.cc | HARD |
| `solver_used=` unconditional log | bundle_adjustment.cc:774 | bundle_adjustment_ceres.cc (after Solve; summary type may have changed to BundleAdjusterSummary — adapt or drop) | HARD |
| CAUCHY DENSE routing **dense=1000/sparse=5000** + env AETHER_DENSE_THRESH/SPARSE_THRESH | incremental_pipeline.cc:170 (GlobalBundleAdjustment) | incremental_pipeline.cc (similar) — but the thresholds are BA options; verify they're still `max_num_images_direct_dense_cpu_solver` and reachable | MODERATE |
| ba_local/global_loss_scale + loss_function_scale | incremental_pipeline.cc:128,164 | incremental_pipeline.cc | MODERATE |
| Tunable loss config + defer_global_ba + skip_finalize_global_ba | incremental_pipeline.h:136,144,150 | incremental_pipeline.h | MODERATE |
| keep-CAUCHY-pass-2 (no TRIVIAL downgrade in IterativeLocalRefinement) | incremental_mapper.cc:1194 | incremental_mapper.cc (similar) | EASY |
| Harness: aether_*c C ABI + on-screen console + phys_footprint sampler | bench/colmap_bench.cc + iosapp/AppDelegate.m | adapt to 4.0.4 BA/pipeline API | MODERATE |

(GLOMAP patches NOT migrated — GLOMAP is out on device.)

## New deps to DISABLE (we are db-only SfM; no feature extraction in the vendored lib)
- `ONNX_ENABLED=OFF` (4.0.4 default ON, for ALIKED) — we don't extract features here.
- OpenImageIO (replaced FreeImage) — image I/O; we use `extract_colors=false` (db-only). Disable/stub.
- LightGlue / ALIKED — not needed.
- Keep only the SfM core (scene, estimators, sfm, controllers, geometry, math, optim, mvs as needed).

## DB schema note
4.0 added rig/frame tables + descriptor-type. Existing 3.x test dbs (db.db, real414_v313, pycolmap 3.13-gen)
may need re-gen with pycolmap 4.0 OR 4.0.4 may forward-migrate. CHECK: does 4.0.4 colmap_bench_exe read our
existing dbs? If not, re-gen one test db with pycolmap 4.0 for the perf check. Production on-device gen uses
the vendored 4.0.4 → emits 4.0.4 schema (no issue).

## Step-by-step execution + per-step checks
Each step has TWO checks the user requires: (A) "copied upstream correctly" = non-patched code is bit-equal
4.0.4 (`diff` vs /tmp/colmap404); (B) "perf actually improved" = the final DENSE-396 is faster than 3.14.

- **STEP 1 — replace source.** Copy `/tmp/colmap404/src/colmap` → worktree `colmap-src/colmap` (+ the repo-root
  CMake/cmake/ as the vendored build needs). CHECK A: `diff -r` worktree colmap-src vs /tmp/colmap404 src = identical.
- **STEP 2 — re-apply patches** (3 sub-areas, can parallelize across files):
  - 2a bundle_adjustment_ceres.cc: EIGEN_SPARSE force + DENSE routing knobs + A1 + solver_used log. CHECK A: only [AETHER] lines differ vs upstream.
  - 2b incremental_pipeline.{cc,h}: DENSE threshold 1000 + loss config + defer/skip. CHECK A.
  - 2c incremental_mapper.cc: keep-CAUCHY-pass-2. CHECK A.
- **STEP 3 — build integration.** Disable ONNX/OpenImageIO; fix vendored CMake + build_ios.sh for the SfM-core-only
  build. CHECK: host cmake configure + `cmake --build` of colmap_bench_exe SUCCEEDS.
- **STEP 4 — host verify (perf + quality).** Run DENSE-396 on db.db (re-gen if schema breaks). CHECK B:
  refine_ms < 3.14's 450s (expect ~15% → ~380s); reproj ≈ 0.958 (quality-neutral). If NOT faster → investigate
  (the ~15% is SIMPLE_RADIAL analytical Jacobian — confirm it's active).
- **STEP 5 — iOS + device verify.** build_ios.sh + iosapp + device run real414 DENSE. CHECK B: device refine_ms
  < 3.14's 635s; no crash; peak mem ≤ 2.30GB.
- **STEP 6 — finalize.** Commit the migration to the colmap-4.0-migration branch; merge to main branch when verified.

## Rollback
The working 3.14 stays untouched on the main branch (`claude/publish-to-community`). The migration is isolated in
the `/tmp/aether-colmap40` worktree on `colmap-4.0-migration`. If 4.0.4 underperforms or breaks, abandon the branch.
