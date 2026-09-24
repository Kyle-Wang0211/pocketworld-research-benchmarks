# Official DA3-Streaming overlap / pointcloud 对齐更新

日期：2026-06-04

## 结论

当前证据不支持“官方 DA3-Streaming 在单个 window/chunk 内有隐藏的点云去重、体素融合、TSDF 融合或几何薄化步骤”这个假设。

官方路径里能确认的处理是：

- 上游窗口：`get_chunk_indices` 只按 `chunk_size / overlap` 做顺序滑窗。
- 相邻拼接：用 overlap point maps 做 dense Sim3，随后累积并应用到后续 chunk。
- 非重叠输出：`save_depth_conf_result` 和 `save_camera_poses` 只保存每个 chunk 的 non-overlap/core frames。
- 点云筛选：`save_confident_pointcloud_batch` 只做 confidence mask、`sample_ratio` reservoir sampling，然后写 PLY。
- PLY 合并：`merge_ply_files` 只是拼接各 chunk PLY 的 vertex payload，不做空间去重。

需要特别区分官方的两条 PLY 路径：

- 官方 CLI 默认 `da3_streaming.py` 最后写 `pcd/combined_pcd.ply`：
  - 每个 `pcd/*_pcd.ply` 是整 chunk 的点云。
  - 对齐后的后续 chunk 会应用 cumulative Sim3。
  - 但 overlap slots 没有被裁掉。
  - 最后的 `merge_ply_files` 只是二进制拼接 vertex payload。
- 官方 downstream `results_output/frame_*.npz + npz_output_process.py`：
  - `save_depth_conf_result` 只保存 non-overlap/core frame。
  - `save_camera_poses` 也只给这些 core frame 写 C2W/intrinsics。
  - `npz_output_process.py:create_point_cloud` stack 这些 saved frames，再做一次全局 confidence threshold + sample。

因此，如果目标是“按官方已有逻辑减少跨 chunk overlap 重复帧”，应复刻 `results_output + npz_output_process.py` 这条 core-frame downstream 路径；如果复刻官方 CLI 默认 `combined_pcd.ply`，则它本身会保留 overlap frame 的重复点云。

因此，K35 单 window 内已经出现的厚层，更可能来自该 window 内部的 pose/scale/point-map 展开误差，而不是某个后续“官方去重模块”没有接上。

## 官方代码证据

本地 vendor：`tools/vendor/official_da3_streaming`。

- `da3_streaming.py`
  - `get_chunk_indices`: 默认 `chunk_size=120, overlap=60`；移动路线缩成 K35/18 是容量适配，不是官方默认。
  - `save_depth_conf_result`: first/middle chunk 保存 `chunk_len - overlap_e`；last chunk 保存剩余 real slots。
  - `process_long_sequence`: adjacent dense Sim3 在 `previous[-overlap:]` 与 `current[:overlap]` 上估计。
  - `process_long_sequence`: 即时 `pcd/*.ply` 对每个 chunk 的完整 points/conf/images 做 confidence filter + sample，不排除 overlap slots；`__main__` 里的 `merge_ply_files` 生成 `pcd/combined_pcd.ply`，也只拼接 payload。
  - `save_camera_poses`: camera pose 输出遵循 non-overlap/core frame 保存规则。
- `npz_output_process.py`
  - 从 `results_output/frame_*.npz` 和 `camera_poses.txt` 重建 downstream PLY。
  - 先 stack 所有保存帧，再用全局 `mean(confs) * conf_threshold_coef`，随后一次性 `save_confident_pointcloud_batch`。
- `loop_utils/sim3utils.py`
  - `save_confident_pointcloud_batch`: mask 是 `(conf >= threshold) & (conf > 1e-5)`；采样是 reservoir sampling。
  - `merge_ply_files`: 只统计各 PLY vertex 数并拷贝二进制数据；没有 voxel/grid/nearest-neighbor 去重。

外部核对：

- 2026-06-04 复核 `git ls-remote https://github.com/ByteDance-Seed/Depth-Anything-3.git`：
  - `refs/heads/main = 41736238f5bced4debf3f2a12375d2466874866d`。
  - `refs/pull/256/head = 641a8b7ef86dbdbcbe165299296f6687a201f4c0`，base 仍是 main `41736238...`。
