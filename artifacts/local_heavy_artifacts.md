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

## VIO session scratch archive 2026-09-22/23

These are the heavy or regenerable parts of three Claude session scratch directories whose lightweight outputs are archived in `data/vio_session_archive_2026_09_22_23/` (see its `README.md` and `MANIFEST.tsv`). Scratch roots:
`A = /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad`,
`B = /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad`.
`/private/tmp` is cleared on reboot. Each entry below says how to rebuild it.

The EuRoC converter is `~/Developer/arloopbench/tools/pwvi_to_euroc.py` (sha256 `3c96ab11cee1401f9fd9ab2159f2c97ca0959d6533243176402ae10f10643938`). `~/Developer/arloopbench` is not a git repository, so a byte-identical snapshot is committed at `data/vio_session_archive_2026_09_22_23/regen_tools/pwvi_to_euroc.py`.

- `A/euroc_6e2d4b99/` (2.5 GB; 1,702 PNG 1920×1440 luma + `cam0/data.csv` + `imu0/data.csv`): the EuRoC conversion of recording `~/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18` (4.4 GB, persistent). It was converted **without** `--exposure-half`; `cam0` timestamps equal `camera_index.csv`. Regenerate with:
  `/usr/bin/python3 ~/Developer/arloopbench/tools/pwvi_to_euroc.py ~/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18 <out>/euroc_6e2d4b99 --intrinsics-csv <out>/k_6e2d4b99.csv`
  The original output log is `per_frame_intrinsics/4437f552/conv_6e2d4b99.out`, and the original K CSV is `per_frame_intrinsics/4437f552/runs/k_6e2d4b99.csv`. A 5-frame spot check (`--limit 5`) on 2026-09-24 reproduced the PNGs, `imu0/data.csv`, the `cam0/data.csv` prefix and the K CSV prefix byte for byte.
- `A/ds640_*`, `A/dsB_*`, `A/dsC_*`, `A/dsD_*` (24 OKVIS2 replay dirs, 8.6 MB of dataset parts). Each has `cam0/data` as a symlink to `~/Developer/viobench-recordings/_euroc_6e2d4b99_640/cam0/data`, plus byte-identical copies of that directory's `cam0/data.csv` and `imu0/data.csv`. The steps are in `agent_reports/4437f552/agent2_okvis2_report.md` lines 244–247 (`mkdir -p $d/cam0 $d/imu0; ln -sfn …/_euroc_6e2d4b99_640/cam0/data $d/cam0/data; cp …/cam0/data.csv $d/cam0/; cp …/imu0/data.csv $d/imu0/`). The OKVIS2 trajectory CSVs from these dirs are archived under `okvis2_trial/`.
- `A/euroc_mono/`, `A/euroc_stereo/` (8.2 MB of dataset parts): `cam0/data` and `cam1/data` are symlinks into `~/Developer/euroc/V1_01_easy/mav0/`, and the `data.csv` files are byte-identical copies of that dataset's. Trajectory CSVs are archived.
- `A/euroc_v101_gt.tum` (2.4 MB): TUM form of EuRoC V1_01 ground truth. Regenerated byte-identically on 2026-09-24 with:
  `awk -F, '!/^#/ && NF>7 {printf "%.9f %s %s %s %s %s %s %s\n", $1*1e-9, $2, $3, $4, $6, $7, $8, $5}' ~/Developer/euroc/V1_01_easy/mav0/state_groundtruth_estimate0/data.csv`
- `B/tr/data/gap_6e2d_{black_0.5s,black_1s,black_3s,black_6s,blur_1s}/` (2.3 MB plus 8,455 symlinks): induced-gap copies of `_euroc_6e2d4b99_640`, all starting 17 s after the first frame. Regenerate with:
  `/usr/bin/python3 tracking_loss_recovery/0b67e90b/tr/make_gap.py ~/Developer/viobench-recordings/_euroc_6e2d4b99_640 <out>/gap_6e2d_<mode>_<dur>s 17 <dur> <black|blur>`
  A spot check on 2026-09-24 (`black 0.5`, `blur 1`) matched `cam0/data.csv` and every frame, including symlink targets and blurred PNG hashes.
- `B/sfmB/runs/**/*.bin` and `**/cloud.ply` (256 MB): COLMAP binary models (`cameras/frames/images/rigs.bin`, including `live/live_end/`) and point clouds from the host SfM replay arms. To regenerate, rebuild with `sfm_host_replay_xrslam_vs_arkit/0b67e90b/sfmB/tools/build.sh` and re-run `run_arm.sh`/`run_arm_diag.sh` with the feeds below.
- `B/sfmB/inputs/` (8.0 MB): per-arm feed lists `feed_S_*.jsonl`, produced by `prep_inputs.py` and `make_*_feed.py`, plus `colmap411_sparse_all_points_xyz.txt`, an awk dump of `~/Developer/colmap-6e2d4b99/sparse_all/points3D.txt` (X Y Z err 2*track_len; see `analyze_takeover.py:25`).
- `B/sfmB/build/` (20 MB): official-route objects, `libcolmap_reuse_sep9host.a` (sha256 in `build/reuse_source.sha256`, `5d8c5030…6ff6`) and the `pwofficial_pose_ab_driver` executable. Rebuild with `tools/build.sh`, which reuses COLMAP/PoseLib/VLFeat objects from the prebuilt Sep-9 arm64 host `libpwofficial_core.a` (`build-host-fullbench`, see the `build.sh` header).
- `B/sfmB/src/aether_cpp/third_party/glomap_vendor/{colmap-src,poselib-src}` (21 MB): a third-party COLMAP/PoseLib source copy taken from `~/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/`.
- `B/pfk/` build products (23 MB: `tbuild/`, `jni/smoke.jar`, `.o`/`.dylib`, test binaries, and `build_pfk.log`/`xcodebuild_pfk*.log` at 4.6–5.1 MB each) and `B/review_pfk/build_head/` plus binaries (1.7 MB): build outputs from the per-frame-intrinsics fork build. They can be rebuilt from the pocketworld per-frame-K worktree (`per-frame-k-host-20260923`, since removed) together with xrslam fork `feat/per-frame-intrinsics`@`04c0e83`. The compile inputs are recorded in the archived `LastTest.log` and code snapshots.
- `A/artifacts/VIOReplacementBench-depth.app` (10 MB, signed app bundle) and `A/run4/libxrslam_gpufenothread.a` (3.1 MB): build products. Their receipts and symbol lists are archived.
