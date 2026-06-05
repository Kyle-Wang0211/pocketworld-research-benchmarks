# window_004_segment_from_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.677259`
- k10 pose diag: `0.394759`
- k35 pose diag: `0.501547`
- k35/k10 pose diag: `1.27052`
- k10 depth p95: `2.10378`
- k35 depth p95: `2.0014`
- k35/k10 depth p95: `0.951337`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.976968 | 0.914951 | 1.04812 | -0.000108817 |
| npz_streaming_style | - | - | - | 0.984543 | 0.967755 | 1.02742 | 0.0201732 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.33016 | 1.0013 | 1.08576 | 0.963929 | 1.02408 |
| 2 | 0.0246741 | 2.34602 | 0.997075 | 1.08746 | 0.979014 | 1.02577 |
| 3 | 0.0766898 | 2.34026 | 0.995534 | 1.09242 | 0.975043 | 1.02553 |
| 4 | 0.124197 | 2.35035 | 0.998109 | 1.08055 | 0.972855 | 1.01872 |
| 5 | 0.150317 | 2.26383 | 1.00459 | 1.05068 | 0.981045 | 0.99532 |
| 6 | 0.293092 | 2.22346 | 0.996244 | 1.04792 | 0.983212 | 0.997054 |
| 7 | 0.29657 | 2.20327 | 0.990132 | 1.04266 | 0.981939 | 0.999057 |
| 8 | 0.297521 | 2.16146 | 0.995135 | 1.03248 | 0.989863 | 1.00252 |
| 9 | 0.313881 | 2.13262 | 0.996754 | 1.0227 | 0.998774 | 0.998906 |
| 10 | 0.394759 | 2.10378 | 1 | 1 | 1 | 1 |
| 11 | 0.411406 | 2.07927 | 0.998267 | 0.984229 | 1.00253 | 1.00374 |
| 12 | 0.489729 | 2.05908 | 0.993391 | 0.957967 | 1.00296 | 0.989388 |
| 13 | 0.501547 | 2.03889 | 0.985417 | 0.93662 | 0.999267 | 0.984213 |
| 14 | 0.501547 | 2.02015 | 0.979339 | 0.922142 | 0.990129 | 0.975811 |
| 15 | 0.501547 | 2.0014 | 0.976968 | 0.914951 | 0.984543 | 0.967755 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.951x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.976968, minor=0.914951, conf_threshold=1.04812, valid_delta=-0.000108817.
- npz_streaming_style: k35/k10 bbox=0.984543, minor=0.967755, conf_threshold=1.02742, valid_delta=0.0201732.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
