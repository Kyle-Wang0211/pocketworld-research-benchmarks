# Official DA3 fixed-shape preprocess authority audit

日期：2026-06-05

## 结论

- status: `fixed_476x742_shape_not_exact_official_preprocess_for_16x9_sources`
- exact aspect-preserving resize possible: `False`
- all direct_stretch: `True`
- official algorithm blame supported: `False`

For this strict capture, the fixed 742x476 CoreML image tensor cannot be the exact output of official aspect-preserving upper_bound_resize for 16:9 source frames. Official long-side-742 resize lands at 742x420 after patch rounding, while the current manifest uses direct_stretch to 742x476. This keeps the product-selected fixed model shape runnable, but it is not an official preprocessing authority.

## 大白话

- 476x742 是一个固定 CoreML 输入形状；它能跑，不等于它就是官方 API 的 preprocess 输出。
- 这批源图基本是 16:9，官方等比 upper_bound_resize 不会把 16:9 变成 742x476。
- 当前 Dart manifest 是 direct_stretch，所以 Y 方向相对 X 方向被额外拉伸；这是上游输入合同差异。
- 因此当前厚层仍不能证明官方原生 DA3 算法有问题；它首先证明我们跑的是固定形状兼容路径。
- 下一步不要再测尺寸，把 476x742 当产品约束，继续查 image-only cam_dec 和官方 preprocess 的权威路径。

## Manifest

- frame_count: `414`
- input_size: `742x476`
- input_aspect: `1.558824`
- median_y_over_x_stretch: `1.140461`
- mode_counts: `{'direct_stretch': 414}`
- source_size_counts: `{'4224x2376': 396, '3840x2160': 18}`

## Official Resize Examples

| source | count | current fixed | current aspect | official long-side 742 | long-side needed for height 476 | exact aspect-preserving? |
|---|---:|---:|---:|---:|---|---:|
| 3840x2160 | 18 | 742x476 | 1.558824 | 742x420 | 846->840x476 | `False` |
| 4224x2376 | 396 | 742x476 | 1.558824 | 742x420 | 846->840x476 | `False` |
