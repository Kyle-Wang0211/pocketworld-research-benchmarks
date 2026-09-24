# Official DA3 image-only CoreML readiness gate

日期：2026-06-04

## 结论

当前不能把 APP 的 DA3 路径称为官方 DA3-Streaming baseline。

官方 baseline 的硬条件是：CoreML 只要求 `image` 输入，不要求 `extrinsics/intrinsics`；ARKit/VIO 只能留作 capture metadata 或后处理产品层信息。

## Gate

- `status`: `fail`
- `official_baseline_ready`: `False`
- `has_image_only_coreml_signature`: `False`
- `current_bundle_is_pose_conditioned_only`: `True`
- `app_contract_ready_for_future_image_only_model`: `True`
- `policy_blocks_current_pose_model_from_official_baseline`: `True`
- `highest_priority_gap`: `missing_image_only_da3_base_coreml_signature`

## CoreML Signatures

- `model_count`: `1`
- `image_only_model_count`: `0`
- `pose_conditioned_model_count`: `1`

| Resource | Required inputs | Outputs | Verdict |
|---|---|---|---|
| DA3BASE_476x742_N35_pose | image, extrinsics, intrinsics | depth, depth_conf, pred_extrinsics, pred_intrinsics | pose_conditioned |

## Policy Evidence

- `path`: `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart`
- `available`: `True`
- `selected_resource_name`: `DA3BASE_476x742_N35_pose`
- `default_da3_input_contract`: `pose_conditioned_coreml_requires_image_extrinsics_intrinsics`
- `default_official_streaming_baseline_false`: `True`
- `blocked_until_image_only_coreml_signature`: `True`
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

### native_adapter

- `path`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift`
- `available`: `True`
- `image_only_resource_allowlist_present`: `True`
- `pose_conditioned_branch_present`: `True`
- `image_only_provider_branch_present`: `True`
- `input_contract_telemetry_present`: `True`

## Next Actions

1. Current APP bundle contains only pose-conditioned DA3 CoreML; treat it as comparison data, not baseline.
2. Export or obtain DA3-BASE K35@476x742 CoreML with required inputs exactly: image.
3. Keep pred_extrinsics/pred_intrinsics outputs from DA3; do not replace them with ARKit/VIO camera inputs.
4. After the image-only package exists, switch selectedDepthModel/resourceName to that package and set officialStreamingBaseline=true.
5. Rerun this readiness gate, then rerun official core-frame npz downstream before judging thickness.

## 大白话

现在手机 APP 的 native adapter 已经准备好未来 image-only 模型：如果模型不是 pose-conditioned，就只会喂 `image`。但 bundle 里还没有这个模型，所以 gate 必须失败。

这正是我们想要的红灯：它防止 `_pose` CoreML + ARKit/VIO 输入继续被误认为官方 DA3-Streaming 默认算法。下一步不是点云清理，而是拿到真正 image-only 的 CoreML 或继续用 PyTorch image-only reference 做对齐。
