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
| loop_window_000 | 35 | True | 0.86667101 | 1.09213 | 1.26014 | 2.73362 | 0 | 8.86114 |
| loop_window_001 | 35 | True | 0.80277032 | 1.00552 | 1.25256 | 2.96211 | 0 | 8.87227 |
| loop_window_002 | 35 | True | 0.75681157 | 0.932174 | 1.23171 | 3.03987 | 0 | 8.88536 |
| loop_window_003 | 35 | True | 0.76671101 | 0.898555 | 1.17196 | 2.14312 | 0 | 9.17061 |
| loop_window_004 | 35 | True | 0.83769031 | 1.07277 | 1.28063 | 3.17656 | 0 | 8.95194 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
