# Official DA3 overlap vs K35 window thickness attribution

日期：2026-06-04

## 结论

- 官方 core-frame downstream 已经消除了跨 window/chunk overlap 帧重复保存：overlap18 和 overlap06 的 selected duplicate frame count 都是 0。
- 但这只解决“同一帧被保存两次”的问题，不解决“同一个 K35 window 内 35 个视角看到同一表面但没有压成一张薄面”的问题。
- 当前厚层证据更指向 within-window / upstream geometry consistency，而不是 downstream 少做了官方隐藏点云去重。
- 因此 APP 继续走 `results_output/frame_*.npz + npz_output_process.py` 是正确 baseline；不要把 `pcd/combined_pcd.ply` full-chunk merge 当产品基线。

## Overlap 保存证据

| metric | left | right |
|---|---:|---:|
| label | overlap18 | overlap06 |
| chunk_size | 35 | 35 |
| overlap | 18 | 6 |
| step | 17 | 29 |
| selected_frame_count | 414 | 414 |
| selected_unique_frame_count | 414 | 414 |
| selected_duplicate_frame_count | 0 | 0 |
| missing_frame_count | 0 | 0 |
| order_matches_source | True | True |
| bbox_diag_p01_p99 | 2.9355306 | 2.8170838 |
| pca_minor_extent | 1.2744254 | 1.2481217 |

关键读法：改变 K35 的 overlap 从 18 到 6 后，最终官方保存帧仍是 414 张、重复保存帧仍是 0。也就是说，官方 core-frame 保存语义已经在 frame selection 层面处理了 overlap 重复。

## 单 window 厚层证据

- largest bbox growth: `{"window_id": "window_016", "style": "glb_style", "pose_scale": 0.7230839040376699, "bbox_growth": 1.2851006596234356, "minor_growth": 1.105667583402953, "pose_span_growth": 4.595401355328742, "conf_threshold_ratio": 1.095505617977528, "valid_fraction_delta": -8.089489164864183e-06, "depth_p95_ratio": 1.0735751406236393}`
- largest PCA minor growth: `{"window_id": "window_016", "style": "npz_streaming_style", "pose_scale": 0.7230839040376699, "bbox_growth": 1.2582178072922119, "minor_growth": 1.4654765399923089, "pose_span_growth": 4.595401355328742, "conf_threshold_ratio": 0.7941074149059311, "valid_fraction_delta": -0.00821803114776909, "depth_p95_ratio": 1.0735751406236393}`
- thickened without valid fraction increase count: `7`
- thickened despite tighter threshold count: `1`
- minor growth vs pose span growth correlation clue: `0.75311571`
- minor growth vs confidence threshold ratio clue: `0.029661445`
- minor growth vs valid fraction delta clue: `-0.024065391`

关键读法：`window_016` 在 npz_streaming_style 下 first35/first10 的 PCA minor growth 约 1.465，同时 valid fraction 下降。这不是“保留了更多低置信点”就能解释的现象。

## Attribution

- overlap_frame_duplicate_saved_to_downstream: `False`
- official_core_frame_selection_removed_overlap_duplicates: `True`
- single_window_thickness_remains_after_official_filter: `True`
- pose_span_is_strongest_current_clue: `True`
- most_likely_current_cause: `within_window_upstream_geometry_consistency`

## 大白话

官方 downstream 做的是：这个 window 和下个 window 重叠的那些帧，不要在最终序列点云里重复保存。

官方 downstream 没做的是：同一个 window 内，35 帧都看到了同一块地板/墙面时，把这些点强行融合成一张薄薄的面。

所以现在的判断是：跨 window overlap 重复这类问题，官方 core-frame path 已经处理；单 K35 window 内厚层，更像 DA3 上游 depth/pose/scale 一致性没完全压住。

## 下一步

1. 保持 APP official baseline：core-frame npz path、`conf_threshold_coef=0.5`、sample ratio 0.015、no voxel/TSDF/surfel cleanup。
2. 关闭 full same-resolution PyTorch K35 reference gate，确认官方 PyTorch full-res 是否也厚。
3. 如果官方也厚，把后续清理明确标成 product adaptation；如果官方不厚，继续查 CoreML/export/preprocess。
