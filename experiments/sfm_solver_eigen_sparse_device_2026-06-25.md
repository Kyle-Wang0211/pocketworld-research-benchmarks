# On-device SfM finalize solver — EIGEN_SPARSE fix + COLMAP-vs-GLOMAP device validation

Date: 2026-06-24 / 2026-06-25
Device: iPhone 14 Pro (iOS 26.5), app jetsam limit ~4.1 GB
Code commit: `aether_cpp` Aether3D-cross `b17820ea` (+ GLOMAP GP-ITERATIVE experiment, uncommitted)
Bench db (Mac): `tools/python/sfm_cmp/db.db` (396 img, 78210 matches, dense)
Bench db (device): `real414_v313_nodesc.db` (396 img, 26201 matches)

## TL;DR
1. **"SPARSE_SCHUR crashes on iOS" was an operation error, not an algorithm limit.** The default Ceres sparse backend is Apple **Accelerate**, whose sparse Cholesky fails (`SparseFactorizationFailed`) on the indefinite/near-singular CAUCHY-reweighted Schur complement. Forcing **`ceres::EIGEN_SPARSE`** (Eigen SimplicialLDLT) factorizes it fine **and** is faster than the ITERATIVE_SCHUR workaround.
2. **Device-validated (COLMAP):** full-scene 396-frame finalize runs on iPhone 14 Pro at **SPARSE_SCHUR + EIGEN_SPARSE**, no crash, 5 refinement passes, thermal 2.
3. **GLOMAP is out on device:** it dies during global positioning (both SPARSE+EIGEN and ITERATIVE), i.e. not a linear-solver fill-in issue — GLOMAP's global working set doesn't fit the 4.1 GB device. **COLMAP is locked as the on-device engine.**

## Solver comparison — Mac (db.db 396 / 78210 matches, full-quality CAUCHY)
| Solver | build (local) | finalize (global) | reproj | peak footprint |
|---|---|---|---|---|
| ITERATIVE_SCHUR + SCHUR_JACOBI (baseline) | 144s | 879s | 0.955 | 2.36 GB |
| ITERATIVE_SCHUR + CLUSTER_JACOBI (A1) | 144s | 679s | 0.9647 | 2.85 GB |
| **SPARSE_SCHUR + EIGEN_SPARSE** | 169-202s | **509-538s** | 0.959-0.961 | 3.77 GB |
| GLOMAP ITERATIVE_SCHUR | — | 1412s (total) | (not output) | 3.31 GB |
| GLOMAP SPARSE_SCHUR + EIGEN_SPARSE | — | 375-571s (recon) | 1.35 (core-only*) / TODO full | 4.20 GB |

\* GLOMAP core-only = `skip_retriangulation+skip_pruning`; reproj unfairly high. Full GLOMAP (retriangulation on) attempted on device → OOM/crash (see below).

## Solver comparison — device (iPhone 14 Pro, real414 396 / 26201 matches, full-quality CAUCHY)
| Solver | build (local) | finalize (global) | reproj | peak memory |
|---|---|---|---|---|
| COLMAP CAUCHY→DENSE (≤200 selected region, ~80f) | — | 42.5-53s | 0.846 | (not measured) |
| **COLMAP SPARSE_SCHUR + EIGEN_SPARSE (full scene)** | 250-261s | **959-1044s (16-17min)** | **0.9606-0.9608** | **3.07 GB** |
| GLOMAP full (RA+GP+BA+retri) | — | **DIED at global positioning** | — | **>4.1 GB (jetsam/crash)** |

Notes:
- Device ≈ 1.8-2× Mac wall-clock for the same finalize.
- Device peak (3.07 GB, real414/26201) < Mac peak (3.77 GB, db.db/78210): device problem is sparser → less memory (confirms Mac mem ≠ device mem).
- GLOMAP died at "Solving the global positioner problem" with **both** SPARSE+EIGEN and ITERATIVE solvers → not a linear-solver fill-in artifact; the GP working set (all frames + all tracks held jointly) exceeds the device limit (or a numerical crash in GP). OOM-vs-crash not 100% disambiguated, but GLOMAP is out either way.

## Why the scale-dependent solver switch (DENSE/SPARSE/ITERATIVE) — not a hack
Web-verified against the foundational literature and the toolchain authors:
- **"Bundle Adjustment in the Large" (Agarwal, Snavely, Seitz, Szeliski, ECCV 2010)** — DENSE for ~100 cameras, SPARSE for larger sparse Schur, ITERATIVE (CG + preconditioner) for very large; "truncated Newton (CG) + simple preconditioners = SOTA for large-scale BA".
- **Ceres Solver FAQ** (the authors) recommend exactly this DENSE_SCHUR / SPARSE_SCHUR / ITERATIVE_SCHUR+SCHUR_JACOBI split by problem size.
- **COLMAP defaults**: `max_num_images_direct_dense_cpu_solver=50`, `..._sparse_cpu_solver=1000`.
- **No single solver is optimal at all scales** (dense O(n³) / sparse fill-in / iterative CG each win a regime). The only "unified" option is ITERATIVE everywhere (low-memory, slower) — which is what was tried to rescue GLOMAP's GP.
- Our override sets dense=200 / sparse=5000 (dense raised from 50 originally to dodge the Accelerate crash). **TODO: with SPARSE+EIGEN no longer crashing, dense can likely drop back toward ~50 so 50-200-frame selected regions take the (possibly faster) SPARSE path — to be benchmarked.**

