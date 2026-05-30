# DA3-BASE K35@476x742 官方 Streaming 路线对照报告

## 结论先说

这次官方路线已经跑通：DA3-BASE K35@476x742 顺序 chunk、VPR loop retrieval、官方 loop chunk 组织、loop chunk forward、dense Sim3、官方 Sim3LoopOptimizer 全部完成。

在这套 414 帧真实素材上，**SelaVPR++ 更适合作为当前默认 loop retrieval 后端**。原因很简单：BoQ-DINOv2 找到更多 loop，但没有换来更好的 dense Sim3 几何；相反它多跑了接近 2 倍的 loop chunk，训练时间显著变长。

## 基线

| 项目 | 数值 |
|---|---:|
| DA3 模型 | DA3-BASE CoreML |
| 固定参数 | K35@476x742 |
| 输入素材 | 414 帧真实 capture |
| 顺序 streaming window | 24 |
| 顺序 overlap | 18 / 半窗附近 |
| 顺序 DA3 forward | 1552.7s / 25.9min |
| 顺序完成 | 414/414 frames, failed=0 |
| 相邻窗口 dense Sim3 | 23/23 条通过 |
| 相邻 RMSE mean | 0.1837 |
| 相邻 P90 mean | 0.2861 |
| 相邻 scale std | 0.1732 |

## VPR + Loop 对照

| 指标 | SelaVPR++ | BoQ-DINOv2 | 判断 |
|---|---:|---:|---|
| descriptor 时间 | 25.9s | 31.4s | Sela 更快 |
| descriptor 维度 | 2048 | 12288 | Sela 更轻 |
| raw loop pairs | 46 | 99 | BoQ 更激进 |
| NMS 后 loop results | 41 | 79 | BoQ 多 93% |
| loop DA3 chunks | 41 | 79 | BoQ 成本接近翻倍 |
| loop forward 时间 | 36.4min | 68.1min | Sela 快 1.87x |
| loop forward 状态 | failed=0 | failed=0 | 两者都跑通 |
| loop constraints | 41 | 79 | BoQ 更多 |
| loop side A RMSE mean | 0.1243 | 0.1279 | Sela 略好 |
| loop side B RMSE mean | 0.1877 | 0.1917 | Sela 略好 |
| loop scale mean | 1.0239 | 1.0115 | 都接近 1 |
| loop scale std | 0.1510 | 0.1874 | Sela 更稳 |
| optimizer 状态 | completed | completed | 两者都通过 |
| optimizer 后 scale std | 0.1915 | 0.1901 | 接近，BoQ 略低 |

## 关键解释

BoQ-DINOv2 的 loop retrieval 更“爱报点”：官方阈值 0.85 下，它给出 79 个 loop chunk；SelaVPR++ 给出 41 个。多出来的 loop 让 DA3 loop forward 从 36.4 分钟涨到 68.1 分钟。

但几何验证没有证明 BoQ 更强：BoQ 的 loop side A/B RMSE 都略高，loop scale std 也更高。optimizer 后的 scale std BoQ 略低一点，但差距很小，抵不过它多消耗的 31.7 分钟。

所以当前生产/研究默认建议：**DA3-BASE K35@476x742 + 官方 streaming route + SelaVPR++ loop retrieval**。BoQ 可以保留为 research 对照后端，但不建议作为默认。

## 注意

这次验证的是 414 帧真实素材上的官方 streaming 内部一致性：loop retrieval 是否提出合理闭环、loop chunk forward 能否跑通、dense Sim3 和官方 Sim3LoopOptimizer 是否稳定。它不是外部 GT 绝对米制 benchmark。绝对米制仍然需要 ARKit/VIO anchors 或 TUM/ScanNet++/TartanGround 这类 GT 数据来判定。

图表：`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30/reports/official_da3_base_k35_streaming_vpr_compare.png`
CSV：`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30/reports/official_da3_base_k35_streaming_vpr_compare.csv`
