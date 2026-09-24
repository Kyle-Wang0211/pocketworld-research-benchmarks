# Official Streaming Mobile-Constrained K35 Loop Config

## 目的

这份 config 只做移动端承载约束下的官方 streaming 参数收缩，不引入自研 graph patch、新融合或额外算法。

## 相对官方 `base_config.yaml` 的变化

- `Model.chunk_size`: `120` -> `35`
- `Model.overlap`: `60` -> `18`
- `Model.loop_enable`: 保持官方默认 `True`

其他参数尽量保持官方默认，包括：

- `loop_chunk_size: 20`
- `align_lib: triton`
- `align_method: sim3`
- `ref_view_strategy: saddle_balanced`
- `ref_view_strategy_loop: saddle_balanced`
- `Pointcloud_Save.sample_ratio: 0.015`
- `Pointcloud_Save.conf_threshold_coef: 0.75`
- `Loop.SALAD.similarity_threshold: 0.85`

## 注意

这份 config 是 official-default-like 的移动端约束版本。它是否能在 macOS/MPS 或移动端直接运行，还取决于官方 streaming 依赖：Triton、faiss-gpu、SALAD、Sim3 optimizer、DA3 weights，以及目标设备是否支持这些 backend。
