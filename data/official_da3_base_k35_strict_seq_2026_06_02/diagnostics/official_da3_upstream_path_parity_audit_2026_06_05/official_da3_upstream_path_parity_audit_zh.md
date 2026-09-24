# Official DA3 upstream path parity audit

日期：2026-06-05

## 结论

- status: `product_image_only_coreml_path_ready_for_same_capture_regression`
- official algorithm blame supported: `False`
- current thickness authority: `product_image_only_coreml_ready_but_same_capture_regression_not_rerun`

The APP/Dart path now selects official image-only K35 semantics and feeds native from a pre-normalized image tensor. DA3BASE_280x504_N35_image_only CoreML now exists, so the next authority gap is not model packaging; it is the same-capture product image-only regression output. Old pose-conditioned outputs remain compatibility evidence.

## 大白话

- 官方默认 DA3-Streaming 是 image-only；当前 APP policy/native allowlist 已指向 image-only K35。
- Dart 已把官方 preprocess 终点推进到 normalized float32 CHW tensor，Swift image-only 分支不再 PNG decode fallback。
- DA3BASE_280x504_N35_image_only CoreML artifact/signature 现在已落地。
- 旧 pose-conditioned 输出只能当 compatibility/research 证据，不能当产品 official authority。

## Checks

| check | status | line | evidence | path |
|---|---:|---:|---|---|
| `official_streaming_call_image_only` | `pass` | 273 | 官方 DA3-Streaming 默认调用只传 images/ref_view_strategy，没有传 extrinsics/intrinsics。 | `da3_streaming.py` |
| `official_forward_uses_cam_enc_only_when_external_camera_exists` | `pass` | 126 | 官方模型只有在外部 camera 存在时才创建 cam_enc token；image-only baseline 不走这个条件分支。 | `da3.py` |
| `official_image_only_cam_dec_predicts_camera` | `pass` | 216 | 官方 image-only 路径用 cam_dec 从图像特征预测 pose encoding。 | `da3.py` |
| `official_external_camera_normalize_and_umeyama_path` | `pass` | 204 | 外部 camera 路径还包含首帧归一化、median-distance normalization 和后续 Umeyama 对齐。 | `api.py` |
| `official_default_preprocess_upper_bound_resize` | `pass` | 71 | 官方默认 preprocess 是 upper_bound_resize，再处理为 patch-size divisible。 | `input_processor.py` |
| `product_policy_selects_image_only_model` | `pass` | 69 | 当前 APP/Dart 主线默认选择官方 image-only K35 CoreML 包。 | `photo_bundle_pipeline_policy_service.dart` |
| `current_dart_camera_tensors_are_metadata_only` | `pass` | 840 | Dart manifest 仍保留 camera tensors，但 image-only runner contract 声明它们不是 DA3 输入。 | `photo_bundle_derivation_service.dart` |
| `current_dart_preprocess_is_official_process_res` | `pass` | 939 | Dart 默认 DA3 input 生成走官方 process_res=504 upper_bound_resize + patch-align。 | `photo_bundle_derivation_service.dart` |
| `current_dart_runtime_input_is_normalized_tensor` | `pass` | 722 | Dart 现在把官方预处理终点推进到 normalized float32 CHW tensor。 | `photo_bundle_derivation_service.dart` |
| `app_swift_image_only_refuses_png_decode_fallback` | `pass` | 589 | Swift image-only 分支强制消费 Dart tensor，不再回退 PNG decode。 | `Da3DepthPlugin.swift` |
| `legacy_pose_coreml_package_exists_for_compat_only` | `pass` |  | 旧 pose-conditioned CoreML 包仍存在，但不再是 official mainline。 | `DA3BASE_476x742_N35_pose.mlpackage` |
| `current_image_only_coreml_package_exists` | `pass` |  | 官方 image-only CoreML 包存在才可把 APP/CoreML 输出当成官方 image-only 路径证据。 | `DA3BASE_280x504_N35_image_only.mlpackage` |
