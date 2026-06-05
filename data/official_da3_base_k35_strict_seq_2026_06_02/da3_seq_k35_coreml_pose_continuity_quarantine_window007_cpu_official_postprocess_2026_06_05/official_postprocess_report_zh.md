# CoreML Official DA3 Postprocess Export

## 做了什么

- 不重新跑 CoreML inference。
- 读取 sealed CoreML raw window 输出。
- 按官方 PyTorch API 后处理顺序执行：`align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)`。
- 用 `depth = raw_depth / pose_scale` 写回 depth。
- 用输入相机的 intrinsics/extrinsics 回填官方 postprocess 语义。

## Window Summary

| window | status | frames | ransac | pose_scale | raw depth mean | post depth mean | raw pose center median | post pose center median | raw K MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| window_007_prefix_before_first_break | skipped_invalid_alignment | 35 | False | n/a | n/a | n/a | n/a | n/a | n/a |
| window_007_segment_from_first_break | completed | 35 | True | 0.73031058 | 0.925723 | 1.26757 | 1.80013 | 0 | 9.10257 |
| window_007_drop_all_high_risk_targets | completed | 35 | True | 0.68257055 | 0.832512 | 1.21967 | 1.71686 | 0 | 9.12 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
