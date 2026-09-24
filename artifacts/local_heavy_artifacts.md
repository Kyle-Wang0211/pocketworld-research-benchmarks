# Local Heavy Artifacts

These files are intentionally kept out of git. They are reproducibility inputs or large intermediate tensors for the reports archived in this repo.

## Latest 414-Frame Capture

- Capture bundle: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229`
- Baseline DA3 tensor export: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_cpu_probe`
- DA3-only vs DA3+MoGe benchmark output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229`
- MoGe auxiliary tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/moge_aux`
- Patch features CSV: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/patch_features.csv`

## Current Overlap Sweep

- Overlap-12 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap12`
- Overlap-9 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap09`
- Overlap-12 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap12_cpu`
- Overlap-9 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap09_cpu`

## Official-Style DA3-BASE K35 Streaming

- Lightweight archived reports: `data/official_da3_base_k35_streaming_2026_05_30/reports/`
- Local full run directory with DA3 tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30`
- Local vendored SelaVPR++ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/SelaVPRplusplus`
- Local vendored BoQ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/Bag-of-Queries`
- Local official DA3 streaming reference copy: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming`

Only manifests, summaries, reports, and scripts are committed. Large depth/confidence tensors, descriptor arrays, copied photos, local databases, and vendor checkouts are intentionally excluded.

## SfM Device-Pose Alignment (2026-09-24)

- Lightweight archive: `data/sfm_device_align_2026_09_24/` (patches B/C, header, tools, text run outputs, results, README).
- Excluded, local only, in the VOLATILE session scratch `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/step2/` (lost on reboot):
  - `proto/cap_*/{U0,U1,U2,RR}/**/*.bin`: 45 COLMAP sparse-model files (about 24 MB), ignored by `*.bin`. To regenerate, rerun `proto/run_upstream.sh` on the `inputs/` feeds.
  - `runs/*/` binaries (`*.bin`, `cloud.ply`, `session.db.arkit_pose_v1`, about 233 MB). To regenerate, apply `patch_B_device_align_v1.diff` to Aether3D `7dc00642` + shim `4e22ee7`, then run `tools/build.sh` and `tools/batch_*.sh`.
  - `src/`, `src_orig/`, `base_sfmB/`, `build/`, `c_patch/`, `dart_check/`, `pubspec*.bak`: source copies and build trees that can be rebuilt from the base revisions plus the patches.
