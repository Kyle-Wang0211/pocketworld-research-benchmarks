# window_016_drop_all_high_risk_targets Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.753712`
- k10 pose diag: `0.296983`
- k35 pose diag: `1.11365`
- k35/k10 pose diag: `3.74986`
- k10 depth p95: `2.42809`
- k35 depth p95: `2.42938`
- k35/k10 depth p95: `1.00053`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.06943 | 1.00279 | 0.95667 | 7.64457e-05 |
| npz_streaming_style | k=12 (1.10203) | - | - | 1.10203 | 1.05055 | 0.935779 | -0.000392421 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.39181 | 1.01388 | 0.941186 | 1.14649 | 1.09029 |
| 2 | 0.188339 | 2.3931 | 0.986499 | 0.950203 | 1.12146 | 1.13227 |
| 3 | 0.208832 | 2.40217 | 0.8666 | 0.801856 | 1.03611 | 0.962714 |
| 4 | 0.218697 | 2.42031 | 0.869603 | 0.816949 | 1.01215 | 0.955093 |
| 5 | 0.230252 | 2.44104 | 0.990261 | 0.982638 | 1.01449 | 0.960951 |
| 6 | 0.232752 | 2.454 | 1.02109 | 1.00861 | 1.00133 | 0.92506 |
| 7 | 0.234558 | 2.45659 | 1.03102 | 1.01366 | 0.989592 | 0.9259 |
| 8 | 0.23827 | 2.45141 | 1.02011 | 0.999949 | 0.984101 | 0.917943 |
| 9 | 0.248539 | 2.43845 | 1.00689 | 0.99636 | 0.986164 | 0.9585 |
| 10 | 0.296983 | 2.42809 | 1 | 1 | 1 | 1 |
| 11 | 0.860389 | 2.42809 | 1.00826 | 0.980236 | 1.04587 | 1.03111 |
| 12 | 1.11365 | 2.42938 | 1.06943 | 1.00279 | 1.10203 | 1.05055 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Pose span expands strongly from k10 to k35 (3.750x camera-center bbox diag), so later-slot view span is the strongest current suspect.
- Depth p95 changes by 1.001x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.06943, minor=1.00279, conf_threshold=0.95667, valid_delta=7.64457e-05.
- npz_streaming_style: k35/k10 bbox=1.10203, minor=1.05055, conf_threshold=0.935779, valid_delta=-0.000392421.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
