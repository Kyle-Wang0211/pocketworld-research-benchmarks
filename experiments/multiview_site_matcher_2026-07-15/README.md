# Physical-site ownership experiments (2026-07-15)

## Outcome

The strongest current result is **multi-view depth-conflict ownership at the
product-point birth certificate**. All verified observations and internal
Point3D hypotheses remain available to registration and bundle adjustment.
Only when two independently certified hypotheses occupy the exact same
physical image site in at least two registered views, yet disagree by at least
12 mm in metric depth, does the stronger hypothesis receive the user-visible
point identity. No captured frame, photo, registered camera, BA observation,
internal hypothesis, or previously visible point is deleted.

The decisive implementation correction was to treat COLMAP's negative
`Point3D.error` value as the "not computed" sentinel. The earlier comparator
mistakenly ranked `-1` ahead of every measured reprojection error. With the
sentinel corrected, matched cap51 and cap56 A/B runs retain 100% frame
registration and identical coverage while improving every comparable geometry
metric and sharply reducing duplicate-layer births. The switch remains
default-OFF until the same code path is compiled and exercised through the
cross-platform product ABI.

### Current no-regression result

| Capture / arm | Registered | Internal points / observations | Published points | floor 16–84% (mm) | coverage median / p10 / min | 8 px conflicts 2v / 3v | normal 30° 2v / 3v | planar p50 / p90 / p95 (mm) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cap51 OFF | 105/105 | 65,794 / 170,338 | 12,632 | 9.420 | 96 / 6.2 / 1 | 48 / 22 | 11 / 9 | 1.1846 / 8.9425 / 14.6115 |
| cap51 owner | 105/105 | 65,794 / 170,338 | 12,611 | **9.405** | **96 / 6.2 / 1** | **25 / 8** | **2 / 1** | **1.1836 / 8.9255 / 14.5845** |
| cap56 OFF | 20/20 | 17,025 / 44,803 | 2,571 | 15.243 | 130 / 104.3 / 97 | 7 / 1 | 0 / 0 | 1.4721 / 7.2508 / 11.1285 |
| cap56 owner | 20/20 | 17,025 / 44,803 | 2,567 | 15.290* | **130 / 104.3 / 97** | **3 / 0** | 0 / 0 | **1.4714 / 7.2152 / 10.9789** |

`*` The per-arm adaptive floor proxy recomputes its 2%/15% rank boundaries
after the product population changes from 2,571 to 2,567. All four withheld
IDs are outside the 334-point OFF floor support set. On that fixed semantic
support, thickness is exactly `15.2425665493 -> 15.2425665493 mm`; the internal
models differ by at most `3.7e-13` in point coordinates. This is a rank-boundary
artifact, not a floor-geometry regression.

Primary evidence for this result:

- `cap51_publish_multiview_owner_nonnegative_ab_20260715.json`
- `cap56_publish_multiview_owner_nonnegative_ab_20260715.json`
- `publish_depth_conflict_owner_verdict_20260715.json`

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
