# Stage 02 - Official DA3 Camera Geometry Audit

Stage 02 的任务是检查 DA3 image-only 自己预测出的相机几何：`pred_intrinsics` 和 `pred_extrinsics`。它还不做 PLY、不做 fusion、不做 cleanup。

## Stage 02 回答什么

Stage 01 已经回答了：输入图、processed 图、depth、confidence、高光/暗部是否异常。

Stage 02 接着回答：

- DA3 预测的内参是否稳定？
- DA3 预测的外参/camera pose 是否稳定？
- 相机轨迹是否符合真实拍摄路径？
- 可疑帧是否在 camera geometry 层面发生跳变？
- 后面的多层地板/黑块是否可能由 pose/extrinsics 放错位置造成？

## 输入

来自 Stage 01:

- `raw_official_prediction_arrays/pytorch_intrinsics.npy`
- `raw_official_prediction_arrays/pytorch_extrinsics.npy`
- `raw_official_prediction_arrays/pytorch_depth.npy`
- `raw_official_prediction_arrays/pytorch_conf.npy`
- `raw_official_prediction_arrays/pytorch_processed_images.npy`

来自 Stage 00:

- `source_pointers/da3_k_windows.json`
- `source_pointers/da3_input_manifest.json`

## 计划产出

表格：

- `tables/stage02_intrinsics_per_frame.csv`
- `tables/stage02_camera_centers_per_frame.csv`
- `tables/stage02_relative_pose_delta.csv`
- `tables/stage02_pairwise_pose_metrics.csv`

图片：

- `figures/stage02_intrinsics_timeseries.png`
- `figures/stage02_camera_trajectory_top_front_side.png`
- `figures/stage02_camera_frustums_world.png`
- `figures/stage02_pairwise_baseline_heatmap.png`
- `figures/stage02_pose_delta_timeseries.png`
- `figures/stage02_depth_pose_scale_panel.png`

报告：

- `stage02_camera_pose_geometry_report.json`
- `README_STAGE02_RESULTS_ZH.md`

## 判断重点

特别关注 `cap-74`, `cap-78`, `cap-80`。如果这三帧的 depth/conf 在 Stage 01 还说得通，但 Stage 02 出现 pose 轨迹尖峰、相机朝向反转、baseline 异常、内参跳变，那么黑色大块更可能是“内容被放错世界位置”，不是凭空生成。

如果 Stage 02 也稳定，再进入 Stage 03：单帧 camera-space 反投影。
