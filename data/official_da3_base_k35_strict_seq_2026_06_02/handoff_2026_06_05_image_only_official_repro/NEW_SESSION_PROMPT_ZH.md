# 新会话提示词：一比一复刻官方 DA3 image-only

你是 Codex，在一个已经有大量 DA3 排查历史的工程里继续工作。请不要从零开始猜，也不要自作主张设计新算法。当前唯一目标是：**一比一复刻官方 Depth-Anything-3 image-only 路径**，让 PocketWorld 在没有 AR/VIO 的设备上也能跑出稳定点云。

## 0. 绝对目标

我要的是官方 DA3 image-only，而不是外部 pose 稳定版。

原因：PocketWorld 必须适配手机、平板、笔记本、iOS、Android、鸿蒙、Windows 等系统和设备。很多设备没有 AR 功能，或者 AR 能力不可用、不稳定、权限成本高。产品不能依赖 AR mode。位姿必须由 DA3 算法内部从图像估计，不能依赖 APP / ARKit / VIO / `cameraTransform` / 外部相机 extrinsics。

因此你要做的是：

- 严格复刻官方 DA3 image-only。
- 找出本地 APP/Research/CoreML/PyTorch 路径和官方路径哪里不一样。
- 每次只修一处差异。
- 每修一处就导出对应 PLY，并打开在 Desktop 上给我肉眼检查。
- 如果视觉变差，立即回滚这处改动。

你不能做的是：

- 不能加自定义暗块删除。
- 不能加颜色过滤。
- 不能加连通域删除。
- 不能加地板保护。
- 不能加平面拟合。
- 不能加点云清理、体素降噪、mesh repair、loop/Sim3 融合来掩盖问题。
- 不能把诊断实验包装成产品修复。
- 不能继续改外部 pose 稳定版。

把黑块、厚层、重叠、漂浮、地板缺失、主体物形状烂，都先看作“官方路径没复刻对”的 parity bug。先找差异，按官方代码修差异。

## 1. 仓库和路径

Research 仓库本地路径：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`

Research 远端：

`git@github.com:Kyle-Wang0211/pocketworld-research-benchmarks.git`

APP / 主工程本地路径：

`/Users/kaidongwang/Documents/progecttwo`

官方 Depth-Anything-3 本地 clone：

`/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`

Research 内官方 streaming vendor copy：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming`

当前 Research 关键提交：

- `04cb362 Checkpoint DA3 K35 official baseline`
- `148214b Add DA3 official replication guardrails`

当前交接包目录：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro`

先读：

- `AGENTS.md`
- `data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/README_ZH.md`
- `data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/NEW_SESSION_PROMPT_ZH.md`

## 2. 目前我们遇到的问题

PocketWorld / Research 当前有几条 DA3 路径，视觉表现不一致。

### 2.1 视觉最好的路径不是目标

视觉最好的参考文件：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/02_external_pose_stable_frozen/highres_k05_res742_mps_pytorch_rgb.ply`

对应 preview：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/02_external_pose_stable_frozen/highres_k05_res742_mps_pytorch_views.png`

这条看起来视觉最好，重叠比较少，但它有黑/紫色暗块问题，而且更重要的是：它不是纯 image-only。

证据：

- report 在：
  `data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/02_external_pose_stable_frozen/highres_k05_res742_mps_official_filter_pointcloud_compare.json`
- 原始 report 指向：
  `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k05/highres_k05_res742_mps_official_filter_pointcloud_compare.json`
- 输入来自：
  `capture_seq_k35_strict`
- PyTorch case 来自：
  `pytorch_vs_coreml_window_000/official_pytorch_highres_k_sweep_mps/k05_res742_mps`
- 相关脚本：
  `tools/python/official_pytorch_k_sweep.py`

`tools/python/official_pytorch_k_sweep.py` 里会读取 manifest 里的 `cameraExtrinsicOpenCvW2c4x4` 和 intrinsics，然后传入官方 PyTorch 路径。也就是说，它使用了外部相机位姿，不是纯 DA3 image-only 自己估 pose。

结论：

- 这条外部 pose 稳定版冻结。
- 只作为视觉参考。
- 不允许继续修改这条路径。
- 不允许把它当成 image-only 成功证明。

### 2.2 当前 K35 image-only / official-postprocess 基线还有问题

主要对照目录：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/03_k35_image_only_window000_baseline`

