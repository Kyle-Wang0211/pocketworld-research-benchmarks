# Official DA3 upstream geometry alignment audit

日期：2026-06-04

## 当前结论

可以开始查 DA3 上游几何一致性，而且现在就应该查。

下游 overlap-frame duplicate 不是主因之后，单个 K35 window 内同一表面变厚，当前最像 upstream depth/pose/scale/camera consistency 问题。根据官方 DA3-Streaming 默认入口，最高优先级不是把 ARKit 矩阵转成另一个坐标系，而是先把 DA3 inference 输入契约改回官方 image-only streaming baseline。

官方 DA3 API 支持两种模式：不提供相机时走标准 depth/pose estimation；提供 `extrinsics/intrinsics` 时走 pose-conditioned mode。官方 DA3-Streaming 默认代码调用的是 `model.inference(images, ref_view_strategy=...)`，CLI 也只收 `--image_dir`，没有 AR/VIO/camera 文件输入。

本次 audit 的最强信号：当前 APP/CoreML 不是官方 streaming 默认入口。`DA3BASE_476x742_N35_pose.mlpackage` 的 CoreML signature 必填 `image/extrinsics/intrinsics`，而 APP native 会把 ARKit `cameraTransform` 作为 `extrinsics` 输入。这只能算 pose-conditioned DA3 派生实验，不能继续冒充官方 DA3-Streaming baseline。

## 数字证据

| Check | Result | Interpretation |
|---|---:|---|
| completed rows checked | 414 | 全序列官方 postprocess 样本 |
| pred extrinsics vs converted OpenCV w2c max abs max | 0 | Research official postprocess 等于转换后的相机 |
| pred extrinsics vs raw row-major cameraTransform median max abs | 2.28660929 | raw 矩阵不等于官方相机输入 |
| pred extrinsics vs raw column-major c2w median max abs | 2.9635303 | ARKit c2w 也不能直接当官方 w2c |
| intrinsics Research vs APP formula max abs max | 0 | 当前 direct_stretch 样本 intrinsics 对齐 |
| current CoreML required inputs | image, extrinsics, intrinsics | 当前模型是 pose-conditioned signature |

camera conversion 证据仍然有用，但它的适用范围变窄了：如果我们故意跑 pose-conditioned DA3，Research 的 OpenCV w2c 转换才是正确方向；如果我们复刻官方 DA3-Streaming 默认算法，就不应该把 ARKit/VIO 相机喂给 DA3。

intrinsics 这项当前不是最大嫌疑：`intrinsicsTransform` 的 offset 全是 0，APP 原图尺寸缩放公式与 Research `scale_intrinsics` 完全一致。但 official streaming baseline 应该让 DA3 自己预测 intrinsics；ARKit intrinsics 只能作为 metadata 或 pose-conditioned experiment 输入。

## Source Evidence

