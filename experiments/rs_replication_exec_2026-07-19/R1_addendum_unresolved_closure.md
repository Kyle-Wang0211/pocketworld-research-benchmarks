# R1 增补:剩余 UNRESOLVED 联网闭环(2026-07-18 执行)

编排语境:关掉 R1 里遗留的 UNRESOLVED/SUPPORTED 级条目。证据分级沿用 R1:
**CONFIRMED**(官方一手文档/可复核原文)> **SUPPORTED**(第三方/用户观察,可交叉)> **INFERRED**(推论)> **UNRESOLVED**(查不到,不硬凑)。

---

## ① RC 2.x(现名 RealityScan 桌面版)对齐默认参数面板 → **CONFIRMED(升级)**

**决定性证据(新渠道,非 R1 用过的 alignsettings 帮助页)**:官方 RS Help 的
**"Keys and Values" CLI 键值表**(https://rshelp.capturingreality.com/en-US/tutorials/setkeyvaluetable.htm)
逐键列出默认值,逐字抄录:

| 面板项 | CLI key | 类型 | **官方默认** |
|---|---|---|---|
| Max features per mpx | `sfmMaxFeaturesPerMpx` | int | **10000** |
| Max features per image | `sfmMaxFeaturesPerImage` | int | **40000** |
| Max feature reprojection error | `sfmMaxFeatureReprojectionError` | float | **2.0** (px) |
| Preselector features | `sfmPreselectorFeatures` | int | **10000** |
| Detector sensitivity | `sfmDetectorSensitivity` | 枚举 Low/Medium/High/Ultra | **Medium** |

R1 的五个数值(40k / 10k / 10k / Medium / 2px)**全部与官方键值表逐字一致**,由 SUPPORTED 升 CONFIRMED。

交叉佐证(独立渠道):
- Epic 官方论坛用户帖(forums.unrealengine.com t/708825)引用 "the Align default settings of 10k Max features/mpx and 40k Max features/img" —— SUPPORTED,与表一致。
- Sketchfab 用户合成测试(ssh4/b014299)描述其设置:"max features per image 40000, detector sensitivity Medium, preselector features 10000" —— SUPPORTED,与表一致。
- 官方 alignsettings 帮助页本身**不写默认值**只写建议("reprojection error 最多设 3px";"preselector 设为检测特征的 1/4–1/2")—— 这解释了 R1 为何只能到 SUPPORTED 级:默认值藏在 CLI 键值表里,不在面板帮助页。

⚠️ 不一致点(如实记录):Azad Balabanian 的 Medium 老文(RC 1.x 时代)称 max features 默认 20,000、preselector 默认 10,000。判读:20k 是 **RC 1.x 旧默认或作者笔误**,现行 RS Help 键值表(2.x)明确 40000;preselector 10k 两代一致。**采信 2.x 官方表**。

对我方复刻的含义:预算锚 = 每图特征上限 40k、每 mpx 10k(12MP≈物理上被 40k/图截住)、匹配预选 10k、检测灵敏度中档、对齐内部重投影闸 2px(与既有"≤3px 裁剪从不无中生有"记忆同向,2px 是默认、3px 是官方建议上限)。

---

## ② RS mobile 家具底下留洞的直接证据 → **SUPPORTED(部分闭环)+ UNRESOLVED(室内场景截图级)**

**已闭环(SUPPORTED,一手用户评测)**:Engineering.com《A First Look at RealityScan on Android》实测椅子:
- "the seat post was missing: the angle of view, the seat obscured the view of the post" —— **被遮挡的座椅立柱直接缺失**。遮挡=洞,与我方 07-19 方向记忆("被遮挡地板留洞=正确几何")直接同构。
- ⚠️【二轮修正】"RS 不发明看不见的几何"这句**在 mesh 层不成立**:同一篇 engineering.com 评测逐字 —— 应用 "**added several flat areas** to the chair's back and one of the armrests",且成品 "missing an arm and part of the back—it looked as if the chair had been blown up"。判读:**点云层诚实留洞成立;mesh/成品层 RS 存在补面/编造平面行为**(官方另有手动 [Close Holes 工具](https://rshelp.capturingreality.com/en-US/tools/closeholes.htm),"removes surface-bound holes—those completely enclosed by mesh geometry")。我方"正确覆盖"尺子应对齐**点云层**语义。
- 同文:地板与椅轮粘连,"没法删掉地板而不削掉椅轮" —— 地板点真实存在于可见区域(不是全场景补面)。
- ⚠️ 局限声明:该评测是**物体模式+云端处理**的早期 RS,非最新室内大场景模式;且缺失的是椅子部件不是"椅下地板"。

**旁证(CONFIRMED,官方设计意图)**:RS mobile 官方 Review Scan 文档的 quality 渲染模式 "color scale from red to green, where greener shades mean higher quality (good coverage)",红=欠覆盖,官方给的解法是**回去补拍**("go back to image capturing and take more images"),不是算法补洞。若 RS 会无中生有填洞,这个 UX 就不成立 —— 强 INFERRED:家具底下拍不到 ⇒ 点云该处就是洞,显示为红/空。

**仍 UNRESOLVED**:未找到可核实的"室内房间级扫描、椅下/床下地板明确是洞"的用户截图/视频逐帧描述。Reddit 对爬虫封锁(搜索 API 明确拒绝 reddit.com 域),YouTube 逐帧内容无法文本检索核实。**不硬凑**。如需钉死,建议用户侧动作:真机装 RS mobile 扫一间房 30 秒即可自证(成本最低的一手证据)。

---

## ③ RS mobile 拍摄中 → Review Scan → Process 两态细节 → **CONFIRMED(大部分)**

官方文档(dev.epicgames.com/documentation/realityscan-mobile,经镜像通道抓取原文)钉死的时序:

1. **触发时机(CONFIRMED)**:Step by Step Guide — "images will be analyzed **after you take 20 images**",分析**自动触发**,无需按钮。即:前 20 张期间用户**看不到点云**,只有 AR 引导。
2. **点云何时可见(CONFIRMED)**:点云 "shows up in the camera view **after the initial analysis** in the quality render mode" —— **边拍边看成立,但有 ≥20 张的冷启动延迟**;首次分析后,拍摄继续时点云就叠加在取景器上(quality 配色)。
3. **Camera View 细节(CONFIRMED)**:点云可见性开关仅在 **AR Guidance 模式**下可用且**前提是 images have been analyzed**;Camera Control 模式不显示点云。
4. **Review Scan 阶段(CONFIRMED)**:"Next step" 进入;可在 color / quality 两种渲染间切换、脱离 AR 自由环视;"this step can help you find parts of the scan that can be improved so you can still **go back to image capturing and take more images**" —— 两态可来回。另可在点云上划定 reconstruction region("limits the area where the model will be reconstructed **before processing**")。
5. **Process 阶段(CONFIRMED)**:"Process Project" 重建+贴图,**云端处理后自动下载回设备**(与既有记忆"RS 拍摄期=云端增量 SfM"一致);处理期间要求留在 app 内。
6. **点会不会被重算(SUPPORTED)**:官方 1.7 版新闻 — 可对已存项目 "re-process any saved project with just a tap",补图后**整体重处理**;结合"补拍后回 Review"的流程,判读为**增量分析(拍摄期)+ 全量重处理(Process/re-process)**双轨。拍摄期新图是否触发对旧点的重定位/删除,文档未写 —— 该子项维持 **UNRESOLVED**(RS 内部红线,不猜)。

对我方复刻的含义:RS 的"预览"不是逐帧实时,是 **20 张冷启动 + 之后滚动可见**;两态(拍摄叠加视图 / Review 自由视图)共享同一份分析产物;裁剪(reconstruction region)发生在 Review、Process 之前 —— 与我方"流式 local-BA 云 + 可选区、全局精化延后"的架构逐点对得上。

---

## 二轮独立核证(2026-07-18,另一执行线补做)

**① CLI 键值表第三次独立复核(curl 原始 HTML,与上表逐字一致):**
`sfmMaxFeaturesPerMpx int 10000` / `sfmMaxFeaturesPerImage int 40000` / `sfmMaxFeatureReprojectionError float 2.0` / `sfmPreselectorFeatures int 10000` / `sfmDetectorSensitivity Low|Medium|High|Ultra 默认列=Medium`。CONFIRMED 维持。

**① 新增独立渠道(默认值旁证,与官方表全部一致):**
- [Puget Systems RS 硬件页](https://www.pugetsystems.com/solutions/photogrammetry-workstations/realityscan/hardware-recommendations/):"**For the default setting of 40K features per image**, you can expect the following boundaries…"(同句亦见 realitycapture-training.com FAQ)。
- 日文 RS 实操教程 [note.com/pgrs_k](https://note.com/pgrs_k/n/nabae4fe7b008):reprojection error "これは**初期設定の 2** のままでOKです"(保持初始设置 2 即可)。
- [Optimising Alignment 论坛帖](https://forums.unrealengine.com/t/optimising-alignment/708867):"148K Max features per image (**default 40K**) … (**default 10K**)";"'Preselector features' set at **default 10k**"。
- [Azad Balabanian Medium 教程](https://wizardofaz.medium.com/reality-capture-alignment-tips-fixes-d49371ee6643):"Preselector presets: 20,000 (**default 10,000**)";其 "Max Features per image (default 20,000)" 为 RC 1.x 旧默认,已在上文⚠️处理。
- 噪声提示:Sketchfab 转储里另有 "Max Reprojection error: 0.01" 字段,是导出元数据的另一单位/字段,与面板 2px 默认不矛盾,勿混用。

**③ Step by Step Guide 全文经 Wayback 存档独立取到(快照 `20260712030225`,即现行版文档),与镜像通道内容一致。补充逐字:**
- "The processes of uploading and analyzing are **interleaved**, with uploading occurring first, followed by initial analysis, then uploading again, and so on."(增量分析节奏)
- "The image limit is **300**." "auto-capture is enabled"(默认自动拍)。
- "Once the images have been analyzed and you're satisfied with the point cloud, tap 'Next' to define the reconstruction region … before processing the project."
- 用户观察佐证([Falkingham 2023-11](https://peterfalkingham.com/2023/11/24/realityscan-photogrammetry-on-android/)):"it shows previous photos in Augmented Reality around the object, showing that it's **aligning cameras as it goes**";"When you've got a bunch of photos, it will create a sparse 3D point cloud"。

**② 新增用户观察(SUPPORTED):** Falkingham 同文:"You can colour the model by quality, and unsurprisingly **the areas underneath where I didn't get many photos, are the worst quality**" —— 质量热图直接把"底下/拍不到"标红,与"欠覆盖→红/洞、解法=补拍"的官方 UX 语义互证。房间级"椅下床下是洞"的截图/视频逐帧证据二轮仍未检索到(Reddit 定向搜索零命中),**UNRESOLVED 维持**。

## 渠道与方法记录
- 官方:rshelp.capturingreality.com(alignsettings、setkeyvaluetable)、dev.epicgames.com RS mobile 文档(直连超时,经 r.jina.ai 镜像抓原文)、realityscan.com 1.7 新闻。
- 第三方:forums.unrealengine.com、engineering.com、wizardofaz.medium.com、sketchfab 模型描述。
- 失败通道(如实):reddit.com 被爬虫协议封锁;fabbaloo.com、journalismcourses PDF 403;dev.epicgames.com 直连 ETIMEDOUT ×3。
- 防幻觉:setkeyvaluetable 表做了二次逐字复核抓取(两次结果一致);二轮另线第三次 curl 复核仍一致。
- 二轮新增通道:Wayback(step-by-step 全文,快照 20260712030225;review-scan 页无存档)、pugetsystems.com、note.com(日文教程)、peterfalkingham.com;web.archive.org 需走 curl(WebFetch 封锁)。

## 结论一览
| 条目 | R1 前状态 | 现状态 |
|---|---|---|
| ① 五个对齐默认值 | SUPPORTED | **CONFIRMED**(官方键值表逐字) |
| ② 家具遮挡→缺失不补 | UNRESOLVED | **SUPPORTED**(engineering.com 实测)+室内截图级仍 UNRESOLVED |
| ③ 20 张自动分析/点云冷启动 | 部分已知 | **CONFIRMED** |
| ③ Review↔拍摄可往返、区域裁剪在 Process 前 | UNRESOLVED | **CONFIRMED** |
| ③ 拍摄期旧点是否被重算 | UNRESOLVED | **UNRESOLVED**(维持,内部机制不猜) |
