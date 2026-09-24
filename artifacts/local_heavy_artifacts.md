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

## Root-cause fixes 2026-09-24 (`data/rootcause_fixes_2026_09_24/`)

Archived from Claude session `2359d42b` scratchpad (`/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/`). The scratch copies below were deleted after this archive was pushed, except `fixC/src/` and `step2/taskB/`, which stay in that scratchpad. Everything listed here can be rebuilt from the archived patches and scripts plus the pinned revisions.

- `fixA/dart/`, `fixB/dart/`, `step2/dart_check/` (copied Flutter trees incl. `.dart_tool`, `build`): check out pocketworld `1a43510`, apply `fixA_device_pose_trust/patch_A_device_pose_trusted.diff`, then `fixB_device_session/patch_fixB_device_session_onA_v1.diff`, then `flutter pub get`. Test logs are archived.
- `fixA/OfficialAetherARKitPlugin.swift`: an unmodified reference copy (blob `7c118aec` = pocketworld `1a43510:ios/Runner/OfficialAetherARKitPlugin.swift`).
- `fixA/research/`: third-party docs and sample/source code (Apple, ARCore, Huawei AR Engine, OpenXR, WebXR, ORB-SLAM3, OpenVINS, VINS-Mono, NeRFCapture, StrayScanner). Not redistributed; re-fetch using `fixA_device_pose_trust/research/SOURCES_NOT_ARCHIVED.txt`.
- `fixA/offline/build/device_align_offline`, `fixB/build/device_align_offline`: host binaries; rebuild with `fixA_device_pose_trust/offline/build.sh` (or `fixB_device_session/tools/build_offline.sh`) against a core tree = Aether3D `7dc00642` + step2 `patch_B_device_align_v1.diff` (branch `data/sfm-device-align-20260924` @ `7b1f8a0`).
- `fixC/src/` (24 MB, kept in the scratchpad for the bench core build): Aether3D `7dc00642` + step2 patch B + `fixC_core_reg_evidence/patch_C_core_reg_evidence_on_B_v1.diff` (the pocketworld shim copy is `vendor/official_sfm` @ `4e22ee7`).
- `fixC/pw_side/{orig,new}`: `orig` = pocketworld `1a43510:vendor/official_sfm/` (10 files, blob-identical); `new` = `orig` + `patch_C_pocketworld_side_v2_abi.diff`.
- `fixC/runs/*/`: COLMAP models (`*.bin`, `live/**/*.bin`), `cloud.ply`, `session.db.arkit_pose_v1`. Re-run `fixC_core_reg_evidence/tools/batch_*.sh` (drivers `run_arm*.sh`, `run_phone2.sh`, `run_mac.sh`) with the core built by `tools/build.sh`; inputs = archived `inputs/*.jsonl` feeds + the capture JPEG / phone DB from the device backups named in each `run.log`. Text outputs (metrics, per-frame, logs, delivered poses) are archived.
- `fixC/lepton/lep_decode` and any decoded capture photos: rebuild from `lepton/lep_decode.c` against the product's vendored Lepton 0.5.8 staticlib, retagged by `lepton/retag_macho_ios_to_macos.py`. Photos are never archived.
- `fixC/base_sfmB/`: identical to `step2/base_sfmB/` except `inputs/colmap411_*` (archived under `fixC_core_reg_evidence/base_sfmB_inputs/`).
- `fixD/build/`, `fixD/libpwofficial_gpu_extract_19075e9.a`, `fixD/shipped_a/*.o`: rebuild with `fixD_gpu_blur_truncation/tools/build_gpu.sh` / `build_replay.sh`.
- `fixD/gpu568/`, `fixD/gpupatched/`, `fixD/gpufi/`: source copies of Aether3D `568f53d3` `aether_cpp/`; `gpupatched` = + `patch/fixD_gss_2pass_default_568f53d3.diff`; `gpufi` = + `gpufi/fault_injection_vs_568f53d3.diff`. `fixD/src_5f3e/`: source copy at Aether3D `5f3e`. `fixD/patch/{a,b,a568,b568}/`: before/after copies of `sift_pyramid_dawn.cc` (reproduced by the two archived diffs).
- `fixD/ext/**/*.bin`, `fixD/runs/*/*.bin`: keypoint / descriptor dumps and COLMAP models; rerun `tools/run_replays.sh` and the extractors in `tools/`.
- `fixD/caps/cap_1788795741337526/`: copy of that capture's metadata and live DB WAL from the device backup (source of truth stays in the backup).
- `step2/src/`, `step2/src_orig/`: Aether3D `7dc00642` with / without step2 patch B. `step2/proto/**/*.bin`, `step2/base_sfmB/runs/**/*.{bin,ply}`: COLMAP models; rerun `proto/run_upstream.sh` and the base_sfmB tools (archived in `7b1f8a0` / `data/vio-session-archive-20260923`). `step2/c_patch/{a,b}`: `a` = pocketworld `1a43510` files, `b` = `a` + `step2_remainder/c_patch/c_patch_a_to_b.diff`. `step2/taskB/` stays in the scratchpad; its text outputs are already in `7b1f8a0`.
