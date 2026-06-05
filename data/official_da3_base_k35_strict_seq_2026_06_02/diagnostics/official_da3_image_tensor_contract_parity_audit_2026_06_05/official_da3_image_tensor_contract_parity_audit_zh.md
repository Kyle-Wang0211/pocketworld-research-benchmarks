# Official DA3 image tensor contract parity audit

日期：2026-06-05

## 结论

- status: `image_tensor_normalization_matches_but_resize_contract_differs`
- normalization parity: `True`
- resize contract parity: `False`
- official algorithm blame supported: `False`

APP Swift normalization matches official ImageNet RGB/NCHW tensor semantics, but the image resize contract still differs: official code does aspect-preserving upper_bound_resize plus patch rounding, while current Dart photos_depth uses direct_stretch to the fixed 742x476 model size. In the strict capture, a 16:9 source frame would become 742x420 under an official long-side-742 upper_bound_resize contract, but the current manifest stores it as 742x476.

## 大白话

- Swift 喂给 CoreML 的 RGB/NCHW/ImageNet normalization 和官方一致，这一点先不要再怀疑。
- 但 APP 当前没有在 Swift 里做官方 boundary resize；它依赖 Dart 预生成固定尺寸 photos_depth。
- Dart 的固定尺寸生成是 direct_stretch，不是官方默认的等比 upper_bound_resize + patch multiple。
- 这批 strict capture 的源图主要是 4224x2376；当前变成 742x476，Y 方向相对 X 方向多拉伸约 14%。
- 如果按官方 upper_bound_resize 并把长边设成 742，同一 16:9 源图会落到 742x420，而不是 742x476。
- 所以 image-side 仍有未复刻点，但它集中在 resize/preprocess contract，不是 normalization。

## Checks

| check | status | line | evidence | path |
|---|---:|---:|---|---|
| `official_default_upper_bound_resize` | `pass` | 71 | 官方默认 process_res_method 是 upper_bound_resize。 | `input_processor.py` |
| `official_preserves_aspect_by_longest_side` | `pass` | 329 | 官方 upper_bound_resize 先按最长边等比缩放。 | `input_processor.py` |
| `official_rounds_to_patch_multiple` | `pass` | 376 | 官方 resize 后还会把宽高调整到 patch size 的倍数。 | `input_processor.py` |
| `official_imagenet_normalization` | `pass` | 56 | 官方输入 tensor 使用 ImageNet mean/std normalization。 | `input_processor.py` |
| `app_dart_photos_depth_direct_stretch` | `parity_gap` | 645 | Dart photos_depth 固定输入是 direct_stretch 到模型尺寸；这和官方等比 upper_bound_resize 不是同一 preprocess。 | `photo_bundle_derivation_service.dart` |
| `app_swift_requires_pre_resized_photos_depth` | `parity_gap` | 569 | Swift 不执行官方 boundary resize；它要求 Dart/photos_depth 已经是固定尺寸。 | `Da3DepthPlugin.swift` |
| `app_swift_imagenet_mean_matches_official` | `pass` | 554 | Swift image tensor 使用与官方一致的 ImageNet mean。 | `Da3DepthPlugin.swift` |
| `app_swift_imagenet_std_matches_official` | `pass` | 557 | Swift image tensor 使用与官方一致的 ImageNet std。 | `Da3DepthPlugin.swift` |
| `app_swift_writes_nchw_float32` | `pass` | 605 | Swift 写入 NCHW float32 normalized tensor，通道顺序与官方 RGB tensor 对齐。 | `Da3DepthPlugin.swift` |
| `strict_capture_manifest_all_direct_stretch` | `parity_gap` |  | frames=414, modes={'direct_stretch': 414}; source resize examples: 3840x2160->742x476 current, 742x420 official-like; 4224x2376->742x476 current, 742x420 official-like; median y/x stretch=1.140. | `da3_input_manifest.json` |
