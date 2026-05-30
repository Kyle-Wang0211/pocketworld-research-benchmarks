# 官方 DA3-BASE K35 Streaming GT 定标报告

- 数据集：tum / tum_freiburg1_desk_selavprpp
- 路线：DA3-BASE K35@476x742 official-style sequential chunks -> SelaVPR++ loop retrieval -> official loop chunk forward -> dense Sim3 -> official Sim3LoopOptimizer -> GT metric calibration
- 帧数：420
- sequential windows：24
- loop windows：0
- VPR backend：selavprpp
- loop candidates：raw=0 / nms=0
- optimizer：not_run_no_loop_constraints，constraints=None

| 路线 | GT RMSE(m) ↓ | GT P90(m) ↓ | GT P95(m) ↓ | Sim3 scale |
|---|---:|---:|---:|---:|
| dense Sim3 only | 0.1703 | 0.2951 | 0.3101 | 1.2393 |
| dense Sim3 + official loop optimizer | nan | nan | nan | nan |

## 结论

- loop optimizer 相对 dense-only 的 RMSE 变化：nan m。
- loop optimizer 相对 dense-only 的 P90 变化：nan m。
- 这张表才是外部 GT 米制真值下的最终定标口径；dense Sim3 内部 RMSE 只能说明窗口之间能对齐，不能单独证明真实世界米制误差。
