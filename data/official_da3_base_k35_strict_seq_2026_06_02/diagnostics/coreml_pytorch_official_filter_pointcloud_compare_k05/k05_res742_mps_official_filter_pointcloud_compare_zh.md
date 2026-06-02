# CoreML / PyTorch Official Filter Pointcloud Compare

## 范围

- 同 K、同图、同 official GLB-style confidence/backprojection/alignment 规则。
- 不做自研过滤，不做 graph patch，不做 loop，不做 mesh。

## Outputs

- comparison png: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_k05/k05_res742_mps_coreml_vs_pytorch_glb_style.png`
- CoreML views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_k05/k05_res742_mps_coreml_views.png`
- PyTorch views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_k05/k05_res742_mps_pytorch_views.png`

## Metrics

| dataset | conf threshold | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|---:|
| CoreML | 3.85742 | 0.600239 | 1000000 | 2.71395 | 0.955185 | 0.413291 |
| PyTorch | 5.25455 | 0.600001 | 1000000 | 2.70712 | 0.896793 | 0.412165 |

## Ratios

- bbox diag CoreML/PyTorch: `1.00253`
- PCA minor CoreML/PyTorch: `1.06511`
- valid fraction CoreML/PyTorch: `1.0004`
- conf threshold CoreML/PyTorch: `0.734111`

## 初步判读

同 K、同图、同 official GLB-style filter 下比较点云。CoreML/PyTorch valid fraction=0.600239/0.600001，bbox diag=2.71395/2.70712，PCA minor=0.955185/0.896793。如果两边都出现类似厚层/暗部片状保留，漂浮更像官方模型/导出规则在这组图上的表现；如果 PyTorch 明显干净而 CoreML 更厚，再回头查 CoreML export parity。
