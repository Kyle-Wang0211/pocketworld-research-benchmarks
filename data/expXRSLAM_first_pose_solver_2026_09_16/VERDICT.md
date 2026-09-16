# 首个位姿：16.3 秒的真凶与修复（2026-09-16）

真机直播 1920×1440，臂 `gpufe_nothread`，每场 70 s，人工前 15 s 手持移动。

| 配置 | 首位姿 | 初始化尝试 | 匹配失败 | 处理 fps | p95 采集→位姿 |
|---|---|---|---|---|---|
| 旧（上游**离线**档 1.0e6 s / 30 iter，200 点） | **16 276 ms** | 387 | 386 | 20.1 | 836 ms |
| **B：solver 0.1 s / 10 iter（= 生产现役），200 点** | **3 535 ms** | **4** | **3** | **24.7** | **168 ms** |
| C：B + `max_keypoint_detection` 300 | 40 606 ms | 1116 | 1115 | 10.4 | 195 ms |

## 真凶
上游有两份 iPhone 配置，求解器预算差四个数量级：
- `configs/iphone_slam.yaml`（离线）：`time_limit 1.0e6 s / iteration_limit 30`
- `xrslam-ios/visualizer/configs/slam_params.yaml`（真机 app，**生产用这份**）：`0.1 s / 10`

台架**所有** XRSLAM 通道（含实时直播）跑的是离线那份。而 `solver.cpp:182-184` 把这两个值直接给 Ceres，
**初始化器自己也用同一个 Solver**（`initializer.cpp:154` 与 `:380`）⇒ 387 次初始化尝试，每次都在跑**无时限** BA。
正反馈：尝试贵 → 帧率掉 → 丢帧 → 轨迹断 → 匹配不够 → 再失败。

## 结论
1. 🏆 **首位姿 16.3 s → 3.5 s（4.6×），尝试 387 → 4**。3.5 s 还含人工反应时间，算法真实值更短，
   已进 ORB-SLAM3(2 s) / VINS-Mono(1.25 s) 量级。**"首位姿 16 秒所以上不了生产"这条判词作废。**
2. ⚰️ **C 在 1920×1440 反效果**：检测成本大涨 ⇒ fps 腰斩 10.4 ⇒ 轨迹更易断 ⇒ 1116 次失败。
   与 EuRoC 上 +13.8% 同向。**否掉。**
3. **精度代价已单独定价**（见 `expXRSLAM_euroc_solver_budget_2026_09_16`）：换生产口径均值 +3.2%，
   三档均值 0.08918 仍与现役 generic 0.08991 持平。
4. ⚠️ 三场的运动/场景不同（跨场比），但效应量极大（4 vs 1116 次尝试），方向可认。

## 横屏
Info.plist 原先**没有** `UISupportedInterfaceOrientations` ⇒ iOS 默认允许横屏。
但 `LiveSensorTransport.swift:324` 写死 `connection.videoRotationAngle = 0`，每场诊断自报 `rotation_degrees = 0.0`
⇒ **引擎收到的帧永远 0°，数据未污染**。已加 `INFOPLIST_KEY_UISupportedInterfaceOrientations = UIInterfaceOrientationPortrait`。

## 复现
`pw_run_arm.sh <label> live-soak -PWLiveFullResolution -PWAutoRunSeconds 70 -PWXrslamGpuFrontend -PWYamlOverride solver.time_limit=0.1 -PWYamlOverride solver.iteration_limit=10`
