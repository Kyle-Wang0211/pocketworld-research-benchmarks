# Official DA3 image-only CoreML target export gate

日期：2026-06-05

## 结论

- status: `pass_target_image_only_coreml_artifact_exists`
- highest priority gap: `None`
- can run image-only overlap gate: `True`
- local memory insufficient for attention floor: `None`
- probe substitution guard: `pass_static_probes_are_research_only_not_product_target`

这个 gate 不跑新的转换，也不改 K。它只回答：当前本机是否适合继续导出官方 preprocess 目标 `DA3BASE_280x504_N35_image_only`。

## 固定目标

- target: `DA3BASE_280x504_N35_image_only`
- window: `K35`
- input: `280x504`
- semantics: `image_only_no_extrinsics_no_intrinsics`
- dimension sweep: `disabled; dimensions come from official process_res=504 upper_bound_resize + patch align for 16:9 inputs`

## 资源下限

- patch grid: `20x36`
- global tokens: `25235`
- attention heads: `12`
- fp16 attention score buffer: `14.23 GiB`
- fp32 attention score buffer: `28.47 GiB`
- local physical memory: `18 GiB`

这里的 buffer 是单个 global attention score 的理论下限，不包含 q/k/v、MLProgram conversion 中间图、编译缓存、Python/CoreMLTools 开销。所以它只能低估目标导出压力。

## Direct Attempt

- dry-run status: `pass`
- dry-run output shapes: `[[1, 35, 280, 504], [1, 35, 280, 504], [1, 35, 3, 4], [1, 35, 3, 3]]`
- convert report exists: `True`
- target package exists: `True`
- status: `target_package_exists_after_dry_run`

## 已有 probe

| probe | status | peak memory | package |
|---|---:|---:|---:|
| highest pass `252x392` | `pass` | `- GiB` | `0.6569 GiB` |
| highest fail `336x532` | `fail` | `35.04 GiB` | `- GiB` |

## Probe 替代保护

- package count: `7`
- exact target package count: `0`
- passed static conversion probe count: `5`
- do not accept probe as product target: `True`
- required product location: `ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage_or_mlmodelc`

这些 probe 只能证明较小 shape 的 image-only CoreML conversion 路线；它们不是 `DA3BASE_280x504_N35_image_only`，也不在 APP CoreML 资源目录里，所以不能解锁 official image-only overlap gate。

## 目标估算

- from highest failed probe ratio: `0.6236x`
- rough target conversion peak from failed probe: `21.85 GiB`
- from highest pass ratio: `2.038x`
- rough target package size from highest pass: `0.9379 GiB`

## 判断



## 下一步

- 运行 da3_image_only_coreml_readiness_gate.py。
- 用同一 capture/window 运行 da3_mac_window_export.py。
- 对 window_016 运行 da3_image_only_overlap_regression_gate.py。
