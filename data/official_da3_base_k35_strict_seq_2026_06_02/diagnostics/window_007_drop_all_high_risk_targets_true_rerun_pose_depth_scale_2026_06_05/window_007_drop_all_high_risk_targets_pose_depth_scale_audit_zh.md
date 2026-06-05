# window_007_drop_all_high_risk_targets Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.682571`
- k10 pose diag: `0.79443`
- k35 pose diag: `0.839269`
- k35/k10 pose diag: `1.05644`
- k10 depth p95: `1.84562`
- k35 depth p95: `1.89999`
- k35/k10 depth p95: `1.02946`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.00368 | 1.00065 | 0.990783 | -4.79582e-05 |
| npz_streaming_style | - | - | - | 1.00192 | 1.02108 | 0.997383 | -0.0058883 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.85707 | 0.80079 | 1.02385 | 0.980086 | 0.967581 |
| 2 | 0.517537 | 1.79268 | 1.04222 | 1.08674 | 1.00849 | 0.939089 |
| 3 | 0.547593 | 1.7655 | 1.04257 | 1.04021 | 1.00001 | 0.907369 |
| 4 | 0.609595 | 1.73116 | 1.02325 | 1.12501 | 0.989323 | 0.914255 |
| 5 | 0.609595 | 1.72973 | 1.00583 | 1.1283 | 0.988697 | 0.926028 |
| 6 | 0.609595 | 1.74118 | 0.995212 | 1.05048 | 0.985135 | 0.930365 |
| 7 | 0.723961 | 1.80413 | 0.999908 | 0.962029 | 0.983646 | 0.956933 |
| 8 | 0.749558 | 1.82845 | 1.00318 | 0.976004 | 0.995169 | 0.973179 |
| 9 | 0.770351 | 1.83704 | 1.00106 | 0.989099 | 0.99858 | 0.989635 |
| 10 | 0.79443 | 1.84562 | 1 | 1 | 1 | 1 |
| 11 | 0.826486 | 1.86279 | 0.999038 | 1.00101 | 1.00333 | 1.01269 |
| 12 | 0.837462 | 1.88282 | 0.997839 | 0.992777 | 0.998924 | 1.01618 |
| 13 | 0.839269 | 1.89999 | 1.00368 | 1.00065 | 1.00192 | 1.02108 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.029x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.00368, minor=1.00065, conf_threshold=0.990783, valid_delta=-4.79582e-05.
- npz_streaming_style: k35/k10 bbox=1.00192, minor=1.02108, conf_threshold=0.997383, valid_delta=-0.0058883.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
