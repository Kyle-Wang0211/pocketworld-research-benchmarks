# RealityScan 拍摄期(Capture Phase)深度调研笔记

> 目的：为 PocketWorld 复刻一套手机端 RGB 3D 扫描的「拍摄期 AR 引导 UI」，标杆是 Epic Games 的 **RealityScan Mobile**（前身 RealityCapture mobile；桌面版 RealityCapture）。
> 调研方法：deep-research workflow（5 路检索 → 17 个一手源 → 74 条断言 → 25 条 3 票对抗式核验 → 23 confirmed / 2 killed，99 个子代理）+ 定向补抓官方一手源逐字确认。
> 日期：2026-06-17。
> 置信度标注：**【官方确认】**=Epic/RealityScan 官方文档原文；**【社区/独立观察】**=第三方实测/评测；**【闭源推断】**=逻辑推断，官方未明说。

---

## 0. TL;DR —— 最重要、且修正我们旧认知的发现

**RealityScan Mobile ≠ RealityScan Desktop。它们的几何架构完全不同：**

⚠️ **2026-06-17 真实用户实拍修正（推翻了我网络调研的一个结论）：** 官方文档把"预览点云"说成稀疏 SfM，但真机截图证明拍摄期是**两套不同的几何**：

- **RealityScan Mobile 拍摄期是「三层几何」（全部不用 LiDAR，纯 RGB+VIO 摄影测量）：**
  1. **拍摄进行时 = 端上实时「稠密彩色点云」覆盖在真实表面上**，红→黄→绿按覆盖质量着色。这是用户拍摄时真正盯着的反馈层（既是覆盖引导，也给粗略形状感）。【真实用户实拍确认】
  2. **拍完 ~1s = 一团较稀疏的「Color Point Cloud」**（Review Scan 页），用户在它上面拖 box 框定后续重建/训练范围。【真实用户实拍确认】
  3. **最终稠密重建 = 全在云端**（alignment/MVS/mesh/texture，RealityCapture 谱系引擎），全分辨率原图上传后云端算、下载回模型。【官方新闻稿 + 独立实测】
- **关键：第 1 层的稠密点云不需要 LiDAR** —— 官方「no special hardware, scan with just your phone」，Android 端「photogrammetry only」（Android 普遍无深度 API）。所以它是**纯 RGB+VIO 摄影测量在端上实时densify 出来的**（机制官方未公开；很可能是累积多帧 AR 特征点 + 每点观测计数着色，或一层轻量 densify）。
- **RealityScan Desktop = 全本地 SfM → MVS 稠密 → 图割网格**（这才是我们记忆 `realityscan-pipeline-architectural-tax.md` 描述的那条管线）。

**对我们的直接含义（展开见 §9）：**
1. 我们记忆里「RealityScan 1 秒出粗点云 + 框选」其实混淆了桌面版。**手机标杆 RealityScan Mobile 的拍摄期预览是稀疏的、preview ≠ final**（最终靠云端补）。
2. PocketWorld 硬约束是 **全本地无服务器** → 我们**抄不了它的「云端做最终重建」这条退路**。
3. 但这恰恰说明：**我们用端上稠密 DiffMVS 当预览（preview≈final），是 RealityScan Mobile 自己都没做到的事** —— 这是真实的产品优势，不只是模仿。
4. 真正值得逐字抄的是它的**覆盖反馈模型**：红→绿着色的信号 = **「每个点被多少相机覆盖」(camera coverage of each tie point)**，官方原文坐实（§2）。这个信号很便宜，且与底层几何是稀疏还是稠密无关，可以直接搬到我们自己的几何上。

---

## 1. 三种拍摄模式（v1.8，2025-11） 【官方确认】

⚠️ 修正：不是用户之前猜的 object / room / scene。RealityScan Mobile 1.8 的「New shooting modes」官方定义是按**引导方式 + 是否抠背景**划分：

