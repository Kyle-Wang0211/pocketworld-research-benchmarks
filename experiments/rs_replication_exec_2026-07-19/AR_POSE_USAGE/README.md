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


---

# RealityScan Mobile AR 模式深查附录(四路信源合并终审)

- **调查日期**:2026-07-18;**对象**:RealityScan **Mobile**(iOS/Android 手机 app),最新版 1.8.1
- **信源纪律**:仅采信 `dev.epicgames.com/documentation/*/realityscan-mobile/*`、realityscan.com/mobile、官方商店页、Epic staff 论坛回复及明确标注的第三方 mobile 评测;桌面 RealityCapture 文档一律未采信(仅一处 staff 回复标注了桌面语境用作反面参照)。
- **证据分级**:E1=mobile 官方文档逐字 / E2=官方 release notes、商店页、Epic staff 论坛回复 / E3=第三方 mobile 评测、用户观察 / INF=明确标注的推断 / UNRESOLVED=查无来源。

---

## Q1 — AR Guidance 的 "real time point cloud" 到底在哪算?

### 汇合证据(四路信源全部收敛,无内部冲突)

**E1 · 点云不是即时的:20 张门槛 + 上传先行**
> "Images will start uploading the moment you begin capturing them, and they will be analyzed after you take 20 images."
> "The processes of uploading and analyzing are interleaved, with uploading occurring first, followed by initial analysis, then uploading again, and so on."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-step-by-step-guide

**E1 · "分析"的官方定义就是 SfM 语义(算位姿+检测共同特征→产点云),不是 ARKit 特征点语义**
> "Analyzing images calculates camera positions and detects common features from which the point cloud will be created."
> 同上 URL

**E1 · 点云在"初次分析之后"才出现,且是覆盖质量渲染(quality render),不是 RGB 点云**
> "The point cloud shows up in the camera view after the initial analysis in the quality render mode, helping you to notice parts where the image coverage could be improved."
> 同上 URL

**E1 · 点云可见性以"图像已被分析"为前置条件;AR 仅是显示通道(Camera Control 模式点云无法以 AR 显示,但点云本身仍存在)**
> "Toggle the point cloud visibility in the camera view if images have been analyzed."
> "In Camera Control mode, the point cloud cannot be displayed in the AR view, but it offers more control over the camera settings."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-camera-view

**E1 · "分析"受联网门控——不联网不分析**
> "You can change the data usage and opt to analyze your images and process your projects only when you are connected to the selected internet connection."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-application-settings

**E2 · 最硬的构造性证据:1.3 版把"实时点云"与"边拍边上传"绑成同一个 Live Guidance 开关——不上传即无实时点云**
> "Turn off Live Guidance in the Settings to avoid uploading photos as you scan, and to disable live guidance features like real-time point clouds and preview models. This replaces the previous Offline Mode option."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-1-3-version

**E2 · 离线路径真实存在(1.2 离线拍摄回网再传),结合上条推得离线时无实时点云**
> "Save time, data, and battery life by capturing images while offline and uploading them later when you're back online."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-1-2-version

**E3 · 第三方评测同口径**
> "While you can use RealityScan in offline mode, you will lose its AR features and be unable to export the final 3D object."
> https://www.makeuseof.com/how-to-use-realityscan-create-3d-models/

### 唯一反向证据(冲突并列,不隐瞒)

**E3 · Falkingham(2023-11,Android,pre-1.8 年代)称稀疏点云"在设备上算"——孤证**
> "When you've got a bunch of photos, it will create a sparse 3D point cloud. Note that it does this on device, it's still uploading the full resolution images at this point."
> 但同文亦确认:"It works purely through photogrammetry, and does most of the processing in the cloud. … That it's cloud-based isn't ideal (data charges, limited availability if no signal)."
> 以及:"As you take photos of the object, it shows previous photos in Augmented Reality around the object, showing that it's aligning cameras as it goes."
> https://peterfalkingham.com/2023/11/24/realityscan-photogrammetry-on-android/

**冲突评估**:Falkingham 的"on device"是博主推断,依据仅为"全分辨率图还在上传时点云已出现"——这与官方"上传先行、分析后随"可用"低分辨率版本先行上传分析"调和;且与其自己"most of the processing in the cloud"并存。E3 孤证不足以对抗 E1×3 + E2 构造性绑定的证据链。

