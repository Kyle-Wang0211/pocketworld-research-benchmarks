# Official DA3 image-only CoreML export kit manifest

日期：2026-06-05

## 结论

- status: `ready_to_transfer_export_kit`
- target image-only CoreML exists: `False`
- pose compat CoreML exists: `True`
- missing required items: ``

这份清单用于把固定目标导出任务迁移到大内存 Mac/CoreML 环境。它不改变 K/尺寸，也不允许用 `_pose` 或小尺寸 probe 替代目标。

## 推荐环境

- preferred unified memory: `64 GiB`
- risky minimum unified memory: `32 GiB`
- current local unified memory: `18.0 GiB`
- A100/H100 role: PyTorch reference gate only, not CoreML packaging or mobile runtime
- note: This is a CoreML conversion/export envelope, not the product runtime memory requirement. Current local 18 GiB Mac has failed/preflighted as risky.

## Kit items

| id | exists | size | role |
|---|---:|---:|---|
| `research_tools_python` | `True` | `2.16 MiB` | all Python export/gate scripts |
| `capture_dir` | `True` | `856.94 MiB` | same capture used for window_016 overlap regression |
| `official_da3_repo` | `True` | `47.51 MiB` | official DA3 source for wrapper import and parity audit |
| `da3_base_model_dir` | `True` | `516.47 MiB` | DA3-BASE checkpoint/config; commercial-safe model |
| `coreml_models_dir` | `True` | `804.41 MiB` | CoreML output directory and current pose compat package |
| `swift_plugin` | `True` | `40.00 KiB` | APP native CoreML adapter evidence |
| `local_runner` | `True` | `120.00 KiB` | APP local pipeline gate evidence |
| `capture_services_dir` | `True` | `10.09 MiB` | capture service package for policy/readiness source |
| `capture_policy` | `True` | `68.00 KiB` | Dart policy source used by readiness gate |
| `target_export_runbook` | `True` | `8.00 KiB` | human runbook for fixed target export |
| `target_export_gate` | `True` | `28.00 KiB` | local resource preflight evidence |

## transfer_from_current_mac

```bash
export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit
mkdir -p "$DA3_EXPORT_KIT_ROOT"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/" "$DA3_EXPORT_KIT_ROOT/research/tools/python/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/" "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/" "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_gate_2026_06_05/" "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_gate_2026_06_05/"
rsync -a "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/" "$DA3_EXPORT_KIT_ROOT/official/Depth-Anything-3/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE/" "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/" "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift" "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Da3DepthPlugin.swift"
rsync -a "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart" "$DA3_EXPORT_KIT_ROOT/app/lib/pipeline/local_pipeline_runner.dart"
rsync -a "/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/" "$DA3_EXPORT_KIT_ROOT/packages/aether_capture_services/"
```

## run_on_large_memory_mac

```bash
export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit
cd "$DA3_EXPORT_KIT_ROOT/research"
mkdir -p data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04
python3.11 tools/python/export_da3_image_only_coreml.py \
  --official-da3-repo "$DA3_EXPORT_KIT_ROOT/official/Depth-Anything-3" \
  --model-dir "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE" \
  --out-model "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage" \
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

## verify_on_large_memory_mac

```bash
export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit
cd "$DA3_EXPORT_KIT_ROOT/research"
python3.11 tools/python/da3_image_only_coreml_readiness_gate.py \
  --app-repo "$DA3_EXPORT_KIT_ROOT/app" \
  --capture-services-dir "$DA3_EXPORT_KIT_ROOT/packages/aether_capture_services" \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05 \
  --date 2026-06-05
python3.11 tools/python/da3_mac_window_export.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \
  --model "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage" \
  --compute-unit all \
  --resume
python3.11 tools/python/da3_image_only_overlap_regression_gate.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --pose-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict \
  --image-only-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05 \
  --window-id window_016 \
  --npz-conf-threshold-coef 0.5
```

## return_artifacts_to_current_mac

```bash
export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit
rsync -a "$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage" "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/"
rsync -a "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/target_280x504_image_only_export_report.json" "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/"
rsync -a "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline/" "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline/"
rsync -a "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05/" "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05/"
rsync -a "$DA3_EXPORT_KIT_ROOT/research/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05/" "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05/"
```

## 完成定义

- `DA3BASE_280x504_N35_image_only.mlpackage` exists.
- readiness gate passes with required inputs exactly `image`.
- Mac exporter writes same-capture image-only output.
- overlap regression gate gives a pass/fail judgement for `window_016`.
- closure matrix no longer reports `target_missing=true`; remaining status comes from the real same-capture overlap/geometry result.
