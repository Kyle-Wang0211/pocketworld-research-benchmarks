# DA3 image-only 官方复刻交接包

创建时间：2026-06-05

Research 仓库本地路径：
`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`

Research 远端：
`git@github.com:Kyle-Wang0211/pocketworld-research-benchmarks.git`

APP / 主工程本地路径：
`/Users/kaidongwang/Documents/progecttwo`

官方 Depth-Anything-3 本地 clone：
`/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`

官方 streaming vendor copy：
`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming`

当前 Research 分支：
`main`

当前关键提交：

- `04cb362 Checkpoint DA3 K35 official baseline`
- `148214b Add DA3 official replication guardrails`

## 硬规则

从这个交接点开始，外部 pose 稳定版不要再动。它只作为视觉参考和回滚对照，不再继续修、不再加清理、不再混入 image-only 复刻路线。

下一阶段唯一目标是：一比一复刻官方 DA3 image-only 路径。不能依赖 AR / VIO / `cameraTransform` / 外部相机位姿。原因是产品必须覆盖手机、平板、笔记本、Android、iOS、鸿蒙、Windows 等设备，其中很多设备没有可靠 AR 能力。位姿必须由 DA3 算法内部自己从图像估计，不能依靠 AR mode。

不要用自定义算法修视觉问题。黑块、厚层、重叠、漂浮、地板缺失都先当作官方路径没有复刻对导致的 parity bug。禁止用暗色过滤、连通域删除、地板保护、平面拟合、点云清理、loop/Sim3 融合、体素降噪、mesh repair 作为替代。

每修一处，只改一处；立刻导出对应 PLY，复制到 Desktop 并打开给用户看。视觉变差就马上回滚，不要继续叠补丁。

## 时间线与文件

### 01 guardrails

目录：
`01_guardrails/`

内容：

- `AGENTS.md`

这是当前已经写入 repo 的硬规则副本。新会话必须先读。

### 02 external pose stable frozen

目录：
`02_external_pose_stable_frozen/`

用途：
视觉最好的外部 pose 稳定版冻结参考。不要再改。

关键文件：

- `highres_k05_res742_mps_pytorch_rgb.ply`
- `highres_k05_res742_mps_pytorch_views.png`
- `highres_k05_res742_mps_coreml_rgb.ply`
- `highres_k05_res742_mps_coreml_views.png`
- `highres_k05_res742_mps_coreml_vs_pytorch_glb_style.png`
- `highres_k05_res742_mps_official_filter_pointcloud_compare.json`
- `highres_k05_res742_mps_official_filter_pointcloud_compare_zh.md`

重要结论：

- 这条视觉最好，但它不是纯 image-only。
- 它来自 `capture_seq_k35_strict`，输入列表是筛选后的 414 帧，不是原始 every-frame 连续相机帧。
- 它的 PyTorch sweep 脚本会把 manifest 里的相机 intrinsics/extrinsics 传给官方 PyTorch 路径，所以它依赖外部 pose。
- 如果这些 `cameraTransform` 来自 ARKit/VIO，它就间接依赖 AR/VIO。

### 03 K35 image-only window000 baseline

目录：
`03_k35_image_only_window000_baseline/`

用途：
当前 K35 window000 的 image-only / official-postprocess 风格问题基线。

关键文件：

- `window000_glb_style_first_35_rgb.ply`
- `window000_glb_style_first_35_views.png`
- `window000_npz_streaming_first_35_rgb.ply`
- `window000_npz_streaming_first_35_views.png`
- `glb_style_report.json`
- `glb_style_report_zh.md`
- `npz_streaming_style_report.json`
- `npz_streaming_style_report_zh.md`
- `window_000_official_filter_micro_audit_report.json`
- `window_000_official_filter_micro_audit_report_zh.md`

重要结论：

- 这是当前要继续复刻官方 image-only 时的主要对照基线之一。
- 不要在这条路径上加暗块清理或点云修补。
- 需要继续找官方路径差异，而不是对输出点云做补偿。

### 04 full414 official save reference

目录：
`04_full414_official_save_reference/`

用途：
现有 414 帧官方 save-frame downstream 参考导出。用户要求可以先接受暗块，只看完整 414 帧是否只剩暗块问题。

关键文件：

