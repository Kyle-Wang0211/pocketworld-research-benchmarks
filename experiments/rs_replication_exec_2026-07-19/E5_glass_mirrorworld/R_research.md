# E5-R·联网调研:RS 的 reconstruction region 与镜面的实践细节

- 执行日:2026-07-18(任务目录名 2026-07-19)
- 方法:纯 WebSearch/WebFetch(dev.epicgames 走 r.jina.ai 镜像;官方帮助页另用 curl 抓原始 HTML 逐字复核)+ 复读既有产物(TRAILS_rs_evidence/README.md、R1_addendum)。无本地重算。
- 证据分级(沿用 E2-C/R1 口径):
  - **[A] 一手官方**(Epic/CR 官方文档原文,curl/镜像取到逐字)
  - **[B] 一手实拍/评测**(作者本人实测记录或 peer-reviewed)
  - **[C] 二手转述**(搜索摘要转述、未取到原帖全文)
  - **[D] 负证据**(检索过未找到 → "无人报告",非"不存在"证明)
- 🔴 红线:RS mobile 内部实现 = UNRESOLVED,不猜。

---

## ① RS mobile 的 reconstruction region 默认行为

### 1.1 流程位置与强制性 [A]
官方 Review Scan 文档(dev.epicgames.com/documentation/realityscan-mobile/realityscan-review-scan,镜像取原文)逐字:
- "The reconstruction area **limits the area where the model will be reconstructed** before processing the project."
- 流程 = Review(color/quality 环视)→ Next → **Reconstruction Area 独立一步** → Next → Process。即画框是 Process 前的**固定流程节点**,不是可选深藏设置(与 R1 addendum ③-4 CONFIRMED 一致)。

### 1.2 存在"初始框"(auto 提议)[A]
同文档 Reconstruction Area Tools 表逐字:
- "**Reset area — Reset to the initial reconstruction area size.**"
- 有 "Reset to initial size" 按钮 ⇒ **app 必然自动提议了一个初始框**(否则无"初始尺寸"可 reset)。工具集 = 视点切换(Viewpoint options,固定 2D 视角)+ 框体 widget 改尺寸(cropping area)+ 点云旋转滑杆。
- **初始框怎么算(auto-fit 到主体?还是整云包围盒?)官方未写 → UNRESOLVED**。桌面版同名机制的口径可作旁证(见②):"set automatically after the alignment, its size depends on the size of the sparse point cloud",即桌面版初始框=按稀疏云尺寸,不是按"主体"语义。mobile 是否同源不猜。

### 1.3 用户不动它时 Process 会怎样 [A+B]
- [A] 语义上:框外一切不进重建。官方帮助(rshelp,Selection/Review 语境,搜索摘要与帮助页一致):"Everything outside the reconstruction region will not be used in the reconstruction and will thus not be in the final model."(此句为检索摘要转述帮助页语义,机制与②的桌面版原文一致,按 [A-] 采信。)
- [B] Fabbaloo 一手实测(hands-on part 1/2,镜像取原文)逐字:
  - "While you're scanning your subject, the app is **dutifully recording the table on which the object sits, and everything else in the vicinity**. By setting the bounding box you can limit the scan to a specific volume."(采集期照单全收,画框才裁)
  - part 2 配图说明:"showing **what happens when you forget to adjust the bottom of the bounding box**"(忘调框底 → 底部杂物入模)
  - "The 3D models do require a bit of cleanup, as **the bounding box of the scan tends to include a bit of the floor**, but that's easily done with a plane cut."
- **结论(合成)**:默认框≠紧贴主体;不动它 → 初始框内的一切(常含一圈地板/桌面)全部进重建,框外全部丢弃。物体模式的初始框倾向于"主体+一点周边";**房间级扫描不动框时初始框是否包住整云 → UNRESOLVED**(未找到房间级一手记录)。
- ⚠️ 局限:Fabbaloo 评测为早期 iOS 物体模式;新版行为见 1.4。

