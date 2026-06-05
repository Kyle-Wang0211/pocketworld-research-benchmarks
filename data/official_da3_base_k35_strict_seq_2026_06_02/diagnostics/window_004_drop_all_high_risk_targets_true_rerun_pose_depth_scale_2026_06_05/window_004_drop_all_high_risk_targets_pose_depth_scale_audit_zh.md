# window_004_drop_all_high_risk_targets Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.702537`
- k10 pose diag: `0.748705`
- k35 pose diag: `0.759641`
- k35/k10 pose diag: `1.01461`
- k10 depth p95: `2.0823`
- k35 depth p95: `2.05728`
- k35/k10 depth p95: `0.987984`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.991216 | 0.996482 | 1.01505 | -4.14402e-05 |
| npz_streaming_style | - | - | - | 0.995707 | 0.995864 | 1.00419 | 0.00976368 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.29914 | 0.877676 | 0.960538 | 0.754124 | 0.905536 |
| 2 | 0.0789004 | 2.28802 | 0.903001 | 0.937965 | 0.811643 | 0.889114 |
| 3 | 0.348951 | 2.2491 | 1.06893 | 1.02125 | 1.02828 | 0.99009 |
| 4 | 0.373837 | 2.2213 | 1.03923 | 1.00373 | 1.04249 | 1.00113 |
| 5 | 0.413561 | 2.19628 | 1.0021 | 1.00239 | 1.01792 | 0.990421 |
| 6 | 0.550497 | 2.17404 | 1.00018 | 1.0182 | 1.01462 | 1.00276 |
| 7 | 0.554833 | 2.1518 | 1.00742 | 1.01233 | 1.01331 | 1.00986 |
| 8 | 0.574542 | 2.12817 | 1.01321 | 1.00767 | 1.00746 | 1.01027 |
| 9 | 0.658693 | 2.10732 | 1.01086 | 1.00501 | 1.00917 | 1.01326 |
| 10 | 0.748705 | 2.0823 | 1 | 1 | 1 | 1 |
| 11 | 0.759641 | 2.05728 | 0.991216 | 0.996482 | 0.995707 | 0.995864 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.988x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.991216, minor=0.996482, conf_threshold=1.01505, valid_delta=-4.14402e-05.
- npz_streaming_style: k35/k10 bbox=0.995707, minor=0.995864, conf_threshold=1.00419, valid_delta=0.00976368.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
