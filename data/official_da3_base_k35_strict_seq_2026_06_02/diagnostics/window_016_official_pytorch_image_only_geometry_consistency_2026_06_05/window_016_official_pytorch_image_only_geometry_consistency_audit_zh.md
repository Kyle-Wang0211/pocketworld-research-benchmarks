# Official PyTorch image-only geometry consistency audit

window: `window_016`

## 结论

- status: `official_image_only_upstream_geometry_residuals_measured`
- first geometry spike: `slot 10 cap-1396 prev=cap-1369 prev_rel_med=0.0154 npz_minor/k10=1.2626`
- first NPZ minor >= 1.10x: `slot 10 cap-1396 prev=cap-1369 prev_rel_med=0.0154 npz_minor/k10=1.2626`
- first NPZ minor >= 1.35x: `slot 11 cap-1413 prev=cap-1396 prev_rel_med=0.0089 npz_minor/k10=1.4150`
- interpretation: First measured upstream projective residual spike is slot 10 (cap-1396); first NPZ minor growth >=1.10x is slot 10 (cap-1396). This supports an upstream depth/pose consistency explanation rather than a pure point-cloud merge explanation.

## 大白话

- 这个审计不生成点云，也不改 DA3 输出；它直接检查官方 image-only 的深度、内参、cam_dec 位姿在同一个 window 内是否互相投得上。
- 如果某一帧投到前面帧时，同一个空间点在目标帧深度上差很多，那厚层就已经是上游几何一致性问题，下游 PLY 只是把它显出来。
- `previous_*` 是当前帧投到前一帧；`best_prefix_*` 是当前帧投到前缀若干帧里取最好的重叠残差。

## Top Previous-Pair Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 24 | `cap-1514` | `cap-1494` | 20 | 0.4506 | 0.0657 | 1.6096 | 0.0030 | 1.5716 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 14 | `cap-1437` | `cap-1429` | 8 | 0.2978 | 0.0163 | 0.5405 | 0.0118 | 1.5034 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 21 | `cap-1488` | `cap-1459` | 29 | 0.3601 | 0.0315 | 0.4306 | 0.0108 | 1.5146 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 10 | `cap-1396` | `cap-1369` | 27 | 0.4388 | 0.0154 | 0.2630 | 0.0050 | 1.2626 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10 |
| 23 | `cap-1494` | `cap-1492` | 2 | 0.1464 | 0.0254 | 0.1176 | 0.0074 | 1.5743 | cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 5 | `cap-1361` | `cap-1360` | 1 | 0.0129 | 0.0729 | 0.0842 | 0.0081 | 0.9795 |  |
| 4 | `cap-1360` | `cap-1358` | 2 | 0.0137 | 0.0448 | 0.0721 | 0.0161 | 0.9924 |  |
| 2 | `cap-1356` | `cap-1354` | 2 | 0.0174 | 0.0405 | 0.0700 | 0.0164 | 0.9957 |  |

## Top Best-Prefix Residuals

| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `cap-1354` | `cap-1346` | 8 | 0.1919 | 0.0286 | 0.0614 | 0.0286 | 1.0104 |  |
| 2 | `cap-1356` | `cap-1354` | 2 | 0.0174 | 0.0405 | 0.0700 | 0.0164 | 0.9957 |  |
| 4 | `cap-1360` | `cap-1358` | 2 | 0.0137 | 0.0448 | 0.0721 | 0.0161 | 0.9924 |  |
| 22 | `cap-1492` | `cap-1488` | 4 | 0.0303 | 0.0161 | 0.0358 | 0.0131 | 1.5457 | cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 14 | `cap-1437` | `cap-1429` | 8 | 0.2978 | 0.0163 | 0.5405 | 0.0118 | 1.5034 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 21 | `cap-1488` | `cap-1459` | 29 | 0.3601 | 0.0315 | 0.4306 | 0.0108 | 1.5146 | previous_pair_relative_p90_high, cumulative_npz_minor_ge_1_10_vs_k10, cumulative_npz_minor_ge_1_35_vs_k10 |
| 5 | `cap-1361` | `cap-1360` | 1 | 0.0129 | 0.0729 | 0.0842 | 0.0081 | 0.9795 |  |
| 3 | `cap-1358` | `cap-1356` | 2 | 0.0160 | 0.0114 | 0.0270 | 0.0077 | 0.9743 |  |

## Parameters

- stride: `6`
- confidence: `max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output`
- conf_threshold_coef: `0.5`
- relative_risk_threshold: `0.1`
