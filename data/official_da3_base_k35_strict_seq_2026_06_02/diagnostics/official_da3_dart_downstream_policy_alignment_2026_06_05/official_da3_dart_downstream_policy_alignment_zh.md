# Official DA3 Dart Downstream Policy Alignment

日期：2026-06-05

## 结论

- Dart capture package 已经把官方 `save_depth_conf_result` 的 core-frame/downstream 语义落到 `officialSaveFrameIDs` 和 `downstreamFrameIDs`。
- 对 `K=35, overlap=18`，window_016 的 smoke 断言是：chunk `f272..f306`，downstream 保存 `f272..f288`，withheld for next overlap 是 `f289..f306`。
- 这个行为匹配官方 `overlap_s=0, overlap_e=overlap` 的保存方式：当前 chunk 保存头部，尾部 overlap 留给下一 chunk 的头部 downstream。
- continuity quarantine 仍被标注为 `research_continuity_quarantine_counterfactual_v1`，不是官方默认 DA3-Streaming 行为。
- 没有把产品侧 `voxel_downsample/statistical_outlier_prune` 伪装成官方 DA3 去厚；它们仍属于 pointcloud preflight/product adaptation。

## 本地源码证据

- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:303-313`
  生成 `officialSaveLocalIndices` 并映射为 `officialSaveFrameIDs`。
- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:344-370`
  写入 `officialChunkFrameIDs`、`officialSaveFrameIDs`、`downstreamFrameIDs`，并声明 native 可以算全 K slots，但 Dart 只索引 officialSaveFrameIDs。
- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:1307-1320`
  `_officialSaveLocalIndices`：单 chunk 保存全量；多 chunk 非末尾保存 `[0, rawFrameCount - overlap)`；末尾保存全量。
- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:1347-1381`
  quarantine variant 的 `selectionMode` 是 `research_continuity_quarantine_counterfactual`，并用 `realFrameCount` officialSaveLocalIndices。

## Smoke 验证

已执行并通过：

```bash
cd /Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services
dart run example/da3_official_streaming_window_plan_smoke.dart
dart run example/da3_continuity_quarantine_window_plan_smoke.dart
```

关键断言来自：

- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/example/da3_official_streaming_window_plan_smoke.dart:40-64`
  - chunkSize `35`
  - overlap `18`
  - step `17`
  - windowCount `24`
  - window016 start/end `272/307`
  - officialSaveFrameIDs first/last `f272/f288`
  - withheld first/last `f289/f306`
- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/example/da3_continuity_quarantine_window_plan_smoke.dart:53-68`
  - quarantine kind `research_continuity_quarantine_counterfactual_v1`
  - riskySourceWindowCount `1`
  - variants prefix/segment/dropRisk are generated as research counterfactuals.

## 风险边界

- 这证明 Dart package 的 window/downstream policy 对齐官方 `save_depth_conf_result` 语义。
- 这不证明 APP 主仓库所有实际点云消费者都已经只消费 `downstreamFrameIDs`；本轮快速搜索 APP 主仓库没有得到可用输出，不能过度声明。
- 这也不证明 core-frame 能去厚。官方 PyTorch image-only 对照已经显示 core-like K17 的 NPZ minor/k10 仍为约 `1.502x`。

## 下一步

- 把 APP/Research 的实际 pointcloud builder 入口继续收敛到 `downstreamFrameIDs`/`depth_index.json`，并在报告里把任何 voxel/outlier/mesh cleanup 标成产品适配，不标成 DA3 官方上游或官方 downstream。
- 继续优先关闭官方 image-only cam_dec/CoreML artifact gap；当前 `DA3BASE_476x742_N35_pose` 仍是 pose-conditioned compatibility path。
