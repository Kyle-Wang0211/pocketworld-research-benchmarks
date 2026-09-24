# window_016_segment_from_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.846465`
- k10 pose diag: `0.547286`
- k35 pose diag: `0.547286`
- k35/k10 pose diag: `1`
- k10 depth p95: `2.18971`
- k35 depth p95: `2.18971`
- k35/k10 depth p95: `1`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1 | 1 | 1 | 0 |
| npz_streaming_style | - | - | - | 1 | 1 | 1 | 0 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.09396 | 0.792999 | 0.952742 | 0.832752 | 1.04984 |
| 2 | 0.17146 | 2.14472 | 0.846702 | 1.06584 | 0.862234 | 0.90488 |
| 3 | 0.194142 | 2.18279 | 0.852894 | 1.01034 | 0.901331 | 0.878524 |
| 4 | 0.276889 | 2.21971 | 0.899789 | 0.999045 | 0.930037 | 0.90945 |
| 5 | 0.460925 | 2.22779 | 0.943684 | 1.02795 | 0.972337 | 0.97004 |
| 6 | 0.479747 | 2.20356 | 0.982986 | 1.03275 | 0.996976 | 1.05928 |
| 7 | 0.547286 | 2.18971 | 1 | 1 | 1 | 1 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.000x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- npz_streaming_style: k35/k10 bbox=1, minor=1, conf_threshold=1, valid_delta=0.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
