# Official DA3 image-only CoreML target export gate

日期：2026-06-04

## 结论

- status: `fail_local_target_conversion_preflight`
- highest priority gap: `DA3BASE_476x742_N35_image_only.mlpackage_or_mlmodelc_missing`
- can run image-only overlap gate: `False`
- local memory insufficient for attention floor: `True`

这个 gate 不跑新的转换，也不改 K/尺寸。它只回答：当前本机是否适合继续强行导出固定 `DA3BASE_476x742_N35_image_only`。

## 固定目标

- target: `DA3BASE_476x742_N35_image_only`
- window: `K35`
- input: `476x742`
- semantics: `image_only_no_extrinsics_no_intrinsics`
- dimension sweep: `disabled`

## 资源下限

- patch grid: `34x53`
- global tokens: `63105`
- attention heads: `12`
- fp16 attention score buffer: `89.01 GiB`
- fp32 attention score buffer: `178.02 GiB`
- local physical memory: `18 GiB`

这里的 buffer 是单个 global attention score 的理论下限，不包含 q/k/v、MLProgram conversion 中间图、编译缓存、Python/CoreMLTools 开销。所以它只能低估目标导出压力。

## 已有 probe

| probe | status | peak memory | package |
|---|---:|---:|---:|
| highest pass `252x392` | `pass` | `- GiB` | `0.6569 GiB` |
| highest fail `336x532` | `fail` | `35.04 GiB` | `- GiB` |

## 目标估算

- from highest failed probe ratio: `3.9x`
- rough target conversion peak from failed probe: `136.65 GiB`
- from highest pass ratio: `12.75x`
- rough target package size from highest pass: `2.345 GiB`

## 判断

image-only wrapper 的官方语义已经明确，中等 K35 CoreML 导出也已经通过；但固定目标模型包仍缺失。在没有更大内存导出环境或 memory-efficient attention/conversion 路径之前，本机继续硬转 476x742 不是合适的下一步。

## 下一步

- 使用更大内存的 Mac/CoreML 导出环境生成固定 476x742 K35 image-only 包，或者等待/获得官方 memory-efficient 导出路径。
- A100/H100 只用于单独关闭官方 PyTorch full-resolution reference gate；CoreML 打包仍需要 CoreML 可用的导出/编译环境。
- 不要用更小 probe 包替代目标，也不要为了 official baseline 回退到 _pose/ARKit。
