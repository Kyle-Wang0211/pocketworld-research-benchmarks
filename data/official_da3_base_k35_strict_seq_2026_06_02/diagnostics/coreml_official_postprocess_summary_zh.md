# CoreML 官方后处理补齐总结

## 动作

这一步没有重新跑 CoreML，也没有改 bbox、graph patch、loop fusion 或 mesh 算法。只把 sealed CoreML raw window 输出补齐到官方 DA3 PyTorch API 的后处理语义：

- `align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)`
- `depth = raw_depth / pose_scale`
- `intrinsics = input_intrinsics`
- `extrinsics = input_extrinsics[:3, :]`

新输出目录：

- `data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict_official_postprocess`
- `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_small_k_parity_official_postprocess`
- `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess`

## Window 级别

| window | pose_scale | raw depth mean | official-post depth mean | raw pose center median | post pose center median |
|---|---:|---:|---:|---:|---:|
| window_000 | 0.47967953 | 0.760074 | 1.58454 | 2.35699 | 0 |
| window_001 | 0.56607753 | 0.712911 | 1.25939 | 2.78477 | 0 |
| window_002 | 0.73995516 | 0.963430 | 1.30201 | 3.28930 | 0 |

## Small-K parity 变化

| case | raw depth scale | post depth scale | raw depth MAE | post depth MAE | raw pose center median | post pose center median | raw K MAE | post K MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| k03_res742_mps | 6.02153 | 2.88841 | 4.08792 | 3.19772 | 1.94356 | 0 | 9.08217 | 0 |
| k05_res742_mps | 1.96509 | 0.94261 | 0.81305 | 0.09707 | 1.94356 | 0 | 9.05639 | 0 |
| k10_res476_mps | 1.97648 | 0.94807 | 0.81301 | 0.09702 | 2.10302 | 0 | 67.61106 | 65.95913 |

`k05_res742_mps` 是当前最可信的硬对比：同为 476x742，K 足够跑 Umeyama，且不像 K3 那样过短。补齐官方后处理后，depth scale 从 1.965 收敛到 0.943，raw depth MAE 从 0.813 降到 0.097，pose 和 intrinsics 对齐到官方语义。

`k03_res742_mps` 仍然不稳定，因为 PyTorch K3 的 pose scale 本身太短；它能说明 depth 结构相似，但不适合作为 full-window 尺度判断。

`k10_res476_mps` 是弱参考，因为 PyTorch 输出是 308x476，CoreML 是 476x742，比较时做过 resize；它不能作为硬 parity 结论。这里 intrinsics MAE 仍大，主要来自分辨率不同。

## 点云 / bbox

official-postprocess 后，点云 bbox 的绝对值变大，这是尺度单位进入官方 input-pose/depth scale 后的预期结果，不是新的 bbox 退化。用 glb_style 统计：

| group | raw bbox | post bbox | raw PCA minor | post PCA minor |
|---|---:|---:|---:|---:|
| slot_00 | 1.16722 | 2.51899 | 0.44410 | 0.93571 |
| first_05 | 1.25813 | 2.71460 | 0.45327 | 0.95513 |
| first_10 | 1.23941 | 2.67147 | 0.45400 | 0.95395 |
| first_35 | 1.34550 | 2.91107 | 0.53340 | 1.11515 |

更重要的是，postprocess 后仍没有出现 0+1、0+1+2、前 5、前 10 的突增崩坏。可视化形态和 raw official-filter 很接近；这说明官方后处理补齐主要解决的是尺度/pose/intrinsics 语义，不会凭空消除 confidence/边缘/暗部导致的厚层和漂浮。

## 结论

这一步验证了一个可控差距：我们的 CoreML 导出链路之前确实少了官方 postprocess。补齐以后，K5@742 的 CoreML/PyTorch 对齐显著改善，pose/intrinsics 语义也对齐了。

下一步不应该先继续调 bbox；更合理的是继续查 confidence 语义、官方 confidence filter 与 CoreML `depth_conf` 的数值 parity，以及再做一版 official-postprocess 后的 window_000 视觉/数值审计。
