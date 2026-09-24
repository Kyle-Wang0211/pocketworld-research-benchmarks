# Official DA3 preprocess parity audit

日期：2026-06-04

## 结论

- `DA3BASE_476x742_N35` 固定目标本身是 patch-aligned：476 和 742 都能被 14 整除。
- 官方 API 默认预处理是 aspect-preserving `upper_bound_resize`，再 round 到 patch-14 multiple，再 ImageNet normalize。
- 当前 APP/CoreML 固定输入使用 `photos_depth`：从高分图直接拉伸到 `742x476`，再 ImageNet normalize。
- 因此 `photos_depth` 是 CoreML/PyTorch same-input parity baseline；它不是官方 API dynamic preprocessing 的百分百等价物。
- 厚层回归实验必须标明使用 `photos_depth` 还是 `photos_highres`，不能混着比较。

## 固定目标

- window size: `35`
- shape: `476x742`
- patch size: `14`
- patch grid: `34x53`
- dimension sweep: `disabled`

## 官方预处理证据

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py:145`: `process_res: int = 504,`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/api.py:146`: `process_res_method: str = "upper_bound_resize",`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:43`: `2) Boundary resize (upper/lower bound, preserving aspect ratio)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:57`: `PATCH_SIZE = 14`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:318`: `return self._resize_longest_side(img, target_size)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:332`: `interpolation = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:239`: `pil_img = self._make_divisible_by_resize(pil_img, self.PATCH_SIZE)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/io/input_processor.py:56`: `NORMALIZE = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])`

## 当前输入证据

- frame0 source: `4224x2376`
- frame0 input: `742x476`
- frame0 resize: `{"mode": "direct_stretch", "interpolation": "cubic", "colorSpace": "sRGB", "jpegQuality": 95}`
- frame0 scaleX/scaleY: `0.17566287878787878` / `0.20033670033670034`
- aspect preserving: `False`

- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:161`: `inputLocked ? 'dart_photos_depth_direct_stretch' : 'runtime_policy',`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:569`: `"DA3 imagePath must already be \(spec.inputWidth)x\(spec.inputHeight) from photos_depth; got \(image.width)x\(image.height): \(imagePath)"`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:605`: `ptr[viewBase + 0 * planeSize + dst] = (r - meanR) / stdR`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:339`: `image = image.resize((width, height), Image.Resampling.BICUBIC)`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:341`: `arr = (arr - IMAGENET_MEAN) / IMAGENET_STD`

## Research 已经区分的两种基线

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/make_official_pytorch_window_manifest.py:25`: `"photos_depth uses the APP fixed 742x476 input and scaled intrinsics; "`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/make_official_pytorch_window_manifest.py:26`: `"photos_highres lets official PyTorch do dynamic upper_bound_resize."`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/make_official_pytorch_window_manifest.py:155`: `"expectedMethod": "already_fixed_742x476_then_upper_bound_resize_no_shape_change",`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/make_official_pytorch_window_manifest.py:150`: `"role": "official_dynamic_aspect_ratio_reference",`

## 判读规则

- official API preprocess: `aspect_preserving_upper_bound_resize_then_patch14_then_imagenet`
- fixed CoreML preprocess: `photos_depth_direct_stretch_742x476_then_imagenet`
- shape parity: `pass_476x742_is_patch14_aligned`
- tensor parity risk: `photos_depth direct_stretch is not identical to official API upper_bound_resize from highres images`
- baseline rule: `Use photos_depth for CoreML-vs-PyTorch same-input parity; use photos_highres only when asking what official API dynamic preprocessing would do.`
- impact on thickness test: `The image-only overlap regression gate must state which preprocessing baseline produced the image tensor. Mixing photos_depth and photos_highres can make a thickness comparison inconclusive.`

## 下一步

1. Keep DA3BASE_476x742_N35 fixed for APP/CoreML parity.
2. When target image-only CoreML exists, run overlap regression on photos_depth same-input parity first.
3. Separately run official PyTorch image-only on photos_highres/dynamic preprocessing if memory allows, and label it as official API reference, not same-input CoreML parity.
4. Do not claim exact official API preprocessing parity for direct_stretch photos_depth.
