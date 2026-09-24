# window_016 Pose / Depth / Scale Audit

这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。

## Summary

- pose_scale: `0.723084`
- k10 pose diag: `0.296983`
- k35 pose diag: `1.16623`
- k35/k10 pose diag: `3.92692`
- k10 depth p95: `2.60657`
- k35 depth p95: `2.58091`
- k35/k10 depth p95: `0.990155`

## Official Point Metric Growth

| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glb_style | k=12 (1.14832) | k=12 (1.26091) | - | 1.241 | 1.15254 | 1.21629 | -1.51559e-05 |
| npz_streaming_style | k=12 (1.14549) | k=12 (1.32667) | k=13 (1.48554) | 1.39652 | 1.42888 | 0.898816 | 0.0313564 |

## Cumulative K Table

| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 2.45936 | 0.993119 | 1.03716 | 1.06773 | 1.11823 |
| 2 | 0.188339 | 2.52418 | 0.976717 | 1.02596 | 1.02836 | 1.03691 |
| 3 | 0.208832 | 2.54174 | 0.875118 | 0.840201 | 1.00354 | 0.984536 |
| 4 | 0.218697 | 2.5701 | 0.880187 | 0.85713 | 1.00691 | 0.988563 |
| 5 | 0.230252 | 2.60251 | 0.980692 | 1.05143 | 0.998588 | 0.971247 |
| 6 | 0.232752 | 2.61467 | 1.00326 | 1.06931 | 0.990844 | 0.971069 |
| 7 | 0.234558 | 2.62007 | 1.0132 | 1.06959 | 0.989884 | 0.965889 |
| 8 | 0.23827 | 2.61737 | 1.00353 | 1.05239 | 0.980151 | 0.950771 |
| 9 | 0.248539 | 2.61197 | 0.998522 | 1.05642 | 0.98062 | 0.967399 |
| 10 | 0.296983 | 2.60657 | 1 | 1 | 1 | 1 |
| 11 | 0.677267 | 2.59846 | 1.01637 | 1.07029 | 1.0577 | 1.09841 |
| 12 | 0.834236 | 2.59846 | 1.14832 | 1.26091 | 1.14549 | 1.32667 |
| 13 | 0.868128 | 2.60251 | 1.17819 | 1.30843 | 1.22554 | 1.48554 |
| 14 | 0.950462 | 2.60251 | 1.21584 | 1.14228 | 1.29864 | 1.6851 |
| 15 | 1.09764 | 2.59846 | 1.23012 | 1.15916 | 1.34009 | 1.38158 |
| 16 | 1.11214 | 2.59036 | 1.24283 | 1.17287 | 1.37189 | 1.48647 |
| 17 | 1.16623 | 2.58091 | 1.241 | 1.15254 | 1.39652 | 1.42888 |

## 初步解释

- K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.
- Pose span expands strongly from k10 to k35 (3.927x camera-center bbox diag), so later-slot view span is the strongest current suspect.
- Depth p95 changes by 0.990x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer.
- glb_style: k35/k10 bbox=1.241, minor=1.15254, conf_threshold=1.21629, valid_delta=-1.51559e-05.
- npz_streaming_style: k35/k10 bbox=1.39652, minor=1.42888, conf_threshold=0.898816, valid_delta=0.0313564.
- Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement.
