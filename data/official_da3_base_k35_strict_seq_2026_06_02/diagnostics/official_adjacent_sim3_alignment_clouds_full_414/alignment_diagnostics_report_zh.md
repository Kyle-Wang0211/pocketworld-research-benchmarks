# DA3 Streaming 对齐诊断

## 路线
DA3-BASE K35@476x742 official sequential chunks + SelaVPR++ loop + official Sim3LoopOptimizer; point cloud diagnostics only

## 关键指标

| 项目 | 点数 | bbox diag | RMSE | P90 |
|---|---:|---:|---:|---:|
| window_000 单窗 | 26272 | 2.9705 | - | - |
| window_000+001 共享帧 | 53079 | 2.6476 | 0.1105 | 0.1871 |
| first_01_windows | 26272 | 2.9620 | - | - |
| first_02_windows | 51556 | 2.8725 | - | - |
| first_04_windows | 97407 | 3.0282 | - | - |
| first_08_windows | 185528 | 2.8985 | - | - |
| first_24_windows | 532369 | 3.3531 | - | - |

## 输出

- window_000_single_ply: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/window_000_single_rgb.ply`
- window_000_single_views_png: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/window_000_single_views.png`
- window_000_001_shared_rgb_ply: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/window_000_001_shared_aligned_rgb.ply`
- window_000_001_shared_source_color_ply: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/window_000_001_shared_aligned_source_color.ply`
- window_000_001_shared_source_color_views_png: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/window_000_001_shared_source_color_views.png`
- incremental: `{"first_01_windows": {"ply": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_01_windows_rgb.ply", "views_png": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_01_windows_views.png"}, "first_02_windows": {"ply": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_02_windows_rgb.ply", "views_png": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_02_windows_views.png"}, "first_04_windows": {"ply": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_04_windows_rgb.ply", "views_png": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_04_windows_views.png"}, "first_08_windows": {"ply": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_08_windows_rgb.ply", "views_png": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_08_windows_views.png"}, "first_24_windows": {"ply": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_24_windows_rgb.ply", "views_png": "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414/first_24_windows_views.png"}}`
