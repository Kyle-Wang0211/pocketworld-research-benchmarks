# Bad Windows Official Micro Audit Summary

这是 read-only diagnostic。只复用官方 GLB export / DA3-Streaming NPZ pointcloud 规则, 不改生产算法。

## 核心表格

| window | style | slot00 bbox | first10 bbox | first35 bbox | first35/slot00 bbox | first10 minor | first35 minor | first35/first10 minor | flags |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| window_000 | glb_style | 2.5190 | 2.6715 | 2.9111 | 1.156 | 0.9540 | 1.1151 | 1.169 | - |
| window_000 | npz_streaming_style | 2.8033 | 2.8615 | 2.9594 | 1.056 | 1.0827 | 1.1803 | 1.090 | - |
| window_006 | glb_style | 1.8756 | 1.6052 | 1.9409 | 1.035 | 0.8542 | 0.8322 | 0.974 | - |
| window_006 | npz_streaming_style | 1.5829 | 1.5871 | 1.7952 | 1.134 | 0.8497 | 0.7947 | 0.935 | - |
| window_014 | glb_style | 1.4456 | 1.9081 | 2.1542 | 1.490 | 1.0261 | 1.2064 | 1.176 | - |
| window_014 | npz_streaming_style | 1.4256 | 1.4304 | 1.6021 | 1.124 | 0.7882 | 0.9405 | 1.193 | - |
| window_015 | glb_style | 1.8304 | 2.4887 | 2.3958 | 1.309 | 0.9749 | 0.9937 | 1.019 | - |
| window_015 | npz_streaming_style | 1.4822 | 1.7279 | 1.7185 | 1.159 | 0.8547 | 0.9187 | 1.075 | - |
| window_016 | glb_style | 1.6965 | 1.7104 | 2.1981 | 1.296 | 0.8508 | 0.9407 | 1.106 | - |
| window_016 | npz_streaming_style | 1.3160 | 1.2706 | 1.5987 | 1.215 | 0.6193 | 0.9076 | 1.465 | minor_jump=first_35 |

## 初步解释

- `window_006/014/015/016` 均没有出现 0+1 或 0+1+2 级别的瞬间崩坏。
- 厚层/范围扩大更像随视角跨度和 slots 累计逐渐增长, 尤其 first_35 相比 first_10。
- `window_016` 的 NPZ-streaming-style 在 first_35 出现 PCA minor jump, 说明 streaming 保存规则下也能出现明显厚化。
- `window_015` 的 GLB-style 在 first_10 bbox 达到高点, first_35 反而略回落, 说明不是简单“帧越多一定越坏”, 而与窗口内视角/内容分布有关。
- 这进一步支持: K35 厚层更应继续查 window 内 pose-depth-scale / confidence / official export-fusion 口径, 而不是直接归因给缺 loop。

## 输出

- compact contact sheet: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_bad_windows_micro_audit_summary/bad_windows_first10_first35_contact_sheet.png`
