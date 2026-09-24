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
| window_016 | completed | 35 | True | 0.72507338 | 0.961981 | 1.32674 | 3.32137 | 0 | 9.12316 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
