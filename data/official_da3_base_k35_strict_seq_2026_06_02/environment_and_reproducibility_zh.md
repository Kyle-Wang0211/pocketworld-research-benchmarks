# Strict K35 baseline 环境与复现记录

日期：2026-06-02

## 仓库与 revision

- research benchmark: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`
  - branch: `main`
  - pre-experiment HEAD: `1802deafd3d28f860426d8cb86509e7acd17f537`
  - remote: `git@github.com:Kyle-Wang0211/pocketworld-research-benchmarks.git`
- product repo: `/Users/kaidongwang/Developer/pocketworld`
  - branch: `main`
  - HEAD: `a9b3428cbc0a9e978283a6403c96404e242dd04b`
- official DA3 repo: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`
  - branch: `main`
  - HEAD: `41736238f5bced4debf3f2a12375d2466874866d`

## 模型与数据

- DA3-BASE PyTorch model: `/Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE`
- DA3-BASE CoreML K35 model: `/Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage`
- source capture: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229`
- strict capture mirror: `data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict`

The strict capture mirror tracks manifests and experiment outputs. Original photo directories remain local capture assets and are referenced by manifest/symlink on the source machine.

## Python environments

CoreML export environment:

- interpreter: `python3.11`
- Python: `3.11.15`
- coremltools: `9.0`
- numpy: `2.4.2`
- Pillow: `12.2.0`

Official PyTorch DA3 environment:

- interpreter: `/Users/kaidongwang/Developer/Aether3D-cross/.venv-da3/bin/python`
- Python: `3.11.15`
- torch: `2.12.0`
- numpy: `1.26.4`
- Pillow: `12.2.0`

Observed warning: `coremltools 9.0` reports that torch `2.12.0` is newer than its tested torch range. CoreML inference was run through `coremltools.MLModel.predict`, not torch conversion.

## 新增 research-only 脚本

- `tools/python/make_strict_k35_timestamp_capture.py`
  - Sorts `photo_bundle.frames[]` by `timestamp`, rewrites sorted `photo_bundle.json` and `da3_input_manifest.json`, and creates strict K35 overlap-18 windows.
- `tools/python/strict_k35_single_window_export.py`
  - Reads CoreML `relative_depth/confidence/pred_pose` outputs, exports one window PLY/PNG and statistics.
- `tools/python/official_pytorch_window_export.py`
  - Runs official DA3 PyTorch API for the same strict window and exports low-res diagnostic arrays/PLY/PNG.

These scripts do not implement graph patch, retrieval, loop closure, Poisson, mesh, or any new DA3 algorithm.

## Commands

Create strict timestamp capture:

```bash
python3.11 tools/python/make_strict_k35_timestamp_capture.py \
  --source-capture /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229 \
  --out-capture data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --chunk-size 35 \
  --overlap 18 \
  --order-field timestamp
```

Run CoreML strict first 3 windows:

```bash
python3.11 tools/python/da3_mac_window_export.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict \
  --model /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage \
  --compute-unit cpu \
  --max-windows 3
```

Export strict CoreML `window_000`:

```bash
python3.11 tools/python/strict_k35_single_window_export.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_coreml \
  --window-id window_000 \
  --prefix strict_window_000
```

Run official PyTorch DA3 diagnostic at `process_res=252`:

```bash
/Users/kaidongwang/Developer/Aether3D-cross/.venv-da3/bin/python \
  tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/strict_window_000_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_252_export \
  --device mps \
  --process-res 252
```

## Known failure modes from this run

- CoreML `--compute-unit all` exited during `model_load_start` without Python traceback. CPU compute unit completed 3 windows.
- Official PyTorch K35 at `process_res=742` failed on MPS with `Invalid buffer size: 89.01 GiB`.
- Official PyTorch K35 at `process_res=476` failed on MPS with `Invalid buffer size: 15.36 GiB`.
- Official PyTorch K35 at `process_res=252` succeeded and is diagnostic-only, not final quality parity with CoreML K35@476x742.

## Primary report

See `strict_k35_baseline_report_zh.md`.
