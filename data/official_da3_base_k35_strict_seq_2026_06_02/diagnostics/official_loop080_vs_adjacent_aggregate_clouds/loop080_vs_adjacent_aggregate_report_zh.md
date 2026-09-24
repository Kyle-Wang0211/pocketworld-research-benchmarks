# Loop080 vs Adjacent Aggregate Diagnostic

这是 threshold=0.80 的 diagnostic-only 对照, 不是生产阈值修改。未做 graph patch、未做新融合、未做 Poisson/mesh。

## Aggregate PLY

- adjacent-only PLY: `adjacent_only_matched_first24_rgb.ply`
- loop080 optimized PLY: `loop080_optimized_matched_first24_rgb.ply`
- blue/orange overlay PLY: `loop080_vs_adjacent_source_color_overlay.ply`

## 数值结论

- shared edge p90 mean adjacent-only: 0.208001
- shared edge p90 mean loop080: 0.202639
- delta p90 mean loop-adjacent: -0.005362
- p90 improved/worsened edge count: 16 / 7
- loop vs adjacent point displacement median/p90: 0.101634 / 0.190502

## 最坏 loop 后相邻边

| edge | adjacent p90 | loop080 p90 | delta |
|---|---:|---:|---:|
| window_006->window_007 | 0.401811 | 0.407063 | 0.005251 |
| window_015->window_016 | 0.364461 | 0.361891 | -0.002570 |
| window_014->window_015 | 0.386085 | 0.347699 | -0.038385 |
| window_016->window_017 | 0.353280 | 0.331970 | -0.021310 |
| window_005->window_006 | 0.305401 | 0.312717 | 0.007316 |
| window_010->window_011 | 0.228183 | 0.225201 | -0.002982 |

## 判断

loop080 optimizer 对平均 adjacent shared p90 有下降, 但仍需肉眼检查 PLY 是否带来形变副作用。
因此当前仍不能把 K35 厚层归因于缺 loop, 也不能把 threshold=0.80 当作生产修复。
