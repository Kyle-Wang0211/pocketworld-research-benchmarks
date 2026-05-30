# TUM RGB-D 官方 DA3-BASE K35 Streaming GT 定标

## 结论

这组测试已经跑完官方-style sequential route：DA3-BASE `K35@476x742`、420 帧、24 个 window、overlap=18。它验证的是跨 window 串接后的真实 GT 相机轨迹误差。

| 路线 | Sela 阈值 | loop pairs | loop constraints | optimizer | RMSE(m) | P90(m) | GT 对齐 scale |
|---|---:|---:|---:|---|---:|---:|---:|
| official sequential K35 + dense Sim3 | 0.85 | 0 | 0 | none | 0.1685 | 0.2936 | 1.2398 |
| official sequential K35 + SelaVPR++ + official optimizer | 0.85 | 0 | 0 | not_run_no_loop_constraints | 0.1703 | 0.2951 | 1.2393 |

## 大白话解释

这条 TUM 序列不是强闭环/360 场景。SelaVPR++ 在生产阈值 `0.85` 下没有提出 loop pair，所以官方 Sim3LoopOptimizer 没有约束可以优化。这个结果不能证明 loop optimizer 无效，只能证明它没有乱闭环。

真正有价值的结果是 dense Sim3 串接后的 GT 误差：RMSE 约 `0.169m`，P90 约 `0.294m`。也就是说跨 window 没有炸，但绝对米制/全局轨迹还有约 17cm RMSE、29cm P90 的误差量级。

## 产物

- 完整 JSON: `reports/tum_official_sela_k35_gt_report.json`
- 汇总 CSV: `reports/tum_official_sela_k35_gt_summary.csv`
- DA3 输出: `sequential_da3_cpu/`
- SelaVPR++ retrieval: `selavprpp/loop_retrieval_report.json`
