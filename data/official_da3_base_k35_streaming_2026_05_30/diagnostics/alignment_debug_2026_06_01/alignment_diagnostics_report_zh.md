# DA3 Streaming 对齐诊断

## 路线
DA3-BASE K35@476x742 official sequential chunks + SelaVPR++ loop + official Sim3LoopOptimizer; point cloud diagnostics only

## 关键指标

| 项目 | 点数 | bbox diag | RMSE | P90 |
|---|---:|---:|---:|---:|
| window_000 单窗 | 43353 | 2.1332 | - | - |
| window_000+001 共享帧 | 72923 | 2.1319 | 0.0759 | 0.1073 |
| first_01_windows | 43353 | 2.0895 | - | - |
| first_02_windows | 86203 | 2.0914 | - | - |
| first_04_windows | 174629 | 2.3879 | - | - |
| first_08_windows | 362823 | 2.5470 | - | - |
| first_24_windows | 1103964 | 2.7781 | - | - |

## 输出

- window_000_single_ply: `data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_single_rgb.ply`
- window_000_single_views_png: `data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_single_views.png`
- window_000_001_shared_rgb_ply: `data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_001_shared_aligned_rgb.ply`
- window_000_001_shared_source_color_ply: `data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_001_shared_aligned_source_color.ply`
- window_000_001_shared_source_color_views_png: `data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_001_shared_source_color_views.png`
- incremental: `{"first_01_windows": {"ply": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_01_windows_rgb.ply", "views_png": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_01_windows_views.png"}, "first_02_windows": {"ply": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_02_windows_rgb.ply", "views_png": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_02_windows_views.png"}, "first_04_windows": {"ply": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_04_windows_rgb.ply", "views_png": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_04_windows_views.png"}, "first_08_windows": {"ply": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_08_windows_rgb.ply", "views_png": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_08_windows_views.png"}, "first_24_windows": {"ply": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_24_windows_rgb.ply", "views_png": "data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/first_24_windows_views.png"}}`