### 1.4 版本演进 [A/C]
- 1.7 官方新闻(realityscan.com,原文 fetch):"Add more images or **redefine the reconstruction region directly on the point cloud** to refine your results."(存档项目可重画框+re-process)
- 更早新版特性(搜索摘要转述 [C]):"easier to achieve precise control over the processing volume … quickly **switch between fixed 2D views** of your subject and **drag the boundary lines** into place."
- 1.8(2025-11,CG Channel 原文 fetch [B]):"**Object Mode automatically removes the background** as an object is scanned";另据 DP/搜索口径 [C]:Standard Mode = 同套控制但**不做背景移除**("suitable for scanning objects within their original environment")。即 RS mobile 已把"主体外=背景"做成**分割模型自动 mask**(物体级),但**房间/环境级扫描仍走 Standard(不自动删背景)**。

---

## ② 桌面 RC(现 RealityScan 桌面版)的 reconstruction region 语义

全部 [A],curl 抓 rshelp 原始 HTML 逐字:

### 2.1 自动性(quickstart_5_reconstructionRegion.htm)
- "**The reconstruction region is set automatically after the alignment, and its size depends on the size of the sparse point cloud.**"
- "It restricts the area where the model will be reconstructed … You can also **remove the reconstruction region to reconstruct the whole scene**."
- "it is recommended that it be set to **speed up the model computation**, as it will leave out unnecessary parts of the scene."

### 2.2 工具语义(tools/reconbox.htm)
- "If you want to reconstruct the whole scene, then **just skip this step**."(region=可选;无 region=全场景重建)
- "By doing this you will speed up a model computation, as **unimportant parts of the scene will not be considered at all**."(框外=完全不参与,硬裁剪非降权)
- 6 种设置方式逐字在册:**Set Region Automatically**("detect a reconstruction region automatically **based on the size of the point cloud**", ctrl+shift+U)/ Set Region on Grid(三击画框)/ **Set Region by Point Density**("based on the **density** of the sparse point cloud. The more dense parts will be preferred. **Works best with turntable datasets or those with minimal background detail**")/ Set Region from Clip Box / Set Region on Reconstruction / Set Region from Control Points;另有 Clear Region。
- 官方给的"密度取主体"方法自己声明只对转台/低背景细节适用 ⇒ **RC 官方没有任何"场景壳/主体语义"的自动裁剪**——自动只有两种:整云包围盒(size)或密度偏好(density,声明不适合复杂场景)。**"自动判断哪些是壳外该杀"在 RC 里不存在,裁剪语义永远是几何盒 + 人来摆。**

### 2.3 与官方默认参数的关系
- region 与 alignment 参数(40k/10k/2px/Medium,R1 addendum 已 CONFIRMED)正交:region 只作用于 mesh/重建阶段的空间裁剪,**不回溯删稀疏云的点**(稀疏云在 3Ds 视图仍整云显示,region 只框 mesh 计算范围)。

---

## ③ 社区实践:含镜/大窗房间,镜像世界最终怎么消失

### 3.1 既有定案复读(TRAILS_rs_evidence,E2-C)
- [A] 官方 mask 文档点名 "**windows, water, sky, shadows, vegetation, or image noise**" 该 mask;机制=**整体剔除→留洞**,不留伪影。
- [C] 社区帖:"You definitely need to **mask the mirror** — that's the final straw to entirely confuse RC."(镜子病理=alignment 层整体混淆)
- [B] Whelan SIGGRAPH 2018:镜像世界真实存在,"reflected scene parts reconstructed **behind mirrors**",且与镜后真实几何重叠互扰。

