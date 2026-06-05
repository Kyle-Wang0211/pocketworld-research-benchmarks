# Official DA3 product runtime alignment audit

日期：2026-06-05

## 结论

- status: `official_image_only_runtime_ready`
- 产品主线: `DA3BASE_280x504_N35_image_only`
- 兼容附录路径: `DA3BASE_476x742_N35_pose`
- 兼容附录角色: `on_disk_research_evidence_not_xcode_packaged_baseline`
- A100/大内存 Mac role: `research_reference_only_not_mobile_viability_gate`

下一步：Run same-capture APP/native image-only overlap regression with DA3BASE_280x504_N35_image_only, then run official core-frame npz downstream.

## 大白话

- 89GiB/178GiB 属于旧研究导出/编译压力路径，不是移动端运行 DA3 的内存需求。
- 产品官方主线现在只能是 DA3BASE_280x504_N35_image_only；DA3BASE_476x742_N35_pose 只是磁盘上的兼容/研究证据。
- Xcode resources 已不再引用旧 pose CoreML，所以 APP 不应再把 AR/VIO pose-conditioned 路径称为官方 baseline。
- Dart DepthStage 现在也只允许 DA3BASE_280x504_N35_image_only 这一条资源名进入 Stage 1。
- Flutter MethodChannel ABI 单测现在确认 native payload 带的是官方 image-only tensor 文件，不是旧 pose/camera 输入。
- APP 资源、ModelLoader、Swift allowlist 和 Dart runner 都不引用 DA3BASE_static_* probe 包；低分辨率 probe 不能被路由成产品 official baseline。
- DA3BASE_280x504_N35_image_only 现在已经导出、通过 image-only 签名 gate，并被 Runner Xcode Resources 引用。
- Swift native 现在在写 confidencePath 前执行官方 DA3-Streaming 的 conf -= 1.0，不再把 raw depth_conf 交给 downstream。
- Research/desktop 的权威 downstream 仍是官方 Python npz_output_process.py；APP Dart PointCloudStage 只是移动端 replay，不替代官方 oracle。
- Swift image-only runtime 现在必须收到模型预测的 pred_extrinsics/pred_intrinsics 输出；缺失时直接失败，不再 fallback 到外部相机。
- Swift native 现在会在加载模型前拒绝非 image-only input contract，防止 MethodChannel payload 绕回 pose-conditioned 输入。
- 下一条产品证据不是点云清理，而是用真正 image-only CoreML artifact 跑 same-capture image-only overlap regression。

## Checks

| check | status | evidence | source |
|---|---:|---|---|
| `pose_compat_coreml_on_disk` | `warning` | Pose-conditioned DA3 CoreML remains on disk as compatibility/research evidence. | `DA3BASE_476x742_N35_pose.mlpackage` |
| `pose_compat_not_referenced_by_xcode_resources` | `pass` | Pose-conditioned DA3 is not referenced by Runner Xcode resources. | `project.pbxproj` |
| `target_image_only_coreml_artifact_present` | `pass` | Official image-only DA3 CoreML artifact is required before APP can claim DA3-Streaming baseline. | `DA3BASE_280x504_N35_image_only.mlmodelc` |
| `target_image_only_referenced_by_xcode_resources` | `pass` | Official image-only DA3 CoreML must be referenced by Runner Xcode resources after the artifact exists. | `project.pbxproj` |
| `pose_coreml_signature_known` | `pass` | Observed CoreML inputs: ['image', 'extrinsics', 'intrinsics']; outputs: ['depth', 'depth_conf', 'pred_extrinsics', 'pred_intrinsics'] | `DA3BASE_476x742_N35_pose.mlpackage` |
| `dart_camera_contract_helper` | `pass` | Pure Dart helper owns ARKit c2w -> OpenCV w2c and scaled intrinsics. | `da3_camera_contract.dart` |
| `dart_manifest_writes_da3_camera_fields` | `pass` | da3_input_manifest.json now stores precomputed DA3 camera tensors per frame. | `photo_bundle_derivation_service.dart` |
| `dart_app_payload_carries_da3_camera_fields` | `pass` | APP Dart payload computes/fills DA3 camera fields before invoking native. | `local_pipeline_runner.dart` |
| `dart_depth_stage_allows_only_target_image_only_resource` | `pass` | Dart DepthStage DA3 resource allowlist contains only the official DA3BASE_280x504_N35_image_only target. | `local_pipeline_runner.dart` |
| `dart_method_channel_payload_carries_image_only_tensor_input` | `pass` | Flutter MethodChannel ABI test now proves native receives the official image-only target, no external camera requirement, and a real float32 CHW tensor file of W*H*3*4 bytes. | `local_pipeline_runner_test.dart` |
| `static_probe_resources_not_packaged_or_routable` | `pass` | APP Xcode resources, model loader, native allowlist, and Dart runner do not reference DA3BASE_static_* probe packages; the resource guard test explicitly rejects static probe names, so Research static probes cannot be routed as product official baseline. | `local_pipeline_runner_test.dart` |
| `swift_confidence_minus_one_before_write` | `pass` | Swift native writes confidencePath after the official DA3-Streaming conf -= 1.0 convention instead of raw depth_conf. | `Da3DepthPlugin.swift` |
| `dart_pointcloud_mobile_replay_npz_executor_smoke` | `pass` | APP PointCloudStage now has a tested Dart mobile replay for the official results_output/frame_*.npz + npz_output_process.py semantics when depth_index payloads are complete; Research/desktop official Python remains the oracle. | `local_pipeline_runner_test.dart` |
| `swift_image_only_requires_predicted_pose_outputs` | `pass` | Swift image-only adapter now requires predicted pred_extrinsics/pred_intrinsics outputs and refuses to synthesize downstream pose files from external camera metadata. | `Da3DepthPlugin.swift` |
| `swift_native_consumes_precomputed_camera` | `pass` | Swift keeps the precomputed camera helper code only for legacy/pose-conditioned compatibility, but the official image-only runtime rejects non-image-only input and requires predicted pose outputs. | `Da3DepthPlugin.swift` |
| `swift_native_rejects_non_image_only_contract` | `pass` | Swift native adapter hard-rejects unsupported DA3 resources and non-image-only input contracts before model loading. | `Da3DepthPlugin.swift` |
| `mac_exporter_consumes_same_camera_contract` | `pass` | Research Mac exporter follows the same Dart manifest camera contract when fields are present. | `da3_mac_window_export.py` |
| `policy_labels_dart_camera_ownership` | `pass` | Capture policy labels DA3 camera tensor convention as Dart-owned. | `photo_bundle_pipeline_policy_service.dart` |
