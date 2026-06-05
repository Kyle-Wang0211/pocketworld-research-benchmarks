# window_006_segment_from_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `1.05893`
- k10 pose diag: `0.696645`
- k35 pose diag: `0.920277`
- k35/k10 pose diag: `1.32101`
- k10 depth p95: `1.62126`
- k35 depth p95: `1.69688`
- k35/k10 depth p95: `1.04664`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.05703 | 0.926453 | 0.847222 | -0.000195149 |
| npz_streaming_style | - | - | - | 1.0238 | 1.03002 | 0.844493 | 0.00800432 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.39071 | 0.680854 | 0.429576 | 0.739514 | 0.939083 |
| 2 | 0.0229488 | 1.41284 | 0.696848 | 0.436456 | 0.772229 | 0.979797 |
| 3 | 0.229269 | 1.40546 | 0.786821 | 0.554469 | 0.864407 | 1.15363 |
| 4 | 0.233152 | 1.39993 | 0.812252 | 0.581221 | 0.891454 | 1.07406 |
| 5 | 0.233152 | 1.41007 | 0.825387 | 0.611463 | 0.916046 | 1.00908 |
| 6 | 0.312272 | 1.43313 | 0.862673 | 0.706641 | 0.93635 | 1.03833 |
| 7 | 0.346253 | 1.45526 | 0.897229 | 0.788845 | 0.953675 | 1.04759 |
| 8 | 0.548283 | 1.50967 | 0.936954 | 0.874149 | 0.973505 | 1.02328 |
| 9 | 0.582094 | 1.55486 | 0.966492 | 0.932234 | 0.987783 | 1.00925 |
| 10 | 0.696645 | 1.62126 | 1 | 1 | 1 | 1 |
| 11 | 0.701954 | 1.68028 | 1.02764 | 1.00977 | 1.00492 | 0.996494 |
| 12 | 0.82182 | 1.7098 | 1.03962 | 0.975643 | 1.01303 | 1.00307 |
| 13 | 0.861547 | 1.70518 | 1.04478 | 0.939241 | 1.01371 | 1.00213 |
| 14 | 0.91795 | 1.69873 | 1.05091 | 0.933342 | 1.02043 | 1.01617 |
| 15 | 0.920277 | 1.6932 | 1.05554 | 0.930134 | 1.01881 | 1.01989 |
| 16 | 0.920277 | 1.69688 | 1.05703 | 0.926453 | 1.0238 | 1.03002 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.047x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.05703, minor=0.926453, conf_threshold=0.847222, valid_delta=-0.000195149.
- npz_streaming_style: k35/k10 bbox=1.0238, minor=1.03002, conf_threshold=0.844493, valid_delta=0.00800432.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
