# window_016 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.725073`
- k10 pose diag: `0.296983`
- k35 pose diag: `1.16623`
- k35/k10 pose diag: `3.92692`
- k10 depth p95: `2.59941`
- k35 depth p95: `2.57517`
- k35/k10 depth p95: `0.990674`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | k=12 (1.14695) | k=12 (1.1819) | - | 1.24097 | 1.08177 | 1.21951 | 4.93816e-05 |
| npz_streaming_style | k=12 (1.16388) | k=11 (1.11004) | k=12 (1.36445) | 1.40313 | 1.41811 | 0.898756 | 0.0315119 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.4553 | 0.991928 | 0.97233 | 1.06464 | 1.11623 |
| 2 | 0.188339 | 2.51726 | 0.974634 | 0.961777 | 1.04046 | 1.05876 |
| 3 | 0.208832 | 2.53477 | 0.87263 | 0.788141 | 1.00774 | 0.985898 |
| 4 | 0.218697 | 2.5617 | 0.877722 | 0.804782 | 1.00366 | 0.976086 |
| 5 | 0.230252 | 2.59537 | 0.978679 | 0.987504 | 1.0028 | 0.973703 |
| 6 | 0.232752 | 2.60749 | 1.0019 | 1.00428 | 0.991824 | 0.9584 |
| 7 | 0.234558 | 2.61288 | 1.01111 | 1.00449 | 0.988523 | 0.950866 |
| 8 | 0.23827 | 2.61019 | 1.00189 | 0.990903 | 0.982733 | 0.951139 |
| 9 | 0.248539 | 2.6048 | 0.99651 | 0.99302 | 0.985104 | 0.966993 |
| 10 | 0.296983 | 2.59941 | 1 | 1 | 1 | 1 |
| 11 | 0.677267 | 2.59403 | 1.01588 | 1.00836 | 1.05311 | 1.11004 |
| 12 | 0.834236 | 2.59133 | 1.14695 | 1.1819 | 1.16388 | 1.36445 |
| 13 | 0.868128 | 2.59537 | 1.17722 | 1.23213 | 1.22272 | 1.45633 |
| 14 | 0.950462 | 2.59672 | 1.21297 | 1.07351 | 1.30511 | 1.67668 |
| 15 | 1.09764 | 2.59403 | 1.22846 | 1.08683 | 1.34095 | 1.40059 |
| 16 | 1.11214 | 2.5846 | 1.24153 | 1.10031 | 1.37704 | 1.48291 |
| 17 | 1.16623 | 2.57517 | 1.24097 | 1.08177 | 1.40313 | 1.41811 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Pose span expands strongly from k10 to k35 (3.927x camera-center bbox diag), so later-slot view span is the strongest current suspect.
- Depth p95 changes by 0.991x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.24097, minor=1.08177, conf_threshold=1.21951, valid_delta=4.93816e-05.
- npz_streaming_style: k35/k10 bbox=1.40313, minor=1.41811, conf_threshold=0.898756, valid_delta=0.0315119.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
