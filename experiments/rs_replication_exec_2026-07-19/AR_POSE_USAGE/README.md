# RS Mobile AR 位姿用途专查(仅 mobile 域,桌面 RealityCapture 文档一律未引未外推)

日期:2026-07-18。方法:dev.epicgames.com 直连 TLS 被掐,经 r.jina.ai 代理取一手 mobile 文档;补 realityscan.com/mobile、App Store、官方 mobile release notes(forums.unrealengine.com 官方贴)、独立评测。搜索中多次撞见 rshelp.capturingreality.com(桌面帮助),**全部弃用未引**。

## 证据分级

- **E1** = mobile 官方文档逐字(dev.epicgames.com/documentation/realityscan-mobile/* 或 realityscan.com/mobile)
- **E2** = mobile 官方 release notes / 官方商店页(forums.unrealengine.com 官方贴、App Store)
- **E3** = 第三方 mobile 评测 / 用户观察(行为级)
- **INF** = 由 E 级证据出发的推断,明确标注,不当事实
- **UNRESOLVED** = mobile 域内无来源,不硬凑

---

## ① AR 数据流(存什么 / 传什么 / Process 输入)

**本地存储(E1,Project Files 文档逐字枚举)**:每个 session 文件夹含:
> "The images in HEIF format (or JPG on Android), The corresponding thumbnail images, A project file in the JSON format, The cropping box files, **The point cloud and camera files**, **The AR files**, A subfolder with the model and texture files"

- "The AR files" 与 "the point cloud and camera files" **只列名,内容零描述**(E1)。
- **上传主语只有 images**(E1,Step-by-Step):"Images will start uploading the moment you begin capturing them, and they will be analyzed after you take 20 images." 全部 mobile 文档中没有任何一句说 AR 文件/位姿文件被上传或进入云端 Process 输入清单。
- **分析的措辞是"算出"而非"读取"位姿**(E1,Step-by-Step):"Analyzing images **calculates camera positions** and detects common features from which the point cloud will be created." —— 位姿被描述为云端从图像计算的产物。
- **关 Live Guidance(1.3 "Unguided mode",E1/E2)**:"avoid uploading photos as you scan" + 关闭 "live guidance features like real-time point clouds and preview models";且 "You can still send your scans for processing as normal when you're finished capturing" —— 行为级:**云端 Process 不依赖拍摄期实时流,事后纯照片包也能照常处理**。
- 没有任何 mobile 文档 / release note 出现"位姿参与对齐 / 初始化 / 加速"的字句(穷举了文档索引:Release Notes / System Requirements / Navigate UI / Step-by-Step / Useful Information + Camera View + Application Settings + Project Files + Review Scan)。

**结论**:AR 文件确凿存在于本地项目(E1);是否上传、是否进 Process 输入 = **UNRESOLVED**。

## ② AR 模式 vs 非 AR 拍摄路径(位姿被用了多少的行为级证据)

RS Mobile 存在**完整的非 AR 拍摄路径**,且逐版本加强:

| 版本 | 事实 | 级 |
|---|---|---|
| 1.3 | "Unguided mode":关 Live Guidance,不上传不实时,事后照常处理 | E1/E2 |
| 1.6 | 新增 Camera Control Mode:"full manual control over your camera settings";AR mode = "the original mode … provides a real-time point cloud and displays camera positions to guide you" | E2 |
| 设置页 | Scanning Mode 二选一(+Always Ask);CC 模式 "does not include AR guidance or a real-time preview of the point cloud" | E1 |
| 1.6.2 | "You can now see your camera positions when reviewing your scan in Camera Control Mode" —— CC 模式无 AR,review 里的相机位姿只能来自云端分析产物 | E2 |
| 1.7 | "Automatic object masking (**Camera Control Mode only**)":"You can now place your object on a **turntable** or **rotate it in place** for each picture—RealityScan Mobile will still capture it perfectly." | E2 |
| 1.8 | 三模式:AR Guidance("Uses Augmented Reality to display a live quality point cloud over your subject, along with real-time visualization of your captured photo positions")/ Object Mode("allowing you to **flip, rotate, and move your object**")/ Standard Mode | E2 |

**关键行为级证据**:转台 / 翻转 / 移动物体的拍法把"物体相对世界系运动"合法化 —— 与 ARKit/ARCore 世界系位姿**根本不相容**(物体动了,世界系位姿对物体就是错的)。所以在 Object/CC 转台工况下,**对齐只能是纯图像 SfM,AR 位姿不用(不能用)**。这是"位姿被用了多少"的上界压制:RS 云端对齐主力不依赖 AR 位姿。

- **相册导入路径**:mobile 文档与评测均只描述 in-app 拍摄,无导入(负证据,弱)。= 不存在(低置信)。
- **两路径对齐成功率 / 尺度对比的用户实测**:未找到任何直接对比帖 = **UNRESOLVED**。

## ③ real-scale 机制

- 唯一明说(E1,realityscan.com/mobile):"**In the augmented reality mode**, your models appear at the right scale and accurately reflect the real object." —— real-scale 是**唯一被明说的位姿(AR)用途**,且措辞把它限定在 AR 模式。
- 其他明说的 AR 用途只有**引导/可视化**:实时点云覆盖 + 拍照位姿显示(1.8 "real-time visualization of your captured photo positions",E2)+ 自动快门(仅 AR Guidance 模式有 auto-capture,Camera View 文档 E1:CC 模式 "auto-capture is also not available";注:1.7.1 后 CC 模式也补了 Auto Capture,E2)。
- 没有任何 mobile 来源明说位姿用于对齐初始化/约束。
- 非 AR 模式(CC/Object/Standard)出的模型尺度是否任意 = **UNRESOLVED**(无来源)。

**INF(标注推断)**:要把云端算出的点云和 photo positions 叠回 AR 实景(①③的显示行为),必须存在 SfM 坐标系→AR 世界系的配准环节;real-scale 声明与此自洽 —— **AR 位姿至少被用作显示层配准 + 输出 gauge(尺度/摆正)**。这解释了为什么 real-scale 只在 AR 模式被承诺。属于强自洽推断,非文档字句。

## ④ 拍摄期"分析交织"(20 张后)用不用位姿

- E1 只说:上传与分析交织,分析 "calculates camera positions and detects common features"。
- **没有任何 mobile 来源暗示 AR 位姿加速/引导该初步分析** = **UNRESOLVED**。
- E3(Fabbaloo mobile 上手评测):"shows previous photos in Augmented Reality around the object, showing that it's aligning cameras as it goes" —— 显示层观察,证明"边拍边对齐"的产品表现,不能证明对齐内部用了 AR 位姿。
- 旁证(E1/E2,①):Unguided/CC 路径分析照常 → 交织分析**不需要** AR 位姿才能工作。

---

## mobile 可证的 AR 位姿用途清单(按证据级)

1. **拍摄引导可视化**:实时点云叠加实景 + 已拍照片位置的 AR 显示(E1/E2,1.6/1.8 逐字)。
2. **自动快门**(AR Guidance 模式原生;E1)。
3. **real-scale 输出**:模型"右尺度"承诺绑定 AR 模式(E1,唯一明说的算法级用途)。
4. **本地落盘 "AR files"**(E1,内容不明)。
5. (INF)显示层 SfM↔AR 世界系配准 + 输出 gauge。

## UNRESOLVED 清单

- U1:"The AR files" 具体内容(位姿?锚点?ARWorldMap?)。
- U2:AR/位姿文件是否随项目上传、是否在云端 Process 输入清单里。
- U3:云端对齐是否用 AR 位姿做初始化/先验/校验(仅能证明"没有它也照常工作")。
- U4:非 AR 模式产出模型的尺度表现(任意 gauge?)。
- U5:AR vs 非 AR 两路径对齐成功率/速度的量化用户实测。
- U6:20 张后交织分析是否被 AR 位姿加速。
- U7:Unguided/关 Live Guidance 时 AR session 是否仍在跑、AR files 是否仍落盘。

## Parity 表:RS Mobile 可证用途 × 我们现状

| RS Mobile 可证用途(证据级) | 我们现状 | 判定 |
|---|---|---|
| 实时点云叠加实景引导覆盖(E1/E2,云端分析回传) | live 流式 SfM 稀疏云 + RS 式覆盖云(0 照片=0 点),全端上无云端 | **已做到,做法不同**(我们端上实时逐帧;RS 20 张后云端交织批式) |
| 已拍照片位置 AR 显示(E2,1.8) | 覆盖云主打覆盖热图;拍照位姿标记是否在 AR 视图显示待核 | **部分/待核** |
| 自动快门(E1,AR 模式) | 有快门背压闸;自动快门待核 | **部分/待核** |
| real-scale 直出(E1,绑定 AR 模式) | ARKit 位姿先验 + BA 精化(生产口径),同 gauge 直出禁 Sim3,重力对齐配方 | **已做到且更强**(RS 疑似仅显示层/输出 gauge;我们位姿进优化) |
| 位姿参与云端对齐(UNRESOLVED;行为证据=不依赖) | 明确用 ARKit 先验进增量 SfM+BA | **做法不同**:我们比 RS 可证程度更依赖位姿 —— 合法,但注意 RS 的对齐鲁棒性不靠 AR,纯图像 SfM 是主力 |
| 非 AR 拍摄路径(E1/E2,三模式+Unguided) | 无,采集绑定 ARKit | **没做到**(非复刻必需;其存在主要是 RS 管线位姿无关性的证明) |
| 分析交织式渐进反馈(E1) | 端上实时逐帧,粒度更细 | **已做到(超出)** |

### 复刻要点

1. RS 的行为证据把 AR 位姿的角色压到"引导可视化 + 输出 gauge/real-scale"这一层;**对齐主力是纯图像 SfM**。我们把 ARKit 先验放进 SfM/BA 属于超出 RS 可证做法的设计,不违背复刻方向,但意味着我们对位姿质量的依赖高于 RS —— 位姿噪声工况(热、快移)要有 RS 式的"纯图像也能对齐"底线意识。
2. real-scale 承诺绑定 AR 模式这一点与我们"同 gauge 直出禁 Sim3"一致,可作为对外行为对标锚。
3. RS 每个可视化点/位姿都来自真实分析产物(与 07-19 记忆"RS 预览每点=真实匹配+BA"一致),本查未发现任何"无中生有的 AR 投影点"证据。

## 用户实机一手证据(2026-07-18 追加,E3-U 级=本项目用户长期实测)

- **实机截图(iOS,2026-07 现行版)**:三模式选择页确认 1.8 结构;AR Guidance 文案逐字:"Evaluate your scan's quality instantly with a real time point cloud on top of your subject using augmented reality."
- **用户实测行为**:"AR 是需要联网的,需要上传照片的" —— AR Guidance 模式**依赖网络、边拍边上传**。
- **裁决 U6/Q1(实时点云在哪算)**:与 1.3 Unguided 文档("avoid uploading photos as you scan" 时同时失去 "real-time point clouds and preview models")互为印证 —— **AR 模式的实时点云=云端增量 SfM 对已上传照片的分析结果回传,叠加显示在 AR 实景上;不是端上算的**。AR 位姿在此的角色=显示层配准(把云端点云/相机位摆回实景),与 ③ 的 INF 推断一致,现升为行为级证实。
- **战略含义**:RS 的"零鬼层预览"是**云端算力**(全图集配对/长 track/全局 BA)买来的,其"real time"本质是云回传;我们全端上、断网可用、逐帧粒度反而是架构性超出。复刻对象是它的**机制**(全局匹配→长 track→BA→重投影裁剪),不是它的云拓扑。

## 来源(全列)

一手 mobile 官方(E1/E2):
- https://dev.epicgames.com/documentation/realityscan-mobile/RealityScan-Project-Files(经 r.jina.ai)
- https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-step-by-step-guide(经 r.jina.ai)
- https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-camera-view(经 r.jina.ai)
- https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-application-settings(经 r.jina.ai)
- https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-1-3-version(经 r.jina.ai)
- https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-1-5-version(经 r.jina.ai)
- https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-mobile-1-7-release-notes(经 r.jina.ai)
- https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-documentation(文档索引,经 r.jina.ai)
- https://forums.unrealengine.com/t/realityscan-1-6-release-notes/2307066(官方贴)
- https://forums.unrealengine.com/t/realityscan-1-6-2-release-notes/2357031(官方贴)
- https://forums.unrealengine.com/t/realityscan-mobile-1-8-release-notes/2676487(官方贴)
- https://www.realityscan.com/mobile
- https://www.realityscan.com/en-US/news/realityscan-mobile-new-release-exciting-new-features(1.7 news)
- https://apps.apple.com/us/app/realityscan-mobile/id1584832280

第三方 mobile 评测(E3):
- https://peterfalkingham.com/2023/11/24/realityscan-photogrammetry-on-android/
- https://www.fabbaloo.com/news/hands-on-with-realityscan-part-2(经搜索摘要引用)

明确弃用(桌面域,用户令):rshelp.capturingreality.com 全部页面、realityscan.com 桌面 2.x news、dev.epicgames.com/documentation/realityscan(无 -mobile 后缀)。
