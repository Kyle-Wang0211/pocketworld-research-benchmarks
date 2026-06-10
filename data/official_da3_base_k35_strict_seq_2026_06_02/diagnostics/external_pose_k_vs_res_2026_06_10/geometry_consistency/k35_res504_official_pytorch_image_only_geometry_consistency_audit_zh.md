# Official PyTorch image-only geometry consistency audit

window: `k35_res504`

## 结论

- status: `official_image_only_upstream_geometry_residuals_measured`
- first geometry spike: `slot 4 cap-21 prev=cap-7 prev_rel_med=0.2912 npz_minor/k10=NA`
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
| 12 | `cap-42` | `cap-39` | 3 | 0.0784 | 1.2496 | 1.5499 | 0.3537 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 33 | `cap-128` | `cap-126` | 2 | 0.0595 | 0.9528 | 1.0701 | 0.1126 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 10 | `cap-37` | `cap-35` | 2 | 0.0520 | 0.6549 | 0.8952 | 0.0744 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high |
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.5918 | 0.7317 | 0.5832 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 18 | `cap-56` | `cap-54` | 2 | 0.0269 | 0.4177 | 0.5707 | 0.0867 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high |
| 11 | `cap-39` | `cap-37` | 2 | 0.0301 | 0.0563 | 0.5315 | 0.0605 | NA | previous_pair_relative_p90_high |
| 4 | `cap-21` | `cap-7` | 14 | 0.2031 | 0.2912 | 0.4647 | 0.2022 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 6 | `cap-29` | `cap-23` | 6 | 0.0827 | 0.3872 | 0.4583 | 0.3959 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 22 | `cap-96` | `cap-80` | 16 | 0.2645 | 0.5918 | 0.7317 | 0.5832 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 6 | `cap-29` | `cap-23` | 6 | 0.0827 | 0.3872 | 0.4583 | 0.3959 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 12 | `cap-42` | `cap-39` | 3 | 0.0784 | 1.2496 | 1.5499 | 0.3537 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 23 | `cap-103` | `cap-96` | 7 | 0.1211 | 0.3113 | 0.4277 | 0.3188 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 5 | `cap-23` | `cap-21` | 2 | 0.0612 | 0.3064 | 0.3781 | 0.3106 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 24 | `cap-105` | `cap-103` | 2 | 0.0367 | 0.2346 | 0.3486 | 0.2676 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 20 | `cap-78` | `cap-74` | 4 | 0.0503 | 0.2952 | 0.3970 | 0.2226 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |
| 27 | `cap-114` | `cap-109` | 5 | 0.0650 | 0.2233 | 0.2940 | 0.2167 | NA | previous_pair_relative_median_ge_threshold, previous_pair_relative_p90_high, best_prefix_relative_median_ge_threshold |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
