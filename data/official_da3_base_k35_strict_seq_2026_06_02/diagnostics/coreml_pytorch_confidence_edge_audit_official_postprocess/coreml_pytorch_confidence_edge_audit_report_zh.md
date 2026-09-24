# CoreML / PyTorch Confidence + Edge Audit

## 范围

- 不改 CoreML 输出，不改 bbox，不做 graph patch/loop/mesh。
- 对比 official-postprocess CoreML 与 saved official PyTorch small-K reference。
- 重点看 confidence 语义、官方 GLB/NPZ 阈值下的 valid fraction、暗部/边缘区域、RGB/depth 边缘是否错位。

## Preprocess Contract

- capture 输入尺寸：source `[4224, 2376]` -> model input `[742, 476]`。
- capture resize：`direct_stretch` / `cubic`。
- saved PyTorch reference 使用：`photos_depth/cap-1.jpg`，实际图片尺寸 `[742, 476]`。
- saved PyTorch process_res_method：`upper_bound_resize`，process_res `[476, 742]`。
- 如果 highres 直接走官方 upper_bound_resize，预期尺寸：`{'476': {'after_longest_side_resize': [476, 268], 'after_patch_multiple_resize': [476, 266], 'scale': 0.11268939393939394}, '742': {'after_longest_side_resize': [742, 417], 'after_patch_multiple_resize': [742, 420], 'scale': 0.17566287878787878}}`。

读法：当前 small-K reference 是和 CoreML 同源的 `photos_depth`，所以它适合检查 CoreML/PyTorch 输出数值语义；但它不能证明 highres -> fixed 742x476 的移动端预处理已经百分百等价官方动态宽高比 API。

## Case Summary

| case | mode | RGB MAE | exact RGB pixel frac | conf MAE | conf pearson | GLB valid CoreML/PyTorch | edge recall CoreML/PyTorch | png |
|---|---|---:|---:|---:|---:|---:|---:|---|
| k05_res742_mps | direct_pixel | 0.291537 | 0.290712 | 2.23145 | 0.863117 | 0.600239/0.600001 | 0.271207/0.268279 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_confidence_edge_audit_official_postprocess/k05_res742_mps_confidence_edge_audit.png` |
| k03_res742_mps | direct_pixel | 0.292636 | 0.292851 | 1.01659 | 0.789202 | 0.600338/0.6 | 0.277308/0.302799 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_confidence_edge_audit_official_postprocess/k03_res742_mps_confidence_edge_audit.png` |
| k10_res476_mps | resized_coreml_weak | 1.77214 | 0.0448066 | 1.83687 | 0.870481 | 0.6/0.6 | 0.304588/0.28699 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_confidence_edge_audit_official_postprocess/k10_res476_mps_confidence_edge_audit.png` |

## Region Metrics

| case | dataset | black<16 frac | dark luma<32 frac | rgb edge conf mean | rgb edge GLB valid | non-edge conf mean |
|---|---|---:|---:|---:|---:|---:|
| k05_res742_mps | coreml | 0.000425264 | 0.0741251 | 3.05352 | 0.274117 | 4.52284 |
| k05_res742_mps | pytorch | 0.000438855 | 0.0770312 | 4.30805 | 0.253052 | 6.91177 |
| k03_res742_mps | coreml | 0.000488875 | 0.0788013 | 3.09161 | 0.277846 | 4.56212 |
| k03_res742_mps | pytorch | 0.000498313 | 0.0815345 | 2.16494 | 0.305546 | 3.64511 |
| k10_res476_mps | coreml | 6.82091e-05 | 0.0618329 | 2.96133 | 0.227784 | 4.55711 |
| k10_res476_mps | pytorch | 7.77584e-05 | 0.0639604 | 3.58215 | 0.22378 | 6.55019 |

## 初步判读

主信号看 k05_res742_mps：这是同图同尺寸的硬对比。RGB 输入 MAE=0.291537，说明 saved PyTorch reference 与 CoreML 当前输入几乎同口径；confidence MAE=2.23145、mean_signed=-2.16317、pearson=0.863117，说明 confidence 数值尺度仍有明显差异，且 CoreML 整体比 PyTorch 低。官方 GLB percentile 阈值 CoreML/PyTorch=3.85742/5.25455，所以全局 valid fraction 被拉到相近的 0.600239/0.600001。暗部 luma<32 区域 GLB valid fraction CoreML/PyTorch=0.970023/0.953754，说明暗部大面积保留不是 CoreML 独有；RGB edge GLB valid fraction CoreML/PyTorch=0.274117/0.253052，RGB edge 与 depth edge top10 recall CoreML/PyTorch=0.271207/0.268279。

当前 saved PyTorch reference 使用 photos_depth/cap-*.jpg，与 CoreML 输入同源；但 capture 的 photos_depth 是 highres direct_stretch 到 742x476。如果从 highres 直接按官方 upper_bound_resize@742，会得到约 742x420，这仍是移动固定输入模型与官方动态宽高比 API 的结构性差异。

下一步优先把同 K、同图、同 official GLB-style filter 的 CoreML/PyTorch 点云放一起看。如果 PyTorch 也保留类似暗部片状厚层，就不要先改 CoreML parity，而要回到官方导出规则、输入宽高比策略和移动固定尺寸适配。
