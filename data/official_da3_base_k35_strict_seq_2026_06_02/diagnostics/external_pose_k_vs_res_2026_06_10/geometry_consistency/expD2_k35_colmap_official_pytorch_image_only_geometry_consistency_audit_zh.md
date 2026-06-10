# Official PyTorch image-only geometry consistency audit

window: `expD2_k35_colmap`

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
| 23 | `cap-103` | `cap-96` | 7 | 0.1224 | 0.0338 | 0.0550 | 0.0076 | NA |  |
| 22 | `cap-96` | `cap-80` | 16 | 0.2622 | 0.0129 | 0.0381 | 0.0051 | NA |  |
| 31 | `cap-124` | `cap-122` | 2 | 0.0279 | 0.0197 | 0.0360 | 0.0045 | NA |  |
| 28 | `cap-116` | `cap-114` | 2 | 0.0249 | 0.0136 | 0.0356 | 0.0062 | NA |  |
| 19 | `cap-74` | `cap-56` | 18 | 0.3298 | 0.0115 | 0.0351 | 0.0057 | NA |  |
| 33 | `cap-128` | `cap-126` | 2 | 0.0597 | 0.0137 | 0.0292 | 0.0079 | NA |  |
| 20 | `cap-78` | `cap-74` | 4 | 0.0487 | 0.0095 | 0.0288 | 0.0072 | NA |  |
| 34 | `cap-131` | `cap-128` | 3 | 0.0365 | 0.0131 | 0.0246 | 0.0027 | NA |  |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 24 | `cap-105` | `cap-103` | 2 | 0.0365 | 0.0099 | 0.0221 | 0.0083 | NA |  |
| 33 | `cap-128` | `cap-126` | 2 | 0.0597 | 0.0137 | 0.0292 | 0.0079 | NA |  |
| 23 | `cap-103` | `cap-96` | 7 | 0.1224 | 0.0338 | 0.0550 | 0.0076 | NA |  |
| 20 | `cap-78` | `cap-74` | 4 | 0.0487 | 0.0095 | 0.0288 | 0.0072 | NA |  |
| 28 | `cap-116` | `cap-114` | 2 | 0.0249 | 0.0136 | 0.0356 | 0.0062 | NA |  |
| 19 | `cap-74` | `cap-56` | 18 | 0.3298 | 0.0115 | 0.0351 | 0.0057 | NA |  |
| 25 | `cap-107` | `cap-105` | 2 | 0.0256 | 0.0082 | 0.0206 | 0.0056 | NA |  |
| 22 | `cap-96` | `cap-80` | 16 | 0.2622 | 0.0129 | 0.0381 | 0.0051 | NA |  |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
