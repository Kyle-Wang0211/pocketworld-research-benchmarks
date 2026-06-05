# window_007 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.730907`
- k10 pose diag: `0.734994`
- k35 pose diag: `0.907075`
- k35/k10 pose diag: `1.23413`
- k10 depth p95: `1.79972`
- k35 depth p95: `1.86786`
- k35/k10 depth p95: `1.03786`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.04587 | 0.692348 | 0.937075 | -0.000132606 |
| npz_streaming_style | - | - | - | 0.987396 | 0.96896 | 0.998372 | -0.0216556 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.84515 | 0.88569 | 0.763843 | 0.999936 | 0.960138 |
| 2 | 0.456036 | 1.81976 | 0.996997 | 0.772933 | 1.02722 | 0.934843 |
| 3 | 0.517537 | 1.79171 | 1.09459 | 0.793409 | 1.03587 | 0.896324 |
| 4 | 0.547593 | 1.78235 | 1.1844 | 0.794349 | 1.0392 | 0.886434 |
| 5 | 0.613935 | 1.7583 | 1.18529 | 0.840695 | 1.04105 | 0.955374 |
| 6 | 0.622657 | 1.73693 | 1.13425 | 0.836377 | 1.0229 | 1.02155 |
| 7 | 0.622657 | 1.73292 | 1.00085 | 0.94806 | 1.01403 | 1.01514 |
| 8 | 0.622657 | 1.7396 | 0.981367 | 1.03175 | 1.00811 | 1.00123 |
| 9 | 0.665299 | 1.76231 | 0.981104 | 1.01428 | 1.00241 | 0.995614 |
| 10 | 0.734994 | 1.79972 | 1 | 1 | 1 | 1 |
| 11 | 0.760219 | 1.81442 | 1.00886 | 0.994803 | 0.996095 | 0.928602 |
| 12 | 0.780728 | 1.82244 | 1.00989 | 0.902386 | 0.993391 | 0.906612 |
| 13 | 0.804497 | 1.83045 | 1.00682 | 0.91378 | 0.988822 | 0.904676 |
| 14 | 0.836167 | 1.84248 | 1.00714 | 0.818313 | 0.990715 | 0.90305 |
| 15 | 0.847017 | 1.85584 | 1.02081 | 0.765302 | 0.985857 | 0.943741 |
| 16 | 0.848804 | 1.86786 | 1.04349 | 0.712572 | 0.984747 | 0.910782 |
| 17 | 0.907075 | 1.86786 | 1.04587 | 0.692348 | 0.987396 | 0.96896 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.038x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.04587, minor=0.692348, conf_threshold=0.937075, valid_delta=-0.000132606.
- npz_streaming_style: k35/k10 bbox=0.987396, minor=0.96896, conf_threshold=0.998372, valid_delta=-0.0216556.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
