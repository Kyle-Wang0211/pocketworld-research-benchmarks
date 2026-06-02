# CoreML / PyTorch Confidence、边缘、点云对照总结

## 这次只查官方一致性

本轮没有改 bbox、没有 graph patch、没有 loop、没有 mesh，也没有新增自研过滤。只做三件事：

- 对同一批图比较 CoreML `depth_conf` 和官方 PyTorch `depth_conf` 的分布、热力图、官方 GLB/NPZ 阈值下的保留比例。
- 比较 RGB 边缘和 depth 边缘是否明显错位。
- 用同 K、同图、同 official GLB-style confidence/backprojection/alignment 规则生成 CoreML 与 PyTorch 点云对照。

## 关键结论

最可信主信号是 `k05_res742_mps`，因为它是同图、同尺寸、同 `476x742` 的硬对比。

| item | CoreML | PyTorch | 读法 |
|---|---:|---:|---|
| RGB input MAE | 0.291537 | - | saved PyTorch reference 和 CoreML 当前输入几乎同口径 |
| confidence MAE | 2.23145 | - | confidence 数值尺度仍有明显差异 |
| confidence mean signed | -2.16317 | - | CoreML 整体 confidence 比 PyTorch 低 |
| GLB conf threshold | 3.85742 | 5.25455 | percentile 规则把不同 confidence 尺度各自归一到阈值 |
| GLB valid fraction | 0.600239 | 0.600001 | 全局保留比例几乎一样 |
| dark luma<32 GLB valid | 0.970023 | 0.953754 | 暗部大面积保留不是 CoreML 独有 |
| RGB edge GLB valid | 0.274117 | 0.253052 | 边缘区域两边都会保留一部分点 |
| RGB/depth edge recall top10 | 0.271207 | 0.268279 | 边缘错位程度非常接近 |

## 点云对照

同 K5、同图、同 official GLB-style 规则下：

| dataset | conf threshold | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|---:|
| CoreML | 3.85742 | 0.600239 | 1000000 | 2.71395 | 0.955185 | 0.413291 |
| PyTorch | 5.25455 | 0.600001 | 1000000 | 2.70712 | 0.896793 | 0.412165 |

Ratios:

- bbox diag CoreML/PyTorch: `1.00253`
- PCA minor CoreML/PyTorch: `1.06511`
- valid fraction CoreML/PyTorch: `1.0004`
- conf threshold CoreML/PyTorch: `0.734111`

视觉上，CoreML 与 PyTorch 都能看到类似的窗帘/暗部片状保留和厚层；CoreML 略厚，但不是数量级差异。

## Preprocess 口径

当前 saved PyTorch reference 使用的是 `photos_depth/cap-*.jpg`，尺寸就是 `[742, 476]`，和 CoreML 输入同源。因此它适合检查 CoreML/PyTorch 输出数值语义。

但 `photos_depth` 本身来自 highres `[4224, 2376]` 到 `[742, 476]` 的 `direct_stretch`。如果 highres 直接走官方 `upper_bound_resize@742`，预期会是约 `[742, 420]`。这仍然是移动固定输入 CoreML 模型与官方动态宽高比 PyTorch API 的结构性差异。

## 当前判断

这次证据不支持“漂浮/厚层主要是 CoreML 后处理或 CoreML 独有 confidence 错误导致”。更像是：

- 官方 GLB percentile filter 会把两边都保留到约 60% 像素。
- 暗部区域在 CoreML/PyTorch 两边都被高比例保留。
- RGB/depth 边缘对应关系两边很接近。
- 同 K5 official GLB-style 点云里，PyTorch 也有类似厚层/片状暗部。

所以，下一步如果继续按“无限贴合官方”走，优先不是改 bbox，而是验证官方原始 highres 动态宽高比输入与移动固定 742x476 输入之间的差异；或者确认官方 export 是否会启用 black/white/background/sky 相关选项。不要先上自研过滤。

## 输出

- confidence + edge audit: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_confidence_edge_audit_official_postprocess/coreml_pytorch_confidence_edge_audit_report_zh.md`
- K5 pointcloud compare: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_k05/k05_res742_mps_official_filter_pointcloud_compare_zh.md`
- K5 pointcloud comparison image: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_official_filter_pointcloud_compare_k05/k05_res742_mps_coreml_vs_pytorch_glb_style.png`
