# Official DA3 APP Pointcloud Execution Layer Audit

日期：2026-06-05

## 结论

- APP `DepthStage` 执行层已经按 `downstreamFrameIDs` 过滤 native/CoreML 返回的窗口帧，再写入 frame-keyed `depth_index.json`。
- iOS `Da3DepthPlugin.swift` 只负责 CoreML 推理和写 `relative_depth/confidence/pred_pose` 二进制文件；它不直接生成 PLY，也不决定 downstream 选帧。
- APP `PointCloudStage` 当前仍是 `stub_contract_only`：只写空 `pointcloud.ply` 和 stage contract，不是真正的点云生成器。
- 本轮已补强 APP `PointCloudStage` contract：未来真实 executor 必须只消费 `stages/depth/depth_index.json frames[]`，不得重读 full K window reports 或 merge withheld slots。
- APP 已新增单测锁住这条 contract：`pointcloud stage contract forbids full-K window merge inputs` 已通过。
- 因此目前不能说 APP 主仓库已经实现了最终官方化 pointcloud builder；只能说 depth stage 的 `depth_index.json` 输入已按官方 core-frame/downstream 语义收敛。
- Research 的 `official_save_sequence_pointcloud_export.py` 是当前最接近官方 `results_output/frame_*.npz + npz_output_process.py` 的实际点云导出器：point-cloud only，无 mesh/cleanup。

## APP 证据

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1209-1240`
  - `final downstreamFrameIDs = _downstreamFrameIDsForWindow(window);`
  - `windowReports` 记录 `officialSaveFrameIDs` 和 `downstreamFrameIDs`
  - 遍历 `result.frames` 时，如果 `frameID` 不在 `downstreamFrameIDs`，直接 `continue`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1404-1511`
  - 最终 `depth_index.json` 的 `frames` 来自 `orderedResults`
  - `geometry_contract.downstream_consumers` 仍声明 pointcloud/mesh/texture/highlight 消费 depth_index
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1621-1653`
  - `PointCloudStage` 注释仍是 TODO
  - 当前写 `status: stub_contract_only`
  - 输出空 `pointcloud.ply`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1788-1827`
  - pointcloud stage spec 规划了 `voxel_size_m/confidence_min_policy/windowToRootSim3/metricDepthPath`
  - 这些属于产品 pointcloud builder 规格，不是官方 DA3 单 window 去厚算法。
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1620-1623`
  - 新 contract 注释要求未来 executor 只消费 `depth_index.json frames[]`
  - 明确不得重读 full K window reports 或 merge withheld slots。
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:1796-1848`
  - 新 stage spec 写入 `official_replication_boundary`
  - `forbidden_inputs` 包括 `mac_da3_window_reports.json full K frames`、未经 `depth_index frames[]` 过滤的 `da3_k_windows.json frameIDs`、`withheldForNextOverlapFrameIDs`、native-side frame selection policy
  - `product_adaptation_not_official_da3` 包括 metric meter alignment、voxel/downsample/outlier/normal/quality gates。
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:120-360`
  - native plugin 读取固定 K 帧、准备 CoreML input、运行模型、写 depth/conf/pose tensor 文件并返回 frame payloads
  - 不生成 PLY，不做官方 save-index/downstream 选择。

## Research 证据

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/coreml_official_postprocess_export.py:324-390`
  - `official_downstream_ids()` 优先读取 `downstreamFrameIDs` / `officialSaveFrameIDs`
  - `merge_selected()` 会跳过非 downstream 帧
  - `write_depth_index_like_raw()` 写入官方 postprocess 后的 `depth_index.json`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/official_save_sequence_pointcloud_export.py`
  - 使用 official save rows
  - 应用 `npz_output_process.py + save_confident_pointcloud_batch` 风格的 confidence threshold 和 reservoir sampling
  - 明确 no cleanup / no Poisson / no mesh。

## 对当前厚层问题的含义

- APP 主仓库当前还没有真正的 pointcloud builder，因此 APP 侧不是“已经生成最终点云但 full-chunk merge 走错了”。
- 当前可量化厚层主要来自 Research 的 official-save/NPZ-style 导出和官方 PyTorch image-only 对照。
- 产品下一步如果实现 pointcloud builder，应从 `stages/depth/depth_index.json frames[]` 读取，而不是从 `mac_da3_window_reports.json` 的全 K slots 直接 merge。
- 如果引入 `voxel_downsample/statistical_outlier_prune/normal_estimation`，必须报告为 product adaptation，不能标成 DA3 官方去厚。

## 当前状态

- `DepthStage downstream selection`: aligned enough for current pose-conditioned product path.
- `APP pointcloud builder`: not implemented, stub only, but future executor contract now forbids full-K merge input.
- `Research official-save pointcloud export`: implemented for diagnostics.
- `Official image-only CoreML`: missing; current app model remains `DA3BASE_476x742_N35_pose`.

## 验证

已执行：

```bash
cd /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter
dart format lib/pipeline/local_pipeline_runner.dart
dart format test/local_pipeline_runner_test.dart
dart analyze lib/pipeline/local_pipeline_runner.dart
dart analyze lib/pipeline/local_pipeline_runner.dart test/local_pipeline_runner_test.dart
flutter test test/local_pipeline_runner_test.dart --plain-name "pointcloud stage contract forbids full-K window merge inputs"
```

结果：`dart analyze` no issues found；目标 Flutter 单测 `All tests passed!`。
