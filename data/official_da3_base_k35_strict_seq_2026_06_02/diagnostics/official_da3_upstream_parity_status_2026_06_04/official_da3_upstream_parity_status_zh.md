# Official DA3 上游复刻状态与 K35 厚层判定 gate

日期：2026-06-04

总决策矩阵：

- `diagnostics/official_da3_parity_decision_matrix_2026_06_04/official_da3_parity_decision_matrix_zh.md`

## 结论先行

单个 K35 window 内部多帧看到同一表面后出现厚层，当前只能判断为“上游几何输出相关”，不能直接等同于“APP 一定没复刻官方”。

它有两个分支：

1. 如果官方 PyTorch 在同一个 K35 / 同一组帧 / 同一官方 downstream 点云路径下也厚，那么这是 DA3 在 K35/mobile setting 下的几何一致性限制。
2. 如果官方 PyTorch 不厚，而 APP/CoreML 厚，那么才是 APP 上游复刻仍未到位，需要继续查 preprocessing、CoreML 输出、pose/depth/scale/confidence。

当前证据更支持继续做上游 parity gate，而不是立刻加 voxel/TSDF/surfel 这类产品层清理。

## 已经有的证据

### 1. Official postprocess 已经能解释一部分尺度差异

来源：

- `tools/python/coreml_official_postprocess_export.py`
- `diagnostics/coreml_official_postprocess_summary_zh.md`
- `diagnostics/coreml_pytorch_small_k_parity_official_postprocess/coreml_pytorch_small_k_parity_report_zh.md`

要点：

- CoreML raw 输出经过 official DA3 API 语义的 postprocess：
  - `align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)`
  - `depth = raw_depth / pose_scale`
  - `intrinsics = input_intrinsics`
  - `extrinsics = input_extrinsics[:3, :]`
- small-K hard comparison 里，`K=5 @ process_res=742` 的 depth scale 接近 `0.942614`，scaled median relative error 约 `0.0177099`。
- pose center median 为 `0`，说明 postprocessed pose/intrinsics 语义已对齐到输入相机语义。

这说明：APP/CoreML 不是完全游离于官方语义之外；官方 postprocess 已经消掉了一部分“尺度/pose 语义”差异。

### 2. Confidence 仍然不是完全一致

来源：

- `diagnostics/coreml_pytorch_confidence_edge_audit_official_postprocess/coreml_pytorch_confidence_edge_audit_report_zh.md`

要点：

- `K=5 @ process_res=742` 是同图同尺寸的 hard comparison。
- RGB 输入 MAE 约 `0.291537`，说明 saved PyTorch reference 与 CoreML 输入几乎同口径。
- confidence MAE 约 `2.23145`，Pearson 约 `0.863117`，CoreML confidence 整体比 PyTorch 低。
- 但 official GLB percentile-style valid fraction 被拉到相近：CoreML/PyTorch 约 `0.600239 / 0.600001`。

这说明：confidence 数值仍是上游 parity 风险，但它不是当前 K35 厚层的唯一解释。

### 3. 厚层与 confidence/valid fraction 的关系弱，pose span 更像线索

来源：

- `diagnostics/official_k35_window_thickness_factor_audit/official_k35_window_thickness_factor_audit_zh.md`
- `diagnostics/window_016_official_filter_micro_audit_official_postprocess/window_000_official_filter_micro_audit_report_zh.md`

要点：

- `window_016` 是当前最强嫌疑窗口。
- `window_016` first35 相比 first10 的 pose span growth 约 `4.5954x`。
- `minor_growth_vs_pose_span_growth` 约 `0.753116`，是当前最强 clue。
- `minor_growth_vs_conf_threshold_ratio` 约 `0.0296614`。
- `minor_growth_vs_valid_fraction_delta` 约 `-0.0240654`。
- `npz_streaming_style` 下，`window_016` 的 first35 PCA minor jump 出现在 first35，而不是早期 0+1、0+1+2 或 first10。

