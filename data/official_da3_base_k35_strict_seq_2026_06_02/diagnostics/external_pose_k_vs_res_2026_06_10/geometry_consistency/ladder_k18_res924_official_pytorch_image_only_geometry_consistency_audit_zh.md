# Official PyTorch image-only geometry consistency audit

window: `ladder_k18_res924`

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
| 4 | `cap-21` | `cap-7` | 14 | 0.2031 | 0.0038 | 0.0100 | 0.0021 | NA |  |
| 10 | `cap-37` | `cap-35` | 2 | 0.0520 | 0.0031 | 0.0097 | 0.0008 | NA |  |
| 12 | `cap-42` | `cap-39` | 3 | 0.0784 | 0.0032 | 0.0095 | 0.0010 | NA |  |
| 13 | `cap-44` | `cap-42` | 2 | 0.0504 | 0.0036 | 0.0094 | 0.0012 | NA |  |
| 9 | `cap-35` | `cap-33` | 2 | 0.1011 | 0.0028 | 0.0086 | 0.0009 | NA |  |
| 14 | `cap-48` | `cap-44` | 4 | 0.0533 | 0.0035 | 0.0084 | 0.0008 | NA |  |
| 17 | `cap-54` | `cap-52` | 2 | 0.0348 | 0.0025 | 0.0077 | 0.0006 | NA |  |
| 16 | `cap-52` | `cap-50` | 2 | 0.0493 | 0.0024 | 0.0075 | 0.0006 | NA |  |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 4 | `cap-21` | `cap-7` | 14 | 0.2031 | 0.0038 | 0.0100 | 0.0021 | NA |  |
| 1 | `cap-3` | `cap-1` | 2 | 0.0166 | 0.0019 | 0.0059 | 0.0019 | NA |  |
| 6 | `cap-29` | `cap-23` | 6 | 0.0827 | 0.0025 | 0.0062 | 0.0012 | NA |  |
| 13 | `cap-44` | `cap-42` | 2 | 0.0504 | 0.0036 | 0.0094 | 0.0012 | NA |  |
| 2 | `cap-5` | `cap-3` | 2 | 0.0341 | 0.0018 | 0.0061 | 0.0012 | NA |  |
| 5 | `cap-23` | `cap-21` | 2 | 0.0612 | 0.0026 | 0.0067 | 0.0011 | NA |  |
| 7 | `cap-31` | `cap-29` | 2 | 0.0483 | 0.0021 | 0.0071 | 0.0010 | NA |  |
| 12 | `cap-42` | `cap-39` | 3 | 0.0784 | 0.0032 | 0.0095 | 0.0010 | NA |  |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