### 3.2 本轮新增:镜像世界的三条消亡路径(合成)
| 路径 | 阶段 | 出处/级别 | 语义 |
|---|---|---|---|
| **mask(拍摄图像层)** | alignment 前 | [A] mask.htm;[C] 社区"mask the mirror" | 镜/窗像素不进管线 → 该处**留洞**,镜像世界不出生 |
| **reconstruction region(空间层)** | mesh 前 | [A] reconbox.htm | 镜像几何在镜面/墙面**之后**(Whelan 机制),把 region 边界摆到墙面 → 镜后虚像整块落框外,"not considered at all" |
| **后期手删(mesh/点层)** | 重建后 | [A] Filter/Lasso 文档 + 支持库 3D Selections 文章 | Lasso 选中 + **Filter Selection**("filtering always creates a new model which does not contain the selected triangles");支持口径:"first need to set the RECONSTRUCTION REGION and then use the FILTERING tool" |
| (新,物体级)AI mask | alignment 前 | [B] RS 2.0 新闻:"Automatically remove backgrounds with a trained segmentation model";1.8 mobile Object Mode 同类 | 主体分割自动 mask 背景——**语义是"主体外"非"反光区"**,对房间级镜子不适用 |
- [C→无链接降级] 泛社区口径(检索摘要,无可核原帖):扫房间前**用布/胶带物理盖住镜子**、拉窗帘,属常见建议;**本轮未取到可核实原帖,不作依据**,仅记录为待核。
- [D] 未找到任何"RS/RC 自动识别并删除镜像世界"的功能或报告——**镜像世界的消失在 RS/RC 生态里 100% 靠人**(mask/摆框/手删/物理遮盖),引擎侧零自动裁决。这与 E2-A 两难直接呼应:**RC 官方也没敢做"壳外自动杀"**(会误杀门洞外真货架类真几何),它把裁决权整个交给用户的几何盒。

### 3.3 官方对玻璃的预期形态复核 [B]
Fabbaloo part 2 一手实拍(玻璃花瓶):"**the glass was not visible in the resulting 3D model**. This is not surprising … It would be possible to spray the vase with a temporary opaque scan spray."——透明玻璃=洞(与 E2-C ①"官方预期形态=不出点"一致);注意这与**平面玻璃倒影→镜像世界**(E3 观测:窗玻璃倒影 0/112 出生纪律免疫)是两种形态,不矛盾:强反射平面产镜像几何,透明/曲面玻璃产洞。

---

## ④ 预览显示层:RS 预览里"壳外远点"显示吗?有无淡化/裁剪?

- [A] 拍摄期叠加视图:1.8 口径 "AR Guidance mode which **displays a point cloud over the object being scanned** to show where more images are needed"(CG Channel 原文);官方 Review 文档只有 color/quality 两种渲染模式,quality=红绿覆盖热图。**两种模式的文档均无任何按距离淡化/按壳裁剪的描述。**
- [B] Fabbaloo:"the app is dutifully recording … **everything else in the vicinity**" + "forget to adjust the bounding box" 配图=框外杂物在预览/成品里可见——即**周边点在预览里如实显示**,靠用户画框才消失。
- [D] 定向检索"RS 预览淡化远点/裁剪窗外点/邻室点"零命中;无任何用户报告 RS 预览对远点做 display-only 隐藏。
- **结论:UNRESOLVED 偏否**。已有证据一致指向:RS 预览=整云如实渲染(color/quality),**没有壳外淡化/隐藏机制的任何痕迹**;"藏点"只发生在 (a) 点根本不出生(出生纪律)、(b) 用户画框裁剪、(c) 1.8 Object Mode 的主体分割 mask(物体级)。房间级预览是否有未文档化的显示裁剪 → 只能真机自证(R1 addendum ② 同款建议:装 RS 扫一间房 30 秒)。

---

## ⑤ 对我方的含义(E2-A 两难的 RS 答案)

