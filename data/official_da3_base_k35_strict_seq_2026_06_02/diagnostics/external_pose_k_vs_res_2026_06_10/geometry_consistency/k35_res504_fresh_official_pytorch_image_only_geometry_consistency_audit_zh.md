# Official PyTorch image-only geometry consistency audit

window: `k35_res504_fresh`

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
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.0384 | 0.0943 | 0.0178 | NA |  |
| 27 | `cap-114` | `cap-109` | 5 | 0.0650 | 0.0389 | 0.0572 | 0.0378 | NA |  |
| 23 | `cap-103` | `cap-96` | 7 | 0.1211 | 0.0373 | 0.0551 | 0.0230 | NA |  |
| 19 | `cap-74` | `cap-56` | 18 | 0.3314 | 0.0174 | 0.0514 | 0.0069 | NA |  |
| 29 | `cap-118` | `cap-116` | 2 | 0.0365 | 0.0373 | 0.0502 | 0.0075 | NA |  |
| 34 | `cap-131` | `cap-128` | 3 | 0.0345 | 0.0175 | 0.0373 | 0.0028 | NA |  |
| 24 | `cap-105` | `cap-103` | 2 | 0.0367 | 0.0210 | 0.0367 | 0.0177 | NA |  |
| 26 | `cap-109` | `cap-107` | 2 | 0.0185 | 0.0179 | 0.0282 | 0.0078 | NA |  |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 27 | `cap-114` | `cap-109` | 5 | 0.0650 | 0.0389 | 0.0572 | 0.0378 | NA |  |
| 23 | `cap-103` | `cap-96` | 7 | 0.1211 | 0.0373 | 0.0551 | 0.0230 | NA |  |
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.0384 | 0.0943 | 0.0178 | NA |  |
| 24 | `cap-105` | `cap-103` | 2 | 0.0367 | 0.0210 | 0.0367 | 0.0177 | NA |  |
| 26 | `cap-109` | `cap-107` | 2 | 0.0185 | 0.0179 | 0.0282 | 0.0078 | NA |  |
| 30 | `cap-122` | `cap-118` | 4 | 0.0209 | 0.0117 | 0.0225 | 0.0076 | NA |  |
| 29 | `cap-118` | `cap-116` | 2 | 0.0365 | 0.0373 | 0.0502 | 0.0075 | NA |  |
| 21 | `cap-80` | `cap-78` | 2 | 0.0197 | 0.0096 | 0.0192 | 0.0075 | NA |  |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
