# CoreML / PyTorch Official Filter Pointcloud Compare

## 范围

- 同 K、同图、同 official GLB-style confidence/backprojection/alignment 规则。
- 不做自研过滤，不做 graph patch，不做 loop，不做 mesh。

## Outputs

- comparison png: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k10_res476/highres_k10_res476_mps_coreml_vs_pytorch_glb_style.png`
- CoreML views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k10_res476/highres_k10_res476_mps_coreml_views.png`
- PyTorch views: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k10_res476/highres_k10_res476_mps_pytorch_views.png`

## Metrics

| dataset | conf threshold | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|---:|
| CoreML | 3.92891 | 0.6 | 1000000 | 2.67188 | 0.953798 | 0.419701 |
| PyTorch | 6.37978 | 0.6 | 759696 | 2.65244 | 0.94095 | 0.450573 |

## Ratios

- bbox diag CoreML/PyTorch: `1.00733`
- PCA minor CoreML/PyTorch: `1.01365`
- valid fraction CoreML/PyTorch: `1`
- conf threshold CoreML/PyTorch: `0.615837`

## 初步判读

同 K、同图、同 official GLB-style filter 下比较点云。CoreML/PyTorch valid fraction=0.6/0.6，bbox diag=2.67188/2.65244，PCA minor=0.953798/0.94095。如果两边都出现类似厚层/暗部片状保留，漂浮更像官方模型/导出规则在这组图上的表现；如果 PyTorch 明显干净而 CoreML 更厚，再回头查 CoreML export parity。
