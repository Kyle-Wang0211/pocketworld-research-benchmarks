# Worst Adjacent Sim3 Shared PLY Diagnostics

路线: full 414 CoreML official postprocess -> adjacent Sim3 worst-edge shared PLY only.

| edge | adjacent p90 | root p90 | sampled points | source-color PLY |
|---|---:|---:|---:|---|
| window_014 -> window_015 | 0.364880 | 0.386085 | 51160 | `window_014_window_015_shared_source_color.ply` |
| window_015 -> window_016 | 0.352374 | 0.364461 | 55921 | `window_015_window_016_shared_source_color.ply` |
| window_006 -> window_007 | 0.346300 | 0.401811 | 55500 | `window_006_window_007_shared_source_color.ply` |
| window_016 -> window_017 | 0.313003 | 0.353280 | 54053 | `window_016_window_017_shared_source_color.ply` |

蓝色=parent window, 橙色=current window。该导出只用于肉眼检查同一 shared frame 的表面是否分层。
