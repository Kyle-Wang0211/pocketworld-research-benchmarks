---
artifact_contract: "ce-handoff/v1"
created_at: "2026-08-30T02:04:13Z"
title: "PocketWorld VIO 三臂替代 Bench：时基、预览与最终替代判决交接"
summary: "交接 Basalt、XRSLAM、生产同配 ARKit 三臂 iPhone Bench 的前因后果、冻结边界、已实现代码、首轮真机暴露的时基与预览问题，以及形成替代判决前的完整执行和验收路径。"
keywords: ["PocketWorld", "VIO", "Basalt", "XRSLAM", "ARKit", "iPhone", "benchmark", "handoff", "clock-domain", "camera-preview"]
cwd: "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829"
resume_focus: "先修复并证明统一单调时基和零拷贝相机预览，不得把当前真机截图中的荒谬延迟当作算法结果；随后完成全套验证、重新装独立 Bench App，并按冻结合同分别运行 Basalt、XRSLAM、ARKit 与 EuRoC 重放，直到能给出是否可替换生产 ARKit 的证据判决。"
repository: "pocketworld-research-benchmarks"
repo_root_sha: "d73f0fb01bc2acff2d90c79284d017ee592438ed"
branch: "research/basalt-vio-phone-bench-20260829"
head: "f1df88b09022d363d851b8f20901fae243f66fff"
worktree_path: "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829"
---

# 先读：这份文件的地位与持久化硬规则

这是一份跨会话继续工作的长期交接，不是一次聊天摘要，也不是已经通过的实验报告。接手者必须用代码、测试、设备收据和不可变实验产物重新核实这里的状态；不能因为本文描述了某个意图，就把它当成已经实现或已经验收。

用户在 2026-08-30 明确追加了以下长期规则：

1. 交接、恢复提示词、关键项目状态和长期记忆不得只写入 `/tmp`、`/private/tmp` 或其他会被系统清理的临时目录。
2. 这类内容必须写成能够长期保留的 Markdown，放在项目版本库内，并在不混入其他脏改动的前提下提交、推送到远端。
3. 临时目录仍可按既有设备构建协议承载可再生的签名/构建输出，但绝不能成为交接文档、源码或实验真相的唯一存储位置。
4. 本文件的长期本地地址是：
   `docs/handoffs/VIO_THREE_ARM_BENCH_HANDOFF_2026-08-30.md`。
5. 远端目标是：
   `https://github.com/Kyle-Wang0211/pocketworld-research-benchmarks/blob/research/basalt-vio-phone-bench-20260829/docs/handoffs/VIO_THREE_ARM_BENCH_HANDOFF_2026-08-30.md`。

# 一句话目标

用一个与生产 PocketWorld 完全隔离、但在同一台真实 iPhone 上运行的三臂 Bench App，公平验证 Basalt 与 XRSLAM 是否能够在启动速度、实时吞吐、延迟、零输入损失、功耗/热/内存代理、固定输入精度和后续生产影子门槛上达到或超过当前生产 ARKit；只有证据全部通过，才讨论替换生产位姿源。

# 用户真正要解决的问题

生产管线现在使用 ARKit。PocketWorld 同时长期研究跨端 VIO，希望未来 iOS、Android 使用同一套通用 C++ 核心，Dart 负责跨端配置、状态、日志、质量比较和产品决策，Swift/Kotlin 只做传感器运输与极薄平台桥接。

过去 XRSLAM 在生产影子运行中反复出现过非常大的位姿误差、时基不通过、跨队列抢锁、相机队列满、停止漏投和误导性健康收据。用户的判断一直是：成熟上游出现数十度或数百米级差距，首先应检查是否没有完整复刻输入、坐标、线程、停止或时基语义，而不是自研补丁掩盖问题。

后来提出 Basalt 作为第二个候选。用户指出：Basalt 没有现成 iOS/Android 实时 App 管线，XRSLAM 也同样没有；所以二者在“需要我们自己搭手机运输层”这一点上处于同一起跑线，不能因为 XRSLAM 已经嵌入生产影子就天然偏袒它。

因此当前任务不是继续在生产 App 里一边拍摄一边试错，而是建立一个对等、隔离、可复验的 Bench：

- Basalt 真机臂；
- XRSLAM 真机臂；
- 与现生产配置一致的 ARKit 参考臂；
- Basalt/XRSLAM 的完全相同 EuRoC 固定输入重放；
- 完整记录启动、输入、输出、时基、队列、停止、资源和精度证据；
- 最终回答“什么时候可以替换 ARKit”，而不是只回答“某段代码能否编译”。

