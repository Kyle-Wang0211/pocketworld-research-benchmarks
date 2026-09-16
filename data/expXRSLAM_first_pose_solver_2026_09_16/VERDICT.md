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

---

## 追加：split 在直播通道的实测（2026-09-16）

| 场次 | split | fps | 首位姿 | 初始化尝试 | p95 |
|---|---|---|---|---|---|
| liveB | 关 | 24.7 | 3535 ms | 4 | 168 ms |
| **liveBsplit** | **开** | **27.0** | 3528 ms | 4 | **141 ms** |

**+9.3%**，远小于回放通道的 +19~26%。原因在 GPU 账里：

```
空提交 13.24 ms | pre_gpu 5.13 | det_gpu 8.16 | 等待 3.26 | 金字塔 2.26
```

**空提交延迟从回放的 6.0–6.7 ms 涨到 13.24 ms**，正落在 `pw_gpu_frontend.cpp:109` 注释所记的
09-04/05 直播降频区间（11–19 ms）——但净值仍为正，未出现该注释所说的 "tipped the pipeline into collapse"。

两场**首位姿几乎相同（3528 vs 3535 ms）、初始化尝试均为 4** ⇒ split 不影响初始化，且两次拍摄的运动相近，
这让跨场的 fps 对比更可信。

直播 1920×1440 现状：**27.0 fps / 相机供 29.9 fps ⇒ 吃下 90.3%**。历次直播帧率：10.5 → 14.1 → 20.1 → 24.7 → **27.0**。

🔴 **但这些 GPU 数字都建立在一个待查的前提上**：台架链接的是 **Debug 版 Dawn**
（`build_bench_nothread_arm.sh:9` 指向 `Debug-iphoneos/libwebgpu_dawn.a`，680 MB，断言与 WebGPU 校验层活着），
而同目录下有一个从未被使用的 **Release 版（20 MB）**。一次空 dispatch 13 ms 在原生 Metal 上不可能，
高度怀疑测到的是校验层开销而非 GPU。见 09-11 已记录但未执行的「下一刀=改 Release」。
