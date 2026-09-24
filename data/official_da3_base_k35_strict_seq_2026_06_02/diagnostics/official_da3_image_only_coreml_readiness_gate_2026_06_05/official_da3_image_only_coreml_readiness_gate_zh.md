# Official DA3 image-only CoreML readiness gate

日期：2026-06-05

## 结论

当前 APP 具备官方 DA3-Streaming image-only baseline 的 CoreML 输入契约。

官方 baseline 的硬条件是：CoreML 只要求 `image` 输入，不要求 `extrinsics/intrinsics`；ARKit/VIO 只能留作 capture metadata 或后处理产品层信息。

## Gate

- `status`: `pass`
- `official_baseline_ready`: `True`
- `has_image_only_coreml_signature`: `True`
- `model_dir_is_pose_conditioned_only`: `False`
- `current_xcode_bundle_has_pose_conditioned_resource`: `False`
- `current_bundle_is_pose_conditioned_only`: `False`
- `app_contract_ready_for_future_image_only_model`: `True`
- `policy_blocks_current_pose_model_from_official_baseline`: `True`
- `highest_priority_gap`: `None`

## CoreML Signatures

- `model_count`: `2`
- `image_only_model_count`: `1`
- `pose_conditioned_model_count`: `1`

| Resource | Required inputs | Outputs | Verdict |
|---|---|---|---|
| DA3BASE_280x504_N35_image_only | image | depth, depth_conf, pred_extrinsics, pred_intrinsics | image_only |
| DA3BASE_476x742_N35_pose | image, extrinsics, intrinsics | depth, depth_conf, pred_extrinsics, pred_intrinsics | pose_conditioned |

## Packaging Evidence

- `models_dir`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML`
- `xcode_project`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner.xcodeproj/project.pbxproj`
- `xcode_project_exists`: `True`
- `target_resource`: `DA3BASE_280x504_N35_image_only`
- `target_mlpackage`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage`
- `target_mlpackage_exists`: `True`
- `target_mlmodelc`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlmodelc`
- `target_mlmodelc_exists`: `False`
- `target_any_coreml_artifact_exists`: `True`
- `target_referenced_by_xcode_resources`: `True`
- `target_xcode_reference_lines`: `4` line(s)
- `target_has_tier_high_odr_tag`: `True`
- `pose_compat_resource`: `DA3BASE_476x742_N35_pose`
- `pose_compat_mlpackage`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage`
- `pose_compat_mlpackage_exists`: `True`
- `pose_compat_mlmodelc`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlmodelc`
- `pose_compat_mlmodelc_exists`: `False`
- `pose_compat_any_coreml_artifact_exists`: `True`
- `pose_compat_referenced_by_xcode_resources`: `False`
- `pose_compat_xcode_reference_lines`: `0` line(s)
- `pose_compat_has_tier_high_odr_tag`: `False`
- `known_asset_tags_include_tier_high`: `True`
- `blocking_packaging_gap`: `None`

## Policy Evidence

- `path`: `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart`
- `available`: `True`
- `selected_resource_name`: `DA3BASE_280x504_N35_image_only`
- `selected_da3_input_contract`: `image_only`
- `selected_official_streaming_baseline`: `True`
- `default_da3_input_contract`: `pose_conditioned_coreml_requires_image_extrinsics_intrinsics`
- `default_official_streaming_baseline_false`: `True`
- `ready_image_only_coreml_signature`: `True`
- `pose_conditioned_compat_tag_present`: `True`
- `camera_fields_marked_compat_only`: `True`
- `official_streaming_default_match_false`: `True`

## APP Evidence

### local_runner

- `path`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart`
- `available`: `True`
- `official_image_only_gate_present`: `True`
- `pose_conditioned_detection_present`: `True`
- `image_only_resource_allowlist_present`: `True`
- `image_only_resource_allowlist_target_only`: `True`

### native_adapter

- `path`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift`
- `available`: `True`
- `image_only_resource_allowlist_present`: `True`
- `image_only_input_contract_hard_reject_present`: `True`
- `pose_conditioned_branch_present`: `True`
- `image_only_provider_branch_present`: `True`
- `input_contract_telemetry_present`: `True`

### model_loader_adapter

- `path`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/ModelLoaderPlugin.swift`
- `available`: `True`
- `image_only_resource_mapping_present`: `True`
- `compiled_mlmodelc_lookup_present`: `True`
- `source_mlpackage_lookup_present`: `True`
- `hardcoded_single_resource_ext_removed`: `True`
- `odr_bundle_miss_mentions_both_extensions`: `True`

## Next Actions

1. Run the APP/native same-capture image-only inference gate with DA3BASE_280x504_N35_image_only.
2. Run official core-frame npz downstream on the new image-only outputs before judging thickness.
3. Keep pose-conditioned DA3 on disk only as compatibility/research evidence; do not add it back to Xcode resources.

## 大白话

现在手机 APP 的 native adapter 和 CoreML bundle 已经具备 image-only baseline：`DA3BASE_280x504_N35_image_only` 存在、被 Xcode Resources 引用、签名只要求 `image`，并输出 `pred_extrinsics/pred_intrinsics`。

旧 `DA3BASE_476x742_N35_pose` 仍可留在磁盘作研究对照，但不能重新进 Xcode Resources、不能作为官方 baseline。下一步是用这个新包跑 same-capture image-only 回归，再看单 window 厚层是否仍存在。
