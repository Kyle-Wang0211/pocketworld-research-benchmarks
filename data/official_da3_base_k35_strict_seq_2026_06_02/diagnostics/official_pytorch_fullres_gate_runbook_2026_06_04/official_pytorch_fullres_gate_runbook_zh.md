# Official PyTorch full-resolution K35 gate runbook

日期：2026-06-04

## 目的

这份 runbook 只用于关闭研究 gate：

> 同一个 `window_016`、同一批 35 帧、官方 PyTorch DA3-BASE、同分辨率输入、官方 core-frame downstream 下，官方 PyTorch 是否也出现 K35 单 window 厚层？

它不是产品硬件要求。PocketWorld 产品路径仍是手机/平板/笔记本上的 CoreML / local runtime。大显存 GPU 只用于一次性 reference A/B。

## 当前本机 blocker

Mac MPS 上官方 PyTorch global attention gate：

- `process_res=742`：`Invalid buffer size: 89.01 GiB`
- `process_res=476`：`Invalid buffer size: 15.36 GiB`
- `process_res=252`：success

这说明本机不能跑 full same-resolution K35 PyTorch hard parity；不说明 APP/CoreML 产品实现需要 89GB。

## 推荐硬件

最低不要租小显存卡来赌：

- 不推荐：consumer / workstation 约 24GB-32GB 显存级别，只能说明“可能仍会 OOM”。
- 可尝试：A100 80GB 或 H100 80GB。
- 更稳：H100/H200 级别或多卡环境，但本实验应先单卡跑通，避免分布式引入新变量。

注意：A100 80GB 不是产品门槛，只是 reference 实验机器。CUDA SDPA/flash attention kernel 可能比 MPS 内存行为更好；如果 A100 80GB 仍 OOM，则需要 H100/H200 或等待官方 memory-efficient attention 更新。

## 需要上传的最小数据

从本地 Research / APP 准备：

- `data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/`
- `data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json`
- `data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_highres_official_manifest.json`
- `tools/python/official_pytorch_window_export.py`
- `tools/python/official_npz_style_k35_dataset_compare.py`
- `tools/python/strict_k35_window_official_filter_micro_audit.py` and its helper dependencies in `tools/python/`
- APP model checkpoint directory: `ios/Runner/Models/DA3-BASE`
- Official DA3 source checkout: `Depth-Anything-3/src`

## Fixed-input hard parity command

Use fixed `photos_depth` input first because it matches the APP sealed input surface.

```bash
python tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json \
  --model-path ios/Runner/Models/DA3-BASE \
  --official-src Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_k35_742_cuda \
  --device cuda \
  --process-res 742 \
  --sample-ratio 0.015 \
  --conf-threshold-coef 0.5
```

Expected output if successful:

- `pytorch_depth.npy`
- `pytorch_conf.npy`
- `pytorch_extrinsics.npy`
- `pytorch_intrinsics.npy`
- `pytorch_processed_images.npy`
- `official_pytorch_window_000_export_report.json`

## Highres dynamic hard parity command

Then run official highres dynamic preprocessing:

```bash
python tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_highres_official_manifest.json \
  --model-path ios/Runner/Models/DA3-BASE \
  --official-src Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_highres_k35_742_cuda \
  --device cuda \
  --process-res 742 \
  --sample-ratio 0.015 \
  --conf-threshold-coef 0.5
```

## Downstream comparison

After the two PyTorch exports finish, compare them against CoreML official-postprocess using canonical `npz_output_process.py` CLI default `conf_threshold_coef=0.5`:

```bash
python tools/python/official_npz_style_k35_dataset_compare.py \
  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --coreml-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_official_save_overlap18_official_postprocess \
  --pytorch-fixed-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_k35_742_cuda \
  --pytorch-highres-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_highres_k35_742_cuda \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_style_window016_k35_fullres_cuda_compare \
  --window-id window_016 \
  --conf-threshold-coef 0.5
```

## Decision rule

If official PyTorch full-res K35 is also thick:

- Treat K35 single-window thickness as DA3/K35 upstream geometry consistency limitation.
- Stop hunting for hidden official downstream dedupe.
- Move product cleanup into a clearly labeled mobile/product layer.

If official PyTorch full-res K35 is clean but CoreML remains thick:

- Continue upstream APP/CoreML parity debugging.
- Re-check fixed input preprocessing, CoreML export, confidence scale, postprocess pose/depth scale, and intrinsics.

If the cloud GPU OOMs:

- This only means the full PyTorch hard gate remains blocked.
- It still does not mean the mobile product must require that GPU.
- Next options are larger GPU, lower-res trend gates, official memory-efficient attention update, or product-layer decision without full hard parity.