# 为什么是一个 App 里的三条臂，但不能同时跑

用户担心三条线塞进一个 App 会互相打架、导致公平性混乱。当前设计的答案是：同一个独立 App、同一个指标体系、同一个结果格式，但每次运行只能独占选择一条臂。

三条臂不能同时争用相机、IMU、CPU、内存和热预算。并发运行既不是公平测试，也会重现生产影子互相干扰的问题。`BenchRunLease` 因而保证一个进程同一时间只有一个活动引擎和一份输出目录；上一条臂必须停止、排空、销毁并释放租约，下一条臂才能开始。

这不是“把三套算法混在一起”。Basalt 和 XRSLAM 分别放在两个私有动态框架中：

- `PWBasaltEngine.framework`
- `PWXRSLAMEngine.framework`

这样固定 Basalt 的 OpenCV 4.12.0 与 XRSLAM 的 OpenCV 4.0.1 不会因为静态合入同一个 Mach-O 而出现符号/ABI 污染。ARKit 臂不进入任何 C++ VIO 核心，而是自己持有一条生产同配 `ARSession`。

# 与生产 PocketWorld 的安全边界

Bench App：

- 产品名：`VIOReplacementBench`
- Bundle ID：`com.kyle.viobench`
- 数据容器：独立于 PocketWorld
- 目标设备：当前真实 iPhone

生产 App：

- Bundle ID：`com.kyle.PocketWorld`
- 本地仓库：`/Users/kaidongwang/Developer/pocketworld`
- 远端：`https://github.com/Kyle-Wang0211/pocketworld`
- 交接时分支：`codex/ptol-phone-ab-20260825`
- 交接时 HEAD：`f4422a86b14364fba8d29ceca9c3325c8bd0f568`

本 Bench 任务严禁安装、卸载、替换、启动或清理 `com.kyle.PocketWorld`。不得用 `flutter drive` 碰生产 Bundle。Bench 的设备安装只允许针对 `com.kyle.viobench`。

生产 ARKit 参考配置的权威实现入口：

- `/Users/kaidongwang/Developer/pocketworld/ios/Runner/OfficialAetherARKitPlugin.swift`
- 冻结合同引用其中的 `startSession` 行为，而不是另造一个“看起来差不多”的 ARKit 默认配置。

# 仓库、分支、远端与工作树

研究仓库主工作树：

- 本地：`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`
- 远端：`git@github.com:Kyle-Wang0211/pocketworld-research-benchmarks.git`
- GitHub：`https://github.com/Kyle-Wang0211/pocketworld-research-benchmarks`

当前 Bench 隔离工作树：

- 本地：`/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829`
- 分支：`research/basalt-vio-phone-bench-20260829`
- 基础 HEAD：`f1df88b09022d363d851b8f20901fae243f66fff`
- 根提交：`d73f0fb01bc2acff2d90c79284d017ee592438ed`

重要：交接创建时，Bench 源码、OpenSpec、实验合同、测试、vendor 收据和 `.gitignore` 修改仍大多是未提交或未跟踪状态。本文件会单独提交和推送，但这不等于 Bench 源码已经远端持久化。接手后必须先冻结/审计现有脏工作，再决定如何把 Bench 实现分批提交；绝对不能 `git add .`、reset、clean 或覆盖用户/其他工作。

# 冻结上游与依赖身份

这些身份已写入 `experiments/basalt_vio_phone_bench_2026-08-29/contract.json`，后续实验不得静默漂移：

## Basalt

- 上游 commit：`0f3b2b52c807f70ff4e2973ce253c73329eea7bc`
- headers commit：`aa441ba3e51050c47ba1902537792a2e4db7e43d`
- vcpkg commit：`1e199d32ad53aab1defda61ce41c380302e3f95c`
- vcpkg registry baseline：`05442024c3fda64320bd25d2251cc9807b84fb6f`
- 官方基线配置：上游 `data/euroc_config.json`
- OpenCV：4.12.0
- 模式：VIO-only float
- 不创建全局并行度控制；不能为“让它跑起来”而悄悄改算法配置。

## XRSLAM

