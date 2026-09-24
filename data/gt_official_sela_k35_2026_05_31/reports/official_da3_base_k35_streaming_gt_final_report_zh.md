# DA3-BASE K35 官方 Streaming + SelaVPR++ GT 定标总报告

这份报告只看外部 GT 米制真值，不再只看 DA3 内部跨 window 是否对得上。

| 数据集 | 帧数 | seq windows | loop windows | Sela loop | dense-only RMSE/P90(m) | loop optimizer RMSE/P90(m) | 变化(m) | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| TUM freiburg1_desk | 420 | 24 | 0 | 0 | 0.1703 / 0.2951 | n/a | n/a | 无生产阈值闭环，不能验证 optimizer 增益 |
| TartanGround House omni | 700 | 41 | 22 | 22 | 0.9562 / 1.3006 | 0.5669 / 0.8142 | RMSE -0.3892, P90 -0.4863 | 闭环显著降低全局米制误差 |

## 读法

- TUM freiburg1_desk 是普通室内短序列，SelaVPR++ 在生产阈值 0.85 下没有提出 loop，所以它只能证明 sequential dense Sim3 没有炸，不能证明 loop optimizer。
- TartanGround House omni 是更接近 360/大规模闭环压力测试的序列，SelaVPR++ 提出 22 个 loop window，官方 Sim3LoopOptimizer 完成，并把 GT RMSE 从 0.9562m 降到 0.5669m，P90 从 1.3006m 降到 0.8142m。
- 所以当前证据支持：官方 streaming loop 路线不是摆设，它确实在闭环场景里把跨 window 全局米制对齐往正确方向拉。
- 但 Tartan 的绝对误差仍然是几十厘米级，不是最终生产质量天花板；下一步应该继续找更接近真实 iPhone/AR capture 的 GT 或加入 AR/VIO anchors 做米制约束。

## 路线固定

- 模型：DA3-BASE K35@476x742。
- sequential：官方 streaming sliding chunks，K35 下半窗 overlap=18。
- loop retrieval：SelaVPR++，生产阈值 0.85。
- loop chunk forward：官方 process_loop_list 思路，缩放到 K35。
- 几何：dense Sim3。
- 优化：官方 Sim3LoopOptimizer。