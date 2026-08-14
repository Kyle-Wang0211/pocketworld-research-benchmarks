# Archive Audit

日期：2026-06-06

## Copy Summary

- archive root: `pocketworld_research_benchmarks/experiments/da3_base_image_only_official_repro_2026_06_06`
- total files after archive: `314`
- total size after archive: about `93M`

## Stage 01 Visual Completeness

Per-frame visual sets:

| Set | Count |
|---|---:|
| `confidence` | 35 |
| `confidence_minus1_log` | 35 |
| `depth_linear` | 35 |
| `depth_log` | 35 |
| `highlight_dark_overlay` | 35 |
| `original_rgb` | 35 |
| `processed_rgb` | 35 |
| `summary_panel` | 35 |

Contact sheets:

- `00_original_rgb_contact.jpg`
- `01_da3_processed_rgb_contact.png`
- `02_depth_linear_contact.png`
- `03_depth_log_contact.png`
- `04_confidence_contact.png`
- `05_highlight_dark_overlay_contact.png`
- `06_summary_panel_contact.jpg`
- `07_confidence_minus1_log_contact.png`

## Raw Prediction Arrays

Copied into `01_stage01_official_depth_conf_photometric/raw_official_prediction_arrays/`:

- `pytorch_depth.npy`
- `pytorch_conf.npy`
- `pytorch_processed_images.npy`
- `pytorch_intrinsics.npy`
- `pytorch_extrinsics.npy`
- `window_000_commercial_safe_image_only_report.json`
- `window_000_commercial_safe_image_only_report.md`

## Explicit Exclusions

The archive intentionally does not copy PLY/fusion products into Stage 01. Stage 01 is limited to official image-only preprocess/depth/confidence/photometric diagnostics plus raw DA3 prediction arrays needed by Stage 02.

No `.ply` file is present in the archive at the time of this audit.

## Why This Matters

This folder is meant to make the official image-only route inspectable stage by stage. If a later stage produces black blocks, thick floors, or misalignment, the diagnosis can refer back to the exact Stage 01 images, tables, and arrays saved here.