### Q1 裁决(INF,高置信)
"real time point cloud" = **云端增量 SfM(20 张起步、批式交错)回传的覆盖质量稀疏云**,由端上 ARKit/ARCore 位姿做**显示层锚定**叠加到实景;商店页 "Evaluate your scan's quality instantly" 的 "instantly" 指"拍摄期间即可见反馈"的体验话术,不指端上即时计算。AR 在此模式的职责是**渲染通道 + auto-capture 触发**("Enable or disable the auto-capture. Available only with the AR Guidance."),不是点云的计算来源。

---

## Q2 — AR 位姿有没有进入算法链(尺度之外)?

**E2 · 官方绑定 AR 模式的唯一输出属性 = 正确尺度,机制未披露**
> "In the augmented reality mode, your models appear at the right scale and accurately reflect the real object."
> https://www.realityscan.com/mobile

**E3(由 E2 降级)· 早期 FAQ 帖明说用 AR 位置算 scale——但作者账号已匿名化(Anonymous_60b8d98be8),staff 身份无法确证**
> "Yes, it is scaled. The app uses the AR positions of the cams to calculate the scale."
> https://forums.unrealengine.com/t/faq-about-realityscan-application/712415

**E2 · staff 口径:用户可拿到的只有图像,位姿不提供**
> OndrejTrhan(2025-01):"Hi, it is not stored there, only the images."
> https://forums.unrealengine.com/t/possibility-to-export-reality-scan-images-with-camera-pose-to-reality-capture/2115522
> kumateCR 谈上传亦只提 images:"If your images were uploaded, then you will be able to see them as a 'project' in the list of projects…"
> https://forums.unrealengine.com/t/can-i-save-photos-and-export-out-of-realityscan-app/721368

**E3 · 🔥本轮唯一实质新证据:论坛用户逐字节检查过官方 iOS mobile app 的采集产物,每图带 XMP,记录相对旋转 + 局部空间坐标(即 AR 轨迹位姿)**
> "I compared it with the XMP data collected by the official iOS RealityScan mobile app. The official app records relative rotation and local spatial coordinates, and the resulting model poses are all fine."
> https://forums.unrealengine.com/t/problem-with-model-rotation-in-realityscan-when-using-absolute-rotation-data-arkit-instead-of-relative-rotation/2675121

**E2 · 同帖 staff 回复涉及重力先验——但语境是桌面 CLI 命令,不能移植为 mobile 云端管线声明**
> OndrejTrhan:"If your images contains gravity information you can use the command setCamerasGravityDirection to apply it for the alignment."
> 同上 URL

**E1 · 项目数据整体可选上行(ML 训练开关)——旁证项目级数据(含 AR files)有上行通道,但非对齐用途声明**
> "Allow anonymous machine learning use of the data from your projects."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-application-settings

**E2 · 隐私标签粒度不足以裁决**
> App Store:"App Functionality: Location (Coarse Location), User Content (Photos or Videos, Customer Support, Other User Content), Identifiers (User ID, Device ID)" — "Other User Content" 是 AR 位姿唯一可能落的桶,但证明不了内容。
> https://apps.apple.com/us/app/realityscan-mobile/id1584832280

**INF · 云端对齐不依赖 AR 位姿的反向构造证据**:Object Mode 官方允许拍摄中途翻转/移动物体(破坏 AR 静态世界假设)仍能对齐;Unguided 模式(不边拍边传、无 AR 引导)拍完仍正常送云处理——对齐主力必为纯图像 SfM,AR 位姿至多可选辅助。
> "you can rotate your object in place and RealityScan Mobile will isolate it with precision, and you can flip the object mid-scan to capture difficult angles"
> https://www.realityscan.com/news/realityscan-mobile-new-release-exciting-new-features

### Q2 裁决
"AR 位姿是否随图上传、是否被云端对齐用作初始化/先验/校验"——**核心问题维持 UNRESOLVED**,但边界收紧了:XMP 观察(E3)证明 AR 位姿数据**以 per-image XMP camera-prior 形态存在于采集产物**,与 staff "only the images" 存在张力(可能是文档年代差,或 staff 特指"无用户可复用格式")。位姿数据"存在且形态适配 RC 生态的 alignment prior"是新事实;"被云端消费"仍无任何一手声明,正反都没有。

