# Official Save Sequence Point Cloud Export

## 做了什么

- 按 capture 的 `officialSaveSlotIndices` 选择保存帧。
- 按官方 DA3-Streaming `npz_output_process.py + save_confident_pointcloud_batch` 语义导出点云。
- 不做清理、不做 Poisson、不做 mesh、不做自研融合。

## 保存帧检查

- source_frame_count: 414
- selected_frame_count: 414
- selected_unique_frame_count: 414
- selected_duplicate_frame_count: 0
- missing_frame_count: 0
- order_matches_source: True
- first_order_mismatch: None

## 官方 Filter

- conf_threshold_coef: 0.75
- conf_mean: 5.0515411
- conf_threshold: 3.7886558
- sample_ratio: 0.015
- valid_point_count_before_downsample: 81334938
- valid_fraction_of_pixels: 0.55624477
- exported_point_count: 1220024

## 几何数值

- bbox_diag_p01_p99: 2.9355306
- bbox_extent_p01_p99: [2.0018608427047733, 1.2785581864416604, 1.7248716306686402]
- pca_minor_extent: 1.2744254
- pca_minor_to_major_ratio: 0.58627768

## 输出

- PLY: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap18/overlap18_official_save_full414_npz_streaming_rgb.ply`
- views PNG: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_save_overlap_compare_2026_06_03/overlap18/overlap18_official_save_full414_npz_streaming_views.png`