- Issue #254 仍是 open，创建/更新时间都是 2026-05-12；标题直接描述 DA3-Streaming 在室内近距离宽视角视频中出现 chunk 内/跨 chunk 多重影和局部错位，当前没有官方评论或清理答案。
- Issue #12 仍是 open；评论里有用户报告 chunk stitching 后出现 double/multiple instances；官方早期回复是 DA3-Long 在计划中，并建议参考 VGGT-Long。
- PR #256 “Real-time Streaming Support for DA3-Streaming” 仍是 open，未合并进官方主线；PR body 声明 batch mode 保持原逻辑、最终 PLY 与原 pipeline 一致，未引入新的 overlap 去重/薄化算法。

## 本地 Research 证据

- `official_save_overlap_compare_2026_06_03`
  - overlap18 与 overlap06 都是 `selected_frame_count=414`。
  - 二者 `selected_duplicate_frame_count=0`。
  - overlap06 的 bbox / minor extent 略好，但没有根治厚层。
- `official_k35_window_thickness_factor_audit`
  - `window_016` 是最强嫌疑窗口。
  - `window_016` first35 相比 first10 的 pose span growth 约 `4.595x`。
  - `window_016` 的 thick layer 在单个 K35 window 内已经出现，不依赖跨 window loop。
  - confidence threshold / valid fraction 与厚层增长相关性弱；pose span 是当前更强线索。
- `official_da3_upstream_parity_status_2026_06_04`
  - 把 K35 厚层判定拆成两个分支：官方 PyTorch full K35 也厚，则是 DA3/K35 上游几何限制；官方 PyTorch 不厚而 CoreML 厚，则是 APP/CoreML 上游复刻未到位。
  - 已有 small-K hard comparison 说明 official postprocess 能解释一部分尺度/pose 语义，但 confidence 数值仍有明显差异。
  - 仍缺 `window_016` full K35 PyTorch-vs-CoreML 同窗口、同 downstream 点云路径的厚度 A/B。
- adjacent / loop Sim3 diagnostics
  - adjacent dense Sim3 与 loop 诊断能改变全局拼接，但没有证明能把 single-window thick layer 压回单表面。
  - loop 不是 first35 内部厚层的直接制造者，也不是已证实修复。

## APP 对齐更新

APP 仓库：`/Users/kaidongwang/Developer/pocketworld`。

这轮已经把 APP 点云 baseline 再往官方 downstream 语义收紧：

- K-window 默认是 `official_streaming_strict_sequential_v1`。
- 每个 window 写出 `officialSaveSlotIndices` 和 `officialCoreFrameIDs`。
- overlap slots 只作为 alignment 输入，不进入官方 core-frame 点云输出。
- `PointCloudStage` 不再是空 PLY stub。
- `PointCloudStage` 现在只消费 `officialCoreFrameIDs`。
- `PointCloudStage` 已从 per-window confidence threshold / per-window sampling 改为：
  - 全局 selected core frames 的 `mean(conf) * 0.5`。
  - `0.5` 对齐 `npz_output_process.py` CLI 默认；`0.75` 只作为 DA3-Streaming `Pointcloud_Save` full-chunk PLY config 对照。
  - 全局 selected core frames 的一次 reservoir sampling。
  - `sample_ratio=0.015`。
- `PointCloudStage` 现在优先从 `imageRelativePath` 读取 source RGB，并按 depth map 坐标最近邻取色；缺图或解码失败才退回 confidence 灰度。
- `PointCloudStage` 写出的 PLY 已改成官方一致的 `binary_little_endian 1.0` header + float32 xyz / uint8 rgb payload。
- `PointCloudStage` report 现在显式声明复刻的是 `results_output_npz_process_core_frames_downstream` 路径：
  - `official_downstream_projection_mode`: 使用 scaled relative depth + saved C2W camera pose 重投影，对齐 `npz_output_process.py:create_point_cloud`。
  - `official_downstream_overlap_policy`: 只消费 saved non-overlap/core frames。
  - `official_cli_combined_pcd_overlap_policy`: 官方 CLI `pcd/combined_pcd.ply` 是 full chunk merge，overlap slots are not removed。
  - 这样避免把官方两条 PLY 输出路径混淆。
