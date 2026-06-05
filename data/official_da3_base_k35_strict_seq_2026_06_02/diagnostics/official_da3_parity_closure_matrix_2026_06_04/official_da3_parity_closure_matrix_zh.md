# Official DA3 parity closure matrix

日期：2026-06-05

## 结论

- status: `not_closed_thickness_persists_after_dart_camera_contract`
- goal complete: `False`
- target missing: `True`
- overlap gate blocked: `False`
- local target export preflight failed: `True`

不要把大内存 image-only 导出作为产品主线；当前可运行 pose CoreML + Dart camera contract 已经复现 window_016 单窗厚层。下一步查 DA3 上游 pose/depth/scale consistency，优先看 slot 10/cap-1396 的 pose span 跳变和 slot 24/cap-1514 之后的 depth/confidence 风险。

## 大白话

- 官方 image-only 语义和 downstream 行为已经足够清楚：不是 AR 输入，也没有隐藏的单 window 去厚融合。
- 89GiB/178GiB 属于研究导出/编译硬 parity 的中间 buffer，不是手机/平板/笔记本运行 DA3 的产品门槛。
- 当前产品主线继续用已经能跑的 DA3BASE_476x742_N35_pose CoreML，不再等待大内存 image-only 导出。
- 最新代码把 OpenCV w2c 和 3x3 intrinsics 前移到 Dart manifest/payload；Swift/CoreML 只消费 tensor。
- 同一 strict capture/window_016 已经用 Dart camera contract + 当前 pose CoreML + 官方 postprocess 重跑；厚层仍存在。
- late-slot 审计显示最大 pose step 是 slot 10/cap-1396，低置信/深度尾部风险集中在 slot 24/cap-1514 之后。
- 下一步应查 DA3 上游几何一致性：同一 K35 window 后段 slot 的 pose/depth/scale 是否互相打架。

## Matrix

| check | status | evidence | source |
|---|---:|---|---|
| `commercial_model_policy` | `pass` | DA3-BASE license evidence exists; LARGE/GIANT/NESTED remain non-commercial or unresolved for product path. | `official_da3_algorithm_replication_audit.json` |
| `official_streaming_image_only_semantics` | `pass` | Official call is model.inference(images, ref_view_strategy=...), and cam_dec predicts camera. | `official_da3_algorithm_replication_audit.json` |
| `official_downstream_no_hidden_in_window_dedup` | `pass` | Single-window thickness must be judged through upstream geometry unless a later official path adds fusion. | `official_da3_algorithm_replication_audit.json` |
| `fixed_preprocess_contract_labeled` | `pass` | K35@476x742 is patch-aligned; current photos_depth is direct_stretch same-input parity, not dynamic upper_bound_resize. | `official_da3_preprocess_parity_audit.json` |
| `coordinate_convention_risk_labeled` | `pass` | Research pose path converts ARKit cameraTransform to OpenCV w2c; APP _pose raw cameraTransform remains compat-only risk. | `official_da3_coordinate_convention_audit.json` |
| `current_runnable_product_coreml_path` | `pass` | current_runnable_da3_base_k35_476x742_pose_coreml | `official_da3_product_runtime_alignment_audit.json` |
| `dart_owned_da3_camera_contract` | `pass` | Dart manifest/payload now owns cameraExtrinsicOpenCvW2c4x4 and cameraIntrinsic3x3; Swift and Mac exporter prefer those fields. | `official_da3_product_runtime_alignment_audit.json` |
| `same_capture_runnable_pose_window016_regression` | `fail` | Single-window thickness still persists after Dart camera contract, current runnable CoreML rerun, and official postprocess. | `official_da3_dart_camera_window016_regression_audit.json` |
| `late_slot_geometry_consistency_suspect` | `warning` | Largest pose step: slot 10 / cap-1396 (0.410); lowest confidence median: slot 24 / cap-1514 (2.027). | `official_da3_window016_late_slot_geometry_consistency_audit.json` |
| `target_image_only_coreml_artifact` | `warning` | DA3BASE_476x742_N35_image_only.mlpackage_or_mlmodelc_missing | `official_da3_image_only_coreml_target_export_gate.json` |
| `target_coreml_export_resource_gate` | `warning` | Target fp16 attention score floor is 89.01 GiB; local memory is 18.00 GiB. | `official_da3_image_only_coreml_target_export_gate.json` |
| `app_image_only_coreml_readiness` | `warning` | missing_image_only_da3_base_coreml_signature | `official_da3_image_only_coreml_readiness_gate.json` |
| `same_capture_image_only_overlap_regression` | `warning` | Need DA3BASE_476x742_N35 image-only CoreML output for the same capture/window before testing whether overlap thickness is removed. | `official_da3_image_only_overlap_regression_gate.json` |
| `image_only_geometry_path` | `pass` | Official pose source is network_cam_dec_from_images_not_arkit_vio; thickness reduction, if any, must come from upstream depth/pose/scale consistency. | `official_da3_image_only_geometry_path_audit.json` |
| `mobile_product_viability` | `warning` | Research sample can warn/pass research checks, but product pass requires real-device telemetry and explicit thresholds. | `mobile_viability_gate_research_sample_report.json` |
| `external_official_status_refresh` | `pass` | Issue #254 remains open with 0 comments; PR #256 remains open; no official hidden single-window cleanup path found. | `official_da3_external_light_refresh_zh.md` |
| `target_export_runbook_ready` | `pass` | Runbook defines the fixed target export command, readiness gate, Mac export, overlap regression gate, and forbidden fallbacks. | `official_da3_image_only_coreml_target_export_runbook_zh.md` |
