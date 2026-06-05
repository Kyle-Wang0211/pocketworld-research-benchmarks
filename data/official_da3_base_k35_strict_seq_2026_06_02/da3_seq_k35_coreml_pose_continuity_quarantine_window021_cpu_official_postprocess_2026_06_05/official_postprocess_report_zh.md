# CoreML Official DA3 Postprocess Export

## 做了什么

- 不重新跑 CoreML inference。
- 读取 sealed CoreML raw window 输出。
- 按官方 PyTorch API 后处理顺序执行：`align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)`。
- 用 `depth = raw_depth / pose_scale` 写回 depth。
- 用输入相机的 intrinsics/extrinsics 回填官方 postprocess 语义。

## Window Summary

| window | frames | ransac | pose_scale | raw depth mean | post depth mean | raw pose center median | post pose center median | raw K MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| window_021_prefix_before_first_break | 35 | False | 1.0906249 | 0.929405 | 0.852177 | 1.91701 | 0 | 9.03712 |
| window_021_segment_from_first_break | 35 | True | 0.68294838 | 1.07143 | 1.56884 | 2.0751 | 0 | 8.96858 |
| window_021_drop_all_high_risk_targets | 35 | True | 0.64086391 | 0.898815 | 1.40251 | 2.21319 | 0 | 8.61263 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
