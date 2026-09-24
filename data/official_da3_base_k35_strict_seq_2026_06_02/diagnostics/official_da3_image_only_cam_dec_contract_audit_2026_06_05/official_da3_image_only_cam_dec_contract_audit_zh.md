# Official DA3 image-only cam_dec contract audit

日期：2026-06-05

## 结论

- status: `official_image_only_contract_and_product_coreml_ready`
- official image-only contract: `True`
- selected image-only policy: `True`
- current pose CoreML requires external camera: `True`
- target image-only CoreML missing: `False`
- official algorithm blame supported: `False`

Official DA3-Streaming is image-only at the public API level: it passes images only, leaves extrinsics/intrinsics as None, and relies on cam_dec to predict camera extrinsics/intrinsics from image features. The product policy and Swift allowlist now select DA3BASE_280x504_N35_image_only; the CoreML artifact/signature is present and image-only; old pose-conditioned outputs remain compatibility/research evidence, not official APP authority.

## 大白话

- 官方 DA3-Streaming 没有借助 AR/VIO 相机输入；它把图片交给模型，模型自己用 cam_dec 估相机。
- 当前 APP policy/native allowlist 已改成官方 image-only K35 目标，不再把 476x742 pose 当 official mainline。
- Swift image-only 分支现在强制吃 Dart 写出的 normalized float32 CHW tensor，不走 PNG decode fallback。
- DA3BASE_280x504_N35_image_only CoreML artifact/signature 现在已存在并通过 image-only 检查。
- 旧 pose-conditioned 输出都必须继续标成 compatibility/research path。

## CoreML Signatures

- pose inputs: `['image', 'extrinsics', 'intrinsics']`
- pose outputs: `['depth', 'depth_conf', 'pred_extrinsics', 'pred_intrinsics']`
- image-only exists: `True`
- image-only inputs: `['image']`

## Checks

| check | status | line | evidence | path |
|---|---:|---:|---|---|
| `official_streaming_calls_inference_without_external_camera` | `pass` | 273 | 官方 DA3-Streaming 默认只传 images/ref_view_strategy，不传 extrinsics/intrinsics。 | `da3_streaming.py` |
| `official_api_external_camera_is_optional` | `pass` | 204 | 官方 API 的 extrinsics 是 optional；没有外部相机时 ex_t_norm 仍为 None。 | `api.py` |
| `official_forward_uses_cam_enc_only_when_external_extrinsics_exist` | `pass` | 126 | 官方网络只有在 extrinsics 存在时才用 cam_enc 生成 camera token。 | `da3.py` |
| `official_forward_image_only_has_no_camera_token` | `pass` | 130 | 没有外部相机时 backbone 的 camera token 是 None，即 image-only 分支。 | `da3.py` |
| `official_cam_dec_predicts_pose_encoding` | `pass` | 216 | 官方 cam_dec 从图像特征预测 pose encoding。 | `da3.py` |
| `official_cam_dec_outputs_extrinsics_intrinsics` | `pass` | 224 | 官方 cam_dec 输出会被转换成 extrinsics/intrinsics。 | `da3.py` |
| `current_pose_coreml_requires_external_camera_inputs` | `pass` |  | 当前 APP bundle 里的 pose CoreML signature 需要 image/extrinsics/intrinsics。 | `DA3BASE_476x742_N35_pose.mlpackage` |
| `target_image_only_coreml_image_only_signature_ready` | `pass` |  | 目标 DA3BASE_280x504_N35_image_only CoreML 必须具备只要求 image 输入的 signature。 | `DA3BASE_280x504_N35_image_only.mlpackage` |
| `app_swift_keeps_pose_conditioned_compat_branch_guarded` | `pass` | 221 | Swift 只在 pose-conditioned compat 分支才消费 external camera tensor。 | `Da3DepthPlugin.swift` |
| `dart_policy_selects_image_only_resource` | `pass` | 69 | Dart policy 默认选择官方 image-only K35 resource。 | `photo_bundle_pipeline_policy_service.dart` |
| `swift_image_only_requires_pre_normalized_tensor` | `pass` | 589 | Swift image-only 分支现在强制消费 Dart 官方预处理 tensor，不再回退 PNG decode。 | `Da3DepthPlugin.swift` |
| `dart_policy_marks_image_only_signature_ready` | `pass` | 83 | Dart policy 已把官方 image-only APP 路径标成 image-only CoreML signature ready。 | `photo_bundle_pipeline_policy_service.dart` |
