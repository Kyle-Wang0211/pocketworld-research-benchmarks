# gpufe_nothread 的 EuRoC 精度判决（2026-09-15）

臂：GPU 前端 ON + 线程化 OFF（engine sha16 `363bedb5b473402c`，程序自报 `app.backend=gpu_frontend`）。
每序列跑两场，两场 ATE/RPE 全部逐位相同 ⇒ replay 通道确定性成立，n=1 即可判。

| 序列 | generic（现役） | gpufe（线程化） | **gpufe_nothread** | vs generic | vs gpufe |
|---|---|---|---|---|---|
| V1_01 | 0.048965 | 0.051418 | **0.048965** | ±0（前 10 位相同） | −4.8% |
| V1_02 | 0.097605 | 0.095370 | **0.104049** | +6.6% 更差 | +9.1% 更差 |
| V1_03 | 0.123156 | 0.105010 | **0.106235** | −13.7% 更好 | +1.2% |
| 三档均值 | 0.089908 | 0.083933 | **0.086416** | −3.9% 更好 | +3.0% 更差 |

RPE-translation(m) / RPE-rotation(deg) / cpu_seconds：

| 序列 | nothread rpe_t | rpe_r | cpu_s | gpufe cpu_s | generic cpu_s |
|---|---|---|---|---|---|
| V1_01 | 0.049905 | 0.46848 | 77.46 / 77.06 | 78.72 | 73.70 |
| V1_02 | 0.071546 | 0.25843 | 46.29 / 46.10 | 47.27 | 43.31 |
| V1_03 | 0.078617 | 0.31335 | 59.45 / 59.31 | 60.84 | 57.84 |

## 结论

1. **关掉线程化没有系统性精度代价**：三档均值比现役 generic 好 3.9%，比线程化 gpufe 差 3.0%，方向一场一个样（V1_01 打平、V1_02 差、V1_03 好），量级都在同一档噪声里。没有"关线程 ⇒ 精度掉"的证据。
2. **V1_01 上 nothread 与 generic 前 10 位相同（差 2.7e-11 m），而线程化 gpufe 差 5%** ⇒ 该序列上 gpufe 与 generic 的差异**来自线程化的非确定性，不是 GPU 前端**。V1_02/V1_03 上三臂两两都不同，说明那两档 GPU 前端确实改了特征集。
3. **门（`ate>0.10` / `rpe_t>0.05`）不是判据**：现役 generic 在 V1_02/V1_03 同样 `gates_not_met`。与 ⑥ 的结论一致——这两个阈值没有可追溯出处，只能当相对尺子用。
4. **零挂死**：本臂连续 6 场无一挂死（累计 9 场干净），线程化嫌疑进一步坐实，但仍是阴性证据、非证明。

## 复现
`pw_run_arm.sh <label> replay-paced -PWDatasetPath euroc_v101_bmp|euroc_v102|euroc_v103 -PWXrslamGpuFrontend`
（本臂必须带 `-PWXrslamGpuFrontend`；不可带 `-PWPosePollHz`。两场之间 ≥90 s 让 run lease 释放。）
逐场 receipt 已追加进同目录 `results.jsonl`（label 前缀 `euroc_*_gpufe_nothread_*`）。
