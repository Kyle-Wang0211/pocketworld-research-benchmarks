# window_021 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.646629`
- k10 pose diag: `1.31117`
- k35 pose diag: `1.37553`
- k35/k10 pose diag: `1.04908`
- k10 depth p95: `2.16266`
- k35 depth p95: `2.1536`
- k35/k10 depth p95: `0.99581`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | - | - | - | 1.06207 | 1.0578 | 0.914798 | 0.00023017 |
| npz_streaming_style | - | - | - | 1.02132 | 0.984423 | 0.970325 | -0.0114201 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.06902 | 0.87071 | 0.757673 | 0.942019 | 1.09569 |
| 2 | 0.041044 | 2.06902 | 0.849664 | 0.773837 | 0.924461 | 1.04709 |
| 3 | 0.0615465 | 2.06298 | 0.846351 | 0.795856 | 0.925452 | 1.05415 |
| 4 | 0.0623739 | 2.05845 | 0.838997 | 0.795505 | 0.90985 | 1.02794 |
| 5 | 0.745633 | 2.03278 | 0.845888 | 0.994208 | 0.94659 | 1.04574 |
| 6 | 1.20137 | 2.03882 | 0.876289 | 1.08067 | 0.970284 | 1.0082 |
| 7 | 1.20566 | 2.04486 | 0.892109 | 1.15587 | 0.989536 | 0.985549 |
| 8 | 1.22342 | 2.05845 | 0.918194 | 1.13247 | 0.991317 | 0.98081 |
| 9 | 1.30511 | 2.11735 | 0.968657 | 0.966944 | 0.994539 | 0.993253 |
| 10 | 1.31117 | 2.16266 | 1 | 1 | 1 | 1 |
| 11 | 1.31907 | 2.20796 | 1.02181 | 1.01541 | 1.00653 | 1.01121 |
| 12 | 1.31907 | 2.19588 | 1.03386 | 1.02409 | 1.00804 | 1.00459 |
| 13 | 1.31907 | 2.18531 | 1.0406 | 1.02822 | 1.00662 | 0.993283 |
| 14 | 1.31907 | 2.17474 | 1.04853 | 1.04242 | 1.01291 | 0.999049 |
| 15 | 1.31907 | 2.16568 | 1.0547 | 1.05935 | 1.02119 | 0.987135 |
| 16 | 1.33205 | 2.15964 | 1.06574 | 1.08365 | 1.03073 | 0.996244 |
| 17 | 1.37553 | 2.1536 | 1.06207 | 1.0578 | 1.02132 | 0.984423 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Depth p95 changes by 0.996x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.06207, minor=1.0578, conf_threshold=0.914798, valid_delta=0.00023017.
- npz_streaming_style: k35/k10 bbox=1.02132, minor=0.984423, conf_threshold=0.970325, valid_delta=-0.0114201.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
