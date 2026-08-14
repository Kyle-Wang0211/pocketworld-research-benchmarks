# Official Image-Only Stage Map

这份 stage map 是为了把问题拆到足够细：每一步都有输入、输出、可视化和判断目标。任何黑块、多层地板、错位或置信度异常，都要能沿着这里倒查回具体阶段。

## Stage 00 - Capture And Window Authority

目的：固定原始照片、窗口选择、帧顺序和官方 image-only 输入契约。

输入：
- 原始 capture bundle
- `photo_bundle.json`
- `da3_input_manifest.json`
- `da3_k_windows.json`

产出：
- 35-frame window 列表
- 原始图像路径索引
- route contract 报告
- image-only / pose-conditioned 分离证据

判断：
- 当前窗口到底是哪 35 帧
- DA3 是否只吃 image，不吃外部 `extrinsics/intrinsics`
- 当前路线是否被 `K35@476x742 pose-conditioned` 污染

## Stage 01 - Official Preprocess, Depth, Confidence, Photometric Audit

目的：复刻官方 image-only 前半段，并把深度、置信度、原图/处理图、高光/暗部风险先全部可视化。这里不做 PLY、不做跨帧融合。

输入：
- Stage 00 的 window frame ids
- official DA3-BASE PyTorch/image-only output arrays
- `process_res=504`
- `process_res_method=upper_bound_resize`

产出：
- contact sheets:
  - original RGB
  - DA3 processed RGB
  - depth linear
  - depth log
  - confidence
  - confidence minus 1 log
  - highlight/dark overlay
  - summary panel
- per-frame images:
  - 35 original RGB
  - 35 processed RGB
  - 35 depth linear
  - 35 depth log
  - 35 confidence
  - 35 confidence-minus-1 log
  - 35 highlight/dark overlay
  - 35 summary panels
- tables:
  - per-frame depth/conf/highlight metrics CSV
  - per-frame visual manifest JSON
- raw arrays:
  - `pytorch_depth.npy`
  - `pytorch_conf.npy`
  - `pytorch_processed_images.npy`
  - `pytorch_intrinsics.npy`
  - `pytorch_extrinsics.npy`

判断：
- 深度图本身是否已经出现明显异常
- 置信度低区是否和远距离、反光、暗部或输入视角相关
- 高光/暗部检测是否解释得通
- 可疑帧是否在 depth/conf 阶段已经显著异常

## Stage 02 - Official DA3 Camera Geometry Audit

目的：只检查 DA3 自己预测的相机几何。这里仍然不做点云融合、不做 PLY。它回答的是：DA3 预测的 `intrinsics/extrinsics` 是否足够稳定，是否可能导致后面的黑块、多层地板或错位。

输入：
- Stage 01 raw arrays:
  - `pytorch_intrinsics.npy`
  - `pytorch_extrinsics.npy`
  - `pytorch_depth.npy`
  - `pytorch_conf.npy`
  - `pytorch_processed_images.npy`
- Stage 00 frame order

产出：
- `stage02_camera_pose_geometry_report.json`
- `stage02_intrinsics_per_frame.csv`
- `stage02_camera_centers_per_frame.csv`
- `stage02_relative_pose_delta.csv`
- `stage02_pairwise_pose_metrics.csv`
- `stage02_intrinsics_timeseries.png`
- `stage02_camera_trajectory_top_front_side.png`
- `stage02_camera_frustums_world.png`
- `stage02_pairwise_baseline_heatmap.png`
- `stage02_pose_delta_timeseries.png`
- `stage02_depth_pose_scale_panel.png`

判断：
- `fx/fy/cx/cy` 是否平滑，是否有突然跳变
- 相机中心轨迹是否符合拍摄路径
- 相邻帧旋转/平移是否有尖峰
- 可疑帧 `cap-74/cap-78/cap-80` 的 pose 是否和前后帧断裂
- depth scale 和 camera baseline 是否出现不一致
- 如果 Stage 01 看起来正常但 Stage 02 崩，问题优先归因到 DA3 camera geometry

## Stage 03 - Single-Frame Camera-Space Geometry

目的：用每帧 depth + intrinsics 反投影到单帧 camera space，不跨帧、不用 extrinsics。这里判断单帧几何是否合理。

产出：
- per-frame camera-space point-map previews
- depth-to-camera coordinate statistics
- valid/confident pixel masks
- per-frame geometry report

判断：
- 单帧地板/墙/物体是否已经厚、扭、断
- 黑块是否单帧就已经是巨大深度面
- 问题是否和 world pose 无关

## Stage 04 - Per-Frame World-Space Geometry

目的：把 Stage 03 的单帧点用 DA3 `extrinsics` 放进 world space，但仍不做融合。

产出：
- per-frame world-space previews
- frame-to-frame overlay previews
- per-frame bounding boxes and principal axes

判断：
- 单帧合理但 world-space 错位，说明 pose/extrinsics 是主嫌疑
- 多层地板是否来自不同帧放到不同世界位置

## Stage 05 - Official Dense Sim3 Overlap Alignment

目的：复刻官方 overlap dense Sim3。只在多 window 或 bridge frames 上做对齐验证。

产出：
- overlap pair reports
- Sim3 scale/rotation/translation tables
- residual histograms
- before/after alignment previews

判断：
- 跨 window 是否能用 dense geometry 对齐
- loop/bridge 边是否可信

## Stage 06 - Window Graph And Loop Transform

目的：把 accepted Sim3 edges 组成 window graph，并传播 window-to-root transform。

产出：
- window graph JSON
- loop candidate report
- accepted/rejected edge table
- transform chain report

判断：
- 哪些 window 被对齐
- 哪些 loop 被拒绝
- global transform 是否引入大漂移

## Stage 07 - Official Export And Fusion

目的：最后才进入 official confidence threshold、frame selection、pointcloud/fusion export。

产出：
- official-save frame list
- combined output
- unique-frame output
- confidence-threshold report
- export audit

判断：
- 黑块/多层地板是否在 export/fusion 阶段才出现
- 是否有 threshold 或重复帧策略导致的视觉问题

## Stage 08 - Backward Problem Attribution

目的：把发现的问题倒查回最早出现的 stage。

产出：
- problem region atlas
- frame attribution table
- stage attribution matrix
- final diagnosis report

判断：
- 问题属于 depth、confidence、intrinsics、extrinsics、single-frame geometry、world transform、Sim3、loop graph，还是 final export
