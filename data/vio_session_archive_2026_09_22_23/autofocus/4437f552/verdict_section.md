## 5. 复刻判决

### 5.1 主线:抄 libcamera RPi 的 CDAF 状态机 + 自己算焦点度量 + 四端镜头适配

**抄哪几个文件(全部 BSD-2-Clause,保留版权头与许可文本)**

| 要抄的件 | 来源(文件:行) | 落到我们哪 |
|---|---|---|
| 搜索状态机(Idle/Trigger/Coarse1/Coarse2/Fine/Settle)、`doScan`、`findPeak`(三点抛物线)、`startProgrammedScan`、`doAF` 的 CDAF 分支、`triggerScan/cancelScan/pause/setMode` | `src/ipa/rpi/controller/rpi/af.cpp:502-767, 915-964`、`af.h` | 一份 C++(与 XRSLAM 同语言,四端共用)`pw_af/af_scan.{h,cpp}`;**删掉** `getPhase/doPDAF/earlyTerminationByPhase/getAverageAndTestIr`(PDAF 与 IR 检测手机上没有这条输入) |
| 参数结构与 json 键(`ranges.normal/macro`、`speeds.normal/fast`) | `af.cpp:38-169` + `imx708.json` 的 `rpi.af` 段 | 同名保留,便于与上游对照;数值必须按手机重标(见 §6) |
| 接口 | `af_algorithm.h:42-57`(`AfRange/AfSpeed/AfMode/AfPause` 四个枚举)、`af_status.h` | 原样保留 |
| 窗口加权 | `computeWeights:267-322`(多窗口按面积合并;无窗口时默认「中 1/2 宽 × 中 1/3 高」) | **默认窗口换成被扫描物体的框**(自动拍摄链已有主体框 / `subjectFootprintRatio`);拿不到主体框时退回 libcamera 的中央窗 |
| **焦点度量(libcamera 没有,这是唯一的缺口)** | Pertuz `fmeasure.m` 的 `TENG`(:188)/`GRAT`(:102),BSD-3;结论依据 Mir 2014 的「一阶导最优 100/99/0.00」 | `getContrast()` 换成「ROI 内 Σ(dx²+dy²)」(Tenengrad),见下 |
| 重对焦与稳定判据 | `doAF:629-667`(`retrigger_ratio` + `retrigger_delay` 双门;Settle 判 Focused/Failed) | 原样抄,只把 AWB R/G/B 那三项换成我们能拿到的亮度统计 |

**焦点度量算在 GPU:是现有管线的副产品,不是新算子**
- `pw_gpu_frontend.cpp:58` 已装载 `sobel_dxdy` 核,`:120` 每帧在 GFTT 前把整幅 CLAHE 图的 Sobel dx/dy 写进 `b_dx_/b_dy_`(`pw_gpufe_wgsl.h:13 k_sobel_dxdy`,OpenCV 4.0.1 `corner.cl` 语义,逐位对过);`:380 k_gftt_max` 已是一支归约核。
- 只需补一支「**ROI 内 Σ(dx²+dy²) 归约**」,读回 1 个 float。纯拍照(VIO 停、GFTT 关)时单独跑 sobel + 归约。
- **不用**现有 `lib/quality/quality_compute.dart` 的 Laplacian 方差驱动镜头:它算在 128×128 缩略图、6 Hz(`:4-21`),分辨率与节奏都不够(AF 每步要 30 Hz 级读数、且要在 ROI 内按全分辨率算)。但它**原样留作验收尺子**(§5.3),因为它跨四端已经一致。
- CPU 退路(Android/Web 无 GPU 前端时):同一算子在 ROI 内用 NEON/WASM 算,ROI 压到 512² 以内即可,3×3 算子成本与像素数线性。