| 模式 | 官方定义（原文） | 适合场景 | AR 数据使用 |
|---|---|---|---|
| **AR Guidance** | "Uses Augmented Reality to display a live quality point cloud over your subject, along with real-time visualization of your captured photo positions." | 通用引导流（小白默认） | 用 AR：实时点云叠加 + 拍摄位姿可视化 + 自动快门 |
| **Object Mode** | "advanced camera controls with automatic background removal, allowing you to flip, rotate, and move your object." | 可手持/可翻转的小物体（转盘式：转物体而非绕物体） | 手动相机控制 + 自动抠背景；**无 AR 点云、无自动快门** |
| **Standard Mode** | "the same advanced camera controls as Object Mode, but without background removal." | 物体留在原环境/场景 | 手动相机控制；无抠背景 |

底层文档其实把它归为两个引擎：**AR Guidance**（点云 + 缩略图 + 自动快门）vs **Camera Control**（手动 Focus/Exposure/WB/Flash，**无点云、无自动快门**）。所以"三模式"部分是 onboarding/营销层的拆分。
- 来源：Epic 1.8 release notes（forums.unrealengine.com/t/realityscan-mobile-1-8-release-notes/2676487）、digitalproduction.com 1.8 实测、camera-view 官方文档、Epic 官推。
- **抄点**：Object Mode 的「自动抠背景 + 翻转物体」对小物体扫描很有用（转盘式）；AR Guidance 是我们要复刻的主线。

---

## 2. 红→绿覆盖反馈：信号到底是什么 【官方确认 —— 最关键】

**着色信号 = 每个 tie point 被多少相机覆盖（camera coverage）。** 逐字原文（RealityCapture/RealityScan Quality Analysis 工具文档 rshelp.capturingreality.com/en-US/tools/qualityanalysis.htm）：

> **Tie points**: "Calculates the quality of tie points in the sparse point cloud. It primarily evaluates the **camera coverage of each tie point** and displays quality values in the 3Ds view using a **color scale from green (good quality) to red (poor quality)**."
>
> **Mesh**: "Calculates the quality of the mesh by evaluating **camera coverage for each triangle**... color scale from green (good quality) to red (poor quality)."

拍摄期 App 的措辞（realityscan.com/mobile）：
> "real-time point cloud showing on top of your subject, showing where you need to have more coverage and areas you already covered well."

Review-Scan 文档：
> "Quality is shown using a color scale from red to green, where greener shades mean higher quality (good coverage)" + "Use the **Render mode** button... switch between viewing a point cloud in color or in quality mode."

**钉死的结论：**
- 信号 = **相机覆盖度**（一个点/三角面被足够多相机、足够好的角度看到 = 绿；覆盖不足 = 红）。**不是**分辨率，**不是**帧间重叠度，**不是**几何完整度为主。
- 载体 = **逐点着色的点云（per-point）**，**不是体素网格，不是屏幕空间 mesh**。
- 拍摄时点云直接以 **quality render mode** 显示（即实时就是红→绿那套），可用 Render mode 切到 color（真实色）。
- 另有**离散的「拍摄位姿标记」(photo position markers / thumbnails)**，可视化「你已经从哪些位置拍过」「哪里还缺」。
- 官方**未公布**具体颜色阈值/最少相机数（qualitative，非 numeric）。【官方未公布 → 阈值需我们自定】

---

## 3. 拍摄期实时预览几何 【真实用户实拍修正 —— 重要】

⚠️ 我原先按官方文档写成"稀疏 SfM 预览"，被真机实拍推翻。实际是**两层不同几何**：

**(3a) 拍摄进行时 = 端上实时「稠密彩色点云」（红→绿质量着色）。**
- 真机实拍：拍摄时屏幕上铺着**成千上万个点**，沿真实表面（地板、柜面、凳子）密铺，按覆盖质量红→黄→绿渐变。这是拍摄时的主反馈层。
- **不用 LiDAR**（官方 no special hardware；Android photogrammetry only）→ 纯 RGB+VIO 摄影测量端上实时生成。
- 机制官方未公开（闭源推断）：最可能是**累积多帧 AR 特征点 + 每点"被多少相机看到"计数着色**，或一层轻量端上 densify。因为是摄影测量，**有纹理表面密（木地板/柜子），弱纹理表面稀（白墙/床单看到红点稀疏）**。
- 状态条 `Analyzing Images X%` / `Uploading Images X%` 实时跑（上传与分析交替）。官方文档另称拍到 ~20 张后才开始分析、出现点云（但"20 张/纯端上 SfM"精确机制被对抗核验降级为存疑）。

