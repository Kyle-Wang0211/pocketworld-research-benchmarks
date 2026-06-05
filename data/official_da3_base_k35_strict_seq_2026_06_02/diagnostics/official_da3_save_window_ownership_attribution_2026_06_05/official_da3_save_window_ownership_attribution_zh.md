# Official DA3 save-window ownership attribution

日期：2026-06-05

## 结论

- status: `window016_official_save_thickness_cap1396_primary`
- goal complete: `False`

After official save-frame downstream alignment, window_016 still thickens, while window_017 does not. The strongest current upstream consistency suspect is cap-1396 inside window_016 official downstream.

Inspect/remediate frame acceptance or capture continuity around cap-1369 -> cap-1396. Keep cap-1514/cap-1529 as window_017 risk signals, but not the current primary thickness cause.

## 大白话

- 官方 save-frame ownership 已经把 window_016 和 window_017 的 downstream 责任分开。
- window_016 official downstream 17 帧仍厚：npz minor vs k10 约 1.429x，bbox 约 1.397x。
- window_017 official downstream 17 帧不厚：npz minor vs k10 约 0.970x，bbox 约 0.948x。
- cap-1396 在 window_016 的 official downstream 内，且从前一帧 cap-1369 跳了 4.47s / 0.410m / elevation +0.387rad。
- cap-1514 和 cap-1529 在 window_017 里是风险信号，但这次没有把 window_017 的官方 downstream 点云拉厚。

## Window Summary

| window | frames | npz minor/k10 | npz bbox/k10 | glb minor/k10 | pose diag/k10 |
|---|---:|---:|---:|---:|---:|
| window_016 | 17 | 1.429 | 1.397 | 1.153 | 3.927 |
| window_017 | 17 | 0.970 | 0.948 | 0.977 | 1.529 |

## Suspects

| frame | ownership | audit row |
|---|---|---|
| `cap-1396` | window_015[slot=27, downstream=False, withheld=True]; window_016[slot=10, downstream=True, withheld=False] | window_016[slot=10, step=0.410, poseDiag=0.677, depthP95=2.442, confMed=6.180] |
| `cap-1514` | window_016[slot=24, downstream=False, withheld=True]; window_017[slot=7, downstream=True, withheld=False] | window_017[slot=7, step=0.371, poseDiag=0.434, depthP95=3.449, confMed=3.654] |
| `cap-1529` | window_016[slot=28, downstream=False, withheld=True]; window_017[slot=11, downstream=True, withheld=False] | window_017[slot=11, step=0.099, poseDiag=0.678, depthP95=3.579, confMed=5.766] |
