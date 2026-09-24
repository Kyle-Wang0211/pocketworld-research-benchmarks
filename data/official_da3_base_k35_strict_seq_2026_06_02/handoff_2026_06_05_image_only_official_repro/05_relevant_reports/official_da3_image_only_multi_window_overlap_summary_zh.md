# DA3 image-only multi-window overlap summary

日期：2026-06-05

## 结论

- status: `warning`
- metric status: `product_official_downstream_metric_pass_full_k35_visual_review_required`
- product pass: `6/6`
- max product official_downstream PCA minor growth: `1.13224`
- max full K35 diagnostic PCA minor growth: `1.31111`
- full K35 diagnostic warning windows: `window_007`
- visual thickness review required: `True`
- do not claim fully solved: `True`

产品 official_downstream metric 全部通过，但完整 K35 诊断仍有尾帧超阈值，需要保留为视觉/上游诊断警告：window_007；不能写成厚层完全根治。

`official_downstream` 是产品验收口径；`full K35` 是诊断口径，用来提示 withheld/tail 帧是否仍有几何漂移。

## Windows

| window | product downstream PCA | full K35 PCA | product pass | full K35 warning |
|---|---:|---:|---:|---:|
| window_004 | 0.987349 | 1.06247 | True | False |
| window_006 | 1.13224 | 1.13567 | True | False |
| window_007 | 1.03069 | 1.31111 | True | True |
| window_016 | 0.948379 | 0.932347 | True | False |
| window_017 | 1.03269 | 1.03916 | True | False |
| window_021 | 0.988594 | 1.01721 | True | False |
