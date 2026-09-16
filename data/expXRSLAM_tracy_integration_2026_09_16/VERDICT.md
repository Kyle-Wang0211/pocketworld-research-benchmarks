# Tracy 接入：跨端剖析器替换手写计时器（2026-09-16）

## 为什么换
手写的主机侧计时器今天被读错两次：
- `nonfinite_pose_rejected` 把**三种无关原因**折进一个数，导致**每一场直播 run 都被判 invalid**；
- `empty_submit_ms` 被当成**可加的每帧成本**，据此算的账全错（split 提交两次却更快，直接证伪）。

## 选型（用户要求：三端一致，不为单一系统设计）
| 候选 | 平台 | GPU | 许可 | 结论 |
|---|---|---|---|---|
| Apple Instruments / `xctrace` | 仅 Apple | ✅ | — | ❌ 只能当单平台交叉验证 |
| Perfetto | Linux/macOS/Windows/Android，**无 iOS** | 部分 | Apache-2.0 | ❌ 缺 iOS |
| **Tracy v0.14.1** | **Win/Linux/Android/OSX/iOS** | **CPU zones 全平台；GPU zones 走 WebGPU 全平台** | **BSD-3** | ✅ 选它 |

🔴 更正：一度引用二手结论说"Tracy 的 GPU 在 iOS 上不支持"——**那只针对 OpenGL**。
Tracy 自己的能力表（`manual/tracy.tex:1129`）列明 iOS 的 **Metal 与 WebGPU GPU zones 都支持**，而 WebGPU 正是本引擎的 Dawn 栈。

## 集成形态
- 接在**引擎的共享 C++**（不是 Xcode 工程）⇒ Android/Linux 编出来自带同一套 zones；
- CMake 选项 `XRSLAM_TRACY`，**默认 OFF**，关闭时垫片头 `pw_trace.h` 把 `PW_ZONE()` 展开为空，Tracy 头不需在场；
- 旧的手写计时器**一个没删**，两套并排互证。

## 传输（本次最大未知）
- `iproxy`/libimobiledevice 1.4.0 **看不到 iOS 26 设备**；devicectl 隧道地址 `No route to host`；
- ✅ **可行路径 = 局域网**：Bonjour 解析 `kyles-iphone.local` → `192.168.1.32`，`tracy-capture -a 192.168.1.32` 直连。

🔴 **踩过的坑**：给 Apple 平台同时加了 `TRACY_DELAYED_INIT` 和 `TRACY_MANUAL_LIFETIME`，
而手册（`tracy.tex:655`）写明后者下"**profiler 在调用 `StartupProfiler()` 之前根本不存在**" ⇒ 无人监听、抓取端永远 `Connecting to ...`。
去掉 `TRACY_MANUAL_LIFETIME` 后立刻连上。原因已写进 CMake 注释。

## 首次抓取（回放通道，输入逐字节固定）
`Timer resolution: 41 ns | Zones: 3,703 | Time span: 29.6 s`

| zone | 次数 | 均值 ms | 手写计时器 |
|---|---|---|---|
| `backend.work` | 741 | 9.839 | 9.12 |
| `backend.sliding_window_track` | 741 | 9.788 | 9.50 |
| `frontend.gpu.preprocess` | 740 | 5.252 | — |
| `frontend.gpu.prefetch` | 740 | 0.154 | — |
| `backend.mirror_frame` | 741 | 0.051 | **0.05** |

⇒ **两把独立的尺子结论一致**，这正是先前缺的交叉验证。

## 🔴 覆盖尚不完整（下一步）
- `frontend.cpu.clahe_and_pyramid` / `detect_gftt` **零触发**：GPU 前端开着时 CPU 那两段不跑；
- 真正在跑的 **CPU 金字塔**是 `gpu_image.cpp` 里调的 `buildOpticalFlowPyramid`，zone 插错了位置；
- **LK 光流尚未插 zone**。
定价必须等覆盖补全，否则又会拿不完整的账去选靶子（今天已犯过一次）。

## 复现
```
configure_engine_tracy.sh && assemble_tracy.sh && build_bench_tracy_arm.sh
tracy-capture -a 192.168.1.32 -o out.tracy -s 30 -f
tracy-csvexport out.tracy > zones.csv
```
