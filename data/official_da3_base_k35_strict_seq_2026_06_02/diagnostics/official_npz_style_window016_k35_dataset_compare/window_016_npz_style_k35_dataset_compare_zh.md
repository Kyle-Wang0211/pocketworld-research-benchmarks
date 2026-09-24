# Official npz-style K35 Dataset Compare

日期：2026-06-04

## 范围

- 模拟 DA3-Streaming `results_output/frame_*.npz + npz_output_process.py` downstream 口径。
- 对所有数据显式应用 `conf += -1.0`，对应官方 `predictions.conf -= 1.0`。
- 使用 `mean(conf) * 0.75` 和 `sample_ratio=0.015`。
- 注意：这份报告现在作为 `0.75` streaming-config sensitivity 对照保留；PocketWorld canonical core-frame `npz_output_process.py` baseline 使用 CLI 默认 `0.5`，见 `diagnostics/official_npz_style_window016_k35_dataset_compare_coef050/` 和 `diagnostics/official_npz_threshold_coef_sensitivity_2026_06_04/`。
- 不做 voxel、TSDF、surfel、mesh、法线过滤或自研去重。

## Outputs

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_style_window016_k35_dataset_compare/window_016_npz_style_contact_sheet.png`

## Metrics

| dataset | shape | threshold | valid frac | points | bbox diag | PCA minor | minor/major | conf median after offset |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| coreml_official_postprocess | 35x476x742x3 | 2.89735 | 0.504206 | 93492 | 1.54741 | 0.841233 | 0.91234 | 2.99219 |
| pytorch_fixed_photos_depth | 35x168x252x3 | 1.3134 | 0.50922 | 11318 | 1.61227 | 0.796032 | 0.856138 | 1.4074 |
| pytorch_highres_official_dynamic | 35x140x252x3 | 1.03032 | 0.490848 | 9091 | 1.55895 | 0.78343 | 0.841653 | 0.954635 |

## Ratios

- CoreML / PyTorch fixed: bbox `0.95977`, PCA minor `1.05678`, valid fraction `0.990153`, threshold `2.206`
- CoreML / PyTorch highres: bbox `0.992602`, PCA minor `1.07378`, valid fraction `1.02721`, threshold `2.81209`
- PyTorch fixed / highres: bbox `1.03421`, PCA minor `1.01609`, valid fraction `1.03743`, threshold `1.27475`

## 初步判读

按 DA3-Streaming sensitivity 口径先做 conf -= 1.0，再用 mean(conf)*0.75 和 sample_ratio=0.015。CoreML/PyTorch fixed bbox diag=1.54741/1.61227，PCA minor=0.841233/0.796032，CoreML/fixed bbox ratio=0.95977。PyTorch fixed/highres bbox ratio=1.03421，highres bbox diag=1.55895。如果这个口径下 CoreML 仍没有相对 PyTorch 成倍变厚，就继续支持“厚层主要是 K35 上游几何一致性限制，而不是下游漏了官方去重”。canonical `npz_output_process.py` CLI 默认 `0.5` 对照见 `official_npz_style_window016_k35_dataset_compare_coef050`。