- `overlap18_official_save_full414_npz_streaming_rgb.ply`
- `overlap18_official_save_full414_npz_streaming_views.png`
- `official_save_sequence_pointcloud_report.json`
- `official_save_sequence_pointcloud_report_zh.md`

报告里的关键指标：

- `point_count`: 1220024
- `per_frame_depth_mean.count`: 414
- `per_frame_conf_mean.count`: 414
- `camera_center_diag`: 2.9042959213256836

### 05 relevant reports

目录：
`05_relevant_reports/`

用途：
按排查顺序归档的重要中文报告。新会话不要从零猜，先读这些。

文件：

- `official_da3_copy_paste_parity_ledger_zh.md`
- `official_da3_cpp_preprocess_kernel_parity_audit_zh.md`
- `official_da3_dart_input_continuity_risk_contract_audit_zh.md`
- `official_da3_external_camera_branch_parity_audit_zh.md`
- `official_da3_image_only_coreml_export_kit_manifest_zh.md`
- `official_da3_image_only_multi_window_overlap_summary_zh.md`
- `official_da3_image_only_overlap_regression_gate_zh.md`
- `official_da3_preprocess_pixel_parity_audit_zh.md`

### 06 desktop visual check archive

目录：
`06_desktop_visual_check_archive/`

用途：
把之前 Desktop 上肉眼检查过的 PLY/PNG 复制回 Research 仓库。这里是历史视觉证据，不是新算法基线。

包含：

- `DA3_baseline_restore_before_bad_changes/*.ply` 的副本
- `DA3_image_only_window007_visual_check/*.ply` 的副本
- `DA3_image_only_window007_visual_check/*.png` 的副本

这些文件是为了新会话快速复盘“哪条看起来好、哪条坏”，不是继续开发的目标路径。

## 当前最重要的事实

1. 视觉最好的外部 pose 稳定版不能作为 image-only 成功证明。
   它把外部相机位姿传入了官方 PyTorch 路径。

2. 当前 `capture_seq_k35_strict/da3_input_manifest.json` 有 414 帧，但不是原始连续相机帧序列。
   前 70 个 id：
   `cap-1, cap-3, cap-5, cap-7, cap-21, cap-23, cap-29, cap-31, cap-33, cap-35, cap-37, cap-39, cap-42, cap-44, cap-48, cap-50, cap-52, cap-54, cap-56, cap-74, cap-78, cap-80, cap-96, cap-103, cap-105, cap-107, cap-109, cap-114, cap-116, cap-118, cap-122, cap-124, cap-126, cap-128, cap-131, cap-136, cap-138, cap-140, cap-142, cap-144, cap-148, cap-167, cap-190, cap-192, cap-194, cap-196, cap-198, cap-205, cap-207, cap-210, cap-214, cap-212, cap-216, cap-220, cap-222, cap-224, cap-227, cap-230, cap-235, cap-257, cap-260, cap-263, cap-272, cap-274, cap-280, cap-288, cap-291, cap-296, cap-310, cap-312`

3. 官方 DA3 streaming 的 chunk 语义是对 `img_list` 做连续切片：`img_list[start_idx:end_idx]`。
   所以现在必须区分：
   原始拍摄连续帧、筛选后的 414 帧 image list、官方 streaming 对 image list 的连续 chunk。

4. APP/Research 曾经存在相机约定差异嫌疑：
   Research 明确把 `cameraTransform` 转成 `opencv_w2c`；APP native 之前被观察到可能把 frame 的 `cameraTransform` 原样塞给 CoreML extrinsics。这个问题对外部 pose 路线重要，但新路线要做纯 image-only，原则上不应该再喂任何外部 extrinsics。

5. C++/OpenCV/libjpeg 预处理 parity 已经有报告认为接近官方目标，不要无意义重测尺寸。用户已经明确不要再测最高分辨率/最佳 K。产品约束仍然是 K35。

## 下一会话第一步建议

1. 读 `AGENTS.md` 和本目录的 `NEW_SESSION_PROMPT_ZH.md`。
2. 不要改外部 pose 稳定版。
3. 先在官方 DA3 clone 内确认真正 image-only 的调用方式：不传 extrinsics、不传 intrinsics、不传 AR/VIO pose，只传 images。
4. 用最小可视化 oracle 跑通一小段纯官方 image-only，导出 PLY 给用户看。
5. 再推进 K35 / CoreML / mobile 版本。每一步一个 PLY，视觉错马上回滚。
