# VIO session scratch archive, 2026-09-22/23

This directory preserves the self-authored outputs of three Claude Code sessions. Their scratch
directories lived under `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/` and are
deleted on reboot. Nothing here was re-run or edited. Every file is a byte-identical copy (sha256
verified at copy time) of the original.

| Session id (prefix) | Original scratch directory |
|---|---|
| `4437f552` | `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/` |
| `0b67e90b` | `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/` |
| `373814b7` | `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/373814b7-9e8a-4c30-8bed-61f68566515c/scratchpad/` |

Layout: `<topic>/<session-prefix>/<path relative to that scratchpad>`. So the original of
`solver_time_budget/0b67e90b/sb/out/V1_01/branch_prod_r1.tum` is
`<0b67e90b scratchpad>/sb/out/V1_01/branch_prod_r1.tum`.

- **`MANIFEST.tsv`** lists all 1,430 archived files with archived path, absolute original path,
  size and sha256.
- Memory references are file names in
  `~/.claude/projects/-Users-kaidongwang-Documents-progecttwo/memory/`.
- Scripts contain absolute scratch paths. Those paths no longer exist once the scratch is cleared,
  so rewrite the `S=`/`B=` variables before re-running anything.

## What was deliberately NOT archived

- **Legal material.** The user's standing rule is that legal material is never committed to any repository. This excludes `pat/`,
  `legal_tmp/`, `ICE-BA/` and `scale/`, the related search scripts and downloads, and three reports
  withheld under the same rule: `agent3_scale_anchor_report.md`, and `papers_section.md` and
  `risks_sources.md` from the autofocus survey.
- **Third-party content:** papers (PDF and text dumps), vendor and API documentation dumps, saved
  web pages, and third-party source checkouts (`okvis/`, `libcamera/`, COLMAP/PoseLib copies).
- **Large or regenerable data:** EuRoC-format replay datasets, COLMAP `*.bin` models, `*.ply`
  clouds, build trees, compiled binaries, and build logs over 1 MB. Heavy items are listed with
  regeneration commands in `artifacts/local_heavy_artifacts.md` (section
  "VIO session scratch archive 2026-09-22/23").

## Topics

### `solver_time_budget/` (559 files, 58 MB)
Per-frame solver time budget copied from OKVIS (BSD-3) into XRSLAM.
Memory: `project_pocketworld_solver_time_budget_20260923.md`. Branch: xrslam fork `feat/solver-time-budget`@`b0937ef` (based on `04c0e83`).

| Archived | Original | What |
|---|---|---|
| `0b67e90b/sb/{build_both.sh,build_basenr.sh,convert.sh,ident.sh,matrix.sh,run1.sh,analyze.py}` | `<0b67e90b>/sb/` | Build (base vs branch), bit-identity check (`ident.*`), matrix driver, analysis |
| `0b67e90b/sb/cfg/` | `<0b67e90b>/sb/cfg/` | EuRoC and phone SLAM configs per budget level (`b0`, `b0.005`…`b0.035`, `bneg`, upstream) |
| `0b67e90b/sb/out/{V1_01,V1_02,V1_03,6e2d4b99}/` | `<0b67e90b>/sb/out/` | Run-1 trajectories (`*.tum`), per-frame solver CSVs and logs |
| `0b67e90b/sb/{results.json,matrix.log,ident.log,build-*.log}` | `<0b67e90b>/sb/` | Run-1 results table and build/configure logs |
| `0b67e90b/sb/data/r*_K.csv, r*.convert.log` | `<0b67e90b>/sb/data/` | Per-frame K CSVs from `pwvi_to_euroc.py` (the EuRoC dirs themselves were not in scratch) |
| `0b67e90b/sb/build-*.ocv_shim/` | same | OpenCV-5 `calib3d_c.h` shim header |
| `373814b7/sb2/` | `<373814b7>/sb2/` | Matrix run 2 (3 repeats × prod budgets + upstream), `analyze2.py`, `analyze2.out`, `results2.json` |
| `373814b7/full/` | `<373814b7>/full/` | `wiring_full.patch` plus the patched `solver.{h,cpp}` and `sliding_window_tracker.cpp` |

### `sfm_host_replay_xrslam_vs_arkit/` (322 files, 9.4 MB)
Host replay of the shipping official SfM route, feeding XRSLAM poses instead of ARKit poses.
Memory: `project_pocketworld_sfm_finalize_scale_not_inherited_20260923.md`, which cites the original
`sfmB/` path.