这说明：单 window 厚层更像是多帧 pose/depth/scale 一致性随窗口跨度扩大而变差，不像是某个简单 confidence 阈值没调对。

### 4. window_016 官方 PyTorch K35 低分辨率对照没有显示 CoreML 独有严重厚层

来源：

- `pytorch_vs_coreml_window_016/official_pytorch_k35_252/official_pytorch_window_000_export_report.json`
- `diagnostics/coreml_pytorch_official_filter_pointcloud_compare_window016_k35_res252/window016_k35_res252_official_filter_pointcloud_compare.json`

要点：

- 同一个 `window_016`、同一批 35 帧、官方 PyTorch DA3-BASE、`process_res=252` 可以在本机 MPS 跑通。
- 官方 PyTorch 输出：
  - processed shape：`35 x 168 x 252`
  - Umeyama scale：`0.903520`
  - camera-center diag：`1.364758`
  - sampled PLY bbox diag：`1.815001`
- 用同一套 official GLB-style point-cloud/filter 规则比较 CoreML official-postprocessed K35 与 PyTorch K35-252：
  - CoreML/PyTorch bbox diag：`2.198405 / 2.034669`
  - CoreML/PyTorch PCA minor：`0.941111 / 1.021095`
  - CoreML/PyTorch valid fraction ratio：`1.000075`
  - CoreML/PyTorch bbox diag ratio：`1.080473`
  - CoreML/PyTorch PCA minor ratio：`0.921668`

这条证据不能替代同分辨率 hard parity，因为 PyTorch 只跑到了 `process_res=252`。但它至少说明：在同 K、同帧、同 official filter 口径下，CoreML 没有表现出比官方 PyTorch 低分辨率参考严重得多的几何厚层；当前更像是 DA3/K35 上游几何一致性本身的问题，而不是一个明显的 CoreML-only 下游去重问题。

### 5. fixed 742x476 vs highres 官方动态输入：fixed 略放大，但不像主因

来源：

- `pytorch_vs_coreml_window_016/official_pytorch_highres_k35_252/official_pytorch_window_000_export_report.json`
- `diagnostics/official_pytorch_fixed_vs_highres_window016_k35_res252/official_pytorch_fixed_vs_highres_window016_k35_res252_zh.md`

要点：

- 同一个 `window_016`、同一批 35 帧、同一官方 PyTorch DA3-BASE、同一 `process_res=252`。
- fixed-input 口径：
  - 使用 APP fixed `742x476` 输入缓存 `photos_depth`
  - processed shape：`35 x 168 x 252`
  - sampled-cloud bbox diag：`1.815001`
- highres official dynamic 口径：
  - 使用 ARKit 原始 highres 图 `photos_highres`
  - 由官方 PyTorch 自己做 `upper_bound_resize`
  - processed shape：`35 x 140 x 252`
  - sampled-cloud bbox diag：`1.699973`
- fixed/highres bbox diag ratio：`1.067664`
- fixed/highres depth median ratio：`1.016097`
- fixed/highres confidence median ratio：`1.231635`
- 两边 camera-center diag 相同：`1.364758`

这说明：移动端 fixed `742x476` direct-stretch 仍是 parity 风险，确实可能略微放大点云范围和 confidence 分布差异；但低分辨率趋势证据不像是“fixed 输入单独造成严重厚层”。当前更强线索仍是 K35 上游多帧 pose/depth/scale 几何一致性。

### 6. 官方 npz downstream 口径下，CoreML 没有比 PyTorch 成倍变厚

来源：

- `tools/python/official_npz_style_k35_dataset_compare.py`
- `diagnostics/official_npz_style_window016_k35_dataset_compare/window_016_npz_style_k35_dataset_compare_zh.md`

要点：

