# Official npz threshold coefficient sensitivity

日期：2026-06-04

## 为什么补这份

实现级审计发现一个参数口径差异：

- `da3_streaming/npz_output_process.py` 的 CLI 默认 `--conf_threshold_coef=0.5`。
- `da3_streaming/configs/base_config.yaml` 的 `Model.Pointcloud_Save.conf_threshold_coef=0.75`，用于 DA3-Streaming full-chunk PLY export / `pcd/combined_pcd.ply` 相关路径。

PocketWorld 当前选择的是 `results_output/frame_*.npz + npz_output_process.py` core-frame downstream，所以 APP official baseline 应使用 `0.5` 作为默认；`0.75` 只能作为 streaming config / full-chunk PLY 口径的对照参数。

## 对照输入

同一组：

- `window_016`
- K35
- CoreML official-postprocess
- official PyTorch fixed `photos_depth` K35 `process_res=252`
- official PyTorch highres dynamic K35 `process_res=252`
- `conf -= 1.0`
- `sample_ratio=0.015`
- no voxel / TSDF / surfel / mesh / normal filtering

产物：

- `diagnostics/official_npz_style_window016_k35_dataset_compare_coef050/`
- `diagnostics/official_npz_style_window016_k35_dataset_compare/`

## 结果

### `conf_threshold_coef=0.5`

这是 `npz_output_process.py` CLI 默认。

- CoreML bbox diag：`1.82250`
- PyTorch fixed bbox diag：`1.80113`
- PyTorch highres bbox diag：`1.67697`
- CoreML / PyTorch fixed bbox ratio：`1.01186`
- CoreML / PyTorch highres bbox ratio：`1.08678`
- CoreML / PyTorch fixed PCA minor ratio：`1.23747`
- CoreML / PyTorch highres PCA minor ratio：`1.29190`

解释：

- `0.5` 比 `0.75` 保留更多点，点云自然更厚、更宽。
- CoreML 相对 PyTorch fixed 的 bbox 仍接近 `1.0`。
- PCA minor 比例升高，但没有出现 CoreML-only 成倍 blow-up，也没有指向一个“官方 hidden downstream dedupe”。

### `conf_threshold_coef=0.75`

这是 DA3-Streaming `Pointcloud_Save` config 口径。

- CoreML bbox diag：`1.54741`
- PyTorch fixed bbox diag：`1.61227`
- PyTorch highres bbox diag：`1.55895`
- CoreML / PyTorch fixed bbox ratio：`0.95977`
- CoreML / PyTorch highres bbox ratio：`0.99260`
- CoreML / PyTorch fixed PCA minor ratio：`1.05678`
- CoreML / PyTorch highres PCA minor ratio：`1.07378`

解释：

- `0.75` 更紧，厚层指标更低。
- 它继续支持 CoreML 没有相对 PyTorch low-res reference 成倍变厚。

## 结论

这次修正的是“官方参数口径”，不是厚层归因大方向。

当前 APP official baseline 应改为：

- `results_output/frame_*.npz + npz_output_process.py`
- `conf_threshold_coef=0.5`
- `sample_ratio=0.015`
- global selected core-frame confidence mean

但两种参数下的研究结论一致：

- 官方 downstream 没有隐藏的 voxel/TSDF/surfel/per-surface dedupe。
- `conf_threshold_coef` 会影响厚度，但不是“重叠点云消除算法”。
- K35 单 window 厚层仍应优先看 upstream depth/pose/scale consistency，以及 full same-resolution PyTorch K35 hard parity gate。
