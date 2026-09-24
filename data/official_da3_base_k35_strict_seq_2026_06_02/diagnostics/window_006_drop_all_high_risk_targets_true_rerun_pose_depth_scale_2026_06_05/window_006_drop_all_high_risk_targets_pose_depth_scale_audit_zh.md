# window_006_drop_all_high_risk_targets Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.939552`
- k10 pose diag: `1.24004`
- k35 pose diag: `1.24004`
- k35/k10 pose diag: `1`
- k10 depth p95: `1.58195`
- k35 depth p95: `1.58195`
- k35/k10 depth p95: `1`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.99445 | 0.998989 | 0.993133 | -5.65235e-05 |
| npz_streaming_style | - | - | - | 0.994379 | 0.991475 | 0.980765 | 0.00209837 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.88754 | 1.00177 | 1.11789 | 0.958193 | 0.952836 |
| 2 | 0.398743 | 1.68797 | 0.770236 | 0.96941 | 0.932817 | 0.999927 |
| 3 | 0.433795 | 1.57988 | 0.810168 | 0.9892 | 0.959067 | 0.939245 |
| 4 | 0.644508 | 1.55805 | 0.860053 | 1.10077 | 0.949324 | 0.982651 |
| 5 | 0.907415 | 1.59858 | 0.905741 | 1.01959 | 0.953286 | 0.994418 |
| 6 | 1.02959 | 1.62769 | 0.996482 | 0.980938 | 0.966642 | 1.01477 |
| 7 | 1.14715 | 1.63185 | 1.01295 | 0.987346 | 0.970064 | 1.00412 |
| 8 | 1.17943 | 1.60898 | 1.00889 | 0.991313 | 0.983723 | 1.01174 |
| 9 | 1.23832 | 1.59443 | 1.00663 | 0.998955 | 0.986612 | 1.00326 |
| 10 | 1.24004 | 1.58195 | 1 | 1 | 1 | 1 |
| 11 | 1.24004 | 1.58195 | 0.99445 | 0.998989 | 0.994379 | 0.991475 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.000x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.99445, minor=0.998989, conf_threshold=0.993133, valid_delta=-5.65235e-05.
- npz_streaming_style: k35/k10 bbox=0.994379, minor=0.991475, conf_threshold=0.980765, valid_delta=0.00209837.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
