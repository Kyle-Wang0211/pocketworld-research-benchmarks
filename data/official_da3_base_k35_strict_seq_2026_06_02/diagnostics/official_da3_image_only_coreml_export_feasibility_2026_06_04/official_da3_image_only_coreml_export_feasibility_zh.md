# Official DA3 image-only CoreML export feasibility

日期：2026-06-04

## 结论

image-only CoreML 的语义已经明确，但当前仓库没有官方提供的 CoreML export 脚本，也还没有真正执行 full K35 CoreML conversion。

要贴官方 DA3-Streaming，CoreML wrapper 必须只暴露 `image` 输入；`extrinsics/intrinsics` 不能作为输入，也不能用 identity camera 替代。DA3 会通过模型内部 `cam_dec` 从多视图图像特征预测 `pred_extrinsics/pred_intrinsics`。

## Decision

- `status`: `ready_to_attempt_export`
- `image_only_wrapper_contract_known`: `True`
- `current_coreml_is_pose_conditioned`: `True`
- `official_repo_contains_coreml_export_script`: `False`
- `local_coremltools_available`: `True`
- `torch_coremltools_version_mismatch_warning`: `True`
- `full_k35_coreml_conversion_attempted`: `False`
- `highest_priority_action`: `write_or_recover_the_original_coreml_export_wrapper_for_image_only_da3`
- `why_not_identity_camera`: `Identity extrinsics would still create a camera-conditioned token path; official streaming default requires extrinsics=None so the backbone uses learned camera tokens and cam_dec predicts poses from image features.`

## Required Wrapper

- `coreml_inputs`: `[{'name': 'image', 'shape': [1, 35, 3, 476, 742], 'dtype': 'float32', 'preprocess': 'already ImageNet-normalized RGB CHW tensor'}]`
- `forbidden_coreml_inputs`: `['extrinsics', 'intrinsics']`
- `torch_call`: `da3_model(image, extrinsics=None, intrinsics=None, export_feat_layers=[], infer_gs=False, use_ray_pose=False, ref_view_strategy='saddle_balanced')`
- `must_not_do`: `['do not feed identity extrinsics', 'do not feed ARKit/VIO extrinsics', 'do not feed ARKit intrinsics']`
- `coreml_outputs`: `[{'name': 'depth', 'shape': [1, 35, 476, 742]}, {'name': 'depth_conf', 'shape': [1, 35, 476, 742]}, {'name': 'pred_extrinsics', 'shape': [1, 35, 3, 4]}, {'name': 'pred_intrinsics', 'shape': [1, 35, 3, 3]}]`

## Model Config Evidence

- `model_name`: `da3-base`
- `has_cam_enc`: `True`
- `has_cam_dec`: `True`
- `backbone_name`: `vitb`
- `alt_start`: `4`
- `out_layers`: `[5, 7, 9, 11]`

## Current CoreML Signature

- `model_path`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage`
- `available`: `True`
- `input_names`: `['image', 'extrinsics', 'intrinsics']`
- `output_names`: `['depth', 'depth_conf', 'pred_extrinsics', 'pred_intrinsics']`
- `required_inputs`: `['image', 'extrinsics', 'intrinsics']`
- `is_pose_conditioned_coreml_signature`: `True`
- `is_image_only_signature`: `False`

## Environment

- `python`: `3.11.15`
- `torch_available`: `True`
- `torch_version`: `2.12.0`
- `coremltools_available`: `True`
- `coremltools_version`: `9.0`
- `torch_coremltools_warning`: `True`

## Official Source Evidence

### api_inference_flow

- `path`: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py`
- `195-210 preprocess -> prepare -> normalize optional extrinsics -> _run_model_forward`
- `341-365 align only when input extrinsics are present`

### da3_forward_contract

- `path`: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/da3.py`
- `100-109 forward(x, extrinsics=None, intrinsics=None, ...)`
- `126-130 if extrinsics is None, cam_token=None`
- `211-226 cam_dec predicts pose encoding, then outputs extrinsics/intrinsics`
- `336-365 DepthAnything3Metric forwards optional cameras through anyview branch`

### reference_view_selection

- `path`: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/vision_transformer.py`
- `314-330 image-only path selects reference view and uses learned camera tokens`
- `323-326 pose-conditioned path uses user-provided camera condition tokens`

### streaming_entry

- `path`: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py`
- `253-274 DA3-Streaming calls model.inference(images, ref_view_strategy=...)`
- `880-915 CLI accepts image_dir/config/output_dir, not camera files`

## Official Export Scripts Found

- none

## Next Commands

```bash
# implement export wrapper, then convert to CoreML
```
```bash
# expected output: /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_image_only.mlpackage
```
```bash
python3.11 tools/python/da3_image_only_coreml_readiness_gate.py --app-repo /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter --capture-services-dir /Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_04 --date 2026-06-04
```
```bash
python3.11 tools/python/da3_mac_window_export.py --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_probe --model /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_image_only.mlpackage --compute-unit cpu --max-windows 1
```

## 大白话

DA3 不靠 AR 也能有位姿，是因为它把位姿估计做进神经网络了：image-only 分支先从图像抽多视图特征，再由 camera decoder 回归位姿和内参。

所以 image-only CoreML 不是少输出 pose，而是少输入 pose。输出里的 `pred_extrinsics/pred_intrinsics` 仍然必须保留。