- 上游 commit：`4beb1a942f33da9afbfae2d70e2c641cfc2bb675`
- OpenCV：4.0.1
- Ceres：1.14
- `XRSLAM_IOS=false`
- frozen generic core threading：关闭
  - **2026-08-31：这一项是 XRSLAM 在真机上崩溃的直接原因。** 关闭线程后
    `xrslam/src/xrslam/utility/worker.h` 的 `resume()` 会就地执行 `worker_loop()`：

    ```cpp
    void resume(std::unique_lock<std::mutex> &l) {
        l.unlock();
    #if defined(XRSLAM_ENABLE_THREADING)
        worker_cv.notify_all();   // 唤醒工作线程,立即返回
    #else
        worker_loop();            // 在调用者栈上跑完整个 worker
    #endif
    }
    ```

    于是 `XRSLAMPushSensorData(CAMERA)` 一路展开成前端加后端的嵌套执行，栈耗尽，
    在设备上表现为第一帧 SIGBUS。已排除的其他解释：首帧前无 IMU（补了仍崩）、
    分辨率（640x480 与 1920x1440 同样崩）、缓冲区越界（补一行冗余无变化）、
    配置传路径还是内容（由 `XRSLAM_IOS` 决定，本构建传路径是对的）。
  - 上游为 iOS 构建时**必开**此项：顶层 `CMakeLists.txt` 的 `if(IOS)` 同时置
    `XRSLAM_IOS ON` 与 `XRSLAM_ENABLE_THREADING ON`。两个都关的组合上游从不发布。
  - 两个开关性质不同，不可混为一谈：`XRSLAM_IOS` 会切到 iOS 专用路径（静态库、
    配置改传内容），跨端要求下不能开；`XRSLAM_ENABLE_THREADING` 只改 `Worker`
    是否起线程，Android 与桌面是同一份代码，开启不引入任何平台分叉，也不改算法。
- 允许的 lifecycle patch 只补显式 destroy 生命周期，不改算法；补丁：
  `tools/ios_basalt_vio_bench/Vendor/patches/xrslam_destroy_lifecycle.patch`
- 现有 archive 混有 iOS 26.2 object build version，因此统一 Bench 如实声明 iOS 26.2；不能拿 receipt 中较低版本伪装兼容。

## ARKit 参考臂

- 角色：同设备、生产同配的系统参考；不是真值。
- 配置：`ARWorldTrackingConfiguration`、autofocus 开、gravity alignment、light estimation 关、horizontal plane detection、锁定 1920×1440 高分辨率能力格式、主 delegate queue、启动时 reset tracking 与移除 anchors。
- ARKit 不接受 EuRoC 重放，因此不能用 ARKit 的实时轨迹当 Basalt/XRSLAM 固定输入精度真值。

## 官方/上游链接

- Basalt：`https://github.com/VladyslavUsenko/basalt-mirror`
- XRSLAM：`https://github.com/openxrlab/xrslam`
- EuRoC：`https://projects.asl.ethz.ch/datasets/doku.php?id=kmavvisualinertialdatasets`
- EuRoC DOI：`10.3929/ethz-b-000690084`
- Apple ARKit：`https://developer.apple.com/documentation/arkit`

# 已经写出的设计与规格

先读以下文件，顺序不要反：

1. `docs/plans/2026-08-29-basalt-ios-vio-bench-design.md`
   - 一页级总体目标、三臂/双通道实验、证据边界与安全边界。
2. `openspec/changes/add-dual-vio-phone-bench/design.md`
   - 公平性、二进制隔离、每个上游输入适配器和允许/禁止的结论。
3. `experiments/basalt_vio_phone_bench_2026-08-29/contract.json`
   - 唯一机器可读实验合同；冻结输入、版本、门槛、终止条件和产物。
4. `docs/plans/2026-08-29-basalt-ios-vio-bench-implementation.md`
   - 原实施顺序。
5. `openspec/changes/add-dual-vio-phone-bench/tasks.md`
   - 当前任务勾选状态；注意勾选仅表示代码已写，不代表首轮真机结果有效。
6. `experiments/basalt_vio_phone_bench_2026-08-29/source_manifest.json`
   - 曾冻结的一次源码与二进制哈希快照。里面的 `/private/tmp/...` 是历史可再生构建位置，不是长期文件地址；用 SHA-256 与仓库文件身份，不得依赖临时路径仍存在。

# 当前代码地图

所有路径均相对于研究 Bench 工作树。

## App 与三臂选择

