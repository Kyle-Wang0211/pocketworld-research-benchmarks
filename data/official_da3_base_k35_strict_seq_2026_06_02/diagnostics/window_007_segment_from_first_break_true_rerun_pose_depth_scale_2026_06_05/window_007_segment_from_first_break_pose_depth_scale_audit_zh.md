# window_007_segment_from_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.730311`
- k10 pose diag: `0.759879`
- k35 pose diag: `0.906761`
- k35/k10 pose diag: `1.1933`
- k10 depth p95: `2.00311`
- k35 depth p95: `2.06061`
- k35/k10 depth p95: `1.0287`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.04829 | 0.963742 | 0.888537 | 7.43222e-06 |
| npz_streaming_style | - | - | - | 0.988979 | 1.00592 | 0.955033 | -0.02047 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.00712 | 0.859986 | 0.758858 | 0.973457 | 1.01459 |
| 2 | 0.0624634 | 1.97235 | 0.869766 | 0.760138 | 0.982365 | 1.0223 |
| 3 | 0.0934724 | 1.94962 | 0.882494 | 0.751462 | 0.976145 | 1.00445 |
| 4 | 0.459217 | 1.90549 | 0.946007 | 0.87094 | 0.981025 | 1.04866 |
| 5 | 0.482291 | 1.8734 | 0.948273 | 0.99682 | 0.980068 | 1.04889 |
| 6 | 0.557355 | 1.88009 | 0.936929 | 1.00332 | 0.991706 | 1.02051 |
| 7 | 0.581361 | 1.89881 | 0.932473 | 1.00384 | 0.99761 | 1.017 |
| 8 | 0.665066 | 1.9309 | 0.94546 | 1.01115 | 0.994283 | 1.01255 |
| 9 | 0.734691 | 1.99241 | 0.981948 | 1.02734 | 1.00188 | 1.00871 |
| 10 | 0.759879 | 2.00311 | 1 | 1 | 1 | 1 |
| 11 | 0.780363 | 2.00444 | 1.00458 | 0.996117 | 0.996504 | 1.00217 |
| 12 | 0.804143 | 2.00846 | 1.00543 | 1.00118 | 1.00163 | 1.00327 |
| 13 | 0.835826 | 2.02317 | 1.01202 | 0.997412 | 0.994561 | 1.00515 |
| 14 | 0.846681 | 2.03654 | 1.02931 | 0.985003 | 0.994605 | 1.00147 |
| 15 | 0.848469 | 2.05125 | 1.05175 | 0.938949 | 0.995435 | 1.00464 |
| 16 | 0.906761 | 2.06061 | 1.04829 | 0.963742 | 0.988979 | 1.00592 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.029x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.04829, minor=0.963742, conf_threshold=0.888537, valid_delta=7.43222e-06.
- npz_streaming_style: k35/k10 bbox=0.988979, minor=1.00592, conf_threshold=0.955033, valid_delta=-0.02047.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
