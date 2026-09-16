# 求解器预算与特征点数的 EuRoC 精度代价（2026-09-16）

臂 `gpufe_nothread`；`replay-paced`；每格 n=1（回放确定性已验：A 臂三个数与当日早先同臂逐位相同）。

| 序列 | A 基线（上游**离线**档 1.0e6 s / 30 iter, 200 点） | **B** solver 0.1 s / 10 iter（上游真机 app 档 = **生产现役**） | C max_keypoint_detection 300 |
|---|---|---|---|
| V1_01 | 0.04896 | 0.05290 (+8.0%) | 0.05455 (+11.4%) |
| V1_02 | 0.10405 | 0.08357 (−19.7%) | 0.11053 (+6.2%) |
| V1_03 | 0.10624 | 0.13108 (+23.4%) | 0.12989 (+22.3%) |
| **均值** | 0.08642 | **0.08918 (+3.2%)** | 0.09832 (+13.8%) |

`config_sha256`：A `e3c1a68ea9` / B `cc1c06e0ea` / C `319b043fb9`。

## 结论
1. **收紧求解器到生产口径只花 +3.2% 均值 ATE**，逐档方向相反（−19.7% ~ +23.4%），非系统性退化。
2. 🔴 **口径**：A 不是生产的配置。上游有两份 iPhone 档，预算差四个数量级：
   `configs/iphone_slam.yaml` = 1.0e6 s / 30 iter / 200 点（离线）；
   `xrslam-ios/visualizer/configs/slam_params.yaml` = **0.1 s / 10 iter / 300 点**（真机 app，生产用这份）。
   台架**所有** XRSLAM 通道（含实时直播）跑的是离线那份。
3. **生产口径下三档均值 0.08918，对照现役 generic 0.08991 ⇒ 仍持平（好 0.8%）**。
4. **C 在 EuRoC 上不划算**（+13.8%，V1_03 CPU +13%），但 EuRoC（752×480）测不到它针对的东西——1920×1440 直播下的 `FailMatches`。**C 的判决留到直播场。**

## 复现
`pw_run_arm.sh <label> replay-paced -PWDatasetPath euroc_v101_bmp|euroc_v102|euroc_v103 -PWXrslamGpuFrontend [-PWYamlOverride solver.time_limit=0.1 -PWYamlOverride solver.iteration_limit=10] [-PWYamlOverride feature_tracker.max_keypoint_detection=300]`
本次把 `solver` 加入 `-PWYamlOverride` 白名单（原只允许 `feature_tracker`/`sliding_window`）；只能改上游 yaml 已存在的键。
