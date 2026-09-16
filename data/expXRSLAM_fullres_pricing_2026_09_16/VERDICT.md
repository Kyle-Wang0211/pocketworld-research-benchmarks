# 1920×1440 全分辨率定价与 split 判决（2026-09-16）

臂：`gpufe_nothread`（GPU 前端 ON + 线程化 OFF）。设备 iPhone15,2 / iOS 26.6.1。
通道：`replay-device-recording`（设备录像 849 帧，输入逐字节固定）与 `live-soak`。

## 一、整帧三分账（凉态 nominal/fair，31.94 ms/帧 = 31.3 fps）

| | ms/帧 | 占比 |
|---|---|---|
| 前端（GPU preprocess 等待 10.84 + 金字塔 2.04 + 光流 1.69 + 其他 0.68） | 15.25 | 48% |
| **XRSLAM 后端**（`track()` 9.50 ms×756 帧；`mirror_frame` 0.05；初始化 1.64×44） | 9.12 | 29% |
| 台架回放 I/O 等其余 | 7.56 | 24% |

后端计时是本次新加（`frontend_worker.cpp` 的 RAII `PwScope` → `xrslam_gpufe_stats.json` 的 `backend_ms`）；
XRSLAM 上游只有 `feature_tracker_time` 一条通道，后端零计时。

🔴 **修正**：09-16 早先一版估计"61% 在后端+台架"，那是基于一场**热降频**数据（19.35 fps），错。

## 二、`-PWXrslamGpuFrontendSplit`（把 CLAHE+detect 的融合提交拆成两次）

### 凉态（nominal/fair）：无损 +26%，轮转臂序四场

| 场次（顺序） | fps | 整帧 ms | `pre_wait` | poses.tum sha |
|---|---|---|---|---|
| base（先） | 31.31 | 31.94 | 10.84 | `e8829182de317d64` |
| split（后） | **39.61** | 25.25 | 2.44 | 同 |
| split（先） | **39.53** | 25.30 | 2.45 | 同 |
| base（后） | 31.53 | 31.71 | 10.74 | 同 |

臂内重复度 <1%；**四场位姿逐字节相同** ⇒ 不是拿精度换速度。

### 机制：空提交延迟

| | base | split |
|---|---|---|
| `empty_submit_ms`（凉） | 0.61–0.62 | **5.96–6.25** |
| `empty_submit_ms`（serious） | 0.63–0.66 | **6.57–6.73** |
| GPU 忙时（凉） | 10.86 | 2.72 + det 2.29 = 5.01 |

拆开多付约 5.4–6.1 ms 空提交延迟，凉态下省的 GPU 忙时（−5.85）与等待（−8.4）远大于它。
`pw_gpu_frontend.cpp:109` 注释记着 **09-04/05 直播降频下这笔涨到 11–19 ms 并"tipped the pipeline into collapse"** ——
本次热态实测为 6.6–6.7 ms，**未达该区间**，也未出现回放通道的崩溃。

### 热态（全程 serious）：未判定

| 场次 | 臂 | fps | 空提交 | GPU 合计 |
|---|---|---|---|---|
| hot1 | ON | 25.83 | 6.57 | 3.95 |
| hot2 | off | 28.73 | 0.63 | 10.67 |
| hot3 | off | 28.00 | 0.66 | 10.85 |
| hot4 | ON | 35.69 | 6.73 | 4.80 |

off 臂稳（28.73/28.00，差 2.6%），**ON 臂飘 38%**（25.83/35.69）。ABBA 均值 ON 30.76 vs off 28.37（+8.4%），
但臂内方差大于臂差 ⇒ **不下判决**。加跑至每臂 6 场的数据见 `results.jsonl` 中 `ha*/hb*`。

## 三、两个失败的实验（记下来免得重做）

1. **GPU 逐核时间戳走不通**：`gpu_kernel_ms` 恒为 `{}`。env 名是 `OFFICIAL_AETHER_GPU_TIMESTAMPS`
   （不是 `pw_gpu_frontend.cpp` 注释写的 `AETHER_GPU_TIMESTAMPS`，编译期宏 `AETHER_GPU_TIMESTAMPS_ENV_OFFICIAL` 切换）；
   名字改对后仍空 ⇒ **适配器不advertise TimestampQuery**。改用结构法（`SPLIT` 旗标）分段。
2. **直播静放做热态斜坡失败**（六场作废）：① 第二场起就全程 serious，斜坡没形成；
   ② **静放不初始化 ⇒ 走到检测的帧数本身不稳定**（`det_gpu` 在 0.09 与 9.03 之间跳）。
   教训：论证"与内容无关"时只考虑了**单帧成本**，漏了**有多少帧走到该阶段**这一层。

## 四、复现
```
pw_run_arm.sh <label> replay-device-recording -PWXrslamGpuFrontend -PWHalfFrameRate [-PWXrslamGpuFrontendSplit]
```
逐场 `xrslam_gpufe_stats.json` 收在 `stats/`，摘要在 `results.jsonl`。