1. **两难在 RS 生态同样无解、且官方选择不解**:门洞外真货架 vs 玻璃虚像同为"壳外",RC/RS 从未做自动壳外裁剪——自动只有整云包围盒/密度盒(且后者自认只适合转台)。**裁决权=用户的几何盒**。我方"预览=选区界面(用户框选重建区)"与 RS 的 Reconstruction Area 步骤**同构**,方向已对。
2. **可直接抄的交互细节**:初始框 auto 提议 + "Reset area" 兜底;固定 2D 视角 + 拖边界线;点云旋转滑杆;Take More Pictures 可回拍。我方选区界面缺哪个补哪个。
3. **镜像世界的正解=三层防线而非单点检测**:出生纪律(E3 已证三热区免疫)→ 用户框(镜后虚像天然落墙外,框摆到墙即灭)→ L2 渲染门/后期删兜底。**不做"自动判虚像"**——RC 都不做,且 E2-A 已证会误杀真几何。
4. **quality 热图**(红绿覆盖)是 RS 预览的第二渲染模式,与我方覆盖云语义同构,可作为选区界面的辅助显示层。
5. 物体级 AI 背景 mask(1.8/2.0)是主体分割,**不迁移到房间场景**,不构成"该做自动裁剪"的反证。

## 结论一览
| 问题 | 状态 |
|---|---|
| ① mobile 有初始框(auto 提议)+ Reset area | **CONFIRMED [A]**;初始框算法 **UNRESOLVED** |
| ① 不动框 → 框内全进(常含地板)、框外全丢 | **[A]语义 + [B]实拍**;房间级默认框范围 UNRESOLVED |
| ② 桌面版 region=对齐后按稀疏云尺寸自动;6 种手动;无"主体/壳"语义自动裁剪 | **CONFIRMED [A] 逐字** |
| ③ 镜像世界消亡=mask/摆框/手删/物理遮盖,零自动 | **[A]+[C]+[D] 合成** |
| ④ 预览对壳外远点淡化/隐藏 | **UNRESOLVED 偏否**([A]文档无痕迹+[B]如实显示+[D]零报告) |

## 来源清单(检索日 2026-07-18)
1. [A] https://rshelp.capturingreality.com/en-US/tools/reconbox.htm(curl 原始 HTML 逐字)
2. [A] https://rshelp.capturingreality.com/en-US/tutorials/quickstart_5_reconstructionRegion.htm(curl 原始 HTML 逐字)
3. [A] https://dev.epicgames.com/documentation/en-us/realityscan-mobile/realityscan-review-scan(r.jina.ai 镜像原文)
4. [B] https://www.fabbaloo.com/news/hands-on-with-realityscan-part-1 、…/part-2(r.jina.ai 镜像原文;直连 403)
5. [A] https://www.realityscan.com/en-US/news/realityscan-mobile-new-release-exciting-new-features(1.7,fetch 原文)
6. [B] https://www.cgchannel.com/2025/11/epic-games-releases-realityscan-mobile-1-8/(fetch 原文)
7. [B] https://www.realityscan.com/news/realityscan-20-new-release-brings-powerful-new-features-to-a-rebranded-realitycapture(fetch 原文,AI masking)
8. [A] https://rshelp.capturingreality.com/en-US/tools/filter.htm 、https://rshelp.capturingreality.com/en-US/appbasics/pointsselection.htm 、https://support.capturingreality.com/hc/en-us/articles/360013354759(Lasso/Filter Selection,检索摘要与帮助页一致)
9. 既有产物复读:TRAILS_rs_evidence/README.md(mask.htm、Whelan18、"mask the mirror" 社区帖)、R1_addendum_unresolved_closure.md(默认参数 CONFIRMED、Review↔拍摄两态)
10. [C/无链接] "盖镜子/拉窗帘"泛社区口径 — 检索返回无链接,不作依据
11. [D] 负检索:UE 论坛镜子照片测量帖(命中皆渲染话题非 photogrammetry);"RS 预览淡化远点"零命中;房间级默认框一手记录零命中

## 失败/降级通道(如实)
- medium.com(Azad interior part 2)fetch 成功但原文只列 mirror/glass 为 "challenging subjects" 无处置建议(用于排除,非依据)。
- fabbaloo.com 直连 403 → r.jina.ai 镜像成功。
- reddit 域继续被爬虫协议封锁(与 R1 一致)。
- WebSearch 返回的摘要文本一律与可取原文交叉后才定级;仅有摘要无原文的一律 ≤[C] 并标注。
