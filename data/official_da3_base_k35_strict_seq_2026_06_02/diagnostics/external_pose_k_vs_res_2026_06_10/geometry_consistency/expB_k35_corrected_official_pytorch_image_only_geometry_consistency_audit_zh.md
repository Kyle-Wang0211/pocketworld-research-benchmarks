# Official PyTorch image-only geometry consistency audit

window: `expB_k35_corrected`

## 结论

- status: `official_image_only_upstream_geometry_residuals_measured`
- first geometry spike: `None`
- first NPZ minor >= 1.10x: `None`
- first NPZ minor >= 1.35x: `None`
- interpretation: No clear upstream residual spike was found with the configured threshold.

## 大白话

- 这个审计不生成点云，也不改 DA3 输出；它直接检查官方 image-only 的深度、内参、cam_dec 位姿在同一个 window 内是否互相投得上。
- 如果某一帧投到前面帧时，同一个空间点在目标帧深度上差很多，那厚层就已经是上游几何一致性问题，下游 PLY 只是把它显出来。
- `previous_*` 是当前帧投到前一帧；`best_prefix_*` 是当前帧投到前缀若干帧里取最好的重叠残差。

## Top Previous-Pair Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 23 | `cap-103` | `cap-96` | 7 | 0.1211 | 0.0193 | 0.0488 | 0.0041 | NA |  |
| 19 | `cap-74` | `cap-56` | 18 | 0.3314 | 0.0121 | 0.0373 | 0.0058 | NA |  |
| 28 | `cap-116` | `cap-114` | 2 | 0.0251 | 0.0134 | 0.0335 | 0.0029 | NA |  |
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.0121 | 0.0335 | 0.0059 | NA |  |
| 20 | `cap-78` | `cap-74` | 4 | 0.0503 | 0.0103 | 0.0276 | 0.0081 | NA |  |
| 33 | `cap-128` | `cap-126` | 2 | 0.0595 | 0.0087 | 0.0270 | 0.0024 | NA |  |
| 34 | `cap-131` | `cap-128` | 3 | 0.0345 | 0.0102 | 0.0244 | 0.0020 | NA |  |
| 31 | `cap-124` | `cap-122` | 2 | 0.0275 | 0.0077 | 0.0237 | 0.0018 | NA |  |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 20 | `cap-78` | `cap-74` | 4 | 0.0503 | 0.0103 | 0.0276 | 0.0081 | NA |  |
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.0121 | 0.0335 | 0.0059 | NA |  |
| 19 | `cap-74` | `cap-56` | 18 | 0.3314 | 0.0121 | 0.0373 | 0.0058 | NA |  |
| 23 | `cap-103` | `cap-96` | 7 | 0.1211 | 0.0193 | 0.0488 | 0.0041 | NA |  |
| 25 | `cap-107` | `cap-105` | 2 | 0.0254 | 0.0087 | 0.0179 | 0.0038 | NA |  |
| 24 | `cap-105` | `cap-103` | 2 | 0.0367 | 0.0053 | 0.0147 | 0.0032 | NA |  |
| 28 | `cap-116` | `cap-114` | 2 | 0.0251 | 0.0134 | 0.0335 | 0.0029 | NA |  |
| 1 | `cap-3` | `cap-1` | 2 | 0.0166 | 0.0029 | 0.0090 | 0.0029 | NA |  |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