- `PointCloudStage` official baseline 现在只读 `relativeDepthPath`：
  - 官方 `npz_output_process.py` 读取的是 DA3 `frame_*.npz` 里的 `depth`，不是 APP 的 ARKit/VIO metric 对齐深度。
  - `metricDepthPath` 被明确标记为产品 metric-alignment layer，官方 baseline exporter 不消费。
  - APP 测试里同时写入 `relativeDepthPath=1.0` 和 `metricDepthPath=10.0`，并解析 binary PLY 首点 z；结果验证 exporter 按 relative depth 输出，而不是偷用 metric depth。
- iOS CoreML `Da3DepthPlugin` 现在对 `depth_conf` 应用官方 DA3-Streaming 的 `conf -= 1.0` 语义，并把 `confidenceMode=official_da3_streaming_conf_minus_one`、`confidenceOffsetApplied=-1.0` 写入 native log / frame payload。
- Dart `DepthStage` / `PointCloudStage` 会把 confidence mode 与 offset 传入 `depth_index.json` 和 `official_pointcloud_report.json`，便于后续审计输入是否真的是官方 normalized confidence。
- `PointCloudStage` 现在写出官方 downstream 期望的 `camera_poses.txt`、`intrinsic.txt` 和 `camera_poses.ply`：
  - C2W pose 按官方 `save_camera_poses` 语义：`S @ c2w` 后 rotation 除以 Sim3 scale 做归一化。
  - `intrinsic.txt` 每行保存 `fx fy cx cy`。
  - `camera_poses.ply` 使用官方 ASCII camera-center visualization 格式。
  - 额外记录 `camera_pose_depth_scales.json`，说明官方 `save_depth_conf_result` 对后续 chunk depth 乘 cumulative Sim3 scale；APP 点云导出现在也先把 relative depth 乘该 scale，再用 saved C2W camera pose 重投影。
- `DartDenseSim3Verifier` 已用三 window 合成测试验证 adjacent transform 方向与累积：
  - 构造 `window_001` 相对 root 局部点图平移 `+2m`，`window_002` 平移 `+5m`。
  - 期望 edge `001 -> 000` 输出 `translation=-2`，edge `002 -> 001` 输出 `translation=-3`。
  - 期望 streaming accumulated `window_002 -> root` 输出 `translation=-5`。
- `PointCloudStage` 现在会尊重 `geometry_gate_blocks_downstream` / `streaming_alignment.status`：
  - dense Sim3 或 streaming alignment 不 ready 时，写出空 `pointcloud.ply` 和 `status=blocked_by_dense_sim3_alignment` 的 report。
  - 这避免在缺少 `windowToRootSim3` 时静默退回 identity，把多个 DA3 window 混成一个看似正常但几何错误的全局点云。

这更接近官方 `npz_output_process.py` 的 downstream PLY 路径。

## 仍未 100% 官方的点

- K35/18 不是官方默认 120/60；这是移动端容量限制。
- CoreML sealed `DA3BASE_476x742_N35_pose` 仍是固定尺寸/固定图，官方 PyTorch API 是动态预处理。
- 官方 `np.random` 没有显式 pointcloud seed；APP 为产品可复现性固定 seed=42。
- loop 官方默认 SALAD；商业路径不能直接捆绑 SALAD/GPL 风险实现，当前仍以 SelaVPR++ / 商业安全替代为主。
- 完整 official loop Sim3 optimizer 尚未成为 APP 的最终生产输出链路。

## 当前判断

如果目标是“先 100% 复刻官方，再做移动端优化”，下一步应该继续复刻官方链路，而不是马上加自研清理：

1. 继续确保最终 pointcloud / camera pose 只消费 official core frames。
2. 把 adjacent dense Sim3 累积应用和 camera pose 输出继续对齐官方。
3. 保持 full414 research 对照使用官方 downstream global threshold/sample。
4. 在 baseline 证据稳定后，再把 voxel / surfel / temporal fusion 作为“官方之外的移动端产品层改进”单独开关化。

换句话说：官方基线负责“忠实复刻”，厚层问题目前更像 DA3 K35 上游几何输出问题；真正的去重/薄化如果要做，应被明确标记为产品增强，而不是误认为官方已有步骤。