**(3b) 拍完 ~1s = Review Scan 里的较稀疏「Color Point Cloud」。**
- 真机实拍：一团真彩点云漂在黑底，明显比拍摄期稠密层稀疏。这是用户**框选 ROI 用的那层**（见 §4）。
- Render mode 可切「Color（真彩）↔ Quality（红绿质量）」。

**(3c) 三层几何关系：** 拍摄期稠密覆盖层(端上) → review 稀疏框选层(端上) → 最终稠密重建(**云端**，§8)。三者都不是同一份几何。所以即便它拍摄期看着稠密，**用户真正框选的是稀疏层，最终又靠云端补** —— 它整条链的 preview ≠ final。

---

## 3.5 真机 UI 元素清单（来自真实用户截图 2026-06-17）【实拍确认】

**Capture 页（拍摄进行时）：**
- 顶栏：`< Projects` | 标题 **Capture** | `?`(帮助/Quick Start) | `⚙`(设置)
- 主区：稠密彩色点云覆盖真实场景（红→绿质量着色）
- **In-capture bounding box**：白色线框 + 一个半透明绿色面，拍摄期即显示、可调（坐实 1.8 的拍摄期框）
- **已拍位姿标记**：3D 锚定的小相框缩略图（每张拍过的帧）；另有散落的绿色小四边形标记
- 中部工具条：2 个图标 = Render mode 切换（图片/真彩 ↔ 点阵/质量）
- 状态条：`Analyzing Images NN%` 或 `Uploading Images NN%` + 进度条（上传/分析交替、实时）
- 提示语：`Keep taking pictures to capture.`
- 底栏：图片计数 `NN/300`（可点开看图）| 自动快门开关 | 大白快门键 | 蓝色 `→`(下一步/Next step)

**Review Scan 页（拍完 ~1s）：**
- 顶栏：`< Capture` | 标题 **Review Scan** | `⋮`(更多菜单) | `?` | `⚙`
- 主区：较稀疏的真彩点云，标签 **`Color Point Cloud`**
- Render mode 切换：油漆滴图标(真彩) ↔ 徽章图标(质量)
- 底栏：单图 / 图堆 两个图标
- 底部按钮：`Save Draft` | `Next`

**实拍出的额外洞察：**
- **覆盖质量着色的经验证据**：红点集中在①过曝窗户附近、②远处/覆盖不足的床沿与地毯；绿点在覆盖充分的中心区 → 印证「覆盖度 + 过曝差 → 红」。
- **耗电/发热**：4 分钟内电量 13%→7%，拍摄期是重负载（相机 + AR + 端上 densify + 上传同时跑）→ 我们端上还要加 DiffMVS，必须严控热/功耗。

---

## 4. ROI / Bounding box（框选重建区域） 【官方确认 + 实拍】

- **桌面版**：reconstruction region 在 **alignment 之后自动生成**，大小取决于稀疏点云尺寸；用户事后用 box widgets 调整。Clipping Box 是另一个**重建后的显示裁剪工具**，不是 ROI。（reconbox.htm / clipbox.htm）
- **手机版主流程**：**拍完 → review → 在已分析的点云上调 reconstruction region box（拖动 widget + 旋转视角）过滤掉不要的部分 → 处理**。即**后框选**（post-capture on the point cloud），不是拍摄前的 AR 框。
- **手机版 1.8 新增**：拍摄期**就有一个 in-capture bounding box**（第三方实测 digitalproduction/Fabbaloo：「setting the bounding box you can limit the scan to a specific volume」）。【社区/独立观察 —— 官方文档尚未详述其世界锁定机制】
- 「所见即所得」一致性：靠 AR 的世界坐标系把 box 锁在世界里；但**官方没有文档化** 1.8 in-capture box 如何与 AR 坐标系保持 world-locked（开放问题，见 §10）。

