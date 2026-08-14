# Stage 01 Portfolio Index

Stage 01 记录官方 DA3-BASE image-only 的输入预处理、深度、置信度和图像光照风险。这里不做点云、不做 PLY、不做融合。

## 快速查看

| Output | Path |
|---|---|
| 原始照片 contact sheet | `contact_sheets/00_original_rgb_contact.jpg` |
| DA3 processed RGB contact sheet | `contact_sheets/01_da3_processed_rgb_contact.png` |
| depth linear contact sheet | `contact_sheets/02_depth_linear_contact.png` |
| depth log contact sheet | `contact_sheets/03_depth_log_contact.png` |
| confidence contact sheet | `contact_sheets/04_confidence_contact.png` |
| highlight/dark overlay contact sheet | `contact_sheets/05_highlight_dark_overlay_contact.png` |
| summary panel contact sheet | `contact_sheets/06_summary_panel_contact.jpg` |
| confidence-minus-1 log contact sheet | `contact_sheets/07_confidence_minus1_log_contact.png` |
| metrics table | `tables/window_000_stage01_depth_conf_highlight_metrics.csv` |
| visual manifest | `tables/per_frame_visual_manifest.json` |
| full report | `stage01_depth_conf_photometric_report.json` |

## Per-Frame Visual Sets

每组都有 35 张图：

- `per_frame/original_rgb/`
- `per_frame/processed_rgb/`
- `per_frame/depth_linear/`
- `per_frame/depth_log/`
- `per_frame/confidence/`
- `per_frame/confidence_minus1_log/`
- `per_frame/highlight_dark_overlay/`
- `per_frame/summary_panel/`

## Raw Official Prediction Arrays

`raw_official_prediction_arrays/` 中保留 Stage 02 需要继续消费的官方预测数组：

- `pytorch_depth.npy`
- `pytorch_conf.npy`
- `pytorch_processed_images.npy`
- `pytorch_intrinsics.npy`
- `pytorch_extrinsics.npy`

这些数组来自同一 `window_000`、同一 K35 frame order、同一 official image-only PyTorch run。
