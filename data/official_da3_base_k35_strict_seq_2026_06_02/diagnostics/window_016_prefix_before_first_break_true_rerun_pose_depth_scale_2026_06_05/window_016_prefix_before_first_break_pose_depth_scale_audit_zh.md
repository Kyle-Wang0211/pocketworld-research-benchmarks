# window_016_prefix_before_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.713096`
- k10 pose diag: `0.296983`
- k35 pose diag: `0.296983`
- k35/k10 pose diag: `1`
- k10 depth p95: `2.42122`
- k35 depth p95: `2.42122`
- k35/k10 depth p95: `1`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1 | 1 | 1 | 0 |
| npz_streaming_style | - | - | - | 1 | 1 | 1 | 0 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.39931 | 1.13921 | 1.13358 | 1.10699 | 1.21141 |
| 2 | 0.188339 | 2.40753 | 1.1102 | 1.0329 | 1.08098 | 1.18771 |
| 3 | 0.208832 | 2.41026 | 0.965644 | 0.925213 | 1.00826 | 0.952274 |
| 4 | 0.218697 | 2.41848 | 0.958222 | 0.914526 | 0.998781 | 0.950008 |
| 5 | 0.230252 | 2.43491 | 0.985783 | 0.925517 | 0.998116 | 0.954565 |
| 6 | 0.232752 | 2.44313 | 1.00458 | 0.953924 | 1.03761 | 1.03909 |
| 7 | 0.234558 | 2.44313 | 1.10956 | 1.04693 | 0.99446 | 0.956402 |
| 8 | 0.23827 | 2.44313 | 1.00565 | 0.983547 | 0.991019 | 0.953498 |
| 9 | 0.248539 | 2.43218 | 0.994194 | 0.969687 | 0.983898 | 0.957726 |
| 10 | 0.296983 | 2.42122 | 1 | 1 | 1 | 1 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.000x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- npz_streaming_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
