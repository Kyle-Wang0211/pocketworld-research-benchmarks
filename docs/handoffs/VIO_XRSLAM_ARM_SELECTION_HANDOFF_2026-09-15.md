# XRSLAM 引擎档选型交接 — 2026-09-15

结果数据:`data/expXRSLAM_generic_vs_gpufe_2026_09_15/results.jsonl`(13 条 receipt 摘要)
新增配方:`tools/xrslam_gpu_frontend/scripts/{configure_engine_nothread,assemble_nothread,build_bench_nothread_arm}.sh`

## 0. 一句话

**新编了 `gpufe_nothread` 档(GPU 前端 ON + 线程化 OFF)。它是目前唯一同时满足
「吃得下生产分辨率 1920×1440」「不挂死」「确定性」三条的引擎档。**

## 1. 起因:台架臂一直不是生产出货的引擎

`pw_build_gpufe_arm.sh` 头注释:`gpufe arm = libxrslam_gpufe_4beb1a9.a (XRSLAM_GPU_FRONTEND=ON, threading+gate as thrbp)`。
而生产 `pw-head-0827/vendor/xrslam/libs/ios-arm64/` **只有** `libxrslam_generic` 与 `libxrslam_official`
(gpufe / thrbp / thrnogate 在生产树里不存在)。
⇒ 09-09~09-14 的全部测量都在非出货配置上做的。

**台架此前无法链 generic**:`XRSLAMBench.cpp` 调 `XRSLAMGetInitCounters` / `XRSLAMGetPropagatedPose`,
而**只有 gpufe 归档导出这两个符号**。本次补齐两个 weak 兜底后即可链生产那份(sha `fdc75c99358014d9`,
与生产影子自报的 `xrslamSha256` 一致)。兜底缺席可观测:位姿清零→走既有 `pose.timestamp<=0` 判据失败关闭;
计数器填 `UINT64_MAX`(单调计数器不可能自然到达)。

## 2. EuRoC 三档:generic(出货) vs gpufe

每档 ×2,**两次散布全为 0.00000**(ATE/RPE/fps),仅 cpu_seconds 差 0–0.8 s ⇒ **EuRoC 回放是确定性的**。

| 序列 | generic ATE | gpufe ATE | RPE平移 gen/gpu | CPU秒 gen/gpu |
|---|---|---|---|---|
| V1_01 easy | **0.04896** | 0.05142 | 0.04990 / 0.05023 | 73.7 / 78.7 |
| V1_02 medium | 0.09760 | **0.09537** | 0.07071 / 0.07082 | 43.4 / 47.3 |
| V1_03 difficult | 0.12316 | **0.10501** | 0.08097 / 0.08188 | 57.4 / 60.8 |

⇒ 互有胜负,但**最难那档 generic 差 17%**;generic 一致省 CPU 6–8%。
⇒ 此前报的 5.14/9.54/10.50 cm 是 **gpufe** 的成绩;出货引擎实际 4.90/9.76/12.32 cm。

## 3. 🔴 generic 在 1920×1440 跑不动(约 7 秒/帧)

直播 1920×1440,generic 臂:
- 300 s 场:`xrslam_initializing_results = 41` ⇒ 300÷41 ≈ **7.3 秒/结果**;位姿 **0**;CPU 1.45 核;**serious 228 秒**
- 30 s 场(全程连续移动):位姿 **0**、`processed_fps = 0`、`stale_camera_dropped = 1`
  (几乎不丢帧却零产出 ⇒ 不是喂不进,是处理不过来)

旁证:`BenchResolution.swift:56` 早写着 "xrslam died with SIGBUS inside its first frame at 1920x1440"。
⇒ **这正是生产影子 `downsampleFactor=3` 的原因**,不是保守。

## 4. 新档 `gpufe_nothread`:配方与验证

