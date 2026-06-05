# Official DA3 window_016 late-slot geometry consistency audit

日期：2026-06-05

## 结论

- status: `late_slot_pose_depth_consistency_suspect`
- goal complete: `False`

window_016 thickening starts after the first 10 frames and aligns most strongly with late-slot pose-span expansion, with additional depth/confidence risk around slot 24.

Inspect/remediate K-window composition and DA3 upstream pose/depth consistency for late slots; do not treat downstream point filtering as the primary fix.

## 大白话

- first10 之后第一个强信号是 slot 10/cap-1396：相机中心 span 从 0.297 跳到 0.677，最大 step 0.410。
- npz downstream 的 bbox/minor 不是最后才突然出现；k12 已经超过 k10 的 1.10x minor 阈值，后面逐步累积。
- slot 24/cap-1514 是第二个可疑点：pose step 很大、depth p95 很高、confidence median 很低，容易把厚层尾部拉大。
- 这更像上游几何一致性和 K-window 组成问题，而不是 downstream 缺一个去重点云开关。

## Top Signals

- Largest pose step is slot 10 / cap-1396 (0.410); this is the first major span break after k10.
- First npz minor ratio >=1.10 vs k10 occurs at slot 11 / cap-1413 (k=12).
- Lowest confidence median is slot 24 / cap-1514 (2.027); low-confidence late slots can lower npz threshold pressure.
- Largest depth p95 is slot 28 / cap-1529 (3.241); this late depth tail can widen the layer after the pose span has expanded.

## Late Slots

| slot | frame | role | step | pose_diag_delta | depth_p95 | conf_med | npz minor vs k10 | npz bbox vs k10 |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 10 | `cap-1396` | `bridge` | 0.410 | 0.380 | 2.442 | 6.180 | 1.098 | 1.058 |
| 11 | `cap-1413` | `bridge` | 0.171 | 0.157 | 2.582 | 5.289 | 1.327 | 1.145 |
| 12 | `cap-1417` | `bridge` | 0.095 | 0.034 | 2.667 | 5.527 | 1.486 | 1.226 |
| 13 | `cap-1429` | `bridge` | 0.093 | 0.082 | 2.615 | 4.961 | 1.685 | 1.299 |
| 14 | `cap-1437` | `bridge` | 0.295 | 0.147 | 2.512 | 4.414 | 1.382 | 1.340 |
| 15 | `cap-1441` | `bridge` | 0.031 | 0.014 | 2.123 | 3.314 | 1.486 | 1.372 |
| 16 | `cap-1448` | `bridge` | 0.093 | 0.054 | 2.262 | 3.594 | 1.429 | 1.397 |
| 17 | `cap-1453` | `bridge` | 0.019 | 0.012 | 2.264 | 2.934 | 1.435 | 1.433 |
| 18 | `cap-1455` | `core` | 0.001 | 0.000 | 2.239 | 2.953 | 1.478 | 1.455 |
| 19 | `cap-1457` | `core` | 0.002 | 0.000 | 2.223 | 2.889 | 1.480 | 1.467 |
| 20 | `cap-1459` | `core` | 0.002 | 0.000 | 2.220 | 3.100 | 1.492 | 1.489 |
| 21 | `cap-1488` | `core` | 0.280 | 0.176 | 1.780 | 3.496 | 1.506 | 1.500 |
| 22 | `cap-1492` | `core` | 0.012 | 0.004 | 1.799 | 3.281 | 1.509 | 1.510 |
| 23 | `cap-1494` | `core` | 0.120 | 0.000 | 1.764 | 2.375 | 1.629 | 1.518 |
| 24 | `cap-1514` | `core` | 0.371 | 0.000 | 3.114 | 2.027 | 1.532 | 1.536 |
| 25 | `cap-1518` | `core` | 0.198 | 0.000 | 2.952 | 5.156 | 1.516 | 1.543 |
| 26 | `cap-1523` | `core` | 0.052 | 0.000 | 3.122 | 3.600 | 1.458 | 1.546 |
| 27 | `cap-1525` | `core` | 0.099 | 0.000 | 3.093 | 5.242 | 1.491 | 1.533 |
| 28 | `cap-1529` | `core` | 0.099 | 0.000 | 3.241 | 3.783 | 1.521 | 1.541 |
| 29 | `cap-1533` | `core` | 0.010 | 0.000 | 3.228 | 4.117 | 1.640 | 1.531 |
| 30 | `cap-1535` | `core` | 0.030 | 0.000 | 3.166 | 4.352 | 1.630 | 1.524 |
| 31 | `cap-1540` | `core` | 0.056 | 0.000 | 3.236 | 4.430 | 1.658 | 1.518 |
| 32 | `cap-1549` | `core` | 0.091 | 0.000 | 3.131 | 3.717 | 1.629 | 1.516 |
| 33 | `cap-1553` | `core` | 0.025 | 0.000 | 3.149 | 4.285 | 1.708 | 1.502 |
| 34 | `cap-1555` | `core` | 0.042 | 0.006 | 3.176 | 5.062 | 1.720 | 1.493 |