---

## 5. 拍摄门槛 / Capture gates 【官方确认】

**哲学 = 宽松引导，不严格拒帧（lenient guided capture, not gated）。** 与我们想走的「少拒帧、强引导」一致。

- **自动快门 = 运动触发**："Start slowly moving your device around the object, and the images will be captured with the detected motion." 默认开，可切手动（仅 AR Guidance 模式有自动快门）。
- **无文档化的逐帧拒绝**（模糊/过曝/重叠不足拒帧）：模糊只靠**用户建议**消化（"avoid hasty movements"）。【"无拒帧"是 absence-of-evidence 推断，官方没说有，也没说没有】
- 缺口靠**事后 review + "Take More Pictures"** 补：回到相机视图继续拍红色/覆盖不足区域。
- 拍摄上限：**300 张**（step-by-step）；另文档提"image limit 300"。
- 拍摄引导启发式："make circles and arches around the object at multiple heights", "at least half of each image to be of the object"。

---

## 6. 曝光 / 过曝处理 【medium：部分 absence-of-evidence】

- **Camera Control（手动）模式**暴露：**Focus / Exposure(快门+ISO) / White balance / Flash**，每项可设 **Auto / Manual / Locked** → 即**支持 AE/AF/WB 锁定**。（camera-view / camera-controls 文档）
- **AR Guidance 模式无这些手动控制**（也无点云外的曝光锁 UI）。
- **没有**文档化的「过曝警告」或玻璃反光/HDR 拍摄期处理；重建期(云端)是否做 RealityCapture 式色彩/曝光均衡，**未对手机版单独确认**（开放问题，见 §10）。
- **我们的优势点**：我们有下游过曝 mask 经验（OVEREXP 阈值 ~245）。RealityScan 拍摄期**不做**过曝警告 → 我们可以加一个实时过曝提示 + AE lock，这是它没有的小边际优势。

---

## 7. AR 数据专项（最重要的工程问题） 【medium —— 这是最大的文档缺口】

**可确认的硬事实：**
- App **硬依赖 ARKit (iOS 16+) / ARCore (Android 7.0+, API 24)** —— 没有 AR 框架就跑不起来 → 拍摄时一定有 AR 框架在跑。
- 用 AR 框架的 **6DoF VIO 位姿**把实时点云**锚定在被摄物上**，并让模型"appear at the right scale and accurately reflect the real object"（realityscan.com/mobile）。
- **【闭源推断】尺度来自 VIO**：纯摄影测量是 scale-ambiguous（桌面版要手动距离/控制点定标，scaling.htm），手机版能自动给正确公制尺度 → 推断尺度由 VIO 提供。（此条对抗核验是 1-1 平票：「AR 模式给出正确尺度」是真的，但「尺度来自 VIO」是有据推断而非 Epic 明说。）
- **存的是全分辨率静态照片**（上传云端重建），端上只留稀疏预览点云。【独立实测】

