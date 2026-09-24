# Window 000 Official Filter Micro Audit

## 前提

- DA3-BASE 是当前可商用路径中的最好模型。
- DA3BASE_476x742_N35_pose.mlpackage 是手机可承载且深度信息最好的调参结果。
- 本实验固定 CoreML 输出，只替换点云导出/过滤规则为官方规则。

## 输出

- glb_style contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/glb_style/glb_style_contact_sheet.png`
- glb_style report: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/glb_style/glb_style_report_zh.md`
- npz_streaming_style contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- npz_streaming_style report: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_report_zh.md`

## 对比

| group | glb bbox | npz bbox | glb minor | npz minor | glb valid | npz valid |
|---|---:|---:|---:|---:|---:|---:|
| slot_00 | 2.5190 | 2.8033 | 0.9357 | 1.0435 | 0.600 | 0.711 |
| slots_00_01 | 2.6186 | 2.8117 | 0.9526 | 1.0616 | 0.600 | 0.709 |
| slots_00_02 | 2.6362 | 2.8441 | 0.9478 | 1.0423 | 0.600 | 0.709 |
| first_05 | 2.7146 | 2.9044 | 0.9551 | 1.0703 | 0.600 | 0.704 |
| first_10 | 2.6715 | 2.8615 | 0.9540 | 1.0827 | 0.600 | 0.714 |
| first_35 | 2.9111 | 2.9594 | 1.1151 | 1.1803 | 0.600 | 0.694 |

## 初步判读

- `glb_style` 使用官方 GLB export 的 percentile/clamp 过滤，slot_00 的 bbox 明显收紧，但仍能看到半透明厚层和少量游离片。
- `npz_streaming_style` 使用官方 streaming pcd 保存规则；由于 base_config 是 `mean(conf)*0.75`，它保留约 69%-71% 像素，行为接近 raw micro audit。
- 两套官方规则都没有出现 0+1、0+1+2、前 5 或前 10 的突增崩坏；问题更像是 CoreML 输出/pose-depth尺度/置信语义与点云消费规则之间的连续厚化，而不是某个早期 slot 拼接瞬间炸掉。

## 自动标记

- glb_style: bbox jump `None`, PCA minor jump `None`
- npz_streaming_style: bbox jump `None`, PCA minor jump `None`