## Code changes (Aether3D-cross commit b17820ea)
- `colmap-src/.../estimators/bundle_adjustment.cc`: force `EIGEN_SPARSE` for CPU sparse path (`!use_gpu`); A1 preconditioner SCHUR_JACOBI→CLUSTER_JACOBI for ITERATIVE fallback; log actual solver+backend.
- `colmap-src/.../controllers/incremental_pipeline.cc`: CAUCHY full-capture → SPARSE_SCHUR (dense≤200, sparse≤5000).
- `glomap-src/.../estimators/{bundle_adjustment,global_positioning}.cc`: same SPARSE+EIGEN routing (GLOMAP); `controllers/global_mapper.cc` releases the pre-filter track superset.
- `bench/glomap_bench.cc`: output mean reprojection error; full pipeline (retriangulation on).
- `iosapp/Sources/AppDelegate.m` (device-test harness, standard going forward): full-screen on-screen console mirroring stdout+stderr; tee to `Documents/aether_console.log` (pull via `xcrun devicectl device copy from`, survives USB drops, no root); phys_footprint peak sampler (PEAK_MEM_MB).

## Decision
**On-device SfM engine = COLMAP, SPARSE_SCHUR + EIGEN_SPARSE for the >200-frame finalize.** GLOMAP is out on device (GP OOM/crash, can't do selected-region efficiently, no capture-time incremental). The "global BA only polishes; local BA does the modeling" framing makes **local-BA optimization the top priority** going forward (capture-time, real-time, determines model quality; user accepts >2s/frame for a qualitative leap).

## 2026-06-25 FINAL UPDATE — DENSE_SCHUR supersedes EIGEN_SPARSE; local-BA levers failed

### Solver: DENSE_SCHUR is the final answer (not EIGEN_SPARSE)
Dense-threshold sweep + device verify reversed the EIGEN_SPARSE decision. No SuiteSparse on
iOS -> the only sparse backend is the slow simplicial EIGEN_SPARSE; AND object-centric
capture makes the reduced camera matrix DENSE (all cameras see the object) -> the "sparse"
Schur fills in -> dense Cholesky (fast BLAS, fixed O(n²) storage) wins on BOTH speed and memory.

| | DENSE_SCHUR | SPARSE_SCHUR+EIGEN_SPARSE |
|---|---|---|
| Mac db.db 396 finalize | 450s / 2.91GB | 538s / 3.77GB |
| db_50 / db_200 finalize | 14.8s / 113s | 16.9s / 146s |
| **Device real414 396 finalize** | **635s / 2.30GB** | 959-1044s / 3.07GB |
| reproj | 0.958-0.960 | 0.959-0.961 (same) |

Device: DENSE 34-39% faster + 25% less memory + same reproj + no crash + cleanest license
(pure Eigen dense MPL2). `incremental_pipeline.cc` CAUCHY dense threshold 200→1000 (commit 86e5eec0).
EIGEN_SPARSE was the necessary stepping stone (ruled out the Accelerate crash) but DENSE is final.

### Local-BA "qualitative leap" — tried, ablated, ABANDONED
Implemented 5 local-BA levers (anchor frames, covis×baseline window, release intrinsics,
retriangulation+long-tracks, more refinements) as toggleable options. Mac ablation on db.db
(local_reproj / drift_mean / drift_max):
- stock 0.987 / 0.50 / 1.87; all-on 1.049 / 1.15 / 3.09 (WORSE); ②④a 0.984 / 0.50 / 2.50 (neutral);
  +① anchor 0.996 / 1.09 (drift doubled — ① is a culprit); release-intrinsics ③ = biggest reproj culprit.
- **No lever delivers a win on clean data.** Local BA is already good (drift ~2%, reproj 0.99/0.95);
  the aggressive levers (① anchor = wrong variant of loop-closure; ③ intrinsics = overfit) HURT.
- Loop-closure (force first↔last match) ALSO doesn't apply: real414 is a DOME capture (cell_X_slot_Y),
  matching already connects spatially-adjacent frames across the capture (id1↔333, id411↔7) -> seam
  already closed -> drift already low. Levers reverted to bit-equal stock.
- Lesson: drift correction is the GLOBAL BA's job (not "just polish"); local BA already does its job on
  clean dome captures. Local-BA optimization only helps the worst (sparse/low-texture) captures.

## Open / next (确定能赢)
- Re-vendor latest COLMAP (analytical Jacobian / single pose block / deterministic seed) — free CPU speedup.
- Front-end DSP-SIFT extraction (5.4s/frame = real heat source) speed.

## 2026-07-12 UPDATE — host GLOMAP bench GP root cause: DENSE_SCHUR = 57 GB reduced matrix → SIGKILL; fix = SPARSE default

Disambiguates the earlier "DIED at global positioning / OOM-vs-crash not 100% disambiguated"
line for the **host full-chain bench** (`AETHER_HOST_GLOMAP_BENCH=ON` → `glomap_bench_full_exe`,
homebrew ceres). Small DBs (db_50 / db_200 / cap47_live) were SIGKILLed (exit 137) at "Solving
the global positioner problem"; db_300 / db.db-396 / sfm_dsp-414 ran. Not a memory-tier accident.

**Root cause (measured, `global_positioning.cc` instrumentation):** GP routed
`num_images <= 200 → DENSE_SCHUR`. That key was copied verbatim from the finalize-BA router
(`bundle_adjustment.cc`), where the DENSE decision above is correct because BA eliminates the
POINTS (e-block = points) so the reduced Schur matrix = cameras = num_images (object-centric →
dense but small). **GP's elimination group 0 is the per-observation SCALES, not points** — so
ALL points + camera positions stay in the reduced system. DENSE_SCHUR then materialises an
explicit `reduced_dim × reduced_dim` matrix where `reduced_dim = 3·(points + frames)`:

| DB | images | scales (e-block) | reduced points | reduced_dim | DENSE reduced matrix |
|---|---|---|---|---|---|
| db_50  | 50  | 158,838   | 29,233  | 87,849  | **57.5 GB** |
| db_200 | 200 | 778,634   | 125,254 | 376,362 | **1,055 GB** |
| db_300 | 300 | 1,159,437 | 172,219 | 517,557 | 1,996 GB |
| db.db-396 | 396 | 1,765,409 | 223,863 | 672,777 | 3,372 GB |

macOS SIGKILLs the tens-of-GB VM allocation. Big DBs (>200) only escaped because they already
fell through to the non-dense branch — the num_images key never described GP's actual cost.

**Fix (`global_positioning.cc`, host-bench-only file):** route DENSE_SCHUR on the ACTUAL
reduced dimension (`reduced_dim ≤ 4096` → 128 MB ceiling; essentially never fires for real GP),
and default the non-dense branch to **SPARSE_SCHUR + EIGEN_SPARSE** — the upstream GLOMAP GP
solver family: a DIRECT sparse factorization, deterministic and exact, that never builds the
dense reduced matrix. This REPLACES the former `ITERATIVE_SCHUR` default, which existed only as
a **device-jetsam salvage** — irrelevant now that `glomap-src` is host-bench-only (shipping iOS
lib `glomap_core` excludes `GLOMAP_SRC`; only `glomap_full`/bench compiles this file, so **iOS
production is untouched**). ITERATIVE's cost is real on host: its parallel-CG is
non-deterministic and on the weakly-triangulated db.db-396 it **metastably COLLAPSED to 3
registered images on one run while a sibling run kept all 396** (same solver, bit-identical GP
initial cost — pure run-to-run coin-flip in the downstream track filter). ITERATIVE stays
available behind `AETHER_GP_ITERATIVE=1` (with `AETHER_SPSE`); `AETHER_DENSE_MAX` force-override
and `AETHER_DENSE_LAPACK` hooks preserved; new `AETHER_GP_DENSE_MAXDIM` tunes the dense ceiling.

**5-DB verification (Fix B, SPARSE default, host homebrew ceres) — all deterministic, RSS ≪ OOM:**
| DB | before | after: registered / points / reproj_ba | peak RSS |
|---|---|---|---|
| db_50  | SIGKILL | 50 / 22,155 / 1.0216 | 0.48 GB |
| db_200 | SIGKILL | 200 / 103,538 / 0.9761 | 2.27 GB |
| cap47_live | SIGKILL | 97 / 36,482 / 1.3312 | 0.64 GB |
| db_300 | ITERATIVE (299 / 1.0367) | 299 / 144,455 / **1.0366** (match) | 3.13 GB |
| db.db-396 | ITERATIVE coin-flip (396 **or** collapse-to-3) | **396** / 197,552 / 1.2002 (stable) | 3.68 GB |
| sfm_dsp-414 | ITERATIVE | 414 / 179,532 / 1.0941 | 3.37 GB |

reproj_ba matches the healthy ITERATIVE runs to ≤0.05%; SPARSE additionally removes the collapse
risk. Note this is orthogonal to the finalize-BA DENSE_SCHUR decision above (that path is correct:
BA eliminates points, reduced = cameras = small dense). The bug was only the GP router reusing
BA's `num_images` key against GP's scale-in-e-block structure.
