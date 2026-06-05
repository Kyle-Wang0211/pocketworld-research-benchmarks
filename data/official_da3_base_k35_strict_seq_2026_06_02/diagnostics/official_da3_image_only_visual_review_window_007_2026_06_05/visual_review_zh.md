# DA3 image-only window_007 visual review

日期：2026-06-05

## 结论

- `official_downstream_core17` 的 metric 通过：PCA minor growth over first10 = `1.030693`，低于 `1.15`。
- `full35_diagnostic` 仍有明确警告：PCA minor growth over first10 = `1.311106`。
- 从导出的三视图 PNG 看，`official_downstream_core17` 比 `full35_diagnostic` 收敛，但不能写成“厚层完全根治”或“薄薄一层”。
- 当前更诚实的状态是：产品 official downstream 指标改善/通过，但视觉厚层验收未关闭，需要继续保留 thick-layer visual review gate。
- 追加官方 NPZ oracle 后，`npz_output_process.py` 直接导出的 PLY 与 Research PLY executor 几乎一致；肉眼看到的形状很烂不是 PLY sampling executor 单独改坏，问题已经进入 `CoreML image-only depth + pred pose + 官方 npz_output_process.py` 链路。
- 单帧 `frame_119` 的 depth/confidence 可视化和数值范围正常，优先嫌疑从“单帧 depth 完全坏”转为“多帧 pose/scale consistency 没有完全对齐官方 streaming postprocess”。

## 文件

- Desktop PLY folder: `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check`
- `first10_baseline`: `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/DA3_image_only_window_007_first10_baseline_npz_rgb.ply`
- `official_downstream_core17`: `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/DA3_image_only_window_007_official_downstream_core17_npz_rgb.ply`
- `full35_diagnostic`: `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/DA3_image_only_window_007_full35_diagnostic_npz_rgb.ply`
- official NPZ oracle report: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_2026_06_05/official_npz_oracle_visual_compare_zh.md`

## Numeric Evidence

| group | point count | PCA minor extent | bbox diag p01-p99 | growth over first10 |
|---|---:|---:|---:|---:|
| first10 baseline | 21168 | 0.650231 | 1.612018 | 1.000000 |
| official_downstream_core17 | 35985 | 0.670188 | 1.585436 | 1.030693 |
| full35 diagnostic | 74088 | 0.852522 | 1.700669 | 1.311106 |

## Product Interpretation

`official_downstream_core17` can be treated as a product-metric pass, but not as visual closure. The report and closure matrix must not claim the thick-layer problem is fully solved until visual acceptance is explicitly passed on the PLY/point-cloud output.
