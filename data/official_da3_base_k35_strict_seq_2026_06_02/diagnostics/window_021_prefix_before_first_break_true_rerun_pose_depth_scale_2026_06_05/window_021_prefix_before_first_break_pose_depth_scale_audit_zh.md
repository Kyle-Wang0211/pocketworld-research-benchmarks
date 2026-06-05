# window_021_prefix_before_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `1.09062`
- k10 pose diag: `0.0623739`
- k35 pose diag: `0.0623739`
- k35/k10 pose diag: `1`
- k10 depth p95: `1.45236`
- k35 depth p95: `1.45236`
- k35/k10 depth p95: `1`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1 | 1 | 1 | 0 |
| npz_streaming_style | - | - | - | 1 | 1 | 1 | 0 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.46221 | 1.01012 | 1.02414 | 1.00585 | 1.04415 |
| 2 | 0.041044 | 1.45684 | 1.01727 | 1.08216 | 1.01132 | 0.995963 |
| 3 | 0.0615465 | 1.45057 | 0.999459 | 1.00542 | 1.0104 | 1.00684 |
| 4 | 0.0623739 | 1.45236 | 1 | 1 | 1 | 1 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.000x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- npz_streaming_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
