# Official Save Overlap Compare

## 一句话

这份对比只比较官方保存语义 + 官方 streaming pointcloud filter/sample 下的 overlap 差异；没有清理、Poisson、mesh 或自研融合。

## 基本检查

| metric | overlap18 | overlap06 |
|---|---:|---:|
| chunk_size | 35 | 35 |
| overlap | 18 | 6 |
| step | 17 | 29 |
| selected_frame_count | 414 | 414 |
| selected_duplicate_frame_count | 0 | 0 |
| missing_frame_count | 0 | 0 |
| order_matches_source | True | True |

## 点云指标

| metric | overlap18 | overlap06 | right-left | ratio |
|---|---:|---:|---:|---:|
| conf_threshold | 3.7886558 | 3.5189869 | -0.26966889 | 0.92882201 |
| valid_fraction_of_pixels | 0.55624477 | 0.54402737 | -0.012217404 | 0.97803592 |
| exported_point_count | 1220024 | 1193227 | -26797 | 0.97803568 |
| bbox_diag_p01_p99 | 2.9355306 | 2.8170838 | -0.11844679 | 0.95965064 |
| bbox_diag_p05_p95 | 1.9883124 | 1.9158327 | -0.072479717 | 0.96354712 |
| pca_minor_extent | 1.2744254 | 1.2481217 | -0.02630369 | 0.97936035 |
| pca_minor_to_major_ratio | 0.58627768 | 0.61344764 | 0.02716996 | 1.0463432 |

## 输出

- overlap18 PLY: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap18/overlap18_official_save_full414_npz_streaming_rgb.ply`
- overlap18 views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap18/overlap18_official_save_full414_npz_streaming_views.png`
- overlap06 PLY: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap06/overlap06_official_save_full414_npz_streaming_rgb.ply`
- overlap06 views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap06/overlap06_official_save_full414_npz_streaming_views.png`
