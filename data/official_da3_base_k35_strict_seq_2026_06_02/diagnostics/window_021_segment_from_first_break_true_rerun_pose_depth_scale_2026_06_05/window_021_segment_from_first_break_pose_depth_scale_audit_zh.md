# window_021_segment_from_first_break Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.682948`
- k10 pose diag: `0.745745`
- k35 pose diag: `1.12755`
- k35/k10 pose diag: `1.51197`
- k10 depth p95: `2.38082`
- k35 depth p95: `2.35222`
- k35/k10 depth p95: `0.987988`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | k=12 (1.1151) | - | 1.03001 | 1.07012 | 1.03405 | 0.00015337 |
| npz_streaming_style | - | - | - | 1.00756 | 0.97948 | 1.02414 | -0.00325463 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.9261 | 0.584073 | 0.676485 | 0.765867 | 0.713392 |
| 2 | 0.541211 | 2.06195 | 0.714322 | 0.824304 | 0.855846 | 0.735785 |
| 3 | 0.549075 | 2.09912 | 0.754301 | 0.892841 | 0.913831 | 0.750595 |
| 4 | 0.581487 | 2.12772 | 0.810545 | 0.895534 | 0.921974 | 0.775333 |
| 5 | 0.722919 | 2.31933 | 0.892546 | 0.915089 | 0.941687 | 0.802706 |
| 6 | 0.732873 | 2.39226 | 0.92943 | 0.941619 | 0.94926 | 0.854646 |
| 7 | 0.745745 | 2.42372 | 0.960003 | 0.971646 | 1.00345 | 1.0018 |
| 8 | 0.745745 | 2.40656 | 0.970539 | 0.96799 | 0.986228 | 0.976139 |
| 9 | 0.745745 | 2.39512 | 0.986315 | 0.977981 | 0.995986 | 0.990103 |
| 10 | 0.745745 | 2.38082 | 1 | 1 | 1 | 1 |
| 11 | 0.745745 | 2.36509 | 1.00965 | 1.01834 | 1.0071 | 0.995459 |
| 12 | 0.927982 | 2.36366 | 1.03282 | 1.1151 | 1.02786 | 1.02616 |
| 13 | 1.12755 | 2.35222 | 1.03001 | 1.07012 | 1.00756 | 0.97948 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.988x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.03001, minor=1.07012, conf_threshold=1.03405, valid_delta=0.00015337.
- npz_streaming_style: k35/k10 bbox=1.00756, minor=0.97948, conf_threshold=1.02414, valid_delta=-0.00325463.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