- 这条对照模拟 DA3-Streaming `results_output/frame_*.npz + npz_output_process.py` downstream：
  - 对所有数据显式应用 `conf -= 1.0`
  - 原对照使用 `mean(conf) * 0.75`
  - 后续 sensitivity 已补 `mean(conf) * 0.5`，这是 `npz_output_process.py` CLI 默认
  - 使用 `sample_ratio=0.015`
  - 不做 voxel、TSDF、surfel、mesh、法线过滤或自研去重
- 同一个 `window_016` K35：
  - CoreML official-postprocess：bbox diag `1.547411`，PCA minor `0.841233`
  - PyTorch fixed `photos_depth`：bbox diag `1.612274`，PCA minor `0.796032`
  - PyTorch highres dynamic：bbox diag `1.558945`，PCA minor `0.783430`
- ratios：
  - CoreML / PyTorch fixed bbox：`0.959770`
  - CoreML / PyTorch fixed PCA minor：`1.056783`
  - CoreML / PyTorch highres bbox：`0.992602`
  - CoreML / PyTorch highres PCA minor：`1.073782`
  - PyTorch fixed / highres bbox：`1.034208`

这条证据比 GLB-style 对照更贴近 APP 当前要复刻的官方 downstream。它说明：按官方 npz downstream 口径走时，CoreML 没有相对官方 PyTorch 低分辨率参考出现成倍厚层。因此，“下游少了官方某个隐藏去重/融合步骤”这个方向更弱；厚层更可能来自 K35 上游多帧几何一致性限制。

## 仍未证明的关键项

### Gate A：官方 PyTorch full K35 同窗口厚度

还没有被充分证明：

- 同一个 `window_016`
- 同一批 35 帧
- 官方 PyTorch DA3-BASE
- 官方 `ref_view_strategy=saddle_balanced`
- 官方 postprocess
- 官方 `results_output + npz_output_process.py` core-frame downstream 点云路径

已尝试但受本机显存/attention buffer 限制：

- `process_res=742`，输入 shape `35 x 3 x 476 x 742`，MPS 报错 `Invalid buffer size: 89.01 GiB`。
- `process_res=476`，输入 shape `35 x 3 x 308 x 476`，MPS 报错 `Invalid buffer size: 15.36 GiB`。
- `process_res=252`，输入 shape `35 x 3 x 168 x 252`，可以跑通，作为低分辨率趋势对照。

新增 memory gate 证据：

- `diagnostics/official_pytorch_k35_fullres_memory_gate_2026_06_04/official_pytorch_k35_fullres_memory_gate_zh.md`
- 官方 DINO attention 直接走 `torch.nn.functional.scaled_dot_product_attention`。
- 官方代码中的 `block_chunks` 是 FSDP wrap 相关，不是推理时的 attention 切块。
- Python 3.11 / torch `2.12.0` 复测 `process_res=476` 仍报 `Invalid buffer size: 15.36 GiB`，说明这不是 torch `2.8.0` 单点问题。

如果这条 PyTorch full K35 也厚，那么 K35 厚层基本可以归因到 DA3/K35 上游几何能力限制。

如果它不厚，而 CoreML 厚，那么 APP/CoreML 上游复刻还没到位。

### Gate B：高分辨率官方动态预处理 vs 移动 fixed 742x476

当前 hard comparison 主要使用 `photos_depth`，也就是 APP 固定输入图。

低分辨率趋势检查已补一条：

- `window_016`、K35、`process_res=252`
- fixed `photos_depth` bbox diag：`1.815001`
- highres dynamic `photos_highres` bbox diag：`1.699973`
- fixed/highres bbox diag ratio：`1.067664`

同分辨率 hard parity 仍未证明：

- highres 原图直接走官方 `upper_bound_resize` 时，`process_res=742/476` 的 K35 输出
- 与 APP `direct_stretch 742x476` 在同分辨率下的几何影响差异
- 这种差异在同分辨率下是否会放大 window_016 的 pose/depth 不一致

