# window_006 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.877487`
- k10 pose diag: `0.912316`
- k35 pose diag: `1.24442`
- k35/k10 pose diag: `1.36402`
- k10 depth p95: `1.65378`
- k35 depth p95: `1.86078`
- k35/k10 depth p95: `1.12517`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | k=14 (1.1034) | - | - | 1.13923 | 0.941912 | 0.788791 | 1.88366e-05 |
| npz_streaming_style | - | k=17 (1.10228) | - | 1.04525 | 1.10228 | 0.811469 | -0.0119372 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.14903 | 1.16894 | 1.03529 | 1.00838 | 1.03401 |
| 2 | 0.393883 | 1.87859 | 0.864056 | 0.932904 | 0.947257 | 1.24816 |
| 3 | 0.404763 | 1.70943 | 0.837487 | 0.833085 | 0.930876 | 1.0659 |
| 4 | 0.440967 | 1.63597 | 0.914239 | 0.888008 | 0.976145 | 0.994026 |
| 5 | 0.452337 | 1.60036 | 0.92236 | 0.86952 | 0.978892 | 0.985462 |
| 6 | 0.452337 | 1.58923 | 0.925789 | 0.864104 | 0.98858 | 0.982817 |
| 7 | 0.6095 | 1.58589 | 0.945935 | 0.933153 | 0.99865 | 0.996111 |
| 8 | 0.651185 | 1.59146 | 0.969646 | 0.975316 | 0.998172 | 0.996306 |
| 9 | 0.877015 | 1.62262 | 0.988556 | 1.00149 | 0.998061 | 1.00213 |
| 10 | 0.912316 | 1.65378 | 1 | 1 | 1 | 1 |
| 11 | 1.03136 | 1.72167 | 1.02138 | 0.9728 | 1.00612 | 1.00041 |
| 12 | 1.03443 | 1.77398 | 1.03618 | 0.954434 | 1.01491 | 1.03921 |
| 13 | 1.15168 | 1.81293 | 1.04621 | 0.935801 | 1.0247 | 1.04131 |
| 14 | 1.18401 | 1.82739 | 1.1034 | 0.933324 | 1.03002 | 1.05399 |
| 15 | 1.2427 | 1.84075 | 1.12969 | 0.933716 | 1.0377 | 1.07257 |
| 16 | 1.24442 | 1.8452 | 1.13981 | 0.940082 | 1.04077 | 1.08751 |
| 17 | 1.24442 | 1.86078 | 1.13923 | 0.941912 | 1.04525 | 1.10228 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 1.125x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.13923, minor=0.941912, conf_threshold=0.788791, valid_delta=1.88366e-05.
- npz_streaming_style: k35/k10 bbox=1.04525, minor=1.10228, conf_threshold=0.811469, valid_delta=-0.0119372.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
