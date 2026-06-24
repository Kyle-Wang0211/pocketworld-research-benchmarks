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

## Open / next
- Local BA qualitative leap (covisibility windows, drift suppression, intrinsics, retriangulation-in-loop) — priority.
- Global BA quality-neutral speedups (dense-threshold 200→50 for selected regions; preconditioners; multithreading).
- Front-end (DSP-SIFT extraction 5.4s/frame = real heat source) speed.
