# Official DA3 external-camera branch parity audit

日期：2026-06-05

## 结论

- status: `coreml_pose_path_pre_forward_extrinsics_normalization_likely_embedded_not_root_cause`
- pytorch pose branch parity: `True`
- coreml pre-forward normalization parity: `True`
- official algorithm blame supported: `False`

The current DA3BASE_476x742_N35_pose package was exported through the pose CoreML wrapper, and that wrapper embeds official-style pre-forward extrinsics normalization inside the model. Mac/Swift feeding raw OpenCV w2c is therefore expected for this package. A research-only raw-vs-pre-normalized rerun on window_016 produced only small raw output differences, so pre-forward extrinsics normalization is no longer a root-cause-level suspect for the NPZ downstream thickness.

## 大白话

- 官方 external-camera API 会在 forward 前归一化 extrinsics，这一点仍然成立。
- 但当前 pose CoreML 的导出 wrapper 本身也做了这一步；所以 Mac/Swift 外面喂 raw OpenCV w2c 不是自动错误。
- 我做了 raw 输入 vs 外部预归一化输入的 window_016 对照，raw 模型输出差异很小；这说明它不是厚层主因级别的差异。
- 当前 _pose CoreML 仍不是官方 image-only baseline；它只是 external-camera compatibility path。
- 现在更该押注的复刻缺口是 image-only cam_dec 和官方等比 upper_bound_resize + patch multiple preprocess。

## Checks

| check | status | line | evidence | path |
|---|---:|---:|---|---|
| `official_api_pre_forward_normalizes_external_extrinsics` | `pass` | 204 | 官方 DepthAnything3.inference 在 external-camera mode 下 forward 前归一化 extrinsics。 | `api.py` |
| `official_api_normalization_first_frame_and_median_distance` | `pass` | 338 | 官方 normalize 先归一到首帧，再用 camera center median distance 缩放平移。 | `api.py` |
| `official_api_post_forward_umeyama_depth_scale` | `pass` | 362 | 官方 external-camera postprocess 用 Umeyama scale 反调 depth，并回填输入相机。 | `api.py` |
| `research_pytorch_pose_branch_matches_pre_forward_normalize` | `pass` | 85 | Research PyTorch pose-conditioned 分支有官方 pre-forward extrinsics normalize。 | `official_pytorch_window_export.py` |
| `research_pytorch_pose_branch_matches_post_umeyama` | `pass` | 108 | Research PyTorch pose-conditioned 分支有官方 Umeyama depth scale postprocess。 | `official_pytorch_window_export.py` |
| `coreml_pose_export_wrapper_normalizes_extrinsics_inside_model` | `pass` | 210 | 用于导出 pose CoreML 的 wrapper 会在模型 forward 内部先 normalize extrinsics。 | `export_da3_pose_coreml.py` |
| `coreml_pose_export_wrapper_uses_first_frame_median_distance` | `pass` | 192 | pose CoreML wrapper 的归一化是首帧相对化 + median camera-center distance。 | `export_da3_pose_coreml.py` |
| `base_476x742_n35_pose_export_uses_pose_wrapper` | `pass` | 61 | K35_476x742 是矩形 DA3-BASE CoreML sweep 的当前 baseline；同目录矩形候选均通过 pose CoreML exporter 生成。 | `run_476742_neighborhood_sweep_20260525.sh` |
| `mac_coreml_runtime_feeds_raw_extrinsics_expected_by_export_wrapper` | `pass` | 368 | Mac CoreML runner 喂 raw OpenCV w2c；如果模型是 pose wrapper 导出，这正是 wrapper 的预期输入。 | `da3_mac_window_export.py` |
| `swift_coreml_runtime_feeds_raw_extrinsics_expected_by_export_wrapper` | `pass` | 631 | Swift CoreML runner 喂 Dart 预计算 raw OpenCV w2c；pose wrapper 内部再做官方式归一化。 | `Da3DepthPlugin.swift` |
| `coreml_postprocess_applies_only_post_forward_umeyama` | `pass` | 132 | CoreML official postprocess 已补 forward 后 Umeyama/depth scale。 | `coreml_official_postprocess_export.py` |
| `window016_raw_vs_external_pre_norm_outputs_nearly_equivalent` | `pass` |  | window_016 raw vs external-pre-normalized raw outputs: depth mean_abs=0.001577, confidence mean_abs=0.017626, pred_extrinsics mean_abs=0.000971, pred_intrinsics mean_abs=0.142857. | `da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_2026_06_05` |
