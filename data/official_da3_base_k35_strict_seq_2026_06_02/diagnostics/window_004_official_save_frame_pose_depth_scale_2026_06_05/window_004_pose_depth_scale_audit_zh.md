# window_004 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.699451`
- k10 pose diag: `0.554833`
- k35 pose diag: `0.759997`
- k35/k10 pose diag: `1.36978`
- k10 depth p95: `2.25065`
- k35 depth p95: `2.11103`
- k35/k10 depth p95: `0.937965`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 0.996888 | 0.983051 | 1.04052 | 0.000318757 |
| npz_streaming_style | - | - | - | 0.977369 | 0.99874 | 1.01027 | 0.0398442 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.38468 | 0.890043 | 1.05897 | 0.796964 | 1.01784 |
| 2 | 0.0789004 | 2.39585 | 0.894445 | 1.01712 | 0.828903 | 1.03827 |
| 3 | 0.3452 | 2.36793 | 0.992886 | 0.983557 | 0.988999 | 1.00869 |
| 4 | 0.357431 | 2.35536 | 1.01276 | 0.978978 | 1.0134 | 0.995956 |
| 5 | 0.381765 | 2.34 | 1.01963 | 0.97784 | 1.01885 | 0.999445 |
| 6 | 0.403852 | 2.33163 | 1.02087 | 0.982501 | 1.01143 | 0.998934 |
| 7 | 0.424678 | 2.30231 | 0.998354 | 0.981451 | 1.00202 | 0.987459 |
| 8 | 0.550747 | 2.28276 | 0.997874 | 0.992603 | 0.993258 | 0.992056 |
| 9 | 0.553512 | 2.27159 | 0.996383 | 1.00244 | 0.993779 | 0.996424 |
| 10 | 0.554833 | 2.25065 | 1 | 1 | 1 | 1 |
| 11 | 0.574542 | 2.22831 | 1.00539 | 0.994889 | 0.998751 | 0.997678 |
| 12 | 0.658693 | 2.20457 | 1.01143 | 0.99642 | 1.00772 | 0.998703 |
| 13 | 0.675127 | 2.18363 | 1.01499 | 0.99337 | 1.00289 | 0.999137 |
| 14 | 0.749066 | 2.16129 | 1.00876 | 0.99112 | 0.999934 | 0.998016 |
| 15 | 0.759997 | 2.14175 | 1.00229 | 0.991293 | 0.990489 | 0.995925 |
| 16 | 0.759997 | 2.12639 | 0.998329 | 0.985947 | 0.98523 | 0.995913 |
| 17 | 0.759997 | 2.11103 | 0.996888 | 0.983051 | 0.977369 | 0.99874 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.938x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=0.996888, minor=0.983051, conf_threshold=1.04052, valid_delta=0.000318757.
- npz_streaming_style: k35/k10 bbox=0.977369, minor=0.99874, conf_threshold=1.01027, valid_delta=0.0398442.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