- `tools/ios_basalt_vio_bench/BasaltVIOBench/BasaltVIOBenchApp.swift`
  - SwiftUI App 入口。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/ContentView.swift`
  - 当前配置页、开始/中止按钮与实时指标；当前没有相机预览。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchViewModel.swift`
  - 权限、状态、开始/停止与 UI 快照桥接。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchBackend.swift`
  - Basalt/XRSLAM/ARKit 三臂身份。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchMode.swift`
  - live soak、replay paced、replay max。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchRunLease.swift`
  - 一次只允许一条臂。

## 运行协调、状态与指标

- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchmarkCoordinator.swift`
  - 从准备、启动、全量 300 秒计量、心跳、排空、终态收据到门槛判定的主状态机。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchmarkTiming.swift`
  - 当前 0 秒 warm-up、300 秒全部计分。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BenchGateEvaluator.swift`
  - live/replay 绝对门槛。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/LiveRunValidity.swift`
  - 任一输入或结果损失使实验无效。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/Metrics/SystemMetricSampler.swift`
  - CPU、内存、热、电量代理；公开 iOS API 不能给校准瓦数，所以 `power_w` 必须为 null。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/Receipts/`
  - started/heartbeat/terminal receipt、诊断、崩溃恢复、artifact finalizer。

## 统一传感器运输

- `tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/LiveSensorTransport.swift`
  - AVFoundation/CoreMotion 原始输入、同一相机格式、各引擎适配语义。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/MonotonicClockMapper.swift`
  - Core Media host clock 与 Core Motion uptime 的映射。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/GyroDrivenIMUAssembler.swift`
  - Basalt 的 gyro-timestamped IMU 与加速度插值。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/BoundedNonblockingHandoff.swift`
  - 回调线程不阻塞的有界移交。
- `tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/SensorTransportAccounting.swift`
  - 每种拒绝、丢帧、回归和中断的累计账。

## Basalt 核心桥

- `tools/ios_basalt_vio_bench/BasaltVIOBench/Native/BasaltBench.h`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/Native/BasaltBench.mm`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/BasaltNativeSession.swift`
- `tools/ios_basalt_vio_bench/BasaltBackend/Exports.txt`
- `tools/ios_basalt_vio_bench/cmake/BasaltVIOCore.cmake`

## XRSLAM 核心桥

- `tools/ios_basalt_vio_bench/XRSLAMBackend/Native/XRSLAMBench.h`
- `tools/ios_basalt_vio_bench/XRSLAMBackend/Native/XRSLAMBench.cpp`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/XRSLAMNativeSession.swift`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/XRSLAMPoseAdapter.swift`
- `tools/ios_basalt_vio_bench/XRSLAMBackend/Exports.txt`
- `tools/ios_basalt_vio_bench/XRSLAMBackend/Config/`

## ARKit 生产参考桥