关键 PLY：

- `window000_glb_style_first_35_rgb.ply`
- `window000_npz_streaming_first_35_rgb.ply`

这些文件用于观察 K35 window000 在官方风格 GLB / NPZ downstream 下的点云表现。当前主要问题包括：

- 多帧看到同一表面时，点云会变厚/重叠。
- 某些输出里主体物和地板形状不稳定。
- 过去尝试过暗块清理、连通域、地板保护等补偿方法，但已经明确禁止继续作为修复方向。

### 2.3 full414 参考

完整 414 帧 official save-frame downstream 参考在：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/04_full414_official_save_reference/overlap18_official_save_full414_npz_streaming_rgb.ply`

preview：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/04_full414_official_save_reference/overlap18_official_save_full414_npz_streaming_views.png`

report：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/04_full414_official_save_reference/official_save_sequence_pointcloud_report.json`

关键指标：

- `point_count`: 1220024
- `per_frame_depth_mean.count`: 414
- `per_frame_conf_mean.count`: 414
- `camera_center_diag`: 2.9042959213256836

这个用于完整场景视觉检查，不是证明 image-only 已完成。

## 3. 关于输入帧序列的现状

当前 Research 的 414 帧 manifest：

`data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_input_manifest.json`

当前窗口文件：

`data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_k_windows.json`

这个 manifest 有 414 帧，但不是原始 every-frame 连续相机帧。它的前 70 个 frame id 是：

`cap-1, cap-3, cap-5, cap-7, cap-21, cap-23, cap-29, cap-31, cap-33, cap-35, cap-37, cap-39, cap-42, cap-44, cap-48, cap-50, cap-52, cap-54, cap-56, cap-74, cap-78, cap-80, cap-96, cap-103, cap-105, cap-107, cap-109, cap-114, cap-116, cap-118, cap-122, cap-124, cap-126, cap-128, cap-131, cap-136, cap-138, cap-140, cap-142, cap-144, cap-148, cap-167, cap-190, cap-192, cap-194, cap-196, cap-198, cap-205, cap-207, cap-210, cap-214, cap-212, cap-216, cap-220, cap-222, cap-224, cap-227, cap-230, cap-235, cap-257, cap-260, cap-263, cap-272, cap-274, cap-280, cap-288, cap-291, cap-296, cap-310, cap-312`

注意这里有跳帧，也有 `cap-214` 到 `cap-212` 的倒序。

官方 DA3 streaming 的 chunk 语义是对 `img_list` 做连续切片，例如：

`chunk_image_paths = self.img_list[start_idx:end_idx]`

因此必须区分三件事：

1. 原始拍摄 every-frame 连续序列。
2. Research 当前筛选后的 414 帧 image list。
3. 官方 streaming 对 image list 的连续 chunk。

新会话不要把“官方 streaming 对筛选后 image list 连续切片”误认为“原始相机帧连续”。

但是也不要擅自设计连续性筛选算法。目标是确认官方 image-only 到底如何接受 image list，以及本地路径哪里偏离官方。

## 4. 相机位姿 / AR 相关事实

`photo_bundle.json` 中有 `cameraTransform`。Research 的 manifest 中也有 `cameraExtrinsicOpenCvW2c4x4`。

之前发现过一个强嫌疑：

- Research 生成官方 manifest 时，会把 `cameraTransform` 显式转换成 `opencv_w2c`。
- APP native 之前看起来可能把 frame 里的 `cameraTransform` 原样塞进 CoreML extrinsics。

这对外部 pose 路线很关键，但新路线是纯 image-only，所以原则上不应该再喂任何外部 extrinsics/intrinsics 作为 pose 输入。

你必须先确认官方 DA3 image-only 的真实调用方式：

- 是否只传 `images`
- 是否不传 `extrinsics`
- 是否不传 `intrinsics`
- 是否由模型内部 `cam_dec` / pose head 估计相机
- 官方后处理是否还会做 `align_poses_umeyama`
- 如果没有输入相机，官方如何确定尺度和坐标系

确认之后再对齐本地。

## 5. 相关脚本

优先阅读这些脚本，不要盲改：

- `tools/python/official_pytorch_k_sweep.py`
  - 当前外部 pose 稳定版相关。
  - 会传外部 extrinsics/intrinsics。
  - 不要再把它当纯 image-only。

- `tools/python/coreml_pytorch_official_filter_pointcloud_compare.py`
  - 生成 PyTorch/CoreML GLB-style 对比 PLY。

- `tools/python/strict_k35_window_official_filter_micro_audit.py`
  - window 级 GLB / NPZ style micro audit。
  - 用于导出 PLY 和报告。

- `tools/python/official_save_sequence_pointcloud_export.py`
  - full414 official save-frame downstream 导出。

- `tools/python/make_official_k35_streaming_capture.py`
  - official streaming capture/window 构建相关。

- `tools/python/make_strict_k35_timestamp_capture.py`
  - 当前 strict timestamp capture 相关。

- `tools/python/make_official_k35_fixed_save_capture.py`
  - fixed K35 official save capture 相关。

- `tools/python/export_da3_image_only_coreml.py`
  - CoreML image-only 导出相关。

- `tools/python/coreml_official_postprocess_export.py`
  - CoreML official postprocess 相关。

官方代码优先读：

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py`
- 官方 `DepthAnything3.inference` 实现
- 官方 input processor
- 官方 `npz_output_process.py`
- 官方 GLB/PLY export 相关代码

