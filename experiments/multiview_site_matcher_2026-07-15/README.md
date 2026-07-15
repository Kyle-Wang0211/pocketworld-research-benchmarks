# Physical-site ownership experiments (2026-07-15)

## Outcome

The strongest current result is **pair-local physical-site assignment after
two-view geometry and before track/Point3D birth**. It prevents multiple SIFT
orientation variants at the same bit-identical image coordinate from creating
parallel 3D entities. It never deletes a captured frame, photo, registered
camera, or already-generated point; losing candidates simply do not receive a
birth edge.

The experiment remains default-OFF. It is the first tested variant that reduces
the cross-object ghost-layer signal on cap51 while improving floor thickness
and median image coverage, but its low-decile coverage and planar-error tail
still regress.

## Immutable inputs

- cap51 DB: `sfm_live.db`, 134,975,488 bytes,
  SHA-256 `af1bd571d81cf27228e6b1bd8faa9617a1734bf0d32c1c67ec849c4bc7f5ba97`
- cap51 pose ledger: `sfm_fed_frames.jsonl`, 105 records,
  SHA-256 `d86ac0c44a9e5ae154f286cc9fc6baf215f949c5335b4bf9210e87c6d018770c`
- Device capture identity: `cap_1783933521157217`
- Replay used stored device matches (`use_gpu_match=0` was not used to
  recompute them), `AETHER_INCREMENTAL_GLOBAL_BA` unset, and
  `AETHER_ENRICH_TIME_BUDGET_MS=1`.
- All reported arms registered every input frame: cap51 105/105, cap56 20/20.
- No LiDAR or sceneDepth input is read by any experiment in this directory.

## Cross-object birth metrics

The near-ray metric counts distinct published Point3D pairs that project within
8 px in at least two/three registered views while remaining 12–100 mm apart in
depth. The normal-layer metric additionally requires locally consistent surface
normals. These are diagnostic birth-conflict signals, not post-generation point
filters.

| Capture / arm | Published points | floor 16–84% (mm) | coverage median / p10 | 8 px conflicts 2v / 3v | normal 20° / 30° | planar p50 / p90 / p95 (mm) |
|---|---:|---:|---:|---:|---:|---:|
| cap51 control | 12,588 | 5.148 | 91.5 / 8.3 | 43 / 22 | 8 / 11 | 1.119 / 8.309 / 13.289 |
| cap51 global forest | 10,370 | 17.121 | 88.5 / 6.2 | 18 / 9 | 2 / 3 | 1.157 / 8.877 / 14.940 |
| cap51 pair-local assignment | 10,367 | **2.844** | **94.0** / 6.6 | **17 / 9** | **2 / 2** | 1.334 / 10.104 / 15.944 |
| cap56 control | 2,570 | 15.975 | 136.0 / 108.6 | 8 / 1 | — | 1.599 / 7.633 / 11.606 |
| cap56 pair-local assignment | 2,163 | 16.038 | 133.0 / 113.9 | 3 / 0 | — | 1.916 / 9.472 / 14.346 |
| cap56 global forest | 2,187 | 16.105 | 136.0 / 117.8 | 1 / 0 | — | 1.898 / 9.155 / 13.222 |

Primary evidence:

- `cap51_cpp_postgeom_site_ab_20260715.json`
- `cap51_global_physical_site_forest_ab_20260715.json`
- `cap56_cpp_postgeom_site_ab_20260715.json`
- `cap56_global_physical_site_forest_ab_20260715.json`

## What was rejected

1. **Global greedy forest**: the physical-site invariant is useful, but a
   single greedy pass can connect the wrong hypotheses across image pairs.
   cap51 floor thickness and low-decile coverage fail despite fewer ghost
   births.
2. **Geometry-first global ordering**: Sampson-first ordering did not recover
   density or plane quality on cap56.
3. **Conservative proximity/descriptor track merging**: changed too few tracks,
   worsened cap51 near-ray conflicts, and can merge genuinely distinct nearby
   structure.
4. **Blind BA multiplicity compensation**: repeating the canonical residual for
   every same-site SIFT variant improved coverage but drove cap51 floor thickness
   to 30.893 mm. The diagnostic implementation was removed from C++.
5. **Ray normalization combined with post-geometry assignment**: applying new
   rays without consistently re-estimating geometry worsened the Pareto result.
6. **Surface residuals after Point3D birth**: parameter sweeps did not solve the
   topology error and violate the intended causal boundary if used as a ghost
   cleanup mechanism.

The cap51 control log contains 61 dense-Cholesky step warnings; the pair-local
arm contains 32. The warning therefore predates site assignment and is not
evidence that the pair-local topology introduced the numerical issue.

## Current implementation boundary

- C++ flag: `AETHER_POSTGEOM_SITE_ASSIGN=1`
- Default: OFF
- Assignment occurs only after robust two-view geometry and before verified
  correspondences are admitted to track/Point3D birth.
- Raw descriptors and raw matches remain available for RANSAC and diagnostics.
- A pair below the verified-inlier gate cannot silently fall back to raw-match
  point birth.

The next accepted change must preserve the cap51 ghost/floor/median-coverage
gains while restoring p10 coverage and planar p90/p95. Candidate ranking should
be pair-local and use verified geometry plus multi-view cycle/track support;
global one-pass union is not accepted.

## External evidence used for direction, not copied code

- COLMAP PR 3681 supports exact one-to-many correspondences but does not impose
  physical-site track ownership:
  <https://github.com/colmap/colmap/pull/3681>
- Meshroom describes same-image multi-feature tracks as track forks and exposes
  fork filtering before reconstruction:
  <https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/StructureFromMotion.html>
- Detector-Free SfM alternates multi-view track-topology refinement with geometry
  refinement instead of treating pair matches as final:
  <https://zju3dv.github.io/DetectorFreeSfM/>
- Pixel-Perfect SfM refines keypoint observations before and after geometric
  estimation:
  <https://github.com/cvg/pixel-perfect-sfm>

## Artifact retention

Derived DB snapshots and replay PLY/session artifacts were removed after metric
extraction to protect workstation disk space. Their pre-deletion size and
SHA-256 identities are preserved in `derived_db_sha256_20260715.tsv`; source
DBs, ledgers, scripts, JSON metrics, run logs, and existing DVC targets were not
removed.
