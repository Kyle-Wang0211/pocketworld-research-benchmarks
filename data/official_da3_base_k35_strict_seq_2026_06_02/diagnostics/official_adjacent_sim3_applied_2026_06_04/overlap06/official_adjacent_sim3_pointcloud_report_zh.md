# Official Adjacent Dense Sim3 Point Cloud Export

## 做了什么

- 按 capture 的 `officialSaveSlotIndices` 选择保存帧。
- 按 DA3-Streaming 相邻 dense Sim3 方向 `current chunk -> previous chunk` 累积并应用变换。
- 按 streaming confidence 语义和 NPZ point-cloud 采样导出 PLY/三视图。
- 不做 loop optimizer、不做清理、不做 Poisson、不做 mesh、不做自研融合。

## 保存帧检查

- source_frame_count: 414
- selected_frame_count: 414
- selected_unique_frame_count: 414
- selected_duplicate_frame_count: 0
- missing_frame_count: 0
- order_matches_source: True

## Adjacent Sim3

- edge_count: 14
- estimated_edge_count: 14
- input_scale_range: 0.94438075 .. 1.1348413
- input_rotation_angle_deg_max: 4.3835578
- accumulated_scale_range: 1 .. 1.4404062
- accumulated_rotation_angle_deg_max: 14.774392
- accumulated_translation_norm_max: 1.2956027

## 官方 Filter

- confidence_mode: streaming_subtract_one
- conf_threshold_coef: 0.75
- conf_mean: 3.6919826
- conf_threshold: 2.7689869
- sample_ratio: 0.015
- valid_point_count_before_downsample: 74915976
- exported_point_count: 1123739

## 几何数值

- bbox_diag_p01_p99: 3.5081364
- bbox_extent_p01_p99: [2.201091678142547, 1.5595779570937154, 2.24275119781494]
- pca_minor_extent: 1.4092916
- pca_minor_to_major_ratio: 0.61697211

## 输出

- PLY: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_applied_2026_06_04/overlap06/overlap06_official_adjacent_sim3_full414_adjacent_sim3_npz_streaming_rgb.ply`
- views PNG: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_applied_2026_06_04/overlap06/overlap06_official_adjacent_sim3_full414_adjacent_sim3_npz_streaming_views.png`
