# TRAILS_rs_evidence — RS/RC 对镜子与高反光的官方指引 + 社区一手证据(E2-C·联网)

- 日期:2026-07-18(检索执行日;任务目录名 2026-07-19)
- 方法:纯联网检索(WebSearch + 官方文档/论文原文 fetch),无本地实验。每条结论标注证据级别:
  - **[A] 一手官方**(Epic/CR 官方文档原文)
  - **[B] 一手论文/一手实拍**(peer-reviewed 或作者本人实拍记录)
  - **[C] 二手/社区转述**(搜索摘要转述、未取到原帖全文)
  - **[D] 负证据**(检索过但未找到 → "无人报告"级结论,非"不存在"证明)

---

## ① 官方指引:RC/RS 文档对镜面/玻璃/高光怎么说

### 1.1 RealityScan Mobile 官方文档(Epic)[A→C]
来源:[Photogrammetry Objects and Backgrounds](https://dev.epicgames.com/documentation/en-us/realityscan-mobile/Photogrammetry-Objects-and-Backgrounds)(fetch 超时,内容经搜索摘要转述,降级 C):
- 光滑/反光表面"may not provide enough unique points to be identified";玻璃物体"may not be reconstructed at all"。
- 官方建议:**scanning spray(哑光喷剂)+ 添加彩色元素**。即官方预期的镜面失败形态是"**不出点/出不来**",不是"出一堆拖尾点"。

### 1.2 RealityScan(桌面,原 RealityCapture)Mask 文档 [A]
来源:[Mask Images - RealityScan Help](https://rshelp.capturingreality.com/en-US/tools/mask.htm)(fetch 原文):
- "Masks allow you to exclude specific areas of images from processing" … 用于 "improve reconstruction accuracy and consistency by removing unwanted image data"。
- 官方点名建议 mask 的对象:"**windows, water, sky, shadows, vegetation, or image noise**"。
- **注意:官方 mask 列表未逐字点名 mirror**(windows/water 同属镜面反射类,语义覆盖但非逐字)。
- 机制:mask 黑区在 alignment 与 reconstruction 中**整体剔除**,结果是该处**留洞**,不是留伪影。

### 1.3 RealityScan Alignment Settings 文档 [A]
来源:[Alignment Settings - RealityScan Help](https://rshelp.capturingreality.com/en-US/appbasics/alignsettings.htm)(fetch 原文):
- **Max feature reprojection error**:"We recommend you to set it maximum to **3px** and keep the errors at most in this extent."(官方建议上限 3px;页面未标注出厂默认值。)
- **Detector sensitivity**:Ultra 档 "may also include less reliable points caused by image noise";Low 档 "more selective and ignores weaker features, which can reduce noise"。另有社区教程称高 ISO 噪图应用 Medium 档 [C]。即 RS 官方自认**灵敏度是"多点↔噪点"的显式取舍旋钮**——与我们记忆锚"RS 弱纹理出点=Ultra 激进检测(官方自认含噪)"一致。

### 1.4 社区支持口径 [C]
来源:[RealityCapture Support 社区帖(interior alignment)](https://support.capturingreality.com/hc/en-us/community/posts/360000096131-Workflow-Process-Interior-Image-Alignment-)(原帖已迁移 Epic Dev Community,fetch 只见跳转页;引文来自搜索摘要,降级 C):
- "You definitely need to **mask the mirror** — that's the final straw to entirely confuse RC."
- 室内场景通病:"Everything is glossy/reflective. Lots of repeating patterns." → mesh 出现整块 misalignment("statistically correct but in reality is not")。
- 即社区共识的镜子病理是 **alignment 层的整体混淆/错位**(镜像视图被当真视图匹配),不是逐点拖尾。

---

## ② 社区一手:含镜房间实拍 — 镜中世界会出现吗?拖尾有报告吗?

### 2.1 镜中世界(mirror world)会出现 — 有一手学术实拍证据 [B]
来源:[Whelan et al., "Reconstructing Scenes with Mirror and Glass Surfaces", SIGGRAPH 2018](https://www.thomaswhelan.ie/Whelan18siggraph.pdf)(PDF 原文已读,p.1-2):
- "Planar reflective surfaces such as glass and mirrors are notoriously hard to reconstruct … When treated naively, they **introduce duplicate scene structures, effectively destroying the reconstruction** altogether."
- "The mirror is therefore essentially 'invisible'. **The mirrored scene, however, will still be reconstructed** using standard vision techniques."
- Fig.2:ScanNet 真实浴室扫描,"**reflected scene parts reconstructed behind mirrors**",且 "This mirrored geometry **overlaps with real geometry located behind the mirror** and interferes with its reconstruction."
- 结论:**镜中世界=真实、被反复观测到的伪影形态**(镜后出现一套翻转的假房间)。注意该论文用的是主动深度传感器(KinectFusion 系),但引言明确说 "pose a significant problem for **any** reconstruction system"。photogrammetry 侧的对应形态见 2.2。

### 2.2 photogrammetry(RC/RS)侧的镜子失败形态 [C]
综合官方文档 + 社区帖:三种被报告的形态,按频率:
1. **不出点/留洞**(玻璃/镜面无稳定特征,或被 mask)— 官方文档预期形态;
2. **alignment 整体混淆**(镜像内容当真实纹理匹配 → 相机错位、mesh 整块错)— 社区帖 "final straw to entirely confuse RC";
3. **镜后镜像几何**(视差一致的镜中场景被当成镜后真实场景三角化)— 与 [B] 同机制,photogrammetry 下镜中特征在多视间**有自洽视差**(虚像=真实场景的镜像,几何上等价于镜后存在一个真房间),所以能通过多视一致性检验。

### 2.3 长拖尾(沿视线 smear)在 RS 输出里有没有被观察到?[D]
- 多轮定向检索("streaks/smear along camera ray"、"RS mirror trail"、reddit/r/photogrammetry、Sketchfab、支持论坛)**未找到任何 RS/RC 用户报告"沿视线的长拖尾"伪影**。被报告的失败形态只有上面三种(洞/错位/镜像几何)。
- 这是负证据(检索覆盖有限,原帖多已迁移),但与机制分析(③)自洽:**拖尾这种伪影形态在 RS 的稀疏 tie-point 管线里构造性难以产生**。
- 学术侧确认 smear/scatter 属于**逐视稠密深度(per-view depth / plane-sweep)在无纹理或反光区的深度歧义**产物(参见 [MVS 不确定性分析 arXiv:2309.09379](https://arxiv.org/pdf/2309.09379)),不是稀疏三角化+BA 的典型产物。

---

## ③ 机制线索(公开可证):什么公开机制能构造性压拖尾

拖尾(沿视线 smear)的生成条件 = **单点深度沿视线方向不确定**且**该不确定点仍被交付**。RS 管线里三道公开可证的闸各自砍掉一个条件:

| 机制 | 公开出处 | 为什么压拖尾 |
|---|---|---|
| **交付点=多视匹配 tie point,非逐视深度** | RS 帮助文档 alignment 体系(tie points/reprojection error 是唯一点质量度量);RS mobile 拍摄期=云端增量 SfM(记忆锚,与官方"AR guidance + color-coded point cloud"口径一致) | 每个点必须在 ≥2 视图独立检出同一特征并互匹配才存在。反光面上的"特征"随视点漂移(高光滑移),跨视匹配天然失败 → **点根本不出生**,而非出生成拖尾 |
| **reprojection error 裁剪(官方建议 ≤3px)** | [Alignment Settings](https://rshelp.capturingreality.com/en-US/appbasics/alignsettings.htm):"set it maximum to 3px" | 低视差/深度歧义点(拖尾的原料)重投影残差大,被 BA 后阈值裁剪掉。沿视线的自由度被 reprojection 残差直接定价 |
| **Detector sensitivity 档位(默认非 Ultra)** | 同上文档:Ultra 自认 "less reliable points caused by image noise" | 反光面上的伪特征(高光、噪点)在默认灵敏度下多数不过检测阈 → 上游就少产歧义点 |
| **(辅)mask/剔除工作流** | [Mask Images](https://rshelp.capturingreality.com/en-US/tools/mask.htm) | 官方推荐把 windows/water 类镜面区整块剔除 → 宁可留洞不留假点 |

**一句话机制结论**:RS 不出拖尾不是因为它"解决了反光",而是因为它的预览/稀疏交付路径**从不无中生有**——点必须赢得多视匹配 + 过 reprojection 闸才存在;反光区赢不了,于是表现为**洞或镜像几何,永远不是 smear**。smear 是"每像素必须给一个深度"的逐视稠密方法(plane-sweep/MVS)在歧义区硬答题的病。这与记忆锚(07-19 签决:"RS预览每点=真实匹配+BA+≤3px裁剪从不无中生有,压扁/拖尾是自创plane-sweep的病")完全对齐,且本次把 3px 建议、灵敏度取舍、mask 语义落到了官方文档级出处。

---

## ④ 两个记忆锚的对齐裁决(不矛盾,分属两个维度)

| 记忆锚 | 指的维度 | 本次证据裁决 |
|---|---|---|
| "RS 对镜面本质无解"(07-12 弱纹理/反光定案) | **召回维度**:能否在反光面上出真点 | **成立 [A/C]**。官方自己说玻璃 "may not be reconstructed at all",解法是喷剂/贴点/mask——物理层规避,不是算法解。镜面上出的"点"若有,多是反射鬼点(镜像几何,见②) |
| 用户观察"RS 完全没拖尾" | **精度/伪影形态维度**:交付的点是否沿视线 smear | **成立 [A+D]**。机制上三道闸构造性压死拖尾(③);社区检索零拖尾报告(D 级负证据佐证) |

**证据级结论**:两锚**正交不矛盾**。RS 在镜面区的行为=「**宁缺毋滥**」:出不了真点(无解=召回失败),但也绝不交付沿视线的歧义点(无拖尾=伪影纪律)。其代价形态是**洞**和(未 mask 时)**镜像世界/整体错位**。对我们的含义:复刻 RS 的预览观感,靶心是复刻这套"点必须赢得存在权"的纪律(多视匹配+reprojection 裁剪),而不是去追镜面出点率。反光区红线维持:不为追点灌假点(07-12 签决不变)。

---

## 来源清单(检索日 2026-07-18)
1. [A] https://rshelp.capturingreality.com/en-US/appbasics/alignsettings.htm — 3px 建议、detector sensitivity 语义
2. [A] https://rshelp.capturingreality.com/en-US/tools/mask.htm — mask 对象与语义
3. [C] https://dev.epicgames.com/documentation/en-us/realityscan-mobile/Photogrammetry-Objects-and-Backgrounds — RS mobile 反光指引(fetch 超时,摘要转述)
4. [B] https://www.thomaswhelan.ie/Whelan18siggraph.pdf — Whelan et al. SIGGRAPH 2018,镜像世界一手实拍(ScanNet 浴室)
5. [C] https://support.capturingreality.com/hc/en-us/community/posts/360000096131 — "mask the mirror / entirely confuse RC"(已迁移,摘要转述)
6. [C] https://wizardofaz.medium.com/reality-capture-alignment-tips-fixes-d49371ee6643 — RC alignment 实战(经核实原文未谈镜面,仅作 alignment 失败形态旁证)
7. [B] https://arxiv.org/pdf/2309.09379 — MVS 稠密匹配不确定性(smear 归属稠密深度歧义)
8. [D] 负检索:reddit/r/photogrammetry、Sketchfab、X/Twitter 定向查"RS trail/smear/streak along ray"零命中

## 红线与免责
- **RS mobile 内部实现=UNRESOLVED 红线不变**:③ 中"RS mobile 拍摄期=云端增量 SfM + tie-point 预览"是记忆锚推断+官方外部口径拼接,非逆向一手;所有机制结论只锚定到**桌面版官方文档可证部分**(3px/灵敏度/mask)。
- 2px vs 3px:任务提示词写"2px 裁剪",官方文档原文是"**建议上限 3px**";未找到 2px 的官方出处,以 3px 为准。
- C 级引文(1.1/1.4)如需升 A/B,需以浏览器访问 Epic Dev Community 迁移后原帖(本环境 fetch 被跳转页挡住)。