**官方完全没有枚举的（= 我们逆向不出来，也不必逆向）：**
- 具体调用了哪些 ARKit/ARCore API：`ARFrame.camera.transform`(位姿)、`rawFeaturePoints`/`ARPointCloud`、`ARWorldMap`、`ARMeshAnchor`/scene reconstruction、平面检测、`sceneDepth`/**LiDAR**、内参来源(AR vs EXIF)、曝光/运动元数据 —— **一概未公布**。
- **是否用 LiDAR：已确认不用、也不需要。**【官方 + 独立实测】官方："no special hardware... scan with just your phone"，兼容任意 iOS 16+ 设备；Android 端 "photogrammetry only"（Android 普遍无深度 API/硬件）。→ 连拍摄期那层稠密彩色点云也是**纯 RGB+VIO 摄影测量**端上实时生成，不靠深度传感器。**这与 PocketWorld「坚决不碰深度相机」完全同赛道。**（来源：realityscan.com 主站/features、App Store 列表、engineering.com Android 首测、peterfalkingham Android 实测。）
- **这对我们不是阻塞**：我们自己选 ARKit API 用法（我们比逆向 RealityScan 更懂 ARKit），且我们的位姿来源早已定（端上实时直接用 AR VIO 位姿，~0.6px，见记忆 sfm-cross-platform-pose-recipe）。

---

## 8. 算法与谱系 【官方/论文确认】

**完整管线（桌面 RealityCapture / 云端 RealityScan）= SfM(稀疏) → MVS(稠密深度) → 图割网格化 → 贴图。**

- **MVS 稠密步骤是闭源、自研 GPU**，官方未文档化，社区也没逆向出确切算法（与我们记忆一致）。
- **创始人 Michal Jančošek = CMPMVS 作者**（同一人的稠密 MVS 工作）；CMPMVS 有第三方镜像 github.com/kikislater/CMPMVS（注意核实许可证，多为非商用/学术）。
- **网格化谱系（有论文实锤）**：Jančošek–Pajdla 的 **weakly-supported surfaces** 方法（CVPR 2011 / ISRN 2014）：
  > "Instead of modeling the surface from input points, we model **free space from visibility information** of the input points. The complement... is full space. The surface occurs at interface between the free and the full space."
  > "augmented the existing **Labatut [CGF 2009]** method... just by **changing the t-edge weights** in the construction of surfaces by a minimal s-t cut."
- **Labatut–Pons–Keriven 2009**（被增强的底座）：Delaunay 四面体化 + 全局最优 **min s-t cut** 给四面体打 inside/outside 标签；能量 = 输出表面质量 + 软可见性约束。
- **拍摄期 vs 离线**：拍摄期「即时预览几何」= 端上稀疏 SfM 覆盖点云；离线/云端「全质量重建」= 上面这套 MVS + 图割网格。

---

## 9. 对 PocketWorld 的战略含义（核心决策）

### 9.1 最大的认知修正
我们旧记忆把 RealityScan 当成「全本地 SfM→MVS→网格」并默认手机版也如此。**手机标杆其实是「端上三层几何 + 云端稠密最终」**（见 §0/§3，真机实拍修正）：拍摄期稠密彩色覆盖层(端上) → review 稀疏框选层(端上) → 最终稠密重建(云端)。这意味着：

- **它拍摄期看着稠密，但用户真正框选 ROI 的是那层稀疏 Color Point Cloud，最终又靠云端补全 → 整条链 preview ≠ final。** 它能容忍这点，是因为：(a) 云端最终稠密高质量；(b) 用户可"Take More Pictures"/re-process 补救；(c) 拍摄期稠密层已经给足覆盖信心，框选只需粗略圈范围。
- **我们没有云端这条退路（硬约束：全本地无服务器）。** 所以不能照抄"框选靠稀疏层、最终靠云端"。**但拍摄期稠密层证明了：纯 RGB+VIO 在端上实时出稠密覆盖是可行的、且用户期待它** —— 我们用 DiffMVS 把这层做成"既是覆盖反馈、又是可靠框选底"的同一份稠密几何，比 RealityScan 的"稠密只看不框、框靠稀疏"更进一步。

### 9.2 因此我们的策略（既抄又必须分叉）
| 维度 | RealityScan Mobile 做法 | PocketWorld 该怎么做 | 理由 |
|---|---|---|---|
| **覆盖反馈信号** | 相机覆盖度，红→绿，逐点 | **直接抄**：按「区域被多少相机/多大角度多样性覆盖」着色 | 信号便宜、与几何稠密度无关，可搬到我们自己的结构上 |
| **预览几何** | 拍摄期稠密(摄影测量,看)+ review 稀疏(框)+ 云端稠密(最终) | **统一成一份**：端上**降分辨率/抽关键帧 DiffMVS 稠密**，既当覆盖反馈又当框选底 | 我们没云端；一份稠密几何 preview≈final，框选可靠 —— 比 RS"稠密只看、框靠稀疏、最终靠云"更进一步 |
| **最终重建** | 云端稠密 | **全端上** DiffMVS/CasDiffMVS（已验证 ~0.5-0.7s/帧、~400MB） | 硬约束无服务器 |
| **ROI 框选** | 主要后框选；1.8 加拍摄期 box | **拍摄期 in-capture box on 稠密预览**（所见即所得） | 我们的稠密预览让"框=最终范围"成立 |
| **拍摄门槛** | 宽松、运动自动快门、不拒帧 | **跟随**：少拒帧、运动自动快门、强覆盖引导 | 与用户既定哲学一致 |
| **三模式** | AR Guidance / Object(抠背景) / Standard | AR Guidance 先做；Object Mode(抠背景+转物体)留作小物体增强 | 复刻主线，余量预留 |
| **曝光** | 手动 AE/AF/WB lock，无过曝警告 | 跟随 + **加实时过曝提示**(我们有 OVEREXP 经验) | 小边际优势 |

### 9.3 关键设计抉择（留给方案阶段）
**「覆盖反馈」和「形状预览」是两件可分离的事：**
- (a) **覆盖引导**（红→绿告诉用户"够没够"）—— RealityScan 在稀疏点上做，很便宜。
- (b) **形状预览**（用户看到物体真实形状去取景/框选）—— RealityScan 的稀疏预览很弱，靠云端兜底。
- **我们要同时做好两者**：用 DiffMVS 稠密给 (b)，再决定 (a) 着色是叠在稠密几何上、还是单独维护一个便宜的「体素视角计数」结构。这是第一版要拍板的架构点。

---

## 10. 开放问题 / 无法考证（官方从未公布）
1. RealityScan Mobile 究竟调用哪些 ARKit/ARCore API（`rawFeaturePoints`/`ARWorldMap`/`ARMeshAnchor`/平面/`sceneDepth`/LiDAR）、内参来自 AR 还是 EXIF —— 全未公布。**对我们非阻塞**（我们自定）。
2. 稀疏预览点云到底纯端上 SfM 还是上传后云端辅助；"20 张才分析"是否当前硬阈值 —— 机制/数字存疑（被对抗核验降级）。
3. 云端重建如何处理过曝/玻璃反光/HDR（是否 RealityCapture 式色彩均衡）；拍摄期除手动 AE/AF/WB lock 外是否有过曝警告 —— 未确认（推测无）。
4. 1.8 拍摄期 in-capture bounding box 如何与 AR 坐标系 world-locked、是约束拍摄引导还是只后过滤点云 —— 仅第三方实测提及，官方未详述。

---

## 11. 来源清单（按质量）

**一手（Epic/RealityScan 官方 + 论文）：**
- realityscan.com/mobile ; realityscan.com/en-US/mobile ; realityscan.com/features
- dev.epicgames.com/documentation/realityscan-mobile/ : step-by-step-guide, camera-view, review-scan, camera-controls
- realityscan.com/en-US/news/realityscan-mobile-new-release-exciting-new-features
- forums.unrealengine.com/t/realityscan-mobile-1-8-release-notes/2676487 ; x.com/UnrealEngine/status/1991166153960677406
- rshelp.capturingreality.com/en-US/tools/ : qualityanalysis.htm, reconbox.htm, clipbox.htm
- epicgames.com/site/en-US/news/epic-games-introduces-realityscan-app-now-in-limited-beta
- epicgames.com/site/en-US/news/capturing-reality-is-now-part-of-epic-games
- 论文：Jančošek–Pajdla "Multi-View Reconstruction Preserving Weakly-Supported Surfaces"(CVPR2011/ISRN2014, semanticscholar 8fb10b57…, PMC4897344) ; Labatut–Pons–Keriven CGF 2009 (onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-8659.2009.01530.x)

**二手 / 独立实测：**
- digitalproduction.com/2025/11/21/realityscan-mobile-1-8-with-tools-for-on-the-go-scanning/
- en.wikipedia.org/wiki/RealityCapture ; github.com/kikislater/CMPMVS
- peterfalkingham.com RealityScan review（实测：端上稀疏点云、上传全分辨率原图、云端处理、"waiting for server"）

**官方截图/视频可视化源（供肉眼对照）：** realityscan.com/mobile（hero 视频+点云截图）、digitalproduction 1.8 实测图、Epic 1.8 release notes、Epic 官方 YouTube/社区教程。
