# CoreML / Official PyTorch Small-K Parity Audit

## 范围

- CoreML：固定 N35 sealed model 的 `window_000`，取前 K 个 slot。
- CoreML postprocess 状态：`official_postprocessed`。
- PyTorch：官方 DA3 PyTorch variable-K forward 的小 K 输出。
- 硬对比：只有输出 HxW 完全一致的 case，当前主要是 `K=3/5 @ process_res=742`。
- 弱对比：shape 不一致时，把 CoreML resize 到 PyTorch shape，只作为诊断，不作为 parity 判定。
- 注意：当前 PyTorch sweep 保存的是官方 postprocess 后的 intrinsics/extrinsics，不是 raw model pose logits。

## Case Summary

| case | mode | direct | depth scale | depth scaled median rel | conf raw MAE | pose center median | png |
|---|---|---:|---:|---:|---:|---:|---|
| k03_res742_mps | direct_pixel | True | 2.88841 | 0.0645275 | 1.01682 | 0 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_small_k_parity_official_postprocess/k03_res742_mps_parity_views.png` |
| k05_res742_mps | direct_pixel | True | 0.942614 | 0.0177099 | 2.23657 | 0 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_small_k_parity_official_postprocess/k05_res742_mps_parity_views.png` |
| k10_res476_mps | resized_coreml_weak | False | 0.948075 | 0.0197364 | 1.83787 | 0 | `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/coreml_pytorch_small_k_parity_official_postprocess/k10_res476_mps_parity_views.png` |

## 读法

- `depth scale` 是把 CoreML depth 乘到最接近 PyTorch depth 的全局比例；如果比例远离 1，说明两边 depth 尺度不在同一坐标系。
- `depth scaled median rel` 是全局 scale 对齐后的中位相对误差，越小越接近。
- `conf raw MAE` 是 confidence 原值平均绝对差；confidence 不做 scale 后的主判定。
- `pose center median` 是 CoreML pose 与 PyTorch postprocessed/input-aligned pose 的相机中心距离中位数。

## 初步结论

主信号看 K=3/5@742。official postprocess 后，pose/intrinsics 已对齐到官方语义；K=5@742 的 depth scale 从 raw 版明显偏离 1 收敛到接近 1，说明 Umeyama pose_scale 基本解释了绝对尺度差异。confidence 仍然差异偏大，K=3 因 PyTorch 小 K pose scale 退化/不稳定仍不应作为 full-window 结论。K=10@476 shape 不一致，只能作为弱参考。

这份 audit 先定位软件对齐问题，不尝试通过 bbox 或自研过滤修图。
