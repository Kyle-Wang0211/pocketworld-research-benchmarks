# window_017 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.694219`
- k10 pose diag: `0.561336`
- k35 pose diag: `0.858428`
- k35/k10 pose diag: `1.52926`
- k10 depth p95: `2.84436`
- k35 depth p95: `3.38735`
- k35/k10 depth p95: `1.1909`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.978295 | 0.976838 | 0.969652 | 8.02763e-06 |
| npz_streaming_style | - | - | - | 0.948132 | 0.969549 | 1.03026 | -0.0388286 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.19306 | 0.994595 | 1.00468 | 1.01359 | 1.06728 |
| 2 | 0.000997828 | 2.20009 | 0.990091 | 0.964794 | 1.00053 | 1.06727 |
| 3 | 0.00254494 | 2.19728 | 0.989314 | 0.932035 | 0.995812 | 1.07053 |
| 4 | 0.00411531 | 2.19446 | 0.983076 | 0.91267 | 0.993791 | 1.07004 |
| 5 | 0.28122 | 2.14804 | 0.989244 | 0.918635 | 1.00918 | 1.05737 |
| 6 | 0.290155 | 2.10443 | 0.987678 | 0.922163 | 1.01145 | 1.01894 |
| 7 | 0.290155 | 2.05661 | 0.988191 | 0.951237 | 1.00717 | 1.0203 |
| 8 | 0.434021 | 2.307 | 1.00999 | 1.01758 | 1.01141 | 1.00509 |
| 9 | 0.534199 | 2.48424 | 1.00003 | 0.996366 | 1.00436 | 0.993423 |
| 10 | 0.561336 | 2.84436 | 1 | 1 | 1 | 1 |
| 11 | 0.608456 | 3.05537 | 0.992832 | 0.982763 | 0.989965 | 0.99831 |
| 12 | 0.677726 | 3.21011 | 0.991022 | 0.97762 | 0.983578 | 0.986227 |
| 13 | 0.682851 | 3.28607 | 0.989072 | 0.976563 | 0.9775 | 0.974938 |
| 14 | 0.701059 | 3.31983 | 0.986611 | 0.97297 | 0.971054 | 0.973133 |
| 15 | 0.749361 | 3.34796 | 0.983399 | 0.972613 | 0.958227 | 0.983591 |
| 16 | 0.834206 | 3.3761 | 0.981248 | 0.974695 | 0.964454 | 0.961139 |
| 17 | 0.858428 | 3.38735 | 0.978295 | 0.976838 | 0.948132 | 0.969549 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.191x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.978295, minor=0.976838, conf_threshold=0.969652, valid_delta=8.02763e-06.
- npz_streaming_style: k35/k10 bbox=0.948132, minor=0.969549, conf_threshold=1.03026, valid_delta=-0.0388286.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
