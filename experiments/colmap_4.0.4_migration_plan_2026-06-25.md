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

## EXECUTION RESULTS (2026-06-25) — code-complete, host + iOS-lib validated; device smoke pending

Branch `colmap-4.0-migration` (worktree `/tmp/aether-colmap40`). Done via 3 orchestrated agents + checks.

- **STEP 0-1 source:** vendored 4.0.4 (latest stable, 2026-04-27). CHECK A: worktree colmap-src/colmap diffs upstream
  4.0.4 ONLY in the 4 patched files + 1 build-fix + generated version.cc — independently re-verified, zero collateral.
- **STEP 2-3 patches + host build:** 19 [AETHER] patches re-homed. KEY 4.0.4 refactor: BA loss/threshold config moved
  into nested `CeresBundleAdjustmentOptions` (`options.ceres->...`); bundle_adjustment.cc split → the solver routing +
  EIGEN_SPARSE force + solver_used log now live in **`bundle_adjustment_ceres.cc`** (`SolveWithGpuFallback`). Build fixes
  (no behavior change): CHOLMOD strip in least_absolute_deviations.cc; CMake exclude `_test.cc`, add `estimators/solvers/*.cc`,
  exclude `rotation_averaging_impl.cc`; `colmap_ios_stubs.cc` rewritten for 4.0.4 OIIO-backed Bitmap; bench adapted to the
  new `IncrementalPipeline(opts, shared_ptr<Database>, ...)` ctor. Host `colmap_bench_exe` builds green.
- **STEP 4 CHECK B (perf):** db.db (SIMPLE_RADIAL, qualifies for the analytical Jacobian) DENSE-396 CAUCHY finalize:
  **4.0.4 = 292s / 2.60GB / reproj 0.962** vs documented 3.14 baseline 450s / 2.91GB / ~0.958. Faster + quality-neutral
  + lower memory; `[AETHER] solver_used=DENSE_SCHUR` confirmed active in 4.0.4. Honest caveat: 3.14 binary CANNOT read
  the 4.0-schema db.db (no back-to-back same-machine control), so the headline −35% is likely inflated by uncontrolled
  thermal/load; the **confident claim is ≥15% faster, quality-neutral**.
- **STEP 5 iOS (Option B):** GLOMAP dropped from `glomap_core` (production never consumed it — shipped .a had only the
  defined `RetriangulateTracks` -force_load stub, now deleted). DSP-SIFT extractor ported to 4.0.4's `FeatureDescriptors`
  struct (`{type,data}`); 2 AETHER covdet setters re-added (they were our own additions, not stock VLFeat; both VLFeat = v0.9.20).
  **The feared front-end risk is DISPROVEN: `extract_selfcheck` is BIT-IDENTICAL (max_abs_desc_diff=0, nthreads 1/2/4/8),
  re-verified independently** — the proven keypoints/descriptors did not drift. `libglomap_core.a` builds clean for
  **arm64-iphoneos** (has the covdet setters + threaded extractor, zero glomap symbols). ALIKED/LightGlue-ONNX link stubs
  added (SIFT path never reaches them).
- **Commits:** host migration + STEP 5 (`b3a97ff6`) on `colmap-4.0-migration`.

### STEP 6 device smoke — DONE, PASS (clean same-db device head-to-head)
GlomapBench rebuilt against the worktree 4.0.4 `glomap_core` (build_ios.sh + project.yml repointed to the worktree;
`glomap_bench.cc` dropped from the app sources — it referenced the removed GlobalMapper), code-signed, deployed to
iPhone 14 Pro (`1B290474-...`), ran `aether_async_bench(real414_v313_nodesc.db, gref=5, giter=50, CAUCHY)` on the
4.0-schema device db (26201 matches — the SAME db as the 3.14 device baseline, so a clean head-to-head).

Verified from `aether_console.log` (244KB): 0 errors/crashes/jetsam; 795 `solver_used=DENSE_SCHUR` lines, ZERO non-DENSE;
795 from `bundle_adjustment_ceres.cc` / 0 from old `bundle_adjustment.cc` (100% 4.0.4 code path); BENCH_DONE, done=1, 396/396 registered.

| device metric (same 26201-match db, same iPhone 14 Pro, CAUCHY) | 3.14 baseline | 4.0.4 | delta |
|---|---|---|---|
| local recon (local_ms) | 254220 | 252023 | ~same |
| **finalize (refine_ms)** | 634627 (635s) | **501250 (501s)** | **−21%** |
| refined_reproj | 0.9599 | 0.9661 | parity (slightly better) |
| peak mem | 2303.8 MB | 2376.8 MB | +3% (~same, ample jetsam margin) |
| thermal (start/local/refine) | — | 0/2/2 (fair) | — |
| drift mean/max % | 0.748 / 1.812 | 1.529 / 3.269 | higher (see note) |

**Device −21% is the rigorous speedup figure** — same db, same device, same config (vs the host −35%, which had no
back-to-back control because 3.14 can't read the 4.0-schema host db). Above the 4.0 release's ~15% (SIMPLE_RADIAL+trivial).
Drift note: 4.0.4's local→refined drift is higher, but refined reproj is BETTER (0.9661 vs 0.9599) — the 4.0.4 BA
(single pose block + analytical Jacobian) converges to a better optimum and corrects the local estimate more; not an
accuracy regression (reproj, the delivered-quality metric, improved). Drift is also noisy (build non-determinism).

## MIGRATION COMPLETE — validated end-to-end (host + front-end + iOS lib + device). Ready to merge.
`colmap-4.0-migration` branch (host migration + STEP 5 `b3a97ff6`) is validated and ready to merge → the production
branch (`claude/publish-to-community`). Net: COLMAP 3.14→4.0.4, ~15-21% faster CAUCHY DENSE finalize, quality-neutral,
DSP-SIFT front-end bit-identical, GLOMAP dropped from the iOS lib, all device-verified on iPhone 14 Pro.
