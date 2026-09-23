# 「量真实尺寸允许几个百分点」— 选择菜单

> 调研日期 2026-09-22 · 本文**不做决定**,只把可核的数和它们的口径摆出来
> 产品前提:手机端单目相机 + IMU 的 VIO,跨 iOS / Android / 鸿蒙 / Web,**永不使用 LiDAR**

---

## TL;DR(30 秒版)

1. **菜单在 §6,三个候选:±1% / ±3% / ±5%。梯子在 §5.1。请你自己挑。**
2. **但我建议你先看 §0 的第 ④ 条**:按 ANSI/NCSL Z540-1 的 4:1 规则,**凡是「判定型」用途(下料、验收、定制),±1% 都不够** —— 那些场景要的是 **0.8–2.5 mm 绝对**,不是百分点。「几个百分点」这个问法只适用于**参考型**用途。
3. **好消息**:LiDAR 不是量级碾压。独立测试里 iPhone LiDAR 的尺度修正系数照样跑到 **±4.6%**,Apple 自家 RoomPlan 也有 **5.7%** 的实例。**你们的 4.13% 落在消费级已发表区间内部,不是离群值。这支持「不用 LiDAR」这个决策。**
4. **坏消息**:**没有一家厂商为纯单目发布过百分比尺度规格**(KIRI / RealityScan / Scaniverse 一个数都不给,Magicplan 有专门的精度页但零数字)。你要么成为第一个,要么加入沉默的多数派。
5. **最刺眼的一格**:4 m 房间上,我们最好的 0.2% = 8 mm(≈RICS Band C),最坏的 19% = 760 mm(**掉出 RICS 全部档位**)。**真正该先定的可能不是「允许几个百分点」,而是「允许多大的跨场波动」** —— 一个承诺被违约一次,和它平均表现多好没关系。

---

## 0. 读这份报告前必须先接受的四件事

**① 「百分点」和「毫米」是两个不同的承诺,必须先选一个。**
尺度误差(%)和绝对误差(mm)在不同用途下哪个咬人完全不同。量 3 m 的墙,1% = 30 mm;量 0.6 m 的柜门,1% = 6 mm。下面所有表格都标了口径,**不要跨口径搬运**。

**② 面积和体积会放大误差。** 线性尺度误差 ε,面积误差 ≈ 2ε,体积误差 ≈ 3ε。
> 例:线性 3% ⇒ 面积 ~6%,体积 ~9%。一个 100 m² 的房子报成 106 m²。
> 标签:[推算] — 这是一阶泰勒展开,不是引用。

**④ 🔑 计量学的 4:1 规则会改变这个问题的问法。** **ANSI/NCSL Z540-1** 原文要求 `the collective uncertainty of the measurement standards shall not exceed 25% of the acceptable tolerance` —— 即**尺子的不确定度 ≤ 被判容差的 25%**。所以「我们允许几个百分点」的答案,取决于**用户拿我们的数去判什么**:

| 用户要判的容差 | 按 4:1,我们须 ≤ | 典型尺寸上的百分比 |
|---|---|---|
| 台面 scribe ±0.8–1.6 mm(AWI Custom 1.2 mm) | **0.3 mm** | 2.4 m 台面上 **0.01%** |
| 定制百叶 ±3.2 mm | **0.8 mm** | 0.9 m 窗宽上 **0.09%** |
| 中国分户验收 净开间 ±10 mm | **2.5 mm** | 3.6 m 开间上 **0.07%** |
| 家具搬运净空 25 mm | **6.25 mm** | 0.8 m 门宽上 **0.78%** |
| RICS Band E 净面积/估价 ±50 mm (2σ) | **12.5 mm** | 4 m 上 **0.31%** |

> 全部 **[推算]**(依据是 Z540-1 原文 + 各自的容差原文)。详见 §4.2。
> 🔴 **这张表的含义:凡是「判定型」用途,百分比口径都是错的问法,要的是毫米口径。**

**③ 行业惯例是「不给数」。** 见 §2 的「厂商缺口」一栏 —— KIRI、RealityScan、Scaniverse **完全不发布任何尺寸精度规格**;Magicplan 有一个专门叫「我们的房间扫描有多准」的帮助页,**里面一个数字都没有**。**目前没有任何一家为纯单目(无深度硬件)摄影测量对外发布过百分比尺度规格。** 这既说明你面对的是一个信息真空,也说明对外承诺尺度精度在这个行业里被普遍规避。

**标签图例**
| 标签 | 含义 |
|---|---|
| **[宣称]** | 厂商自己的营销/文档口径,没有独立验证 |
| **[独立]** | 同行评审论文、或有明确方法描述的第三方测试 |
| **[推算]** | **我自己算的**,不是任何来源里的原话 |
| **[未知]** | 数存在但出处/方法不明 |
| **[缺失]** | 我确认了对方**没有**公布这个数 |

---

## 1. 平台层:ARKit / ARCore / RoomPlan 能做到多少

### 1.1 有可比方法的独立测量

| 来源 | 系统 / 设备 | 用了深度硬件? | 测的是什么 | 结果 | 标签 |
|---|---|---|---|---|---|
| Sensors 22(24):9873 | **ARCore** / LG V60 ThinQ | **否**(纯单目 VIO) | 闭环终点漂移 FDE,6 条 84–3051 m 轨迹 | 走廊 **0.12 m / 145 m**、校园 **0.07 m / 514 m**;但楼梯 **3.98 m / 114 m**、道路 **140 m / 3052 m** | [独立] |
| 同上 | 同上 | | **换算成相对误差** | **0.08% / 0.014% / 3.5% / 4.6%** | **[推算]** |
| Sensors 22(24):9873 | **ARKit** / iPhone 12 Pro Max | **是**(该机型带 LiDAR) | 同上 | 0.14–2.68 m;OptiTrack 验证下 RPE ≈ **0.02 m/s** 漂移 | [独立] |
| 同上 | ARKit | | 尺度定性判据 | 楼梯实验中 ARKit 估的层高**与建筑图纸吻合**(论文未给数) | [独立] |
| Sensors 22(14):5382 | **ARKit** / iPhone 11(**无 LiDAR**) | 否 | ATE vs OptiTrack,8 字形路径 | **0.369 ± 0.105 m** | [独立] |
| 同上 | **ARKit** / iPad Pro 11(**有 LiDAR**) | 是 | 同上 | **0.121 ± 0.027 m**(全场最好,且**唯一**跨路径一致的设备) | [独立] |
| 同上 | **ARCore** / 六款安卓 | 否 | 同上 | 0.162(小米 11 Lite)→ **1.451 m**(OPPO Find X3 Lite),**跨机型差 9 倍** | [独立] |
| IEEE OJEMB 5:54-58 (2024) | ARKit 后置 / iPhone 13 Pro | **是(LiDAR)** | 1/2/3 m 处测到门的距离 | MAE **1.37 / 0.48 / 1.40 cm**(画面中心);**画面边缘显著变差** | [独立] |
| Sensors 23(9):4486 | ARKit **前置 TrueDepth** / iPhone X 等 5 机型 | **是(结构光)** | 20–60 cm 面部距离,工业机器人(0.03 mm)定位为真值 | 相对误差 **0.88% – 9.07%**,全区间均值 **5.32%** | [独立] |

> 🔴 **最重要的一条**:Sensors 22(24):9873 里 **ARCore 在纯单目、无任何深度硬件的条件下**,相对误差在走廊上是 **0.08%**,在楼梯上是 **3.5%**,在长距离道路上是 **4.6%**。**同一个系统、同一台手机,好坏差 50 倍,取决于场景。** 这与你们 XRSLAM 观察到的 **0.2%–19% 跨录制跳动是同一类现象**,不是你们独有的缺陷。
> ⚠️ 口径警告:FDE 是**闭环终点位置误差 / 路径长度**,**不等于尺度误差**。我把它写成百分比是为了给量级,标了 [推算];它不能替代直接的尺度标定实验。

### 1.2 厂商自己怎么说

