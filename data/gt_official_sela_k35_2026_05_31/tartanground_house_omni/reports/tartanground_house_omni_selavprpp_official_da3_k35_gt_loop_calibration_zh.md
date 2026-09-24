# 官方 DA3-BASE K35 Streaming GT 定标报告

- 数据集：tartanground / tartanground_house_omni_selavprpp
- 路线：DA3-BASE K35@476x742 official-style sequential chunks -> SelaVPR++ loop retrieval -> official loop chunk forward -> dense Sim3 -> official Sim3LoopOptimizer -> GT metric calibration
- 帧数：700
- sequential windows：41
- loop windows：22
- VPR backend：selavprpp
- loop candidates：raw=111 / nms=22
- optimizer：completed，constraints=22

| 路线 | GT RMSE(m) ↓ | GT P90(m) ↓ | GT P95(m) ↓ | Sim3 scale |
|---|---:|---:|---:|---:|
| dense Sim3 only | 0.9562 | 1.3006 | 1.5897 | 5.2002 |
| dense Sim3 + official loop optimizer | 0.5669 | 0.8142 | 0.9341 | 4.3698 |

## 结论

- loop optimizer 相对 dense-only 的 RMSE 变化：-0.3892 m。
- loop optimizer 相对 dense-only 的 P90 变化：-0.4863 m。
- 这张表才是外部 GT 米制真值下的最终定标口径；dense Sim3 内部 RMSE 只能说明窗口之间能对齐，不能单独证明真实世界米制误差。
