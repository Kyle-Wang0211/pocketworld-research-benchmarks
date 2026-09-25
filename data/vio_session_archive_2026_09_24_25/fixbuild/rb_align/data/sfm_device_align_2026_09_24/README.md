# SfM delivered-scale fix: device-pose Sim3 alignment (2026-09-24)

Archive of the 2026-09-24 work on "on-device SfM does not inherit the device
trajectory's scale". Everything here was copied from a volatile session
scratch dir (lost on reboot):

`SCR = /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad`

Diagnostic/research material only. Nothing here is shipped. The patches are
not applied to any product branch by this commit.

## Decisions (user-approved)

- **B + C.**
  - **B**: in the SfM core (Aether3D `official_pipeline`), add an end-of-finalize
    robust Sim3 alignment of the delivered model to the fed device camera
    centres. This copies COLMAP 3.14's pose-prior alignment step (LO-RANSAC Sim3
    followed by `Reconstruction::Transform`) and adds a gate.
  - **C**: retire the Dart `SCALE-ANCHOR` switch, which was silently off.
    Dart reads the `Platform.environment` launch snapshot and never sees the
    Swift `setenv`.
- **σ comes through COLMAP's official prior-covariance input, set to
  0.040 m.** The value is pocketworld `lib/vio/platform_pose/platform_pose_source.dart:57`
  `kPlatformTranslationSigmaFloorM` (pw-dense-stage @1a43510), and it is
  supplied as the per-prior `PosePrior::position_covariance`. This follows the
  upstream `RunPosePriorMapper` `prior_position_std_*` +
  `overwrite_priors_covariance` path (`exe/sfm.cc:508-515`). The RANSAC
  threshold is computed only by the copied upstream formula
  (`bundle_adjustment_ceres.cc:1402-1426`). No threshold is typed by hand.
  Full provenance is in the header comment of `step2_patches_and_results/header/device_pose_alignment_v1.h`.

## Headline results

- **σ = 0.04 m via the official mechanism: all controls pass**
  (`step2_patches_and_results/results/analyze_cov040.json`).
  - Good arms (prod74 / prod / deb74 / deb, each with A and Xhost): all
    `aligned`, all pairs inliers. Delivered units per device metre are
    0.9984–0.9997.
  - Negative controls trip the gate: `Xdev` 7/13 inliers; shuffled poses
    (`shuf` A / Xhost) 4/13.
  - ×1.10 device-scale control: the delivered ratio is 1.099997 / 1.100000 /
    1.100001.
  - Rerun is reproducible (ratio 1.0000000000). σ=0.04 and σ=1 m give the same
    scale on the good arms (ratio 1.000000000000).
  - Held-out scale error (fit on even frames, evaluate odd frames): at most
    1.76% at 13 frames and at most 0.185% at 109–110 frames.
- **Phone gate replay on 90 captures: 6 trips.** The result is bit-identical
  to the older σ=0.040 typed-constant variant
  (`taskB/summary_taskB.json`, `logs/phone_gate_cov040.log`).
  - 2 are **device-side**:
    - `cap_1787733401226757`: fed ARKit poses marked `limited_initializing`
      (poseSource=imu).
    - `cap_1789119308200005`: mixed ARKit sessions after orphan recovery. The
      extend-capture refeed after a reboot gives 34.4 deg yaw about gravity.
  - 4 are **SfM-side**: `cap_1788795741337526`, `cap_1784820775062947`,
    `cap_1786013666212373` and `cap_1786199789306631`. The core bypasses
    upstream `RegisterNextImage` evidence checks, so weakly supported frames
    get registered.
- **Upstream pose-prior BA does not fix it.** Example: `cap_1786013666212373`
  U0/U1/U2 still has frames 18–19 at 595 mm, and re-registration gives the same
  result.
- **The resume path is mixed.**
  - It fixes two big captures:
    - `cap_1786013666212373`: 154/154 aligned, max 28 mm.
    - `cap_1786199789306631`: 189/189.
  - It bends to wrong poses in the mixed-session case. On
    `cap_1789119308200005`, the model follows the device and the gate passes.
- Step 1 (phone captures, before the fix, 90 captures): the delivered/device
  scale deviation has median 2.38% and max 22.49%. Most of it forms during
  live reconstruction: finalize/live median is 0.25% (n=54).

## Contents

### `step1_phone_scale/`: from `SCR/step1/`

