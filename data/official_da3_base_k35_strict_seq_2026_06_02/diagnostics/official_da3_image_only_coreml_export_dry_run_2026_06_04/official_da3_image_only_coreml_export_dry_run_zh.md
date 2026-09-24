# Official DA3 image-only CoreML export dry-run

日期：2026-06-04

## 结论

image-only PyTorch wrapper 已经跑通：它只接收 `image`，不接收 `extrinsics/intrinsics`，并且仍然输出 `depth/depth_conf/pred_extrinsics/pred_intrinsics`。

这证明“没有 AR/VIO 输入时 DA3 仍能输出位姿”这件事在本地权重上成立。位姿来自官方模型内部 camera decoder，不是 identity pose，也不是 ARKit/VIO pose。

CoreML conversion 还没有通过。一个 tiny conversion probe 在 CoreML PyTorch frontend 的 `int` op 转换处失败：

`TypeError: only 0-dimensional arrays can be converted to Python scalars`

所以当前状态不是“image-only CoreML 已导出”，而是“image-only wrapper 语义已验证，CoreML converter 卡点已暴露”。

## Dry-run：K35@28x28

- `status`: `pass`
- `input`: `image [1,35,3,28,28]`
- `outputs`:
  - `depth [1,35,28,28]`
  - `depth_conf [1,35,28,28]`
  - `pred_extrinsics [1,35,3,4]`
  - `pred_intrinsics [1,35,3,3]`
- `finite`: `true` for all outputs
- 官方日志触发了 `Selecting reference view using strategy: saddle_balanced`

JSON:

`official_da3_image_only_coreml_export_dry_run.json`

## Tiny conversion probe：K3@28x28

- `dry_run.status`: `pass`
- `conversion.status`: `fail`
- `conversion.reason`: `TypeError: only 0-dimensional arrays can be converted to Python scalars`
- `torch`: `2.12.0`
- `coremltools`: `9.0`
- `coremltools` 同时提示 torch 2.12 未在它的官方测试范围内。

JSON:

`official_da3_image_only_coreml_tiny_convert_probe.json`

## Interpretation

这不是 DA3 官方算法语义的问题，而是 PyTorch graph -> CoreML graph 这一步的问题。当前 wrapper 调的是官方 image-only 语义：

`net(image, None, None, export_feat_layers=[], infer_gs=False, use_ray_pose=False, ref_view_strategy='saddle_balanced')`

而不是：

- identity extrinsics
- ARKit extrinsics
- ARKit intrinsics

## Next

1. 继续修 `export_da3_image_only_coreml.py` 的 conversion path，定位 CoreML frontend `int` op 来自 DA3 backbone 哪个 shape/rope/reference-selection 片段。
2. 尝试 coremltools 官方测试过的 torch 版本，例如 torch 2.7.x 环境，排除版本兼容误报。
3. 如果仍失败，再考虑用官方语义等价的 trace/export wrapper 固定 shape，减少动态 Python int/shape 分支。
4. 只有当 `DA3BASE_476x742_N35_image_only.mlpackage` 的 required inputs 变成 exactly `image`，readiness gate 才能 pass。

## 大白话

我们现在已经证明：DA3 不靠 AR 也会输出位姿。它在模型里自己估。

但把这个 PyTorch image-only wrapper 变成 CoreML 时，转换器卡在一个图里的 `int` 操作。下一步要修的是导出工程问题，不是再回头把 ARKit 塞进去。