这是移动端 K35 适配里最大的结构性差异之一。

### Gate C：full K35 CoreML vs full K35 PyTorch 同尺寸同输入

small-K 已经有 hard comparison，但 K35 full window 仍需要单独比较：

- depth scale / median relative error
- confidence MAE / Pearson / valid fraction
- intrinsics/extrinsics
- camera-center span
- first10 vs first35 point-cloud thickness

small-K 不能替代 full K35，因为 K35 的 ref-view、pose normalization、长窗口几何一致性都可能不一样。

## 下一步实验入口

优先做 read-only 对照，不改算法。

已补齐 `window_016` 的官方 PyTorch manifest 入口：

- fixed-input hard parity：
  - `data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json`
  - 图像来源：`photos_depth/cap-*.jpg`
  - 作用：与 CoreML 使用同一批固定 742x476 APP 输入，隔离模型/runtime/postprocess 差异。
- highres official dynamic parity：
  - `data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_highres_official_manifest.json`
  - 图像来源：`photos_highres/cell_*.jpg`
  - 作用：让官方 PyTorch 自己做 `upper_bound_resize`，检查移动 fixed input 与官方动态宽高比 API 的结构性差异。

生成命令：

```bash
python3 tools/python/make_official_pytorch_window_manifest.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --window-id window_016 \
  --image-source photos_depth \
  --out data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json

python3 tools/python/make_official_pytorch_window_manifest.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --window-id window_016 \
  --image-source photos_highres \
  --out data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_highres_official_manifest.json
```

建议的 next command 方向：

1. 用 `tools/python/official_pytorch_window_export.py` 或扩展脚本导出 `window_016` 的官方 PyTorch full K35 输出。
2. 使用与 APP baseline 一致的 official downstream core-frame PLY 逻辑：
   - relative depth
   - `conf -= 1.0`
   - saved C2W camera pose
   - global `mean(conf) * 0.5`
   - `sample_ratio=0.015`
3. 与 CoreML official-postprocessed `window_016` 做同口径对照：
   - first10 / first35 bbox
   - PCA minor extent
   - camera-center span
   - depth p95
   - confidence threshold ratio / valid fraction

可复用 window_000 旧实验的 PyTorch 参数，先跑 fixed-input hard parity：

```bash
python3 tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_k35_742 \
  --device mps \
  --process-res 742 \
  --sample-ratio 0.015 \
  --conf-threshold-coef 0.5
```

再跑 highres official dynamic parity：

```bash
python3 tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_highres_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_highres_k35_742 \
  --device mps \
  --process-res 742 \
  --sample-ratio 0.015 \
  --conf-threshold-coef 0.5
```

## 当前工程判断

- 下游方面：APP 已经更接近官方 `results_output + npz_output_process.py`，并且不再把 `metricDepthPath` 混入 official baseline。
- 上游方面：仍不能宣称 100% 官方，因为 K35 fixed CoreML、fixed 742x476、confidence 数值差异和 full K35 同分辨率 PyTorch A/B 都还没完全关 gate。
- 但新增的 `window_016` PyTorch K35-252 对照没有显示 CoreML 独有严重厚层，当前判断应从“APP 可能没复刻准”前移为“更偏 DA3/K35 上游几何一致性限制，仍缺同分辨率硬证明”。
- 新增的 highres dynamic K35-252 对照显示 fixed input 只把 bbox diag 放大约 `6.77%`，不是当前最强主因，但它仍是移动端复刻官方 API 时必须保留的风险项。
- 新增的 official npz-style 对照显示：CoreML / PyTorch fixed bbox ratio 为 `0.959770`，PCA minor ratio 为 `1.056783`；这进一步削弱“官方 downstream 有隐藏去重而 APP 没做”的解释。
- 因此，K35 单 window 厚层目前应标记为“上游几何一致性问题/限制”，而不是“已知下游缺去重”。
