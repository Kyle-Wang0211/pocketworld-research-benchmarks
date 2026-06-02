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
| window_000 | 35 | True | 0.47967953 | 0.760074 | 1.58454 | 2.35699 | 0 | 8.80627 |
| window_001 | 35 | True | 0.56607753 | 0.712911 | 1.25939 | 2.78477 | 0 | 8.62746 |
| window_002 | 35 | True | 0.73995516 | 0.96343 | 1.30201 | 3.2893 | 0 | 8.58042 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
