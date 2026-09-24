# window_021_drop_all_high_risk_targets Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.640864`
- k10 pose diag: `1.31226`
- k35 pose diag: `1.31226`
- k35/k10 pose diag: `1`
- k10 depth p95: `2.10592`
- k35 depth p95: `2.08306`
- k35/k10 depth p95: `0.989146`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.998424 | 1.01011 | 1.01477 | 7.59266e-05 |
| npz_streaming_style | - | - | - | 0.989674 | 0.977603 | 1.02419 | 0.0107605 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.01449 | 0.89404 | 0.70298 | 0.885431 | 0.736738 |
| 2 | 0.041044 | 1.99925 | 0.892374 | 0.768219 | 0.892301 | 0.772182 |
| 3 | 0.0615465 | 1.98706 | 0.882745 | 0.752237 | 0.896085 | 0.762999 |
| 4 | 0.0623739 | 1.97487 | 0.873502 | 0.754261 | 0.884372 | 0.748576 |
| 5 | 1.19821 | 1.97792 | 0.919618 | 0.956777 | 0.953433 | 0.909826 |
| 6 | 1.21608 | 1.98859 | 0.935971 | 0.903598 | 0.962558 | 0.949181 |
| 7 | 1.29823 | 2.04497 | 0.964944 | 0.929122 | 0.989056 | 0.986168 |
| 8 | 1.30432 | 2.08611 | 0.984068 | 0.950055 | 1.0002 | 1.00741 |
| 9 | 1.31226 | 2.12116 | 0.995785 | 0.973908 | 1.00538 | 1.00387 |
| 10 | 1.31226 | 2.10592 | 1 | 1 | 1 | 1 |
| 11 | 1.31226 | 2.09373 | 1.00221 | 1.01077 | 0.993282 | 1.00291 |
| 12 | 1.31226 | 2.08306 | 0.998424 | 1.01011 | 0.989674 | 0.977603 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.989x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.998424, minor=1.01011, conf_threshold=1.01477, valid_delta=7.59266e-05.
- npz_streaming_style: k35/k10 bbox=0.989674, minor=0.977603, conf_threshold=1.02419, valid_delta=0.0107605.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