## 6. 已经归档的重要报告

交接包报告目录：

`data/official_da3_base_k35_strict_seq_2026_06_02/handoff_2026_06_05_image_only_official_repro/05_relevant_reports`

先读这些：

- `official_da3_copy_paste_parity_ledger_zh.md`
- `official_da3_cpp_preprocess_kernel_parity_audit_zh.md`
- `official_da3_dart_input_continuity_risk_contract_audit_zh.md`
- `official_da3_external_camera_branch_parity_audit_zh.md`
- `official_da3_image_only_coreml_export_kit_manifest_zh.md`
- `official_da3_image_only_multi_window_overlap_summary_zh.md`
- `official_da3_image_only_overlap_regression_gate_zh.md`
- `official_da3_preprocess_pixel_parity_audit_zh.md`

## 7. 具体工作方式

请按这个顺序做：

1. `git status`，确认 Research 工作区状态。
2. 读 `AGENTS.md`。
3. 读本交接包 README 和提示词。
4. 找官方 DA3 image-only 最小调用方式。
5. 写一个最小 oracle：只用官方 PyTorch image-only，不传外部 pose，先跑一个小 K 或小窗口。
6. 导出 PLY，复制到 Desktop，打开给用户看。
7. 视觉可接受后，再迁移到 K35。
8. 再考虑 CoreML/mobile 路径。

每次改动前说明你准备改什么；每次改动后必须有可见 PLY。

不要再出现“一次改很多轴，最后不知道谁导致视觉变差”的情况。

## 8. 验收标准

新会话阶段性验收不是“报告写得好”，而是：

- 能确认当前路径是否真的纯 image-only。
- 能确认没有传外部 AR/VIO pose。
- 能跑出一个官方 image-only PLY。
- PLY 肉眼比当前问题基线更接近用户想要的效果。
- 如果变差，能明确回滚到上一版。

最终产品方向：

- 手机 CPU 可运行。
- K35 是重要产品约束。
- 不依赖 AR。
- 跨 iOS / Android / 鸿蒙 / Windows / 笔记本。
- Python / C++ 可以保留，只要跨平台可用；不需要硬改成 Dart。
- Dart 主要用于那些 Native/Swift 不好跨平台的部分。

## 9. 重要提醒

用户现在最不接受的是“你自己设计补偿算法，然后视觉越来越烂”。请把这句话当成硬边界：

**只复刻官方。找不同。改不同。每一步 PLY 可视化。坏了回滚。**