- `tools/ios_basalt_vio_bench/BasaltVIOBench/ARKitReference/ARKitReferenceSession.swift`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/ARKitReference/ARKitReferenceAccounting.swift`
- `tools/ios_basalt_vio_bench/BasaltVIOBench/Config/arkit_production_reference.json`

## 固定输入重放与精度

- `tools/ios_basalt_vio_bench/Replay/EuRoCReplayLoader.swift`
- `tools/ios_basalt_vio_bench/Replay/ReplayScheduler.swift`
- `tools/ios_basalt_vio_bench/Evaluation/TrajectoryEvaluator.swift`
- `tools/ios_basalt_vio_bench/Evaluation/TUMTrajectoryLoader.swift`
- `tools/ios_basalt_vio_bench/Evaluation/Geometry.swift`

## 构建、冻结和验证

- `tools/ios_basalt_vio_bench/project.yml`
  - XcodeGen 项目定义；统一 App、两个私有框架、测试 Bundle。
- `tools/ios_basalt_vio_bench/scripts/fetch_vendor.sh`
- `tools/ios_basalt_vio_bench/scripts/verify_vendor.sh`
- `tools/ios_basalt_vio_bench/scripts/build_ios_arm64.sh`
- `tools/ios_basalt_vio_bench/scripts/freeze_source_manifest.py`
- `tools/ios_basalt_vio_bench/Validation/validate_bench_artifact.py`
- `tools/ios_basalt_vio_bench/Validation/tests/`
- `tools/ios_basalt_vio_bench/BasaltVIOBenchTests/`

# 已实现到什么程度

## 已经存在的实现

- 三臂统一 UI 与运行模式选择。
- 进程级互斥租约，不允许多臂并发。
- Basalt 与 XRSLAM 私有动态框架隔离及受控导出符号。
- Basalt gyro-driven IMU 组装。
- XRSLAM 相机、陀螺仪、加速度计同一串行回调顺序与通用 C++ 核心包装。
- ARKit 生产同配参考 session 与独立 accounting。
- Basalt/XRSLAM 统一 640×480、30Hz、full-range NV12 luma 的实时输入合同。
- 0 秒排除 warm-up、整整 300 秒计分的产品时长合同。
- 首个可用位姿、处理帧率、P95 pipeline latency、队列损失、CPU、内存、热、电量代理、有限位姿比例等指标结构。
- started/heartbeat/terminal receipt 与中断恢复。
- EuRoC MH_01_easy 单目 cam0+IMU 重放、SE(3) 固定尺度对齐、ATE/RPE 计算。
- 大量 schema、Swift、Objective-C++/C++ 与 Python 测试文件。
- 独立 Bench App 已经成功装到手机并能进入 Basalt live soak 页面、启动相机权限和产生位姿输出。

## 只实现了一半或尚未得到真机证据的部分

- 源码和规格大多仍在脏工作树中，尚未形成远端可恢复的实现提交序列。
- `source_manifest.json` 是一次快照，但当前状态必须重新冻结；不能把旧 manifest 当最新提交。
- 设备端首次运行暴露了严重的跨时钟域错误，当前延迟数据完全无效。
- 当前 UI 没有相机画面，用户无法按真实拍摄轨迹操作五分钟，也无法知道算法看到什么。
- 尚未获得一场完整、终态收据可验证、零损失的 Basalt 300 秒 live run。
- 尚未获得一场完整、终态收据可验证、零损失的 XRSLAM 300 秒 live run。
- 尚未获得一场生产同配 ARKit 300 秒参考 run。
- 尚未在同一 Bench 二进制上完成 Basalt/XRSLAM 的相同 EuRoC manifest replay-paced 与 replay-max。
- 尚未形成 Basalt/XRSLAM 对 ARKit 的最终“可替换/不可替换/证据不足”判决。
- 尚未有外部地面真值的 live trajectory，因此任何“实时精度超过 ARKit”的说法都被禁止。

# 首轮真机到底暴露了什么

用户在真机 Basalt 5 分钟 live soak 中看到：

- 阶段：`measuring`
- 运行约 97 秒
- 处理帧率：约 30.0 fps
- 位姿计数：2892
- 相机/App 丢帧 UI：0/0
- CPU 核等效：约 0.35
- 物理内存：约 38 MB
- 热状态：`nominal`
- “首个可用位姿”：约 `81,219,577 ms`
- “P95 延迟”：约 `81,219,463.2 ms`
- 页面没有相机预览。

前六项只能说明 App 在持续收到/发布事件，不能说明轨迹准确；最后两个延迟数值在 97 秒会话里不可能成立，因此这一场实验是无效诊断 run，绝不能用来比较 Basalt、XRSLAM 或 ARKit。

## 时基问题的最可能根因

`LiveSensorTransport` 把相机/IMU 映射到 Core Media host-clock nanoseconds；`BenchmarkCoordinator` 的 run start 与 `now` 使用 `DispatchTime.now().uptimeNanoseconds`。在 iOS 上，这两个底层时基不应未经证明就按绝对值相减，尤其会在设备睡眠累计时间上产生巨大常量偏移。

当前代码的 `firstPoseLatencyMilliseconds` 使用：

`pose.capturedMonotonicNanoseconds + pose.pipelineLatencyNanoseconds - runStartNanoseconds`

如果 pose capture 的绝对时基与 runStart 的绝对时基不同，就会得到截图中约 81,219 秒的伪延迟。这个量级很像设备不同 monotonic clock 对睡眠累计语义的差，而不是 Basalt 真花了二十多个小时。

这仍是需要测试钉死的诊断结论，不得直接靠改常量“修正”。正确做法是给整个 Bench 选定唯一的单调时基，并让以下所有时间都来自同一 provider 或经过一次明确映射：

- run start/end；
- camera capture；
- Core Motion；
- queue admission；
- native publication；
- heartbeat；
- system samples；
- receipt monotonic fields。

修复必须新增真机/单元不变量：任何 first-pose 或 pipeline latency 均不得大于当前 run elapsed 加上一个很小的调度余量；负值、溢出、不同域相减必须直接令实验 invalid，而不是截成 0 或继续出分。

## “手机放桌上，位姿仍然增加”并不等于位置在漂移

当前 UI 的“位姿 2892”是 pose output sample count，不是累计位移米数。一个 VIO 即使手机静止，也应该继续在每个处理周期发布当前位姿，所以该数字仍以约 30/s 增长是正常现象。

但 UI 文案确实会误导用户。必须改成“位姿输出数”，并另行显示真正有意义的稳定性证据，例如：

- 从某个静止段起点到当前的平移漂移（m）；
- 旋转漂移（deg）；
- finite/nonfinite 状态；
- 最近一秒输出率；
- 可选的 tracking/quality 状态（上游真实提供时才显示，不能自造置信度）。

静止漂移仍不能替代有真值精度实验，只能用于即时 sanity check。

## 没有相机预览不是算法证明，而是 Bench 产品缺口

机器合同当前明确写了 `preview_enabled: false`，`ContentView.swift` 也只有 Form 和数字。这是此前为减少 UI 干扰做的设计决定，但用户已经推翻它：五分钟真机测试需要按真实拍摄方式移动，如果看不到摄像头，就无法知道取景、运动和覆盖轨迹。

下一版必须显示所选臂正在使用的同一相机流，不能另开第二个相机 session，也不能为预览复制/压缩每一帧或阻塞 sensor callback。推荐边界是：

- Basalt/XRSLAM：把 `LiveSensorTransport` 已有 `AVCaptureSession` 只读呈现给一个 `AVCaptureVideoPreviewLayer`；预览不进入算法队列、不改变像素格式、不改变时间戳、不计入算法处理耗时。
- ARKit：使用同一个 `ARSession` 的相机背景/视图呈现，不能额外启 AVFoundation。
- UI 层只负责显示，不拥有相机生命周期；开始/停止仍由 coordinator 状态机唯一管理。
- receipt 记录 `preview_enabled=true`、预览实现模式和是否出现 UI/background 生命周期异常。

# 实验两条通道分别回答什么

## 通道 A：真机 live soak

Basalt/XRSLAM 使用相同的 AVFoundation/CoreMotion 输入合同；ARKit 使用生产同配私有 sensor chain。三条臂分开跑，完整 300 秒，无排除 warm-up。

它回答：

- 首个可用位姿能否在生产 1800 ms fallback 内交付；
- 是否能持续接近目标帧率；
- pipeline P95 是否可接受；
- 是否零输入/队列/输出损失；
- CPU、内存、热、电量代理是否不劣于 ARKit；
- 停止是否真正封入口、排空、销毁并返回终态收据。

它不回答 live 绝对轨迹精度，因为没有外部真值。

## 通道 B：EuRoC 固定输入 replay

Basalt 与 XRSLAM 使用同一 `EuRoC_MH_01_easy` cam0+IMU manifest、同一 evaluator、同一 SE(3) fixed-scale 规则，分别运行 paced 与 max。

它回答：

- ATE RMSE；
- 1 秒 RPE translation RMSE；
- 1 秒 RPE rotation RMSE；
- ground-truth coverage；
- 固定输入下的运行速度与资源。

ARKit 不可被喂入 EuRoC，因此没有 ARKit replay 臂。

# 冻结验收门槛

来自 `contract.json`，未经 OpenSpec 明确变更不得在看到结果后调线。

## Live 绝对门槛

- first usable pose latency ≤ 1800 ms；
- 30 FPS 臂 processed FPS ≥ 27；否则 ≥ 冻结目标 FPS 的 90%；
- P95 pipeline latency ≤ 66.7 ms；
- app drop rate = 0；
- thermal critical seconds = 0；
- thermal serious seconds = 0；
- peak physical footprint ≤ 750 MB；
- finite pose ratio ≥ 0.995；
- 全程与最终排空期间的相机、IMU、handoff、native queue、pose bridge、timestamp 与 nonfinite loss 必须全部为 0。

## Replay 精度门槛

- ATE RMSE ≤ 0.10 m；
- RPE translation RMSE ≤ 0.05 m；
- RPE rotation RMSE ≤ 5°；
- ground-truth coverage ≥ 0.99。

## 真正替代 ARKit 的额外条件

候选不仅要过自己的绝对门槛，还必须在同一设备、同一 OS、分别运行的 live soak 中，在启动交付、P95 延迟、传输损失、热、内存、CPU 和电量代理上不劣于 ARKit 参考臂。

即使这些都通过，仍需：

- 独立外部真值的 live accuracy 证据；
- 回到 PocketWorld 的隔离 production-shadow 验证；
- 证明候选不会干扰自动取帧、AR 云显示、12MP 相机或后台 COLMAP；
- iOS/Android 同 commit、同参数、同通用 C++ 核心与平台薄运输层的证据。

# 下一阶段完整执行顺序

下面是顺序依赖，不是可以随意并行打乱的“建议清单”。

## 1. 先保护当前状态

- 读取本交接与上述 OpenSpec/合同。
- 记录 `git status`、所有未跟踪文件、当前 source manifest 与 vendor hashes。
- 不 reset、不 clean、不 checkout 覆盖、不 `git add .`。
- 为 Bench 实现按逻辑拆分可审核提交；每次只 stage 明确文件。
- 任何长期交接继续写在 `docs/handoffs/`，绝不只放临时目录。

## 2. 用测试先钉死唯一时基

- 抽象一个统一 `BenchMonotonicClock`/provider，或让 run start 也来自 Core Media host clock；只能选一个绝对域。
- Camera、Motion、coordinator、native publication 与 metrics 使用该域或显式转换。
- 新增针对 sleep-offset/anchor-offset 的测试：故意给两个时钟一个大常量偏移，保证映射后 latency 仍是小的真实差值。
- 新增 first-pose/P95 上界不变量与 invalid receipt 测试。
- 检查 ARKit callback latency 是否也使用同一域，不能只修 Basalt/XRSLAM。
- 更新 contract 和 source manifest，明确唯一时钟语义。

停止条件：只要时钟域仍混用，禁止重装和再次让用户举手机跑五分钟。

## 3. 加入不改变算法输入的实时预览

- Basalt/XRSLAM 复用同一个 `AVCaptureSession` 的 preview layer。
- ARKit 复用同一个 `ARSession` 的 camera background。
- 不开第二 session，不做额外 per-frame 图像拷贝，不改变算法像素、分辨率、FPS、时间戳或队列。
- 预览视图要能在三臂切换前配置、运行中固定、停止后立即释放。
- 测试预览开关不改变 input/accepted count、drop count、hash/config receipt。
- UI 将“位姿”改成“位姿输出数”，增加静止漂移 sanity 字段，但不伪造算法置信度。

停止条件：如果预览会改变算法输入合同或造成任何 drop，这个实现不能进入正式测试。

## 4. 完成源码、vendor、二进制与测试审计

- `verify_vendor.sh` 验证固定上游、依赖、patch 与 archive hash。
- Python schema/validator tests 全过。
- Swift/Objective-C++/C++ unit tests 全过。
- unsigned Release device build 成功。
- 检查 bundle 只有 `com.kyle.viobench`；绝不能出现生产 Bundle。
- 检查两个 framework 的导出符号只有各自 C bridge，不能暴露/重叠 OpenCV 符号。
- 检查 app/framework deep signature、arm64、deployment target 与资源 hash。
- 重新生成 source manifest，永久保存 hashes；manifest 不能依赖临时产物路径长期存在。
- 进行 fresh-context read-only review，审查公平性、上游复刻、时基、资源隔离、停止和门槛实现。

## 5. 只安装修复并验收过的独立 Bench

- 只安装 `com.kyle.viobench`。
- 不触碰 `com.kyle.PocketWorld`。
- 安装后核验设备上实际 bundle ID、可执行文件 UUID/hash、两个 framework hash 和实验 marker；不能只看同样的 build number。
- 不打开一堆 Terminal 窗口；优先用非 GUI 构建/安装路径。若设备签名/安装确实受项目既定 runbook 限制，只用一个专用窗口并关闭完成窗口。

## 6. 先做 10–20 秒诊断 run，再做五分钟正式 run

诊断 run 只验证：

- 相机预览与实际输入一致；
- first pose 数值在 0–1800 ms 合理区间；
- P95 不可能大于 run elapsed；
- 手机静止时 pose count 继续增长，但平移/旋转漂移合理且可解释；
- 所有 drop/rejection 为 0；
- 中止能生成 terminal receipt。

只有诊断 run 合格，才让用户按真实拍摄方式各举手机五分钟。不能再让用户先付出五分钟，然后才发现基础时钟坏了。

正式 live 顺序建议固定并记录环境：

1. ARKit reference 300 秒；
2. Basalt 300 秒；
3. XRSLAM 300 秒。

不同 live 轨迹不是精度 A/B，因此每臂至少要有独立有效 run；温度、电量起点和冷却条件必须记录，必要时进行拉丁方/交错顺序复测，不能用一次先后顺序直接定功耗输赢。

## 7. 运行固定输入 replay

- 准备并验证 EuRoC MH_01_easy 内容 manifest。
- Basalt replay-paced。
- XRSLAM replay-paced。
- Basalt replay-max。
- XRSLAM replay-max。
- 每一条都验证 input count、zero loss、poses.tum、receipt.json、SHA256SUMS 与 evaluator 结果。
- 失败/无效 run 也保留，不删除、不覆盖。

## 8. 最终判决格式

对每个候选给出三态之一：

- `eligible_for_product_shadow`：全部绝对门槛、同设备 ARKit 不劣门槛和固定输入精度都通过；仍不等于已替代生产。
- `not_eligible`：有明确、可复验的失败门槛。
- `insufficient_evidence`：时基、输入、收据、真值或公平条件不足。

在外部 live ground truth 与 PocketWorld product-shadow 前，不得写“Basalt/XRSLAM 已经比 ARKit 更准”或“可以直接替换”。

# 验证命令入口

先在 Bench 工作树执行。具体 SDK/device destination 需按当前机器发现结果填写，不能照抄历史临时输出路径。

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829
git status --short
python3 tools/ios_basalt_vio_bench/scripts/freeze_source_manifest.py --help
```