### official_da3

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/README.md:20-21 DA3 supports arbitrary visual inputs with or without known camera poses`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/docs/API.md:200-209 extrinsics/intrinsics are optional pose-conditioned inputs`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:253-274 DA3-Streaming calls model.inference(images, ref_view_strategy=...) without external cameras`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:880-915 DA3-Streaming CLI accepts image_dir/config/output_dir, not AR/VIO camera files`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py:195-218 preprocess -> prepare -> normalize extrinsics -> forward -> align to input camera`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py:327-339 first-frame inverse + median camera-distance normalization`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py:341-365 Umeyama alignment, ransac for >=10 views, depth divided by pose scale`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:219-257 resize, patch-size alignment, intrinsics resize/crop, ImageNet normalization`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/vision_transformer.py:314-338 saddle_balanced reference selection and alternating local/global attention`

### research

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:311-315 camera_transform_to_opencv_w2c`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:318-352 scale_intrinsics using intrinsicsTransform when present`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/make_official_pytorch_window_manifest.py:104-114 writes cameraExtrinsic4x4 with extrinsicConvention=opencv_w2c`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/coreml_official_postprocess_export.py:66-85 mirrors official Umeyama + depth scale postprocess`

### app

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:2451-2465 copies photo_bundle cameraTransform/intrinsics into Da3DepthFrameSpec`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:595-623 makeExtrinsics copies frames[].cameraTransform as-is`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:625-671 makeIntrinsics scales by original image size to locked input size`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage CoreML signature requires image/extrinsics/intrinsics`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/capture/dome/captured_frame_sample.dart:105-115 ARKit/IMU pose is guidance metadata; reconstruction pose should be solved from images independently`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:2953-2961 declares photos_depth direct_stretch fixed input preprocessing`

## Alignment Matrix

| Official step | Research state | APP state | Status | Next probe |
|---|---|---|---|---|
| DA3-Streaming inference input contract | current Mac/CoreML exporter follows the existing pose-conditioned CoreML model | current CoreML model requires image/extrinsics/intrinsics and APP supplies ARKit metadata | open_high_risk | export/use image-only DA3-BASE CoreML for official streaming parity, or label pose-conditioned CoreML as a non-default DA3 mode |
| image preprocessing | fixed photos_depth parity path and highres official dynamic path both documented | locked K35@476x742 photos_depth direct_stretch + native sRGB/ImageNet tensor | intentional_mobile_difference | pixel/tensor parity between photos_depth, native CoreGraphics decode, and official InputProcessor for the same frame |
| camera extrinsics input | if pose-conditioned mode is intentionally used, Research conversion to OpenCV w2c is correct | native makeExtrinsics copies ARKit camera-to-world metadata as-is | not_official_streaming_default | remove external camera inputs from the official baseline; conversion is only relevant for a separately labeled pose-conditioned experiment |
| intrinsics input | scale_intrinsics honors da3_input_manifest.intrinsicsTransform | native makeIntrinsics scales by source image size and fixed input size | currently_matched_for_direct_stretch | do not feed ARKit intrinsics in official streaming baseline; keep intrinsics only as metadata or pose-conditioned experiment input |
| reference view and attention | PyTorch low-res probes exist; full same-resolution K35 blocked by local MPS memory | sealed CoreML graph behavior is not directly inspectable | blocked_by_fullres_reference_gate | run full same-resolution PyTorch K35 on larger CUDA memory or wait for official memory-efficient path |
| pose/depth scale postprocess | coreml_official_postprocess_export mirrors pose-conditioned API semantics, not streaming default semantics | APP downstream currently consumes pose-conditioned CoreML outputs | must_rebaseline_for_streaming_default | build image-only DA3 reference outputs and rerun core-frame npz downstream before judging product cleanup |

## Decision

- `start_upstream_geometry_alignment_now`: `True`
- `thickness_current_attribution`: `within_window_upstream_geometry_consistency`
- `official_streaming_default_uses_external_camera_inputs`: `False`
- `current_app_coreml_is_pose_conditioned`: `True`
- `highest_priority_gap`: `app_pose_conditioned_coreml_vs_official_streaming_image_only_contract`
- `research_camera_path_matches_official_converted_input`: `True`
- `raw_camera_transform_not_equal_to_official_w2c`: `True`
- `current_intrinsics_formula_matches_direct_stretch_manifest`: `True`
- `required_official_baseline_action`: `Export/use an image-only DA3-BASE CoreML path matching official DA3-Streaming, or keep the current CoreML path explicitly labeled as optional pose-conditioned DA3 mode.`
- `do_not_add_product_cleanup_yet`: `True`

目标仍不能 complete：full same-resolution PyTorch K35 hard parity 还没关闭，并且 APP/Research 当前用的是 pose-conditioned CoreML，不是官方 DA3-Streaming image-only 默认输入契约。

## Next Probes

1. Export or obtain a DA3-BASE K35@476x742 image-only CoreML model whose signature does not require extrinsics/intrinsics.
2. Run a same-window image-only PyTorch reference and compare it against current pose-conditioned CoreML to quantify how much AR/VIO conditioning changes thickness.
3. Keep ARKit/VIO data in photo_bundle metadata only; do not feed it into the official DA3-Streaming baseline.
4. If a pose-conditioned experiment is retained, label it separately and convert ARKit camera-to-world to OpenCV world-to-camera before model input.
5. Pixel/tensor preprocessing parity: compare APP photos_depth/CoreGraphics normalized tensor to official InputProcessor output for the same fixed image.
6. Full same-resolution PyTorch K35 reference gate on larger CUDA memory or official memory-efficient attention.

## 大白话

现在的问题不像是“点云最后合并时多加了几层”，而更像是“模型上游几帧对同一面墙的深度/相机没有完全压到同一个几何面”。

你这个纠正是对的：如果官方 DA3-Streaming 原生算法不带 AR mode 采集数据，我们就不应该带。当前 APP 把 ARKit pose 喂进 CoreML，不是“更官方”，而是切到了官方 API 支持的另一个 pose-conditioned mode。

所以下一刀很明确：先拿到 image-only DA3-BASE CoreML 或用 PyTorch image-only reference 重跑 K35，再判断厚层是不是官方 DA3 本身的限制。ARKit/VIO 先退回 metadata 和后处理产品层。
