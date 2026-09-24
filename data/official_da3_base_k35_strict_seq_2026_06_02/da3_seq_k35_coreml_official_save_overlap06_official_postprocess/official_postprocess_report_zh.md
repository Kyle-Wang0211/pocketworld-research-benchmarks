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
| window_001 | 35 | True | 0.73999491 | 0.929229 | 1.25572 | 3.14077 | 0 | 8.72439 |
| window_002 | 35 | True | 0.71356602 | 0.997674 | 1.39815 | 3.23603 | 0 | 9.00228 |
| window_003 | 35 | True | 0.9005133 | 1.0829 | 1.20254 | 2.8788 | 0 | 8.7258 |
| window_004 | 35 | True | 0.79453753 | 0.934359 | 1.17598 | 2.12976 | 0 | 9.27465 |
| window_005 | 35 | True | 0.73291833 | 1.03468 | 1.41172 | 1.77018 | 0 | 9.17374 |
| window_006 | 35 | True | 0.59650199 | 0.832382 | 1.39544 | 1.98775 | 0 | 8.98992 |
| window_007 | 35 | True | 0.64201808 | 0.766727 | 1.19425 | 2.72257 | 0 | 9.09822 |
| window_008 | 35 | True | 0.76347006 | 0.988885 | 1.29525 | 3.1704 | 0 | 8.93278 |
| window_009 | 35 | True | 0.66569684 | 0.951534 | 1.42938 | 3.36482 | 0 | 9.02001 |
| window_010 | 35 | True | 0.69417495 | 0.974529 | 1.40387 | 2.99421 | 0 | 9.17586 |
| window_011 | 35 | True | 0.74372519 | 0.915456 | 1.23091 | 2.53134 | 0 | 8.62775 |
| window_012 | 35 | True | 0.75098011 | 1.02117 | 1.35979 | 2.15809 | 0 | 9.01278 |
| window_013 | 35 | True | 0.73957078 | 0.847722 | 1.14624 | 2.61259 | 0 | 9.06502 |
| window_014 | 35 | False | 0.66304857 | 0.810518 | 1.22241 | 2.31136 | 0 | 9.08565 |

## 判断

这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。
