# Official DA3 image-only CoreML target export runbook

日期：2026-06-05

## 目的

这份 runbook 只做一件事：

> 生成固定目标 `DA3BASE_280x504_N35_image_only.mlpackage/.mlmodelc`，用于真正复刻官方 DA3-Streaming image-only baseline。

它不是 K/尺寸搜索，也不是产品调参。目标固定：

- model: `DA3-BASE`
- window: `K35`
- input: `280x504`
- preprocess: official `process_res=504` + `upper_bound_resize` + patch14 align
- CoreML input signature: exactly `image`
- forbidden inputs: `extrinsics`, `intrinsics`
- output signature: `depth`, `depth_conf`, `pred_extrinsics`, `pred_intrinsics`
- semantics: `net(image, None, None, [], False, False, "saddle_balanced")`

## 为什么不能在当前本机继续硬转

当前本机：

- model: `Mac15,6`
- unified memory: `18 GiB`

固定目标资源下限：

- patch grid: `20x36`
- global tokens: `25235`
- attention heads: `12`
- single global attention fp16 score buffer floor: `14.23 GiB`
- single global attention fp32 score buffer floor: `28.47 GiB`

已有 probe：

- K35 `280x504` image-only PyTorch dry-run: pass, output shapes `[1,35,280,504]`, `[1,35,280,504]`, `[1,35,3,4]`, `[1,35,3,3]`
- K35 `280x504` target package: missing
- K35 static probe conversion succeeds at smaller probe sizes, but target conversion has not produced the fixed package on this 18GiB Mac

因此，在当前 18GiB Mac 上继续硬转 `280x504` 目标包仍然风险很高。需要更大内存的 macOS/CoreML conversion 环境，或者官方 memory-efficient attention/conversion 路径。这里讨论的是 CoreML 导出/转换中间内存，不是手机/平板/笔记本的最终运行内存门槛。

## 推荐导出环境

优先：

- Apple Silicon Mac with `64 GiB` unified memory or higher
- macOS + Xcode command line tools available
- Python 3.11 environment with `coremltools`

可尝试但风险高：

- Apple Silicon Mac with `32 GiB` unified memory

不推荐作为 CoreML packaging 环境：

- A100/H100-only Linux box

A100/H100 只适合单独关闭“官方 PyTorch reference gate”，不适合作为 CoreML package 的转换、编译和签名验收环境；它也不是移动端产品运行门槛。

## 需要带到导出环境的最小输入

代码和模型：

- Research repo: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`
- APP repo: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter`
- Official DA3 repo: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`
- DA3-BASE checkpoint/config dir: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE`

关键脚本：

- `tools/python/export_da3_image_only_coreml.py`
- `tools/python/da3_image_only_coreml_readiness_gate.py`
- `tools/python/da3_mac_window_export.py`
- `tools/python/da3_image_only_overlap_regression_gate.py`

关键 capture：

- `data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict`

目标输出位置：

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage`

## 导出命令

在 Research repo 根目录运行：

```bash
python3.11 tools/python/export_da3_image_only_coreml.py \
  --official-da3-repo /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3 \
  --model-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE \
  --out-model /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage \
  --window-size 35 \
  --height 280 \
  --width 504 \
  --dry-run \
  --convert \
  --compute-precision float16 \
  --minimum-deployment-target iOS18 \
  --static-shape-export-patches \
  --allow-duplicate-openmp \
  --out-report data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/target_280x504_image_only_export_report.json
```

## 成功产物

必须存在：

- `DA3BASE_280x504_N35_image_only.mlpackage`
- `target_280x504_image_only_export_report.json`

`target_280x504_image_only_export_report.json` 必须满足：

- `dry_run.status == "pass"`
- `conversion.status == "pass"`
- `contract.coreml_inputs == ["image"]`
- `contract.forbidden_coreml_inputs == ["extrinsics", "intrinsics"]`
- outputs include `depth`, `depth_conf`, `pred_extrinsics`, `pred_intrinsics`

## 签名验收

生成包以后，在 APP/Research 当前环境跑 readiness gate：

```bash
python3.11 tools/python/da3_image_only_coreml_readiness_gate.py \
  --app-repo /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter \
  --capture-services-dir /Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05 \
  --date 2026-06-05
```

必须从当前 fail 变成 pass，至少满足：

- image-only CoreML model count >= 1
- required inputs exactly `image`
- no `extrinsics`
- no `intrinsics`
- selected/policy path can recognize `DA3BASE_280x504_N35_image_only`

## 同 capture 导出

readiness pass 以后，跑同一 capture 的 image-only CoreML 输出：

```bash
python3.11 tools/python/da3_mac_window_export.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \
  --model /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage \
  --compute-unit all \
  --resume
```

输出 `depth_index.json` / `mac_da3_window_reports.json` 必须显示：

- `da3_input_contract == "image_only"`
- model resource is `DA3BASE_280x504_N35_image_only`
- `window_016` has 35 completed frames
- output files include depth/conf/pred_extrinsics/pred_intrinsics

## 厚层判案 gate

image-only 输出存在以后，跑原始问题的 regression gate：

```bash
python3.11 tools/python/da3_image_only_overlap_regression_gate.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --pose-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict \
  --image-only-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05 \
  --window-id window_016 \
  --npz-conf-threshold-coef 0.5
```

判读：

- `pass_image_only_reduced_single_window_thickness`: `_pose`/AR/pose-conditioned path 是主嫌，official image-only 解决或明显减轻厚层。
- `fail_image_only_did_not_reduce_single_window_thickness`: 更强地支持 DA3-BASE/K35/该 capture 的上游几何一致性限制。
- 任何 missing-output / wrong-contract 状态都不能判案。

## 禁止事项

- 不要用 `DA3BASE_476x742_N35_pose.mlpackage` 冒充 official image-only baseline。
- 不要用 identity extrinsics 冒充 image-only。
- 不要把 ARKit/VIO cameraTransform 喂入 official baseline。
- 不要把 K35 小尺寸 probe 包替代固定目标。
- 不要在这个 gate 关闭前加入 voxel/TSDF/surfel cleanup 并声称是官方复刻。

## 完成定义

这条 runbook 只有在以下全部满足时才算完成：

1. `DA3BASE_280x504_N35_image_only.mlpackage/.mlmodelc` 存在。
2. readiness gate pass。
3. Mac exporter 用 image-only 包跑完同一 capture/window。
4. overlap regression gate 对 `window_016` 产生 pass/fail 判案。
5. closure matrix 从 `not_closed_missing_target_image_only_coreml` 更新到下一状态。