**接在 iOS 相机槽哪一层**
- 读数:`PwCameraSlot.swift:323-395 captureOutput(_:didOutput:)` 已逐帧拿到 `CVPixelBuffer` + PTS + 曝光 + 内参 —— 在这里把 Y 平面交给 `pw_af`;
- 驱动:`:237-241` 的 `setFocusModeLocked(lensPosition:completionHandler:)` 从「启动锁一次」改成「状态机每步调一次」,**`completionHandler` 的 `CMTime` 就是「镜头已到位」的硬信号**(四端里只有 iOS 有),到达后再等 ISP/统计延迟即可读 FoM,不必死等 `step_frames` 帧;
- 快门:`:707 capturePhoto(requestId:)` 之前插一次 `triggerScan()`,等 `Focused`(或 `Failed`/超时)再拍,拍完 `AfPauseDeferred`;
- **标度与方向**:libcamera 内部是屈光度、`focusMin`=远、`focusMax`=近;**iOS/HarmonyOS 的归一化值方向相反(0=最近、1=最远)**,Android 屈光度同向,Web 是米 ⇒ 内部统一用「屈光度式标度(大=近)」,四端各写一个换算,**沿用 libcamera 已有的 `cfg_.map` 分段线性结构**(`setLensPosition:889-904` 的 `cfg_.map.eval`)。iOS 上 `lensPosition = 1 − 归一化近度`。
- **近焦优先**:`startProgrammedScan:736-757` 的起点改成近端 + 步长取负,范围用 `AfRangeMacro` 语义(libcamera `imx708.json` 的 macro = 3–15 屈光度 ≈ 33–6.7 cm,正好覆盖 10–30 cm)。这是**参数与起点的选择**,不是自研算法;首峰即停 ⇒ 多峰时天然取最近者。

**对 VIO 的影响(一句话)**:镜头每动一步 fx 就变,iOS 走「逐帧 `CameraIntrinsicMatrix` 喂引擎」、扫描期间的帧不进滑窗只做 IMU 传播 —— 这是另一份调研(`adaptive_focus_vio_survey_20260922.md`)的题,本份不展开。**口径是:VIO 适应镜头动,不是镜头迁就 VIO。**

### 5.2 次选:Micro-Manager `OughtaFocus`(BSD-3)——为什么不选

`OughtaFocus` 的度量比 libcamera 全(11 种,含 Tenengrad/NormalizedVariance/Volath,`ImgSharpnessAnalysis.java`),而且**自带 ROI**(`CropFactor`,`OughtaFocus.java:71/91/149-150`,居中裁 w×cf、h×cf)。但:
1. 搜索是 **commons-math3 的 Brent 一维优化**(`BrentFocusOptimizer.java:146-181`),假设焦点曲线在搜索区间内单峰 —— 显微镜上成立(样品在载物台,范围窄),手机上对着桌面小物体**多半多峰**(物体 + 背景),Brent 会收到哪个峰不可控,且**没有「取最近峰」的位置**;
2. **没有重对焦触发,也没有稳定判据** —— 用户要的「反复对焦不振荡」「场景变了要重对」这两件事它一件都没有,等于要我们自研这两块(违反「禁止自研」);
3. Java + `MaxEval(100)` 的预算模型不适合逐帧实时;移植到 C++ 等于重写。

⇒ **只从它借两样**:`CropFactor` 的 ROI 做法,和 `computeTenengrad:261-281` 的算子实现参照(与 Pertuz 的 TENG 同式)。

### 5.3 验收判据(台架,不碰 iPhone;两条任务分开评)

用户口径:**主指标是成片在物体上的锐度,对焦时间是次指标**。

| 任务 | 主指标 | 次指标 | 阴性对照 |
|---|---|---|---|
| **A. 按快门瞬间对到物体**(最关键,因为 §4 的景深只有毫米级) | **成片在物体 ROI 上的锐度**:`quality_compute.dart` 同一 Laplacian 方差算子(ROI=主体框),或台架有 ISO 12233 靶时用 MTF50;**与苹果 AF 同场同物成片对照**(`focusMode = .autoFocus` + 同一快门路径);10 / 20 / 30 cm 各 ≥10 次,报**中位数与最差值** | 触发→`Focused` 的帧数与时间;`Failed` 率 | ① 现状锁 `lensPosition = 0.835` 的成片(必须显著低于两者);② 把 ROI 换成全画面算同一指标 —— 若两者排序一致,说明 ROI 策略没起作用,要重新设计 |
| **B. 视频流持续对焦** | 预览帧**物体 ROI** 锐度的时间中位数 | 重触发次数/分钟;**振荡**(连续两次扫描的峰位差 < `step_fine` 却仍重扫 ⇒ 判振荡);每次扫描帧数 | 关掉场景变化门(`retrigger_delay = 0`)看振荡是否出现 —— 证明这道门是承重的 |
| 通用 | 同一静止场景 60 s 内扫描次数 ≤ 1 | 镜头位置曲线可回放(sidecar 已带逐帧内参,可同时画 fx(t)) | |

**数值门槛不预设**:先出对照表,肉眼裁。(历史上四次「指标放行了肉眼否决的东西」,不重蹈。)