| Archived | Original | What |
|---|---|---|
| `0b67e90b/sfmB/tools/` | `<0b67e90b>/sfmB/tools/` | `build.sh`, `prep_inputs.py`, feed generators (`make_*_feed.py`), `run_arm*.sh`, `batch_takeover*.sh`, analysis and render scripts |
| `0b67e90b/sfmB/driver/pwofficial_pose_ab_driver.cc` | same | A/B driver |
| `0b67e90b/sfmB/src/aether_cpp/{include,official_pipeline,src}` and `third_party/glomap_vendor/{CMakeLists.txt,bench,stubs}` | same | Snapshot of the Aether3D official-route sources that were compiled (COLMAP/PoseLib copies excluded as third-party) |
| `0b67e90b/sfmB/src/pw_vendor_4e22ee7/` | same | pocketworld vendor sources @`4e22ee7` |
| `0b67e90b/sfmB/runs/` | same | Per-arm run logs, `per_frame.jsonl`, `sfm_match_fail.jsonl`, `delivered_poses.txt`, `official_finalize_segments.json`, `session.db.arkit_pose_v1`, `ab_*.json`, `takeover_*.json`, render PNGs. COLMAP `*.bin` and `cloud.ply` excluded |
| `0b67e90b/sfmB/logs/` | same | Build, run and takeover logs, env-key lists, `frame58.png`/`frame698.png` |

### `tracking_loss_recovery/` (145 files, 8.8 MB)
Induced visual gaps (black or blur) and the reset-on-loss replica.
Memory: `project_pocketworld_xrslam_never_resets_on_loss_20260923.md`. Branch: xrslam fork `feat/tracking-loss-recovery`@`d5d072a`.

| Archived | Original | What |
|---|---|---|
| `0b67e90b/tr/{make_gap.py,gapeval.py,evalall.sh,run1.sh}` | `<0b67e90b>/tr/` | Gap generator, gap-aware ATE evaluator, drivers |
| `0b67e90b/tr/wip_tracking_recovery{,_v2,_v3}.patch` | same | Successive WIP patches |
| `0b67e90b/tr/cfg/`, `tr/stubs/` | same | Replay configs (`slam_bench_rec*`), CMake stubs |
| `0b67e90b/tr/out/` | same | Trajectories and logs for base/off/on/mid/onreset arms, `eval_*.txt`, `final/` |
| `0b67e90b/tr/data/conv_*.log` | same | Conversion logs. The gap datasets are excluded and regenerable |
| `0b67e90b/tr/{cmds.txt,build.*.log}` | same | Compile commands and build logs |

### `per_frame_intrinsics/` (109 files, 4.1 MB)
Per-frame camera intrinsics fed into XRSLAM.
Memory: `project_pocketworld_per_frame_intrinsics_landed_20260923.md`. Branch: xrslam fork `feat/per-frame-intrinsics`@`04c0e83`.

| Archived | Original | What |
|---|---|---|
| `4437f552/{run_ac.sh,run_arm.sh,mkdev.py,base_build.out,new_build.out,conv_6e2d4b99.out}` | `<4437f552>/` | Host A/B driver (A_base vs A_new vs C_new), device YAML maker, build/convert outputs |
| `4437f552/{cfg,runs}/` | same | Device YAMLs, `slam.yaml`, `k_6e2d4b99.csv` |
| `4437f552/euroc/*_K.csv, *.convert.log` | same | Per-frame K and conversion logs for 6e2d/5966/4ad6. The converted EuRoC image dirs were not kept in scratch |
| `4437f552/out/*.tum` | same | A_base / A_mod / C trajectories for the three recordings plus smoke640 |
| `4437f552/stubs/` | same | argparse/liteviz CMake stubs for the xrslam-pc build |
| `0b67e90b/pfk/` | `<0b67e90b>/pfk/` | Fork and transport build checks: code snapshots (`fork04/`, `old/`), ABI mirror test source, NDK/JNI smoke source, fixtures (`fixture*.csv`, `fx*/converter_intrinsics.csv`), disassembly `*.s`, `prev_agent_*.diff`, `msg*.txt`, `LastTest.log`. Binaries, build trees, Apple doc JSONs and the 4.6–5.1 MB xcodebuild logs are excluded |
| `0b67e90b/review_pfk/` | `<0b67e90b>/review_pfk/` | Independent review: base/head/fork source snapshots, `all_rows.csv`, Dart VIO logs, probe sources. Binaries and `build_head/` are excluded |

### `okvis2_trial/` (153 files, 53 MB)
OKVIS2 monocular replay against RD-VIO/XRSLAM.
Memory: `project_pocketworld_okvis2_mono_trial_20260922.md`. Report: `agent_reports/4437f552/agent2_okvis2_report.md`, which also records how the `ds*` datasets were assembled.

