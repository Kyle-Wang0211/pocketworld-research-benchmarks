# Official npz-style K35 Dataset Compare

日期：2026-06-04

## 范围

- 模拟 DA3-Streaming `results_output/frame_*.npz + npz_output_process.py` downstream 口径。
- 对所有数据显式应用 `conf += -1.0`，对应官方 `predictions.conf -= 1.0`。
- 使用 `mean(conf) * 0.75` 和 `sample_ratio=0.015`。
- 不做 voxel、TSDF、surfel、mesh、法线过滤或自研去重。

## Outputs

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_style_window016_k35_dataset_compare_coef050/window_016_npz_style_contact_sheet.png`

## Metrics

| dataset | shape | threshold | valid frac | points | bbox diag | PCA minor | minor/major | conf median after offset |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| coreml_official_postprocess | 35x476x742x3 | 1.93157 | 0.548702 | 101743 | 1.8225 | 1.11461 | 1.17059 | 2.99219 |
| pytorch_fixed_photos_depth | 35x168x252x3 | 0.875597 | 0.556155 | 12361 | 1.80113 | 0.900711 | 0.823108 | 1.4074 |
| pytorch_highres_official_dynamic | 35x140x252x3 | 0.686879 | 0.531838 | 9850 | 1.67697 | 0.862762 | 0.912264 | 0.954635 |

## Ratios

- CoreML / PyTorch fixed: bbox `1.01186`, PCA minor `1.23747`, valid fraction `0.9866`, threshold `2.206`
- CoreML / PyTorch highres: bbox `1.08678`, PCA minor `1.2919`, valid fraction `1.03171`, threshold `2.81209`
- PyTorch fixed / highres: bbox `1.07404`, PCA minor `1.04399`, valid fraction `1.04572`, threshold `1.27475`

## 初步判读

按 DA3-Streaming npz downstream 口径先做 conf -= 1.0，再用 mean(conf)*0.5 和 sample_ratio=0.015。CoreML/PyTorch fixed bbox diag=1.8225/1.80113，PCA minor=1.11461/0.900711，CoreML/fixed bbox ratio=1.01186。PyTorch fixed/highres bbox ratio=1.07404，highres bbox diag=1.67697。如果这个口径下 CoreML 仍没有相对 PyTorch 成倍变厚，就继续支持“厚层主要是 K35 上游几何一致性限制，而不是下游漏了官方去重”。