---

## Q3 — "The AR files" 是什么?

**E1 · 官方 Project Files 文档逐字列出,独立条目、零解释**
> "The images in HEIF format (or JPG on Android) … A project file in the JSON format … The cropping box files … The point cloud and camera files … The AR files … A subfolder with the model and texture files"
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/RealityScan-Project-Files

**E3 · 用户翻过文件夹,但无人晒出 AR files 内容物**
> iOS 路径 "Files -> On My iPhone -> RealityScan -> Captures";Android "Android\data\com.epicgames.realityscan\files\projects\"(https://forums.unrealengine.com/t/can-i-save-photos-and-export-out-of-realityscan-app/721368)
> Android 用户提及 project.json/xmp/EXIF 存在:"It isnt clear why gps data is sometimes in the files and sometimes not."(https://forums.unrealengine.com/t/gps-exif-realityscan-mobile-android/2654212)
> 最接近的一手记录 = Q2 的 XMP 检查帖(相对旋转+局部空间坐标),但那是随图 XMP,未必等于 "The AR files" 本体。

### Q3 裁决
**UNRESOLVED**(ARWorldMap?位姿 json?格式全无记录)。注意三方张力:文档列出 point cloud/camera/AR files ↔ staff "only the images" ↔ 用户实见 xmp。**最快钉死路径:用户自己 iPhone 上 Files.app 实翻 Captures 目录,30 秒可做。**

---

## Q4 — AR 模式 vs Standard/Object 的质量差异?

**E2 · 官方自认 1.8 之前 Android AR 模式输入端有系统性质量缺陷(已修)**
> "Poor image quality & large HEIF file size for scans made in AR mode"
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-mobile-1-8

**E1 · 结构性取舍成文:各牺牲一头**
> Camera Control:"full manual control over your camera settings, allowing you to adjust focus, shutter speed, ISO values, white balance and flash … Camera Control Mode does not include the real-time point cloud or camera position overlay"
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-mobile-1-6-release-notes
> "The point cloud cannot be displayed in the AR view, but it offers more control over the camera settings. Auto-capture is also not available."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/RealityScan-Camera-View

### Q4 裁决
模式差异**仅在采集侧成文**(AR 模式无手动相机控制 + 历史画质 bug;Camera Control 无点云引导/auto-capture)。**成品质量/对齐成功率/尺度表现的用户实测对比:四路全渠道查无,UNRESOLVED**(1.8 发布仅 8 个月,社区对比未出现;媒体文章全是官方稿转述)。

---

## Q5 — 版本时间线与最新官方口径

**E2 · 截至 2026-07,mobile 最新版 = 1.8.1(2025-12-02),纯 bugfix,无 1.9/2.0;桌面 2.x 是另一产品线勿混淆**
> "RealityScan 1.8.1 is now available. Bugs fixed: - Issue with ISO in object/standard mode - Black camera view on clean install"
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-release-notes
> Google Play 最近更新仅修上传:"Updated on Jun 17, 2026 … Fix for Sketchfab upload issue."
> https://play.google.com/store/apps/details?id=com.epicgames.realityscan&hl=en_US

**E2 · AR Guidance 最新官方定义(1.8,2025-11-19,Epic 员工 Piotr Ignatowicz 发布)——措辞只谈 display,未提 AR 参与重建**
> "AR Guidance– Uses Augmented Reality to display a live quality point cloud over your subject, along with real-time visualization of your captured photo positions, allowing you to check where more pictures are needed as you scan."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-mobile-1-8
> 1.6 称 AR 模式为原生模式:"This is the original mode of RealityScan. It provides a real-time point cloud and displays camera positions to guide you during the scanning process."(realityscan-mobile-1-6-release-notes)
> 1.8.1 修复项确认离线路径存在:"Tutorial video crashes the app in offline mode"(realityscan-mobile-1-8-1)

**E1 · AR 能力是全 app 准入门槛(不只是 AR 模式)**
> "RealityScan is compatible with iOS devices, which can run version 16 and higher, and Android devices, which support ARCore and can run version 7 (API level 24) and higher."
> https://dev.epicgames.com/documentation/en-us/realityscan-mobile/RealityScan-System-Requirements-and-Installation

---

## 既有结论逐条裁决

| 既有结论 | 裁决 | 判据 |
|---|---|---|
| **RS 云端对齐主力 = 纯图像 SfM** | **维持并加强** | E1 官方把 analyze 定义为"calculates camera positions and detects common features"(纯 SfM 语义);Object Mode 翻转物体破坏 AR 静态世界假设仍对齐(E2+INF);Unguided 模式无 AR 引导仍可正常处理。加强项:分析联网门控(E1)+ Live Guidance=上传开关(E2)把计算位置也钉向云端。 |
| **AR 位姿唯一明说算法用途 = real-scale** | **维持(证据降级)** | 官方页 "right scale"(E2)仍成立;但 "AR positions … calculate the scale" 原帖作者匿名化,该句从 E2 降为 E3。本轮未发现任何第二个明说用途。 |
| **上传主语只有 images** | **维持官方口径,但加注张力** | staff 两处口径一致(E2);但 XMP 检查帖(E3)证明官方 app 每图伴随相对旋转+局部坐标的 XMP——"只传 images"不再等价于"只传像素",位姿数据存在事实上的随图上行通道。此张力必须记录,不可再当无保留结论引用。 |

---

## 特别裁决

### 一、AR Guidance "real time point cloud" 的计算位置,现有证据最多支持到哪一级?

**最多支持到:高置信 INF(由 E1×4 + E2×2 构造性证据链闭合),不是 E1/E2 逐字事实。**

- 官方**从未逐字写过**"the point cloud is computed on our servers"——所以不能标 E1。
- 但证据链是构造性的:①点云由 analyze 产出(E1);②analyze 受联网门控(E1);③20 张门槛+上传先行交错(E1);④关掉上传 = 失去实时点云(E2,1.3 Live Guidance 开关,最硬一条)。四条合围,点云计算依赖上传管线在文档层面无出口。
- 唯一反证是 Falkingham 2023 的 E3 孤证("on device"),且与其自述"most of the processing in the cloud"并存、属 pre-1.8 年代、依据可被"低清先传"调和——**不足以翻案**。
- **要升格为事实只剩一条路:飞行模式真机实测**(AR Guidance 下断网,看点云是否完全不出现)。全网无此实测记录。

### 二、"AR 位姿进云端对齐"有没有任何新的一手证据?

**没有官方一手声明——正反都没有,核心问题维持 UNRESOLVED。** 但本轮有一条实质性新一手观察改变了证据地形:

- **新证据(E3)**:论坛用户实检官方 iOS app 产物,确认每图带 XMP(相对旋转+局部空间坐标)——AR 位姿数据以 RC 生态标准的 camera-prior 形态**存在**于采集产物。这推翻了"AR 位姿只存在于内存/仅用于渲染"的最弱解读。
- 但"存在"≠"上传"≠"被对齐消费":staff 的 gravity/alignment 回复是**桌面 CLI 语境**,不可移植;mobile 云端管线是否读这些 XMP 当先验,查无任何拆包/抓包/官方声明(信源 4 专项排查落空:无 MITM 记录,appbrain 403)。
- 结论:用户"我们低估了 AR 模式"的质疑**部分成立但不在对齐环节**——被低估的是 (a) AR 位姿以 XMP 形态随图存在的事实,(b) AR 追踪对显示层锚定与 auto-capture 的深度绑定;"AR 位姿进云端对齐当先验"依然一条一手证据都没有,INF 上限是"很可能至少用于尺度标定"。

## 残留 UNRESOLVED 清单(后续钉死路径)

1. **Q1**:飞行模式下 AR Guidance 实机行为(能否进入/点云是否出现)——需真机实测,全网无记录。
2. **Q2**:XMP 位姿是否随 HEIF 上传、云端是否消费——需抓包或 Epic 一手声明;隐私标签与 Play 数据安全页粒度不足("and 3 others" 未能展开)。
3. **Q3**:"The AR files" 内容物(ARWorldMap?位姿 json?)——用户自己 iPhone Files.app 实翻 30 秒可钉死。
4. **Q4**:三模式成品质量/对齐成功率/尺度实测对比——社区内容尚未出现,建议自测。
5. 信道缺口:Reddit 检索被 403 全挡(代理亦拦);1.4/1.5.x release notes 未逐页抓取(索引显示无 AR 相关变更,优先级低);带 revision_hash_id 的旧版文档链接 403,已用现行版锚定。