This study is read-only. It measures whether the delivered SfM scale inherits
the device (ARKit) trajectory across 90 phone captures.

- `analyze.py`: the analysis script. `python3 analyze.py` writes
  `results.{json,tsv}`. `python3 analyze.py controls` writes `controls.json`.
- `results.tsv`, `results.json`, `controls.json`: per-capture outputs and
  control checks.
- `rows.json`, `usable_caps.json`, `caps_dirs.json`, `all_cap_ids.txt`:
  intermediate capture selection.
- `all_files*.txt`, `find_dev*.txt`, `files_known_roots.txt`: file
  inventories that `analyze.py` reads (`all_files_stat.txt`). Capture data
  stays in the device-backup dirs listed there. It is not copied here.

### `step2_patches_and_results/`: from `SCR/step2/`

Patches (base: Aether3D `7dc00642` + PocketWorld shim `4e22ee7` for B, and the
pocketworld Flutter app for C):

- `patch_B_device_align_v1.diff`: **current B**. σ is supplied through the
  official per-prior covariance (0.040 m). It passes `git apply --check`
  against the base. The first `diff --git` line of the new header shows
  `a/../src/...`, but that is cosmetic because `git apply` uses the
  `+++ b/...` path.
- `patch_B_device_align_v1.sigma1m.diff`: B with σ from the upstream 1.0 m
  fallback. Shuffled negative controls did not trip with this variant.
- `patch_B_device_align_v1.sigma040.diff`: B with σ=0.040 typed as a constant.
  This is the older form and is superseded by the covariance path.
- `patch_C_retire_dart_scale_anchor.diff`: current C, which removes the Dart
  scale-anchor switch and the Swift `setenv`. `.v0.diff` is the first version
  and differs only in a comment.
- `header/device_pose_alignment_v1.h`: copied from
  `SCR/step2/src/aether_cpp/official_pipeline/src/device_pose_alignment_v1.h`.
  It is identical to the file that `patch_B_device_align_v1.diff` creates
  (blob `a701456`).

Tools, runs and results:

- `tools/`: build and batch scripts (`build.sh`, `batch_*.sh`, `run_arm*.sh`),
  control-feed generators (`make_control_feeds.py`, `make_phone_replay*.py`),
  analyzers (`analyze_{1m,cov,fix}.py`), the offline phone gate
  (`phone_gate_offline.py`, `device_align_offline.cc`), and ablations.
- `driver/`: `pwofficial_pose_ab_driver.cc`, the host A/B driver. The
  `.pre_jpeg` file is its pre-JPEG-input version.
- `inputs/`: feed jsonl files. All are under 1 MB, so all are kept.
- `runs/<arm>/`: text outputs only (`run.log`, `per_frame.jsonl`,
  `sfm_match_fail.jsonl`, `delivered_poses.txt`, json). Binary models
  (`*.bin`, `cloud.ply`, `session.db.arkit_pose_v1`) are excluded. The
  `pre_*` runs hold relative symlinks into their matching `fix*` runs.
- `results/`: `analyze_cov040.json` (headline), the `analyze_1m_*` /
  `analyze_fix_*` / `analyze_sigma040_*` earlier σ arms, per-arm held-out
  pairs, `phone_gate/` (90 per-capture pair tables), `pred1m/`, and
  `takeover_*.json`.
- `taskB/`: per-capture root-cause work for the 6 trips.
  `summary_taskB.json` holds the verdicts. There are also two-view checks
  (`twoview_*`), `eval/`, frame tables and `sheet_cap_1788795741337526.png`.
- `proto/`: upstream-COLMAP prototypes (U0/U1/U2 pose-prior BA,
  RR re-registration) with `prep_db.py` and `run_upstream.sh`. The sparse
  models (`*.bin`) are excluded by the repo `.gitignore` (`*.bin`). Only
  `points3D.txt` and the scripts are kept.
- `logs/`: build, batch and phone-gate logs.
- `dart_anchor_offline.{py,json}`: an offline replay of the Dart
  scale-anchor.
- `dart_check_*.txt`: pub get, analyze and test output for patch C.

Not copied: `src/`, `src_orig/`, `base_sfmB/`, `build/`, `c_patch/` (already
captured by patch C), `dart_check/` (a copied Flutter tree), `pubspec*.bak`,
`pick.txt` and `device_pose_alignment_v1.h.sigma040.bak`. The last one is
captured by the sigma040 diff. See `artifacts/local_heavy_artifacts.md`.