| Archived | Original | What |
|---|---|---|
| `4437f552/pw640_*.yaml`, `euroc_mono.yaml` | `<4437f552>/` | OKVIS2 configs (phone 640 and EuRoC) |
| `4437f552/okvis_csv_to_tum.py` | same | OKVIS2 CSV to TUM (body and camera) converter |
| `4437f552/run_*.log` | same | Replay logs (arms B/C/D, slam/vio, EuRoC mono/stereo) |
| `4437f552/*.tum` (A*, AS*, BV*, CS*, CV*, DV*, B*_cam, slam*/vio*, euroc_*_body) | same | Converted trajectories |
| `4437f552/{ds*,euroc_mono,euroc_stereo}/okvis2-*_trajectory.csv` | same | Raw OKVIS2 trajectory outputs. The dataset parts of those dirs are excluded |
| `4437f552/{okvis_*,ocv_*}.log` | same | OKVIS2 and OpenCV configure/build/install logs |

### `agent_reports/` (10 files)
Sub-agent reports from 2026-09-22. `agent3_scale_anchor_report.md` is withheld under the legal-material rule.

| File | Memory / branch |
|---|---|
| `agent1_tolerance_report.md` | `reference_scale_tolerance_menu_published_20260922.md` |
| `agent2_okvis2_report.md` | `project_pocketworld_okvis2_mono_trial_20260922.md` |
| `agent4_engine_pedigree_report.md` | `project_pocketworld_gpufe_engine_pedigree_reproducible_20260922.md` |
| `agentA_consumption_report.md` | `project_pocketworld_vio_consumption_flag_wired_20260922.md` (`feat/vio-consumption-flag`@`5f3a223`) |
| `agentB_android_feed_report.md` | `project_pocketworld_android_vio_feed_chain_20260922.md` (`feat/android-vio-feed`@`001087c`) |
| `agentC_scale_accept_report.md` | `project_pocketworld_scale_accept_5pct_and_rescale_20260922.md` |
| `agentD_depth_ruler_report.md` | `project_pocketworld_lidar_depth_ruler_bench_20260922.md` (research repo `76b8d47`) |
| `agentE_engine_switch_report.md` | `project_pocketworld_engine_arm_switch_20260922.md` (`feat/engine-arm-switch`) |
| `agentP_photo_capture_report.md` | `project_pocketworld_ios_native_photo_capture_20260922.md` (`feat/ios-native-photo-capture`@`405eca6`) |
| `agentZ_zero_arkit_report.md` | `project_pocketworld_zero_arkit_capture_path_20260922.md` (`feat/ios-zero-arkit-capture`@`7206969`) |

### `zero_arkit_capture/` (43 files, 9.2 MB)
Builds, Flutter test runs and patches for the zero-ARKit arms on 2026-09-22.
Memory: `index_archive_2026_09_22.md` entries for research-bundle build (`feat/research-bundle-build`@`3e50521`), runtime fixes (`feat/zero-arkit-runtime-intrinsics-wait`@`78bdc7c`) and photo promotion (`feat/zero-arkit-photo-promotion`@`7c01bea`), plus agents A, P, Z and E above.

| Archived | What |
|---|---|
| `before.json`, `after.json`, `after2.json`, `baseline_full_test.json`, `final_full_test.json`, `zeroarkit_full_test.{json,err}`, `flutter_test_full.log`, `baseline_failures.txt` | Flutter machine-readable test runs before and after each agent change, with the known baseline failures |
| `full_test*.log`, `path_test*.log`, `other_tests.log` | runtime-intrinsics-wait worktree test logs |
| `build.log`, `step1_asis.log`, `build_step2*.log`, `install*.log`, `install_1.json`, `apps.json`, `info.plist`, `ent.plist` | Research bundle `com.kyle.PocketWorld.zeroarkit` build and install evidence |
| `build_debug*.log`, `build_release.log`, `build_ios*.{sh,log}`, `ios_build.log`, `bench_build.log`, `pbx_final.txt`, `ffi_syms.json` | iOS builds and export-symbol whitelist evidence |
| `photo_append.swift`, `slot_stub.swift`, `stub_live.swift`, `patch_slot.py`, `commit_msg.txt` | Patches and commit message for photo capture and promotion |

### `autofocus/` (25 files)
Memory: `reference_autofocus_algorithm_survey_20260922.md`, `project_pocketworld_pw_af_cdaf_ported_20260923.md`, `project_pocketworld_production_autofocus_already_solved_20260923.md`.