Vendor 与 Python 验证入口：

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench
./scripts/verify_vendor.sh
uv run pytest Validation/tests
```

项目生成与 Xcode 测试入口：

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench
xcodegen generate --spec project.yml
xcodebuild -project VIOReplacementBench.xcodeproj -scheme VIOReplacementBench -showdestinations
```

正式 build/test 命令必须在确认当前 Xcode、SDK、设备 destination 与签名身份后补全；不得为了让命令通过而换依赖、换 Bundle、降低 deployment target 或跳过合同检查。

# 已失败或明确禁止重走的路线

- 不在生产 PocketWorld 里继续并行塞 Basalt/XRSLAM/ARKit 做基准。
- 不让三条臂同时运行。
- 不用 ARKit 实时轨迹当 Basalt/XRSLAM ground truth。
- 不用手机单场素材反推全球 C 端默认参数。
- 不用 30 秒 warm-up 抹掉启动问题；产品很多会话短于 30 秒，当前合同是 0 秒排除、完整 300 秒计分。
- 不把没有相机预览的五分钟 run 当可用用户轨迹。
- 不把 pose output count 误读为累计移动距离。
- 不把截图中八千多万毫秒的延迟当算法慢；先修时基。
- 不用加大队列掩盖 drop，不用丢输入换取表面 FPS。
- 不把 iOS 公共 API 的 CPU/电量代理伪造成校准瓦数。
- 不在看到结果后调门槛。
- 不把临时构建目录当长期源码、交接或实验产物存储。
- 不因为 `source_manifest.json` 记录了某个临时 app 路径，就假定那个路径仍可恢复。

# 接手者第一轮应交付什么

第一轮不要承诺“已完成替代”。应交付以下可审核证据包：

1. 时基根因测试与修复 diff；
2. 预览不改变输入合同的测试与实现 diff；
3. 更新后的 OpenSpec/contract/source manifest；
4. 全量单元、schema、vendor、symbol、unsigned Release build 结果；
5. 独立只读 review 的 findings 与逐项处置；
6. 一个 10–20 秒真机诊断 run 的完整终态收据，证明延迟量级正常、零 drop、停止有效；
7. 只有上述都通过，才申请下一轮 300 秒三臂真机与 EuRoC replay。

# 当前最重要的事实结论

当前 Bench 不是“算法已经输了”，也不是“算法已经能替代 ARKit”。它已经证明三臂隔离骨架与真实手机运行路径存在，但首轮设备测试暴露了一个会污染所有延迟结论的统一时基缺陷，以及一个让用户无法执行真实轨迹的相机预览缺口。

所以现在的正确状态是：`insufficient_evidence / implementation incomplete`。下一步不是再让用户盲举五分钟，也不是改算法参数，而是先把 Bench 自己变成可信测量仪器。
