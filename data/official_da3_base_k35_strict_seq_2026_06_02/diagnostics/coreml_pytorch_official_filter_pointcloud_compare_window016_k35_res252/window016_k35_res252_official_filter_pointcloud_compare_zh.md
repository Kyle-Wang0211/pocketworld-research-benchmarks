# CoreML / PyTorch Official Filter Pointcloud Compare

## 范围

- 同 K、同图、同 official GLB-style confidence/backprojection/alignment 规则。
- 不做自研过滤，不做 graph patch，不做 loop，不做 mesh。

## Outputs

- comparison png: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_window016_k35_res252/window016_k35_res252_coreml_vs_pytorch_glb_style.png`
- CoreML views: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_window016_k35_res252/window016_k35_res252_coreml_views.png`
- PyTorch views: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_window016_k35_res252/window016_k35_res252_pytorch_views.png`

## Metrics

| dataset | conf threshold | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|---:|
| CoreML | 2.28516 | 0.600045 | 1000000 | 2.19841 | 0.941111 | 0.596408 |
| PyTorch | 1.4919 | 0.6 | 889056 | 2.03467 | 1.0211 | 0.688775 |

## Ratios

- bbox diag CoreML/PyTorch: `1.08047`
- PCA minor CoreML/PyTorch: `0.921668`
- valid fraction CoreML/PyTorch: `1.00008`
- conf threshold CoreML/PyTorch: `1.53171`

## 初步判读

同 K、同图、同 official GLB-style filter 下比较点云。CoreML/PyTorch valid fraction=0.600045/0.6，bbox diag=2.19841/2.03467，PCA minor=0.941111/1.0211。如果两边都出现类似厚层/暗部片状保留，漂浮更像官方模型/导出规则在这组图上的表现；如果 PyTorch 明显干净而 CoreML 更厚，再回头查 CoreML export parity。