| Archived | What |
|---|---|
| `verdict_section.md`, `platforms_section.md`, `published_section.md`, `repos_section.md`, `agentout/` | Survey report sections. `papers_section.md` and `risks_sources.md` are withheld under the legal-material rule |
| `arxiv2.log`, `dl2.log`, `strip.py` | Survey helpers |
| `p1.py`…`p8.py` | Edit scripts for the `prod-af-20260923` worktree (`PwFocusArms.swift`, `pw_focus_ffi.dart`, probe page) |
| `prodbuild*.log`, `benchbuild*.log`, `podinstall.log`, `fulltest.log` | Focus-arms prod/bench builds and the full Flutter test on 2026-09-23 |

### `vio_replays/` (21 files)
Device recording pull, EuRoC conversion and replay pipeline, morning of 2026-09-22.
Memory: `project_pocketworld_paper_conditions_replay_20260922.md`, `project_pocketworld_exposure_midpoint_timestamp_landed_20260922.md` (pocketworld `f0b3a40`), `project_pocketworld_td_exposure_midpoint_20260922.md`.
Files: `runB_pipeline.sh` and `runB_stage2.sh` with their logs, `paper_cmp.{sh,log}`, `edit_{timebase,recorder,native_arm}.py`, device console and syslog captures, `device_files.txt`, `preflight_pull/preflight.json`, `runA_*.log`, `*.path`, `runs_after.txt`, `conv640.log`.

### `xrslam_lib_repro_build/` (18 files, 1.2 MB)
Reproducible rebuild of the shipped `libxrslam` (gpufenothread) and symbol comparisons.
Memory: `project_pocketworld_gpufe_engine_pedigree_reproducible_20260922.md`.
Files: `build_run1..4.log`, `cmake_cfg.log`, `normalize_ar.py`, `generic_*.txt`, `run1_*.txt`, `shipped_*.txt`, `transport_syms*.txt`, `dart_syms.txt`, `flutter_smoke.log`, `run4/*.receipt.json`, `run4/*.syms.txt`. The 3.2 MB `.a` is excluded.

### `scale_anchor_depth_ruler/` (9 files)
Memory: `project_pocketworld_scale_accept_5pct_and_rescale_20260922.md`, `project_pocketworld_lidar_depth_ruler_bench_20260922.md`, `reference_scale_anchor_survey_and_arbiter_tool_20260922.md`.
Files: `board.png`, `lever/` (board poses, camera TUM, scale report), `scale_accept.json`, `synth_depth.log`, `artifacts/synth_depth_ruler_report.json`, `artifacts/synth_depth.log`, `appledoc.py`. The signed `VIOReplacementBench-depth.app` is excluded.

### `bench_app_backups/` (7 files)
`~/Developer/arloopbench` is not a git repository. These backups are the only record of its files before the 2026-09-23 bench-replay edits.
Memory: `feedback_one_bench_app_merge_features_into_arloopbench.md` (`feat/bench-replay`).

| Archived | Backup of |
|---|---|
| `373814b7/arloopbench_Podfile.before` | `arloopbench/ios/Podfile` |
| `373814b7/arloopbench_Runner-Bridging-Header.h.before` | `arloopbench/ios/Runner/Runner-Bridging-Header.h` |
| `373814b7/arloopbench_main.dart.before` | `arloopbench/lib/main.dart` |
| `373814b7/arloopbench_project.pbxproj.before` | `arloopbench/ios/Runner.xcodeproj/project.pbxproj` |
| `373814b7/arloopbench_sync_from_integration.sh.before` | `arloopbench/.sync_from_integration.sh` (production-to-bench mirror sync) |
| `4437f552/Podfile.ORIGINAL.bak` | `arloopbench/ios/Podfile` as of 2026-09-20 (byte-identical to `arloopbench_Podfile.before`) |
| `4437f552/bench_pbxproj.bak` | `arloopbench/ios/Runner.xcodeproj/project.pbxproj` (bundle `com.kyle.arloopbench`) before the 2026-09-23 01:15 edit |

### `bench_replay/` (8 files)
`373814b7/c1.txt`…`c5.txt` hold the drafted commit messages for the bench recording-replay feature (`feat/bench-replay`). `373814b7/cmtest/` is a CoreMotion stub module compile test.

### `regen_tools/`
`pwvi_to_euroc.py` is a snapshot of `~/Developer/arloopbench/tools/pwvi_to_euroc.py` (sha256 `3c96ab11…3938`, mtime 2026-09-22 23:40). That is the version that produced `euroc_6e2d4b99`. It is kept because arloopbench is not under version control, and the regeneration commands in `artifacts/local_heavy_artifacts.md` depend on it.