| 厂商 | 说法 | 标签 |
|---|---|---|
| **Apple / Measure app** | **不发布任何精度规格。** 官方用户指南(Measure dimensions / Measure a person's height)全文无精度数字、无容差、无置信区间 | **[缺失]** |
| **Apple / RoomPlan** | 墙和窗检测 **95% precision & recall**,门 **90%**;16 类家具 3D IoU=30% 下 AP/AR = **91% / 90%**;体素分辨率 x/y **3 cm**、z **30 cm**;支持 15 m × 15 m × 3.6 m | [宣称] |
| | 🔴 注意:以上全是**检测率**(有没有认出这面墙),**不是尺寸精度**。Apple **没有**发布 RoomPlan 的尺寸容差 | **[缺失]** |
| | 🔴 且 RoomPlan **必须有 LiDAR**,与本产品无关,仅作天花板参照 | — |
| **Google / ARCore** | 未发布测距精度规格。Google 自述认证流程要标定「camera geometry、IMU behavior、the relative position of the two、**most critically the relative timing**」 | [宣称] |
| **IKEA Place** | 「AR technology … is so precise - with **98% accuracy**」+「all of the products in the app are 3D and **true to scale**」(2017 新闻稿) | [宣称] |
| | 🔴 这个 98% **没有定义口径** —— 不知道是长度、放置成功率还是别的。**不要当尺度指标用** | — |

### 1.3 RoomPlan 的独立反例(LiDAR,仅作参照)

| 来源 | 发现 | 标签 |
|---|---|---|
| it-jim 技术博客 | 演示空间实测长度 **6.45 m**,RoomPlan 报 **6.821 m**,偏差 **37 cm** | [独立-弱](有具体数,但未写设备和方法) |
| 同上 | 换算相对误差 **5.7%** | **[推算]** |
| 同上(原话) | "For professional use, where high precision and detail are required, RoomPlan may prove insufficiently reliable" | [独立-弱] |

> 🔴 **这条很有价值**:**带 LiDAR、由 Apple 亲自调优的 RoomPlan,在一个具体房间上也能跑出 5.7% 的尺寸误差。** 这说明 5% 量级的误差**不是单目独有的失败**,而是「消费级房间扫描」这一整类产品的现实表现。

### 1.4 可信度被我否掉的来源(不要用)

| 来源 | 流传的数 | 为什么否掉 |
|---|---|---|
| devicetests.com | 「iPhone Measure 误差 2%–20%」 | 我逐页读过:**无测量对象、无参考仪器、无试验次数、无机型**。纯观点文 → **[未知,不可引用]** |
| marketingscoop.com | 「Measure app 平均误差约 2.5%」 | 内容农场,无方法描述 → **[未知,不可引用]** |
| 某搜索摘要 | 「Canvas/RealityScan/Scaniverse 达亚毫米」 | 量级上不可能,判定为检索幻觉 → **丢弃** |

---

## 2. 商业扫描 app:公开宣称 vs 独立实测

### 2.1 厂商公开宣称(全部 [宣称])

| 产品 | 宣称精度 | 口径 | 依赖深度硬件? | URL 见末尾 |
|---|---|---|---|---|
| **Matterport Spaces 测量** | **"generally accurate to within 1% of reality"**;举例 3 m 房间内偏差 **3 cm** | **相对 1%** | 通用口径,**未按采集设备分列** | ✅ |
| **Matterport 示意平面图** | **"generally accurate to 2% of reality"** + **"cannot guarantee this tolerance for all measurements and scanned environments"** | 相对 2% | 同上 | ✅ |
| **Matterport Pro2** | 深度精度 **50 mm @ 10 m** | 绝对(= **0.5%** [推算]) | **专用结构光相机,非手机** | ✅ |
| **Matterport Pro3** | E57 导出 **~20 mm @ 10 m** | 绝对(= **0.2%** [推算]) | **专用 LiDAR 相机,非手机** | ✅ |
| **Canvas (Occipital)** | **"most measurements … within 1-2%"** | 相对 1–2% | **是(内置 LiDAR)** | ✅ |
| 同上 | **< 1 ft 的小尺寸方差更大**;自举例墙厚 4.5″ vs 实际 4.625″ = **3% 误差** | 相对 | 是 | ✅ |
| 同上 | 🔴 自认:**墙厚等不可直接观测的量是按施工常规「推算」的,不是测的** | — | — | ✅ |
| **Polycam Space/Floorplan** | **±0.5 inch (±12.7 mm)**,"standard interior captures" | 绝对 | **是(LiDAR)** | ✅ |
| **Polycam Photo 模式** | 只肯说 "inch-level accuracy",**无条件、无参照、无百分比** | 定性 | 否 | ✅ |
| **KIRI Engine** | **无任何精度或比例尺规格**(官网 + FAQ 逐页确认) | — | — | **[缺失]** |
| **RealityScan (Epic)** | **无任何尺寸精度规格**(官网 + 开发者文档) | — | — | **[缺失]** |
| **Scaniverse (Niantic)** | **无任何数值精度规格** | — | — | **[缺失]** |
| **Magicplan** | 有专页《How Accurate is magicplan's Room Scan?》,**全文零数字**,只说「光照最关键」并**建议外接蓝牙激光测距仪** | — | — | **[缺失]** |

> 🔴 **结论**:**两家给出百分比规格的厂商(Matterport ±1%、Canvas 1–2%)全部依赖主动深度硬件。** 没有一家为纯单目发布过百分比。把 ±1% 当作「单目要对标的线」在证据上站不住。

### 2.2 独立实测(同行评审 / 有方法的第三方)

| 来源 | 对象 | 用 LiDAR? | 结果 | 口径 | 标签 |
|---|---|---|---|---|---|
| Sensors 25(15):4596 | 六款 app,**游标卡尺 0.1 mm 为真值** | 混合 | SureScan **2.9** / Structure **3.0** / Heges **3.6** / 3D Scanner App **4.4** / **KIRI 5.0** / **Polycam 21.4** mm | 绝对 | [独立] |
| 同上 | **Polycam 摄影测量** | **否** | **平均误差 21.4 mm,六者最差**;原文点名 **"inconsistent physical scale"** | 绝对 | [独立] |
| J.S. Held 白皮书 | iPhone LiDAR 扫描 vs 地面三维扫描 | **是** | **50% 的扫描需要缩放修正,修正系数 97.72%–104.60%**(即**尺度误差 −2.3% ~ +4.6%**) | **相对** | [独立] |
| Sensors 22(21):8504 | iPad LiDAR,标定球 | **是** | 球心距 **270.81 ± 4.06 mm** vs 标称 **269.4 mm** ⇒ **0.52% 尺度误差** | 相对 | [独立] |
| 同上 | 室内房间 690×525×275 cm | 是 | iPad 中位偏差 **4.2 cm** vs 摄影测量 **1.7 cm** | 绝对 | [独立] |
| Procedia CS(1:300 建筑模型,28 构件) | **Scaniverse** | 是 | **平均误差 10.36%** | 相对 | [独立] ⚠️ |
| 同上 | **Polycam Pro** | 是 | **平均误差 42.58%** | 相对 | [独立] ⚠️ |
| MDPI Geomatics 3(4):30 | Polycam / Scaniverse vs TLS(建筑记录) | 是 | Polycam RMSE **10 cm**;Scaniverse RMSE **56 cm** | 绝对 | [独立] ⚠️未核原文 |
| Sensors 25(18):5629 | Polycam **Photo 模式**,⌀0.10 m 参考柱 | **否** | 相对误差 **−5%** | 相对 | [独立] ⚠️ |

> ⚠️ **三处必须向决策者如实说明的矛盾**:
> 1. **Scaniverse vs Polycam 排名在两篇独立研究里方向完全相反**(建筑模型里 Scaniverse 远好;建筑记录里 Scaniverse 远差)⇒ **这类排名极度依赖场景和物体尺度,不能跨研究搬运。**
> 2. Sensors 25(18):5629 **自身内部不自洽**:Polycam Photo 模式的 Δ 栏写 −0.00 m,Δ/x 栏写 −0.05(−5%),正文又说「<3 mm 且 <5%」。⌀0.10 m 上 −5% 就是 −5 mm,与「<3 mm」冲突。
> 3. Procedia CS 的 42.58% 是 **1:300 缩比模型**上的构件级误差,**不能**当成实尺房间的尺度误差读。
> 4. 标 ⚠️未核原文 的条目被 403 / 付费墙挡住,数来自检索摘要,**引用前需复核**。

---

## 3. 摄影测量(带物理比例尺)—— 天花板参照

> 🔴 **这一整节都有一个前提:有物理比例尺 / 编码靶标 / 控制点。我们的产品没有。** 列出来只是为了让你知道「尺度问题在有外部基准时能解到什么程度」,从而判断「我们差的到底是算法还是基准」。

| 来源 | 适用范围 | 数值 | 标签 |
|---|---|---|---|
| Luhmann, *3D imaging: how to achieve highest accuracy*, **SPIE Proc. 8085 (2011)**, doi:10.1117/12.892070 | 工业多视摄影测量的 state of the art | 相对**精度** **1:100,000 – 1:200,000**;相对**准确度**(相对可溯源标准长度)**1:50,000 – 1:100,000** | [独立] |
| 同上 | 换算 | 1:100,000 ≈ **10 m 物体上 0.1 mm** | **[推算]** |
| Luhmann, *Close range photogrammetry for industrial applications*, **ISPRS J. Photogramm. (2010)** | 近景工业摄影测量,配位形/尺寸/参考系合适时 | 原话:`accuracies of better than 1:10000 of the measuring volume can be achieved` | [独立] |
| **Metrology 2(3):20 (2022)**,按 VDI/VDE 2634 Part 1 布多根标定尺(**一根定尺度、其余当检查长度**) | 便携摄影测量,2–10 m 零件(场景 3–64 m) | **优于 0.015 mm/m** | [独立] |
| 同上 | 换算 | **≈ 1:67,000** | **[推算]** |
| **Agisoft Metashape 官方** | 近景 | 支持 12/14/16/20-bit 编码标靶自动识别 + scale bar 工具,`to set reference distance without implementation of positioning equipment`;厂商/经销商口径「close-range 可达 1 mm」 | [宣称] |
| **Agisoft 官方(方法学)** | 如何算数才算数 | enabled scale bar 参与优化 = **控制**;disabled scale bar = **检查**。**只有 disabled(check)残差才是独立验证** | [宣称] |
| **RealityCapture / RealityScan 官方** | 控制点与尺度 | 每个 control point 可设 position accuracy;Ground Test 用不参与优化的 test points 报偏差。**官方文档未给出任何标称精度数字** | **[缺失]** |
| **VDI/VDE 2634 Blatt 1/2/3** | 光学 3D 测量系统的**验收与复检试验** | 定义 **probing error**、**sphere spacing error (SD)**、**flatness measurement error**;用球/球杆/平面三种器具,器具尺寸按测量体积体对角线定标。⚠️**它规定「怎么测、报哪几个量」,不是一套固定容差值** —— MPE 由厂家声明、按此法验证 | [独立] |
| **ISO 10360-13** | 同上的国际对应标准 | 3D 光学系统性能评定 | [独立] |
| Cultural Heritage Imaging 标定尺 | **基准本身**的精度 | `calibrated to 1/10mm accuracy or better` | [宣称] |

> 🔑 **这一节真正的信息不是那些漂亮的数字,而是三件事:**
> 1. **1:10,000 是「有基准的近景摄影测量」的下限门槛。** 换算成百分比是 **0.01%** —— 比我们讨论的 1%/3%/5% 好两到三个数量级。**这不是算法差距,是「有没有物理基准」的差距。**
> 2. **Epic 的 RealityCapture 连官方标称精度都不给**,只给「你自己放 test points 去测」的工具。**这印证了 §2.1 的结论:摄影测量厂商普遍拒绝承诺绝对精度。**
> 3. **Agisoft 官方点破的方法学**(参与优化的基准 = 控制,不参与的 = 检查)**直接适用于我们自己的台架**:任何用来对齐/标定的量都不能同时用作验证量。



---

## 4. 行业/标准层的容差

### 4.1 中国:住宅分户验收的硬性尺寸偏差(与「量房」最直接相关)

| 标准 | 项目 | 允许偏差 | 允许极差 | 量具 | 标签 |
|---|---|---|---|---|---|
| **《住宅工程质量分户验收规程》XJJ-145-2022**(新疆维吾尔自治区住建厅,2022-06-01 实施)第 6.0.2 条表 6.0.2 | **净开间、净进深** | **±10 mm** | 20 mm | **激光测距仪辅以钢卷尺** | [独立-地方规程] |
| 同上 | **净高度** | **−15 / +20 mm** | 20 mm | 同上 | [独立-地方规程] |
| 中文行业问答/博客转述的另一口径 | 净开间 ±15 mm、极差 18 mm;净高 ±15 mm、极差 20 mm | | | 同上 | **[未知-中文行业问答]** |
| 装修行业经验帖 | 「量房误差尽量在毫米间,超过 3 cm 基本不能用」;「2 mm 误差可忽略」 | | | | **[未知-经验帖]** |

> 🔴 **这里有一个极易混淆的口径,必须点破**:±10 mm 是 **施工偏差**(房子盖出来允许与图纸差多少),**不是测量偏差**(尺子允许差多少)。但它对我们有直接含义 —— 见下面的 4:1 规则。
> 📌 换算:3.6 m 开间上的 ±10 mm = **±0.28%**;4.2 m 上 = **±0.24%**。**[推算]**
> 📌 值得注意:**该规程明文规定量具是「激光测距仪辅以钢卷尺」。** 一个手机 app 想进入这个场景,面对的是一件已经被写进规程的专用工具。

### 4.2 计量学的铁律:尺子要比容差准 4 倍(决定本报告怎么读的一条)

| 来源 | 规则 | 标签 |
|---|---|---|
| **ANSI/NCSL Z540-1**,10.2 节 B 段原话:*"the collective uncertainty of the measurement standards shall not exceed 25% of the acceptable tolerance for each characteristic of the measuring"* | 即 **TUR ≥ 4:1** —— 测量设备的不确定度 ≤ 被判容差的 **25%** | [独立-标准原文] |
| 行业沿革 | 早年惯例是 **10:1**,随着仪器进步 **4:1** 成为普遍可接受下限 | [独立] |

> 🔑 **这条规则把整份报告的问题重新定义了。** 「我们允许几个百分点」这个问法,答案取决于**用户要拿我们的数去判什么容差**:

| 用户要判的容差 | 按 4:1,我们的不确定度须 ≤ | 换算成百分比(典型尺寸) | 标签 |
|---|---|---|---|
| 分户验收 净开间 **±10 mm** | **2.5 mm** | 3.6 m 开间上 = **0.07%** | **[推算]** |
| 定制百叶 制造公差 **±3.2 mm** | **0.8 mm** | 0.9 m 窗宽上 = **0.09%** | **[推算]** |
| 家具搬运净空 **25 mm** | **6.25 mm** | 0.8 m 门宽上 = **0.78%** | **[推算]** |
| 房产面积(线性 1%) | **0.25%** 线性 | — | **[推算]** |

> 🔴 **结论(而不是决定)**:**严格按 4:1,连 ±1% 都不足以支撑上面任何一个「判定型」用途。** 这意味着诚实的产品定位只有两种:
> **(a) 参考型** —— 明说「这是估算,不能用于下料和验收」,那么 3%–5% 完全够用,且是行业多数派做法;
> **(b) 判定型** —— 必须引入外部尺度基准,并且目标是**毫米口径**而不是百分点口径。
> **中间地带(承诺 ±1% 但不引入基准)在计量学上是站不住的。**

### 4.3 跨端的现实:Web 端连「有没有米制尺度」都是个开关

| 平台 | 情况 | 标签 |
|---|---|---|
| **8th Wall (WebAR)** | 提供 **Responsive Scale**(尺寸随设备离地高度变,**根本不是米制**)与 **Absolute Scale**(真实尺寸)两种模式;Absolute Scale **要求用户先沿 z 轴前后移动设备**来初始化 | [宣称] |
| 同上 | **未发布任何 Absolute Scale 的数值精度规格**(我检索了产品页与博客,未找到) | **[缺失]** |

> 🔴 **对跨端产品的含义**:Web 端的尺度不是「精度高低」的问题,而是**默认压根没有米制尺度**,且开启后需要**规定动作**。iOS/Android/鸿蒙/Web 四端若要给同一个尺寸承诺,**Web 是最弱的一环,而且弱在架构上,不在调参上。**


### 4.4 USIBD LOA —— 唯一真正给 as-built 容差数的规范

**Document C120 Guide v2.0 (2016), p.8** [独立,原文逐字]

| Level | Upper Range | Lower Range |
|---|---|---|
| LOA10 | **User defined** | 5 cm * |
| LOA20 | 5 cm * | 15 mm * |
| LOA30 | 15 mm * | 5 mm * |
| LOA40 | 5 mm * | 1 mm * |
| LOA50 | 1 mm * | 0 * |

`* Specified at the 95 percent confidence level.`

- p.9 原文:`Numbers represented in the following table relate to standard deviation of 2 Sigma.` ⇒ **表里的数是 2σ 标准差,不是最大误差**
- p.9 原文:`The upper range of LOA10 has been intentionally left undefined.` 🔴 **网上大量二手资料写「LOA10 = 5–15 cm」是错的**,上界官方故意不定义
- 基于 **DIN 18710**;英制换算官方自认 `this conversion is not an exact translation`,`rounding to the nearest 1/16th of an inch`
- 适用范围:按 **CSI UniFormat 2010 逐构件**(Level 1–3)指定,**不是整个项目一个值**
- 现行版本 v3.1 (2025),v3.0 (2019) 的小升级,新增「tolerance 与 standard deviation 互转的简化算法」[宣称]

**🔑 Measured Accuracy vs Represented Accuracy(C120 p.9–10,原文)**
> `Measured Accuracy represents the standard deviation range that is to be achieved from the final measurements taken regardless of the method used to acquire those measurements.`
> `Represented Accuracy represents the standard deviation range that is to be achieved once the measured data is processed into some other form such as line work or a model.`
> p.10: `error will always be introduced when measured data is processed into, or 'represented as', some other form of deliverable`

> 🔑 **这个拆分与我们「VIO 位姿精度 vs 最终网格模型精度」完全同构,是现成可抄的契约结构。** C220 表单里就是左右两个独立色块(蓝=Measured / 绿=Represented),各带 Absolute/Relative 勾选和 A/B/C 验证等级(A = 不校核,B = 用重叠数据集校核,C = 用独立测量或方法校核)。

### 4.5 BIM LOD —— ✅ 阴性结论:**LOD 根本不是容差规范**

BIMForum *LOD Specification 2024 Part I* 原文:
- p.12: `Level of Development is the degree to which the element's geometry has been thought through – the degree to which project team members may rely on the information when using the model.` ⇒ **讲「想清楚了多少」,零几何数值**
- LOD 200: `Any information derived from LOD 200 elements must be considered approximate.` —— 只说近似,不给数
- LOD 300/350: `quantity, size, shape, location, and orientation can be measured` —— 只说可量,不给精度
- **LOD 500(AIA 原文, p.13)**: `The level of accuracy shall be noted or attached to the Model Element.`
- **BIMForum Expansion (p.13)**: `The LOD 500 definition requires that the model element's accuracy be specified – BIMForum recommends USIBD's Level of Accuracy (LOA) Specification for this purpose.`

> ⇒ **LOD 定义建模深度,精度必须另外挂 LOA。两者正交:LOD 相同的两个模型,精度可以差很远。** 🔴 **如果有人拿「我们做到 LOD 300」来谈精度,那是话术,不是指标。**

### 4.6 RICS —— 有硬数字,而且直接点名「面积测量」

关键文件**不是**流传最广的 *RICS Property Measurement / IPMS*(那个只管「算什么面积、含不含墙」,**不给容差**,且 2nd ed 已于 2025-06 归档),而是:

**RICS《Measured surveys of land, buildings and utilities》3rd edition (professional standard, 2024-04) §2.2–2.3 "Survey accuracy banding"** [独立,原文表格]

| Band | 平面 1σ | 平面 2σ | 高程(硬/软) | 典型用途 |
|---|---|---|---|---|
| A | ±2 mm | ±4 mm | ±2 mm / N/A | 监测、高精度工程放样与加工 |
| B | ±4 mm | ±8 mm | ±4 / ±8 mm | 监测、高精度工程**与建筑实测**、放样 |
| C | ±5 mm | ±10 mm | ±5 mm / N/A | 工程测量放样、**高精度建筑实测、文物记录** |
| D | ±10 mm | ±20 mm | ±10 / ±25 mm | 工程测量放样、**建筑实测**、高精度地形 |
| **E** | **±25 mm** | **±50 mm** | ±10 / ±50 mm | 建筑实测、地形、低精度放样、**净面积测量、估价测量**、面积登记 |
| **F** | **±50 mm** | **±100 mm** | ±50 / ±100 mm | 低精度建筑实测、**毛面积测量** |
| G/H/I | ±100 / 250 / 500 mm | ±200 / ±500 mm | … | 地形、制图、资产测绘 |

- §2.3.1 原文:`1 sigma accuracy means that 68% of normally distributed observation residuals will fall within the band value shown for 1 sigma with 95% falling within the 2 sigma value.`
- §2.3.2 原文:`a client requiring 10mm plan accuracy at 95% confidence interval should select a band C survey (i.e.+/- 10mm at 2 sigma or 95% confidence).`
- band 值是**相对控制点的单点精度**;两细节点之间的相对精度 = √(σ₁²+σ₂²) + (间距−100 m)×控制 PPM

> 🔑 **面积测量的官方答案在这里**:**净面积/估价测量 = Band E(±25 mm 1σ / ±50 mm 2σ)**;**毛面积测量 = Band F(±50 mm / ±100 mm)**。
> 🔴 **警告**:网上流传的第三方「RICS bands」表(如 Band A ±15–25 mm / B ±50 / C ±100 / D ±250)**与 RICS 原文完全不符**,不要用。

### 4.7 ANSI Z765-2021(住宅面积计算)—— ⚠️ 它**只有分辨率规则,没有准确度容差**

§3 原文:
> `When using English measurement units, the house is measured to the nearest inch or tenth of a foot; the final square footage is reported to the nearest whole square foot. When using Metric or Standard International (SI) measurement units, the house is measured to the nearest 0.01 meter; the final floor area is reported to the nearest 0.1 square meter.`

**Annex(informative)commentary 里最有价值的一句:**
> `The standard makes no statement concerning differences between square footage calculations made by multiple parties for the same property.`

> 🔑 **ANSI Z765 规定的是读数分辨率(1 inch / 0.01 m)与报数进位(1 sq ft / 0.1 m²),不是准确度。它明确不承诺两方各自量同一套房能对得上。**
> 📌 它改用**声明制**兜底:未进室内查看用 Declaration 1、按图纸算用 Declaration 2、估算尺寸用 Declaration 3。**这对我们是一个可抄的产品形态 —— 不承诺精度,而是强制声明「这个数是怎么来的」。**
> 📌 Fannie Mae / Freddie Mac 已采纳为评估强制标准 ⇒ 在美国房产语境下这是硬约束。
> 📌 其他硬性规则:天花板净高 ≥7 ft (2.13 m);梁/管下 ≥6 ft 4 in (1.93 m);斜顶房间至少一半面积需 ≥7 ft,且 <5 ft (1.52 m) 部分不计。

### 4.8 ISO —— 分工要点破,不然会引错

| 标准 | 实际管什么 | 给不给容差数值 |
|---|---|---|
| **ISO 7976-1:1989**(Tolerances for building — **Methods of measurement**) | §4 尺寸、§5 方正度、§6 直线度、§7 平整度、§8–12 位置/水平/垂直/偏心;Section three §15 全是量具(游标卡尺、EDM、倾角仪、激光、水准仪、钢尺…);Annex 是钢尺垂度/温度/坡度改正 | ❌ **不给允许偏差。** 它给的是每种量法的 **"Accuracy table"** —— 「用这个方法能量到多准」,**不是「建成后允许差多少」** |
| **ISO 7976-2:1989** | 测点打在哪 | ❌ |
| **ISO 4463-1:1989**(Setting-out and measurement) | §1 Scope 原文:`…it gives values of permitted deviations and guidance on independent check measurements (quality control)…`;含 §18.5 验收准则、§18.6 不合规后果 | ✅ **这才是给 permitted deviations 的那本** ⚠️具体数表在付费正文,本次**未取到逐条数值** |
| **ISO 17123 系列**(Parts 1–11,含 **Part 9 地面激光扫描仪 2018**、Part 11 GNSS 2025) | 仪器**现场检验程序**,测 precision(重复性)。原文定位:`field verifications of the suitability of a particular instrument for the immediate task at hand... not proposed as tests for acceptance or performance evaluations` | ❌ 不是容差规范。但 **Part 9 明写** `provides an estimate as to whether the precision of a given laser scanner equipment is within the specified permitted deviation in accordance with ISO 4463-1` ⇒ 印证容差数在 4463-1 |

> 🔴 **常见引错**:把 **ISO 7976** 当成「建筑容差标准」引用。它的标题里确实有 "Tolerances for building",但正文是**量法与量具精度**。真正的允许偏差在 **ISO 4463-1**。

### 4.9 橱柜 / 台面 / 木作 —— 安装工真正需要的数

**ANSI/AWI 0620-2024 Finish Carpentry & Installation §3.4**(按等级) [独立,官方逐条]

| 项目 | Premium | Custom | Economy |
|---|---|---|---|
| **§3.4.6 台面 scribe to wall**(⬅ 对 as-built 最关键) | **0.8 mm [.031″]** | **1.2 mm [.047″]** | 1.6 mm [.063″] |
| §3.4.6 台面高度 | ±6.4 mm [.250″](全等级) | | |
| §3.4.6 悬挑均匀度 | 4.8 mm [.188″] 沿整个立面(全等级) | | |
| §3.4.1.1 现场接缝间隙(木-木) | 0.4 mm | 0.8 mm | 1.2 mm |
| §3.4.1.2 现场接缝齐平度 | 0.4 mm | 0.8 mm | 1.2 mm |
| §3.4.2.1 门/抽屉边缘对齐 | 0.8 mm | 1.2 mm | 1.6 mm |

其他参照:
- **数字模板设备**:LT-2D3D 标称 `1/16″ accuracy up to 200 feet`(≈1.6 mm)[宣称];Proliner ≈0.2 mm [宣称-第三方转述]
- **数字 vs 物理模板**:数字 ±1/32″–1/16″(**0.8–1.6 mm**),物理 ±1/8″–1/4″(**3.2–6.4 mm**)[宣称/行业]
- **MIA(Marble Institute)**:台面与墙间隙 ≤1/8″(3.2 mm,打胶前);拼缝 ≤1/16″(1.6 mm)[行业-第三方转述]
- **🔑 基层现实(很重要)**:**墙本身就不直。** 石膏板饰面隔墙允许不垂直 **1/4″ in 10′(6.4 mm / 3 m)**(Handbook of Construction Tolerances, Ballast);龙骨面变化 ≤1/8″(GA-216 / ASTM C840)。常被当「行业标准」的「1/8″ in 10′ 平整度」**其实并不在 ASTM C840 / GA-216 / GA-214 里** [独立]
- **NKBA Kitchen Planning Guidelines**:⚠️ 阴性结论 —— 只规定**净空/间距**(洗碗机边到水槽 ≤36″、站立空间 ≥21″),**完全不规定测量容差**

> 🔑 **「墙本身允许 6.4 mm/3 m 不垂直」这一条,对我们是一把双刃剑:**
> 一方面它说明**真实房间根本没有「唯一正确的尺寸」**,同一面墙在不同高度量出来本来就不一样 —— 这给了我们一条合理的话术空间。
> 另一方面它也意味着**用户拿卷尺复核我们时,他自己的读数也会飘 6 mm**,所以**用户感知到的「不准」里有一部分不是我们的错**。但这不能当成放宽指标的理由,因为台面 scribe 容差是 **0.8–1.6 mm**,比墙的不垂直量还小一个量级 —— 施工方是靠**现场配切(scribe)**而不是靠图纸精度解决这个矛盾的。



---

## 5. 用途 → 需要的容差(核心表)

> 每行的「依据」列写清这一行是引用还是推算。**「需要的容差」列凡标 [推算] 的,都是我从依据里反推的,不是任何标准的原话。**

| # | 用途 | 决策的硬边界是什么 | 需要的容差 | 依据 | 标签 |
|---|---|---|---|---|---|
| 1 | **家具放得下吗(门 / 楼梯 / 电梯)** | 搬家行业要求**总净空 25–50 mm**(每边 12–25 mm);卸门可再多 50–90 mm | 在 ~800 mm 门宽上,误差须 **≪ 25 mm** ⇒ **约 ±10 mm 绝对**,即 **~1.2%** | 搬家行业操作指南的净空建议 | 依据[独立-弱] / 数值**[推算]** |
| 2 | **房间面积估算(自住参考)** | 无硬边界,用户拿来「心里有数」 | 线性 **3–5%** 即可(面积 6–10%) | 无任何标准规定消费级面积估算容差;此行**纯属推算** | **[推算]** |
| 3 | **房产/估价用的面积** | **RICS Band E:净面积/估价测量 = ±25 mm (1σ) / ±50 mm (2σ)**;毛面积测量 = Band F ±50/±100 mm。**ANSI Z765 只规定读数分辨率 1 inch / 0.01 m,不规定准确度,并明说不承诺多方复现** | **±50 mm 绝对(2σ)**;4 m 房间上 = **1.25%** | RICS《Measured surveys》3rd ed §2.2–2.3 原文表;ANSI Z765-2021 §3 + Annex | 依据**[独立-标准原文]** / 换算**[推算]** |
| 4 | **装修下料 / 定制窗帘百叶** | 厂商制造公差本身就是 **±1/8″ = ±3.2 mm**,且要求**测到 1/8″ 并原样提交、不许自行扣减**;定制品**不退** | 在 ~900 mm 窗宽上,**±3 mm 绝对 ⇒ ~0.35%** | 百叶厂商订货政策原话:"the manufacturers are allowed an + or - 1/8″ tolerance on all measurements" | 依据[宣称] / 换算**[推算]** |
| 5 | **橱柜/台面模板** | **ANSI/AWI 0620-2024 §3.4.6 台面 scribe to wall:Premium 0.8 mm / Custom 1.2 mm / Economy 1.6 mm**;数字模板设备标称 0.8–1.6 mm | **≈1 mm 绝对**;2.4 m 台面上 = **0.04%** | AWI 0620-2024 官方条文 | 依据**[独立-标准原文]** / 换算**[推算]** |
| 6 | **电商商品尺寸(买家判断「合不合适」)** | **无公开容差标准。** 「item not as described / smaller than expected」是主要退货原因之一,但平台不规定容差 | 由商品类别决定,**无法给统一数** | Amazon 卖家论坛与第三方指南;**Amazon 本身未发布尺寸容差** | **[缺失]** |
| 7 | **电商/物流的分档费率** | **有硬悬崖**:FBA Small Standard 厚度上限 **0.75″**,**0.8″ 就跳档**按 Large Standard 计费 | 在分档边界附近须 **优于 1 mm**;远离边界则无所谓 | 第三方 FBA 费率汇总(非 Amazon 官方页) | **[未知-第三方汇总]** |
| 8 | **保险/理赔(屋面等)** | 某测量服务商博客称「行业惯例把总面积 **1%–3%** 的偏差视为可接受」 | **1%–3%** | 🔴 该文**自认这是行业惯例,不是任何标准机构、承保方或法规的规定**,且作者是卖测量报告的 | **[未知-厂商博客]** |
| 9 | **建筑实测 / as-built 文档** | **USIBD LOA20 = 15 mm–5 cm(2σ,95%)**,这是最常用的建筑文档档;LOA30 = 5–15 mm(文物/高要求) | **LOA20:±50 mm**;LOA30:±15 mm | USIBD C120 Guide v2.0 p.8 原文表 | **[独立-标准原文]** |
| 10 | **中国住宅分户验收(量房场景)** | **净开间/净进深 ±10 mm、极差 20 mm;净高 −15/+20 mm**;规程指定量具为激光测距仪 | 若只是**复核**:±10 mm;若要**替代量具**判定:按 4:1 须 **≤2.5 mm** | XJJ-145-2022 §6.0.2 表 6.0.2 | 依据**[独立-地方规程]** / 4:1 换算**[推算]** |

### 5.1 一把「数量级梯子」(把上面所有硬数按严到松排一列)

> 全部为 2σ / 95% 口径或厂商制造公差。**[独立-标准原文]** 除非另注。

| 档位 | 数值 | 出处 | 谁在用 |
|---|---|---|---|
| 工业摄影测量(有基准) | **1:10,000 – 1:100,000**(= 0.01%–0.001%) | Luhmann / Metrology 2022 | 工业计量,**与我们不可比** |
| 台面/木作 scribe | **0.8 – 1.6 mm** | ANSI/AWI 0620-2024 §3.4.6 | 橱柜台面安装 |
| 定制百叶制造公差 | **±3.2 mm (±1/8″)** | 百叶厂商订货政策 [宣称] | 定制窗饰 |
| RICS Band A / B | **±4 / ±8 mm** | RICS Measured Surveys §2.3 | 监测、高精度工程放样 |
| RICS Band C · 中国分户验收开间 | **±10 mm** | RICS §2.3 / XJJ-145-2022 | 高精度建筑实测、文物;住宅交付验收 |
| USIBD **LOA30** | **5 – 15 mm** | USIBD C120 p.8 | 文物记录、高要求 as-built |
| RICS Band D | **±20 mm** | RICS §2.3 | 一般建筑实测 |
| 家具搬运净空 | **25 – 50 mm 总净空** | 搬家行业指南 [独立-弱] | 「放不放得下」 |
| RICS Band E · USIBD **LOA20** | **±50 mm** / **15 mm–5 cm** | RICS §2.3 / USIBD C120 | **净面积/估价测量;最常用的建筑文档档** |
| RICS Band F | **±100 mm** | RICS §2.3 | 毛面积测量 |

> 🔑 **把我们的现状放进这把梯子**(全部 **[推算]**,按 4 m 典型房间尺寸换算):
> | 我们的表现 | 4 m 上的绝对值 | 落在哪一档 |
> |---|---|---|
> | 最好 0.2% | 8 mm | ≈ RICS Band B/C |
> | 典型 4.13%(对 ARKit) | 165 mm | **比 RICS Band F(最松的一档)还差** |
> | 最坏 19% | 760 mm | **掉出整张表** |
>
> 🔴 **这是全报告最刺眼的一格:我们的最好成绩能进 Band C,最坏成绩掉出整张表。** 决定「允许几个百分点」之前,更该先决定的是**「允许多大的跨场波动」** —— 因为一个承诺被违约一次,和它平均表现多好没有关系。

---

## 6. 三个候选数 —— 请你自己挑一个

> 下面每个数我都按同一个模板写:**谁达到过 / 达不到会怎样 / 对「单目无 LiDAR」意味着什么**。
> 🔴 我不替你选。选择的实质是:**你要在「能承诺什么」和「要造多少基础设施」之间取哪个点。**

### 候选 A:**±1% 线性**

| | |
|---|---|
| **谁达到过** | **只有带主动深度硬件的系统敢宣称**:Matterport ±1%[宣称]、Canvas 1–2%[宣称]。**这两家都是宣称,不是独立实测。** |
| **独立实测打不打得到?** | 🔴 **打不到。** 同样是 LiDAR,独立测试里 iPhone 扫描**一半需要缩放修正,系数跑到 97.72%–104.60%(±4.6%)**;iPad LiDAR 在标定球上是 **0.52%**,在整房间上中位偏差 **4.2 cm / 6.9 m = 0.6%**。**即便 LiDAR,±1% 也只在小物体和好条件下成立。** |
| **达不到的后果** | 下料级用途(窗帘、百叶、台面、橱柜)**必须**在这个量级,达不到就是**做废一件定制品且不可退**。房产/保险面积也在这条线附近。 |
| **对标到行业档位** | 4 m 房间上 ±1% = **40 mm** ⇒ 约等于 **RICS Band E(净面积/估价测量,±50 mm 2σ)**、**USIBD LOA20 的松端**。**[推算]** 即:±1% 只够到「面积/估价」这一档,**够不到** RICS Band C(±10 mm)、中国分户验收(±10 mm)、台面 scribe(1 mm) |
| **对我们意味着什么** | ±1% 意味着你们要把当前 **0.2%–19%** 的跨录制跳动压进 **±1%**,即**最坏情况改善 19 倍**。以现有证据,**纯单目 VIO 没有任何公开先例达到过这个稳定度**。走这条线等价于承诺:要么引入外部尺度基准(已知尺寸参照物 / 标定流程 / 用户输入一个已知长度),要么放弃这一档用途。**这是一个架构决定,不是调参决定。** |

### 候选 B:**±3% 线性**

| | |
|---|---|
| **谁达到过** | 消费级扫描的**实测中位水平**大致落在这里:iPad LiDAR 整房间 ~0.6%[独立]、iPhone LiDAR 尺度修正 ±2.3~4.6%[独立]、Polycam Photo −5%[独立]、RoomPlan 单房间 5.7%[独立-弱]。**3% 大致是「消费级扫描在好条件下的实际表现」这条带的中间。** |
| **达不到的后果** | 「家具放得下吗」会开始翻车:3% 在 800 mm 门宽上是 24 mm,**正好吃掉搬家行业要求的 25 mm 全部净空**。面积估算会到 6%,在房产语境下会被质疑。 |
| **对标到行业档位** | 4 m 上 ±3% = **120 mm** ⇒ 介于 **RICS Band F(±100 mm,毛面积测量)** 与更松之间。**[推算]** 即:±3% 连「毛面积测量」都勉强 |
| **对我们意味着什么** | 你们的 **ARKit 对照场里 4.13%** 已经很接近这条线,**但 0.2%–19% 的跳动意味着你无法保证**。达成 ±3% 的真正工作不是把均值压下来,而是**把最坏情况压下来**——即消除尺度的场景依赖性。参照 Sensors 22(24):9873:**ARCore 在走廊 0.08%、在楼梯 3.5%**,说明**一流的单目 VIO 也是靠场景吃饭的**。所以 ±3% 应该被理解为「**±3% 且带一个可靠的置信度提示**」,而不是「±3% 无条件」。 |

### 候选 C:**±5% 线性**

| | |
|---|---|
| **谁达到过** | 这条线基本等于「不做额外工作的现状」。**Apple 自己的 RoomPlan 带 LiDAR 也跑出过 5.7%**[独立-弱];ARKit TrueDepth 在 20–60 cm 上全区间均值 **5.32%**[独立];Polycam Photo **−5%**[独立]。 |
| **达不到的后果** | 只剩「大致感受尺寸」。面积误差到 10%,**100 m² 报成 110 m²**。任何涉及钱的判断(下料、买家具、面积、理赔)都不能用。 |
| **对标到行业档位** | 4 m 上 ±5% = **200 mm** ⇒ **掉出 RICS 全部 A–F 档**,只落在 Band G(±200 mm,地形/制图)。**[推算]** 即:±5% 在建筑测量的语境里不是一个「档位」,是「不做建筑测量」 |
| **对我们意味着什么** | 🔴 **注意:你们现在也达不到 ±5%,因为最坏是 19%。** ±5% 不是「躺平线」,它仍然要求把跳动收敛。真正的「躺平选项」是**根本不承诺百分比**,像 KIRI / RealityScan / Scaniverse / Magicplan 那样**一个数都不给**——这是目前行业里**多数玩家的实际选择**。 |

### 一张对照图(全部 [推算],用于直觉)

| 被测对象 | ±1% | ±3% | ±5% | 现状最坏 19% |
|---|---|---|---|---|
| 门宽 800 mm | 8 mm | 24 mm | 40 mm | **152 mm** |
| 沙发 2.2 m | 22 mm | 66 mm | 110 mm | **418 mm** |
| 房间 5 m | 50 mm | 150 mm | 250 mm | **950 mm** |
| 房间面积 100 m²(≈2ε) | 2 m² | 6 m² | 10 m² | **38 m²** |
| 窗宽 900 mm(百叶公差 ±3.2 mm) | 9 mm ❌ | 27 mm ❌ | 45 mm ❌ | 171 mm ❌ |

> 🔴 最后一行值得单独看:**即便 ±1%,也已经是百叶制造公差(±3.2 mm)的 2.8 倍。** 下料级用途需要的是**绝对毫米承诺**,不是百分比承诺。**如果这个用途在路线图上,那么「选几个百分点」这个问题本身就问错了。**

---

## 7. 我认为这份报告里最需要你注意的五条

1. **没有一家厂商为纯单目发布过百分比尺度规格。** 你要么成为第一个,要么加入「不给数」的多数派。这是一个**对外承诺**的决定,不只是技术指标。
2. **跨场景的跳动比均值更致命。** 公开数据(ARCore 0.08% 走廊 / 3.5% 楼梯)证明**场景依赖是单目 VIO 的结构性特征,不是 bug**。任何单一百分比承诺都隐含「在某些场景下会违约」。可行的替代是**承诺 + 置信度**,让 app 在没把握时拒绝给数。
3. **LiDAR 不是量级碾压,只是天花板高一点。** 独立测试里 iPhone LiDAR 的尺度修正系数照样跑到 **±4.6%**,Apple 自家 RoomPlan 也有 **5.7%** 的实例。**你们的 4.13% 落在消费级已发表区间内部,不是离群值。** 这对「不用 LiDAR」这个产品决策是**支持性**证据。
4. **「量真实尺寸」这个需求需要拆成两档卖,而且拆点不在 1% 和 3% 之间。** 把所有硬数排成梯子(§5.1)后可以看到,**真实的断层在「毫米口径」和「百分比口径」之间**:
   - **判定型用途(台面 scribe 0.8–1.6 mm、百叶 ±3.2 mm、分户验收 ±10 mm)全部是绝对毫米口径**,而且按 ANSI/NCSL Z540-1 的 4:1 规则,我们需要做到 **0.8–2.5 mm** —— 这不是「几个百分点」能表达的,**问法本身要换。**
   - **参考型用途(面积、估价、能不能放得下)才是百分比口径**,落在 **RICS Band E/F(±50–100 mm)**,对应 **1%–2.5%**。
   - **中间那档 ±1% 两边都不讨好**:够不上判定型(差 4–40 倍),又要付出引入外部基准的全部代价。

5. **有两个现成的、可直接抄的契约结构**,比自己发明指标划算:
   - **USIBD 的 Measured vs Represented 拆分** —— 官方原话是「数据被处理成另一种形式时一定会引入误差」,所以**测量精度和成品模型精度必须分别声明**。这与我们「VIO 位姿精度 vs 最终网格精度」完全同构。
   - **ANSI Z765 的声明制** —— 它干脆**不承诺准确度**,改为强制声明「这个数是怎么来的」(进室内量的 / 按图纸算的 / 估的)。对一个不能保证跨场稳定的单目系统,**这可能比承诺一个百分比更诚实、也更能上生产。**

---

## 8. 本次调研的已知缺口(诚实披露)

| 缺口 | 影响 |
|---|---|
| **RealityScan 手机端零可引用数** | 无法把 Epic 放进对比。ISPRS XLVIII-M-9-2025-1167 那篇 PDF 抓取失败,值得手工下载 |
| MDPI Geomatics 3(4):30、Procedia CS 两篇被 403 挡住 | 其中 Polycam / Scaniverse 的数**未亲自核对表格**,且两篇结论方向相反,引用前必须复核 |
| Matterport **手机端 Capture app** 的单独精度口径 | 未找到。±1% 是通用口径,**不能直接当手机数用** |
| Matterport 两个支持页直接抓取返回 401 | 1% / 2% 的原话来自该页的搜索索引文本,URL 已给,**建议人工复核一次** |
| 没有找到「单目 ARKit(无 LiDAR 机型)专门做尺度标定」的论文 | 这正是我们所处的位置,**公开文献在这一格是空的** |
| **ISO 4463-1 的 permitted deviations 数表未取到** | 这是 ISO 体系里**唯一真正给允许偏差**的那本,预览只到 p.3。若要在国际语境下引用「建筑容差」,**必须买正本** |
| XJJ-145-2022 的数来自转载页 | 建议取规程正本复核;宁夏的 PDF 是 OFD 转换流,解析失败 |
| GB 50210-2018 的允许偏差表未取到 | 中文语境下最常被引用的装修验收标准,**具体数值需正本** |
| Matterport 两页 401、MDPI Geomatics 与 Procedia CS 两篇 403 | 报告里已逐条标注 ⚠️,**引用前需人工复核** |
| RealityScan 手机端零可引用数 | ISPRS XLVIII-M-9-2025-1167 值得手工下载 |


---

## 9. 来源清单

### 9.1 同行评审论文 [独立]

| # | 来源 | 用在哪一节 |
|---|---|---|
| S1 | Kim P. et al. *A Benchmark Comparison of Four Off-the-Shelf Proprietary Visual–Inertial Odometry Systems.* **Sensors 22(24):9873, 2022.** https://doi.org/10.3390/s22249873 · 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC9785098/ | §1.1 ARCore/ARKit FDE |
| S2 | Marino E. et al. *Benchmarking Built-In Tracking Systems for Indoor AR Applications on Popular Mobile Devices.* **Sensors 22(14):5382, 2022.** https://doi.org/10.3390/s22145382 · 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC9320911 | §1.1 ATE(OptiTrack 真值) |
| S3 | Hamilton-Fletcher G. et al. *Accuracy and usability of smartphone-based distance estimation approaches for visual assistive technology development.* **IEEE OJEMB 5:54–58, 2024.** https://doi.org/10.1109/OJEMB.2024.3358562 · 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC10939328/ | §1.1 ARKit 后置(LiDAR)1–3 m |
| S4 | Nissen L. et al. *Towards Preventing Gaps in Health Care Systems through Smartphone Use: Analysis of ARKit for Accurate Measurement of Facial Distances in Different Angles.* **Sensors 23(9):4486, 2023.** https://doi.org/10.3390/s23094486 · 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC10181530/ | §1.1 TrueDepth 0.88–9.07% |
| S5 | 六款移动 3D 成像 App 体模评估(游标卡尺真值). **Sensors 25(15):4596.** https://pmc.ncbi.nlm.nih.gov/articles/PMC12349111/ | §2.2 KIRI 5.0 mm / Polycam 21.4 mm |
| S6 | iPhone 13 Pro 摄影测量与 LiDAR 对比(榛树). **Sensors 25(18):5629.** https://pmc.ncbi.nlm.nih.gov/articles/PMC12473222/ | §2.2 Polycam Photo −5% ⚠️内部不自洽 |
| S7 | *Accuracy Verification of Surface Models of Architectural Objects from the iPad LiDAR in the Context of Photogrammetry Methods.* **Sensors 22(21):8504.** https://pmc.ncbi.nlm.nih.gov/articles/PMC9657006 | §2.2 标定球 0.52% / 房间 4.2 cm |
| S8 | 移动 LiDAR App 建筑构件级精度比较. **Procedia Computer Science.** https://www.sciencedirect.com/science/article/pii/S1877050925026742 | §2.2 Scaniverse 10.36% / Polycam Pro 42.58% ⚠️1:300 缩比模型 |
| S9 | iPhone 13 Pro 低成本建筑记录. **MDPI Geomatics 3(4):30.** https://www.mdpi.com/2673-7418/3/4/30 | §2.2 ⚠️403,未核原文 |
| S10 | Li J. et al. *RD-VIO: Robust Visual-Inertial Odometry for Mobile Augmented Reality in Dynamic Environments.* **IEEE TVCG, 2024.** https://arxiv.org/abs/2310.15072 | 背景(我方已有 VICON 数) |
| S11 | Ju H. et al. *Have We Mastered Scale in Deep Monocular Visual SLAM? The ScaleMaster Dataset and Benchmark.* **ICRA 2026.** https://arxiv.org/abs/2602.18174 | 佐证「单目尺度不一致是公开的开放问题」 |
| S12 | Wang M. et al. *Empirical Studies of Large Scale Environment Scanning by Consumer Electronics.* **IEEE Consumer Electronics Magazine, 2025.** https://arxiv.org/abs/2506.14771 | Matterport Pro3 vs iPhone,C2C 4.08 cm |

### 9.2 厂商官方文档 [宣称] / [缺失]

| # | 来源 |
|---|---|
| V1 | Apple — *3D Parametric Room Representation with RoomPlan*(2022-10-04)https://machinelearning.apple.com/research/roomplan — 95%/90% 检测率、3 cm/30 cm 体素;**无尺寸容差** |
| V2 | Apple — iPhone 用户指南 Measure 章节 https://support.apple.com/guide/iphone/measure-dimensions-iphd8ac2cfea/ios — **全文无精度数字 [缺失]** |
| V3 | Matterport — *How accurate are dimensions in Matterport Spaces?* https://support.matterport.com/hc/en-us/articles/212629928-How-accurate-are-dimensions-in-Matterport-Spaces- ⚠️直接抓取返回 401,「within 1% of reality / 3 m 房间 3 cm」来自该页搜索索引文本,**建议人工复核** |
| V4 | Matterport — *FAQ: Schematic Floor Plans* https://support.matterport.com/hc/en-us/articles/218802457-FAQ-Schematic-Floor-Plans ⚠️同样 401;「accurate to 2% of reality」+「cannot guarantee this tolerance for all measurements and scanned environments」来自搜索索引 |
| V5 | Matterport Pro2 规格 https://support.matterport.com/hc/en-us/articles/115004093167-Matterport-Pro2-3D-Camera-Specifications — 50 mm @ 10 m |
| V6 | Matterport Pro3 FAQ https://support.matterport.com/s/article/FAQ-Pro3-Camera — ~20 mm @ 10 m |
| V7 | Canvas — *What kind of accuracy can I expect from Canvas?* https://support.canvas.io/article/5-what-kind-of-accuracy-can-i-expect-from-canvas — 1–2%,小尺寸 3% 举例,墙厚系推算 |
| V8 | Polycam — Spatial Capture https://poly.cam/spatial-capture — ±0.5 inch(LiDAR) |
| V9 | Polycam — How to Measure Your Captures https://learn.poly.cam/hc/en-us/articles/29647317758100-How-to-Measure-Your-Captures — Photo 模式仅 "inch-level" |
| V10 | KIRI Engine FAQ https://www.kiriengine.app/faq — **[缺失]** |
| V11 | RealityScan Mobile 官方文档 https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-documentation — **[缺失]** |
| V12 | Scaniverse https://scaniverse.com — **[缺失]** |
| V13 | magicplan — *How Accurate is magicplan's Room Scan?* https://help.magicplan.app/how-accurate-is-magicplan — **有专页但零数字 [缺失]** |
| V14 | IKEA 新闻稿(2017-09-29)https://www.ikea.com/kr/en/newsroom/corporate-news/page-title-h1-pubb1d8e437/ — 「98% accuracy」「true to scale」**口径未定义** |
| V15 | 8th Wall — World AR 产品页 https://www.8thwall.com/products/world-ar · Absolute Scale 模板 https://www.8thwall.com/8thwall/absolute-scale-aframe — Absolute vs Responsive Scale;**无数值规格 [缺失]** |
| V16 | Blinds Made in USA 订货政策 https://www.blindsmadeinusa.com/info/order-policy.php — 原话:"the manufacturers are allowed an + or - 1/8″ tolerance on all measurements" |

### 9.3 标准与规程 [独立-标准原文]

| # | 来源 |
|---|---|
| R1 | **《住宅工程质量分户验收规程》XJJ-145-2022**(新疆维吾尔自治区住房和城乡建设厅,2022-06-01 实施),第 6.0.2 条表 6.0.2 — 净开间/净进深 **±10 mm**、净高 **−15/+20 mm**、极差 20 mm、量具「激光测距仪辅以钢卷尺」。转载页 https://yajuyun.com/cms/2026/08/08/78813/ ⚠️**建议取规程正本复核** |
| R2 | 宁夏回族自治区住建厅《分户验收(竣工阶段)的内容、项目、标准、频率及方法》 https://jst.nx.gov.cn/ztzl/gczlaqjd/gczlaqjg/202509/P020250928403039584785.pdf ⚠️PDF 为 OFD 转换流,**未能解析,数未取到** |
| R3 | 上海市住建委《上海市住宅工程质量分户验收办法》沪住建规范〔2018〕5 号 http://jsjtw.sh.gov.cn/zjw/static/capture/b58433be2e3543d2/d19f516f17120bfc901c7479b8b20d8f.pdf ⚠️未核 |
| R4 | **ANSI/NCSL Z540-1** TUR ≥ 4:1 要求。原文引用见 Keysight 技术概览 https://www.keysight.com/us/en/assets/7018-03019/technical-overviews/5990-8293.pdf;10:1 与 4:1 规则的沿革见 ASQ https://asqasktheexperts.org/2012/05/04/using-the-10-1-ratio-rule-and-the-4-1-ratio-rule/;NCSLI Z540.3 https://ncsli.org/page/z5401 |
| R5 | GB 50210-2018《建筑装饰装修工程质量验收标准》 http://www.jianbiaoku.com/webarbs/book/202/2051977.shtml ⚠️**具体允许偏差表未取到**(需正本) |

### 9.4 有方法但非同行评审 [独立-弱] / 行业惯例 [未知]

| # | 来源 | 注意 |
|---|---|---|
| W1 | J.S. Held — *A Comparison of Mobile Phone LiDAR Capture and Established Ground-Based 3D Scanning Methodologies* https://www.jsheld.com/insights/articles/a-comparison-of-mobile-phone-lidar-capture-and-established-ground-based-3d-scanning-methodologies — **50% 扫描需缩放修正,系数 97.72%–104.60%** |
| W2 | it-jim — *RoomPlan is Awful and it's Great!* https://www.it-jim.com/blog/roomplan-framework-by-apple/ — 6.45 m 实测 vs 6.821 m;**未写设备与方法** |
| W3 | Aerial Estimation 博客 — 屋面测量容差 1–3% https://www.aerialestimation.com/blog/roof-measurement-tolerances-how-much-error-is-too-much-for-an-insurance-claim/ — 🔴**自认是「行业惯例」,无标准机构/承保方背书,且作者卖测量报告** |
| W4 | 搬家/家具配送净空指南(1–2 inch 总净空;卸门再加 2–3.5 inch)https://www.gotlcmovingandstorage.com/how-to-fit-furniture-through-a-door/ · https://furnitureacademy.com/how-to-measure-doorway-for-furniture-deliveries/ |
| W5 | 百叶测量指南(记录到 1/8″、原样提交不自行扣减)https://www.architecturelab.net/how-to-measure-for-blinds-inside-mount-depth-deductions |
| W6 | Amazon 卖家论坛(尺寸不符是主要退货原因,**平台未发布容差**)https://sellercentral.amazon.com/seller-forums/discussions/t/ca22eab2-3fbe-4826-ab22-74a842fac674 |
| W7 | FBA 分档阈值第三方汇总(Small Standard 厚度上限 0.75″)https://amzbase.com/guides/fba-size-tiers/ — **非 Amazon 官方页** |
| W8 | 中文装修行业量房经验帖 https://zhuanlan.zhihu.com/p/56945723 · https://www.zhihu.com/question/303919599 — **[未知-经验帖]** |

### 9.5 我明确否掉、请勿引用的来源

| 来源 | 流传的数 | 否掉理由 |
|---|---|---|
| devicetests.com/how-accurate-is-iphone-measure | 「2%–20%」 | 逐页读过:无对象、无参考仪器、无次数、无机型 |
| marketingscoop.com | 「平均 2.5%」 | 内容农场,无方法 |
| 某检索摘要 | 「Canvas/RealityScan/Scaniverse 亚毫米」 | 量级不可能,判为检索幻觉 |


### 9.6 标准原文(由 §3、§4 引用)[独立-标准原文]

| # | 来源 |
|---|---|
| T1 | **USIBD Document C120 Guide v2.0 (2016)** — LOA 表 p.8、Measured vs Represented p.9–10 https://cdn.ymaws.com/www.nysapls.org/resource/resmgr/2019_conference/handouts/hale-g_bim_loa_guide_c120_v2.pdf |
| T2 | **USIBD Document C220 Spec v2.0** — LOA 规格表单 https://cdn.ymaws.com/www.nysapls.org/resource/resmgr/2019_conference/handouts/hale-g_bim_loa_spec_c220_v2..pdf |
| T3 | USIBD LOA 官方页(现行 v3.1, 2025)https://usibd.org/level-of-accuracy/ · 版本说明 https://lidarmag.com/2025/02/09/usibd-a-new-chapter-for-2025/ |
| T4 | **BIMForum LOD Specification 2024 Part I** https://bimforum.org/wp-content/uploads/2024/11/LOD-Spec-2024-Part-I-official-English.pdf — **阴性结论:LOD 不是容差规范** |
| T5 | **RICS《Measured surveys of land, buildings and utilities》3rd edition (2024-04)** §2.2–2.3 https://www.rics.org/content/dam/ricsglobal/documents/standards/measured_surveys_of_land_buildings_and_utilities_3rd_edition_rics.pdf |
| T6 | **ANSI Z765-2021** https://www.mlsnow.com/pdf/ANSIsqft.pdf · 2020 草案(含背景)https://www.homeinnovation.com/documents/national_standards/ansi_z765/ANSI%20Z765%20-%20DRAFT%2020200207%20-%20no%20cover%20art.pdf · Fannie Mae 采纳 https://singlefamily.fanniemae.com/media/30266/display |
| T7 | **ISO 7976-1:1989** https://www.iso.org/standard/14965.html · 预览 https://cdn.standards.iteh.ai/samples/14965/fa45a93fc33e484baadcc4035a37b130/ISO-7976-1-1989.pdf |
| T8 | **ISO 7976-2:1989** https://www.iso.org/standard/14966.html |
| T9 | **ISO 4463-1:1989**(permitted deviations 在这本)https://www.iso.org/standard/10356.html · 预览 https://cdn.standards.iteh.ai/samples/10356/3052306ccda243e186f75ba9d896f783/ISO-4463-1-1989.pdf ⚠️**具体数表在付费正文,本次未取到** |
| T10 | **ISO 17123-9:2018**(地面激光扫描仪)https://www.iso.org/standard/68382.html · ISO 17123 系列 https://www.iso.org/standard/42215.html |
| T11 | **ANSI/AWI 0620-2024** Finish Carpentry & Installation §3.4 https://awinet.org/standards/finish-carpentry-installation/requirements/3-4-aesthetic-3/ |
| T12 | 石膏板/轻钢龙骨容差(含「1/8″ in 10′ 并不在 ASTM C840/GA-216/GA-214 里」的澄清)https://www.wconline.com/articles/94271-gypsum-panel-finish-tolerances · https://www.woodworks.org/resources/construction-tolerances-for-light-wood-frame-projects/ |
| T13 | **NKBA Kitchen Planning Guidelines**(阴性:只管净空,不管容差)https://media.nkba.org/uploads/2022/05/Kitchen-Planning-Guidelines.pdf |
| T14 | **VDI/VDE 2634 Blatt 2** https://www.dinmedia.de/en/technical-rule/vdi-vde-2634-blatt-2/51778339 · 与 ISO 10360-13 的关系 https://www.sciencedirect.com/science/article/abs/pii/S0141635924000795 |

### 9.7 摄影测量精度(由 §3 引用)

| # | 来源 |
|---|---|
| P1 | Luhmann T. *3D imaging: how to achieve highest accuracy.* **SPIE Proc. 8085 (2011)**, doi:10.1117/12.892070 https://spie.org/Publications/Proceedings/Paper/10.1117/12.892070 |
| P2 | Luhmann T. *Close range photogrammetry for industrial applications.* **ISPRS J. Photogramm. (2010)** https://www.sciencedirect.com/science/article/abs/pii/S0924271610000584 |
| P3 | *Methodology to Evaluate the Performance of Portable Photogrammetry for Large-Volume Metrology.* **Metrology 2(3):20 (2022)** https://doi.org/10.3390/metrology2030020 |
| P4 | Agisoft Metashape 功能页 https://www.agisoft.com/features/professional-edition/ · 编码标靶与标定尺 https://agisoft.freshdesk.com/support/solutions/articles/31000148855-coded-targets-and-scale-bars · 控制 vs 检查的方法学 https://agisoft.freshdesk.com/support/solutions/articles/31000162602-creating-scale-bars-in-the-project-without-coded-targets |
| P5 | RealityCapture 控制点与 Ground Test https://rshelp.capturingreality.com/en-US/tools/controlpoints.htm — **无标称精度数字** |
| P6 | Cultural Heritage Imaging 标定尺规格 https://culturalheritageimaging.org/What_We_Offer/Gear/Scale_Bars/ScaleBars_UG_v3.pdf |
| P7 | 台面数字模板设备 LT-2D3D https://www.laserproductsus.com/lt-2d3d/ · Proliner 评测 https://slabwise.com/reviews/proliner-review · 数字 vs 物理模板 https://slabwise.com/guides/what-is-the-difference-between-physical-and-digital-countertop-templating · MIA 口径转述 https://countertopauthority.com/countertop-templating/ |
