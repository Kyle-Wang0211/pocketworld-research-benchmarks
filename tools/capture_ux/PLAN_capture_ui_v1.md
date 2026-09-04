# PocketWorld 拍摄期 AR UI —— 第一版方案（待用户最终确认）

> 标杆：RealityScan AR Guidance（研究见 `RESEARCH_realityscan_capture.md`）。
> 第一版聚焦：**通用 AR Guidance（场景/房间）**，用 414 帧房间数据离线回放调通，不做背景剔除。
> 状态：草案，待用户点头后从 M0 开始动代码。日期：2026-06-17。

## 一、第一版目标（验收）
离线回放模式下，iOS app 复刻 RealityScan AR Guidance 核心体验：
1. 414 帧 + manifest 回放，逐关键帧跑 **DiffMVS 稠密深度** → 反投影累积成**世界稠密点云**。
2. 实时叠加点云，**Render mode 切换**：真彩(Color) ↔ **红→绿覆盖质量(Quality)**。
3. **已拍位姿标记**（相机轨迹 + 小相框缩略图）。
4. **可调 in-capture bounding box**（世界锁定），框内/外点云区分高亮 —— 所见即所得框选。
5. 全程内存 ≤4.1GB（体素下采样 + LOD），渲染目标 30fps。

**第一版刻意不做**：真机实时 ARKit 流(M4)、Object Mode 抠背景、云端、贴图。

## 二、架构（跨端预留，iOS 先行）
```
FrameSource(协议)  ── ReplayFrameSource(读manifest)  [后续 ARKitFrameSource / ARCore / AREngine]
   每帧: RGB + pose(cam→world) + K内参 + timestamp
KeyframeSelector   ── baseline≥6cm 选源视图(记忆铁律), N=5
DepthEngine        ── DiffMVS CoreML(.mlpackage已有), 512×896, .cpuAndGPU(绝不.all)
GeometryStore      ── 体素哈希: 累积深度点; 每体素记录{观测关键帧集合, 视角多样性, RGB}; LOD + 流式
   ├── CoverageModel: 每体素覆盖分 = f(视角数, 角度多样性) → 红/黄/绿
   └── PointRenderer(Metal): 点云 + 着色模式切换 + 位姿标记 + box
ROIBox             ── 世界锁定3D包围盒gizmo, 框内/外区分
```
- 渲染：建议 **Metal 自绘点云渲染器**（撑大点云 + 每点自定义着色 + LOD）；M0 可先 SceneKit 快验再换 Metal。
- 许可证：DiffMVS=Apache✓、融合思路=MIT✓、渲染走 Apple 原生✓。全绿。

## 三、抄什么 / 怎么抄
| RealityScan | 我们第一版 |
|---|---|
| 拍摄期稠密彩色覆盖点云(摄影测量,无LiDAR) | DiffMVS 稠密深度反投影累积(同源稠密层) |
| 红→绿 = camera coverage of tie point | 每体素按「被多少关键帧、多大角度多样性看到」着色，阈值自定 |
| Render mode: Color ↔ Quality | 同做两模式切换 |
| 已拍位姿标记 | 相机轨迹 + 关键帧缩略图 quad |
| in-capture bounding box(1.8) | 世界锁定 box gizmo，框内高亮，框=最终范围 |
| 宽松运动自动快门、不拒帧、300上限 | 回放期按运动/视差选关键帧；门槛后置 |
| 过曝不提示 | (后续)加 OVEREXP~245 实时过曝提示 = 边际优势 |

## 四、里程碑
- **M0**：回放管线打通 —— 读 manifest，喂 414 帧 pose/RGB，3D 视图渲染相机轨迹+当前帧朝向(无 ARKit)。
- **M1**：DiffMVS 每关键帧深度 → 反投影 → 体素下采样累积 → 渲染**真彩稠密点云**(=稠密预览)。
- **M2**：覆盖度着色(红→绿) + Render mode 切换 + 位姿标记。
- **M3**：in-capture bounding box + 框选交互 + 框内高亮(所见即所得闭环)。
- **M4**：FrameSource 换 ARKit，真机实时(用户连机实测)。
- 后续：跨端接口、Object Mode 抠背景、过曝提示、热/功耗优化。

## 五、风险/已知坑（规避）
- ANE 陷阱 → CoreML `.cpuAndGPU`；grid_sample/3D conv 走 GPU。
- 源视图 baseline≥6cm（否则近物零视差出垃圾）。
- 拍摄重负载(实测 4min 掉 6% 电) → 关键帧抽稀 + 深度降分辨率 + 盯热。
- 内存随点云增长 → 体素哈希+LOD+流式从 M1 就上。

## 六、已决架构点
覆盖着色**统一叠在 DiffMVS 稠密几何上**（一份几何），不拆两份 → 省内存 + 保证 preview≈final。