配方 = `configure_engine.sh` **只改一个开关**(`XRSLAM_ENABLE_THREADING=ON → OFF`),其余逐字不动。
两个开关正交,根 `CMakeLists.txt:24-27` 的注释明写解耦目的就是"便于做单变量对比"。

归档验证(对照原版):

| 归档 | 成员 | `THREADING ENABLE` | `GpuImage` 符号 |
|---|---|---|---|
| **libxrslam_gpufe_nothread.a** | **57** | **0** | **39** |
| libxrslam_gpufe_4beb1a9.a | 57 | 1 | 39 |
| libxrslam_generic_4beb1a9.a | — | 0 | 0 |

装机包探针:`@compute 20`(GPU 前端在)、`THREADING 0`、`GPU_WAIT_MS 1`(A1 看门狗在);engine sha16 `363bedb5b473402c`。

**1920×1440 设备录像回放 ×3(半帧率)**:

| 场 | 帧 | 位姿 | CPU 秒 | fps |
|---|---|---|---|---|
| a | 849 | **804** | 19.46 | 31.52 |
| b | 849 | **804** | 20.24 | 31.95 |
| c | 849 | **804** | 20.78 | 31.76 |

⇒ **三场位姿数完全一致、零挂死**。对照 gpufe(线程化 ON)同配置 799 位姿,且 09-14 在同配置下**挂死过一次**。

## 5. 仍然成立的约束与未结项

- **喂帧率必须 ≤30**:`gap×(num−1)=35` 帧的初始化窗口在 60 fps 下只有 0.58 s,攒不出 `min_parallax=10 px`
  (三个常数都在 `config.cpp:38-44` 写死,无 YAML 覆盖)。与分辨率无关。
- **挂死未定案**:已排除 GPU 等待(`dawn_kernel_harness.cpp` 零 `UINT64_MAX`,每个 `WaitAny` 都有限超时)。
  新档三场零发生 ⇒ 方向指向线程化,但样本仅 3 场,**不能称已证明**。
- **精度未验**:本档尚未跑 EuRoC 三档,不知道关掉线程化是否有精度代价。
- **ARKit 基线**(见下)与本档的直播热态对照尚未做。

## 6. ARKit 热态基线重测(推翻 09-03 那个数)

同机、同日、nominal 起跑、300 s、1920×1440、协议=举起动 10 s 后平放静置:
```
thermal = {nominal: 44, fair: 256, serious: 0}
CPU 核当量 均值 0.72 / 峰 0.79   内存峰 317 MB   首个可用位姿 2874.92 ms
```
⇒ **ARKit 44 秒即进 fair**,不是旧基线的"600 秒全程不出 fair"(那次不跑重建、凉机、单场)。**旧基线作废。**
用户口径澄清:**只在乎 serious,fair 属正常**。本场 serious 0 秒 ⇒ 按该口径合格。

## 7. 🔴 方法教训(本轮踩到的)

- **weak 兜底若落在某条路径的唯一数据源上,会造出"零产出"假象**:`-PWPosePollHz` 只经
  `XRSLAMGetPropagatedPose` 读位姿,generic 不导出它 ⇒ 兜底清零 ⇒ 每个位姿判 non_finite。
  差点据此误判"生产引擎在直播下不出位姿"。**加兜底前必须检查该函数是不是唯一数据源。**
- **真机测试必须设硬性 300 秒上限并在过程中报进展**(一次让设备空转 664 s)。
- **设备 run 目录每次启动被 purge,只留最新;取"最新 run"必须按时间列排序**,不能对字母序 `tail -1`。
- **短场之间租约未释放会被拒**("有 run 正在进行"),至少隔 70 s 并确认 `viobench` 进程为 0。
- **zsh 不对未加引号的 `$var` 分词**:本轮因此两次事故(批次跑成空数据集路径、libtool 收到含换行的单参数)。
  **多参数循环/列表一律写进 bash 脚本文件,不在命令行做变量分词。**
