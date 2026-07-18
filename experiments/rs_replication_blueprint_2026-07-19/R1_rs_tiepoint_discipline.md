# R1 · RS/RC tie-point 发布纪律与遮挡处可见行为(联网深挖)

日期:2026-07-18(为 2026-07-19 复刻蓝图供料)
范围:桌面 RealityCapture(2025-06 起更名 RealityScan 2.x,官方帮助 rshelp.capturingreality.com,旧 rchelp 已 301 到 rshelp)+ RealityScan Mobile 1.7/1.8 的**可见行为**。
🔴红线重申:RS mobile 内部机制 = UNRESOLVED。本文所有 mobile 条目只描述官方文档/发布说明写明的可见行为,绝不声称其内部算法。
证据分级:[VERIFIED]=官方文档/官方人员原话,一手抓取;[SUPPORTED]=多个独立二手源一致(社区高质量教程/论坛/搜索索引中的官方页摘录);[INFERENCE]=由已证事实合理推断,标明推理链;[UNRESOLVED]=查不到/不可证。
注:本次调研避开与既有 M1-M16(components/merge/priors/≤3px 裁剪/uncertainty percentile 70%/quality 着色/misalignment 只染色不删)重复,只补缺口;与 M 条目相符处做交叉确认标注。

---

## TL;DR(对蓝图的五个回答)

1. **出生纪律**:桌面 RC 一个 tie point 活到发布 = 检测(sensitivity+双上限)→ 预选(Preselector 子集)→ 匹配 → "两图及以上"三角化 → 对齐求解(位姿+内参逐图解出;final BA 在 draft 模式里是显式开关,反证标准对齐含 BA)→ Max feature reprojection error 封顶(推荐≤3px,默认 2px)。**没有查到 2-view 之上的最小 track 长度出生门**;track length 只在展示层做滑杆过滤。
2. **遮挡处 = 留洞**:相机看不到的地方不出点、不补面,是 RC 及整个 photogrammetry 领域的一致行为;RC 甚至显式检查"相机与云之间有无遮挡物",被遮挡的部分**不建**。"椅子下留洞=正确几何"与 RS/RC 行为完全一致。
3. **增量行为**:桌面 RC 的再对齐以 component 为单位(合并/扩展/重匹配是三个显式开关),不做静默的逐点手术;mobile 可见行为 = 预览点云随拍摄增长,修正靠"re-process 整体重跑",无任何文档提到逐点删除/移动。
4. **质量展示层**:uncertainty(默认 percentile 70)/quality(红→绿)/misalignment(蓝对红错)全部是**display-only 重着色,不过滤不删点**;唯一的"少看点"手段是展示层 track-length 滑杆。mobile 预览同范式:同一片点云在 color/quality 两种 render mode 间切换。
5. **默认参数**:见 §5 表(含版本漂移与置信标注)。

---

## ①(核心)RC 对齐期 tie point 的完整出生纪律

### 1.1 流水线各关卡

| 关卡 | 事实 | 证据级 | 来源 |
|---|---|---|---|
| 检测 | Detector sensitivity 控制特征点在视角/光照变化下的稳定性评估;Ultra 在弱纹理也出点但含噪声点,Low 更挑剔 | [VERIFIED] | rshelp alignsettings.htm |
| 检测上限 | Max features per mpx 与 Max features per image 双上限封顶检测量 | [VERIFIED] | rshelp alignsettings.htm |
| 预选 | Preselector features = "从检测到的特征中用于对齐的数量",官方建议设为检测量的 1/4–1/2 → **检测出的特征只有一个子集进入匹配/对齐** | [VERIFIED] | rshelp alignsettings.htm |
| 匹配→tie point 定义 | tie point = "a relation between images which says which point in **two or more images** corresponds to the same physical location"(官方定义,亦即最小 view 数=2) | [VERIFIED] | rshelp controlpoints.htm / quickstart_2.htm |
| 对齐=检测+匹配+建稀疏云 | "Image alignment or registration is a process of image feature detection and matching common tie points to create a sparse point cloud, during which the camera positions, orientations, and internal camera parameters are calculated for every image" | [VERIFIED] | rshelp quickstart_2.htm |
| 重投影封顶 | Max feature reprojection error = "internal precision level used during alignment",官方建议"set it maximum to 3px and keep the errors at most in this extent"(与 M 条目 ≤3px 裁剪互证) | [VERIFIED] | rshelp alignsettings.htm |
| 重投影默认 | 默认 2px(UI 默认,社区多处报告;官方页未见明文默认值) | [SUPPORTED] | 社区论坛/搜索索引 |
| 发布产物带账本 | 组件报告字段:componentMaximalError / componentMedianError / componentMeanError(px)、componentPointCount("number of registered points")、componentAverageTrackLength("the **average number of images for each observed 3D point**")、componentTotalProjection | [VERIFIED] | rshelp reports_fav_components.htm |

### 1.2 有没有 min views / min track length 出生门?

- 最小 view 数 = **2**,来自 tie point 官方定义("two or more images")。[VERIFIED]
- **2 之上的最小 track 长度出生门:官方文档通篇查无此设置**(alignsettings 全清单里没有)。track length 仅出现在两处:发布后的组件统计(AverageTrackLength),与 inspection 的**展示层**滑杆("applicable to points that are displayed w.r.t. the chosen Track length … Use the slider to restrict the points")。→ 结论:RC 发布 2-view 点,不设更高出生门;想少看 2-view 点是**显示过滤**不是数据删除。[VERIFIED(文档全清单核对后的"未见");出生门不存在这一否定命题本身标 SUPPORTED]

### 1.3 BA 是必经的吗?有没有点绕过 BA 发布?

- 标准对齐:对齐即"为每张图解算位姿+朝向+内参"并产出稀疏云,组件报告随发布公布 max/median/mean 重投影误差 —— 发布云天然是优化解的产物。官方标准对齐页没有单独把 "bundle adjustment" 一词写出来。[VERIFIED(引文)+ SUPPORTED(据此判"标准路径无绕过")]
- **反证最强的一条**:Draft(快速草稿)模式设置里有显式开关 "Final model optimization — When set to Yes, a final bundle adjustment is performed to optimize camera registration"。→ RC 把"跳过最终 BA"做成了一个**只存在于 draft 降质路径的、显式标注拿质量换速度的开关**;标准对齐没有这样的开关。[VERIFIED] rshelp draftalign.htm / alignsettings.htm(Draft settings 小节)
- 结论:**标准对齐路径查无任何"绕过 BA 发布"的机制;唯一低于 BA 纪律的发布路径是显式的 Draft 预览,且 final BA 仍可开**。[SUPPORTED]
- mobile 端是否同纪律:[UNRESOLVED](内部机制红线)。

### 1.4 对我们蓝图的含义(INFERENCE,单独隔离)

- 我们"预览=对齐 tie-point 云、每点=真实匹配+三角化+BA+重投影裁剪"的方向与桌面 RC 的发布纪律逐关对得上;RC 连"降质快路"都要显式标 draft 并保留 final-BA 开关 —— 支持我们"≤30s 预览"若走轻量 BA,也应像 draft 一样是**显式降质档 + 正式段补全量 BA**,而非静默省略。
- RC 靠 Preselector 把"检测量"与"进入对齐量"解耦(1/4–1/2)省算力,这是一个我们端上可直接抄的免费杠杆(与质量门九门兼容性需另行验证)。

---

## ② 家具下/遮挡处:RS/RC 稀疏云长什么样

| 事实 | 证据级 | 来源 |
|---|---|---|
| RC 显式遮挡检查:"RC checks if there is 'something' between the cameras and the dense part of the sparse cloud, and if there is, **it won't get built**"(用户借此把支撑架从模型中排除) | [SUPPORTED](资深用户长期教程一手观察,非官方文档) | dinosaurpalaeo.wordpress.com 教程13 |
| 室内扫描"沙发背后、餐桌下面、柜顶"是公认的洞区:"gaps usually appearing in spots that weren't captured from enough angles … the space behind a big sofa … or underneath a dining room table";"If the camera can't see an area well, it can't build it" | [SUPPORTED] | ai-stager.com 室内扫描指南 |
| 业余扫描"椅子和桌子的底面是彻底被遗忘的区域" | [SUPPORTED] | Steam 社区 VR 扫描指南 |
| Meshroom issue #755:椅子未被覆盖 → 网格里椅子整个缺失、地板上留洞(跨软件同律) | [SUPPORTED] | github.com/alicevision/meshroom/issues/755 |
| 学术侧:室内点云"occlusions and clutter produce significant holes … 无额外信息无法区分真空与被遮挡" | [SUPPORTED] | MDPI Appl.Sci. 8(9):1529 |
| RealityScan mobile 用户实测椅子:"parts are completely missing"(覆盖不足即缺件,不脑补) | [SUPPORTED] | App Store 评论/评测汇总 |
| RS/RC 对反光镜面同样无解、不造假点(与既往弱纹理/反光辨伪定案互证) | [SUPPORTED] | 既有 dossier + 本轮评测汇总 |

**结论:"被遮挡地板留洞 = 正确几何"是 RS/RC 与全行业一致的可见行为,且 RC 有主动的"看不见就不建"机制。** 没有任何一个来源显示 RS/RC 会在遮挡处填充/外推表面。用户④指令(unseen≠surface,plane-sweep 只补"可见+验证"的地板)与业界纪律完全一致。
未找到"椅子底下稀疏云特写"的可核验官方截图 → 该视觉细节级别的证据:[UNRESOLVED](但上表多源行为证据已足够支撑蓝图判断)。

---

## ③ 预览期/再对齐的增量行为:点会被修正/移动/删除吗

### 桌面 RC(机制可证)

- 再按 Align Images:应用"apply fixes from the corrected component",实践中把多 component 收敛成更少 component("just click 'Align images' again. This will lead to fewer (ideally, one) component(s)")。[VERIFIED(官方 components.htm 引文)+ SUPPORTED(dinosaurpalaeo 实操)]
- 三个显式开关控制增量语义,无静默行为:
  - Merge components only=Yes:"**no new images are added to existing components**, the application merges only existing components" → 只做组件级拼接;[SUPPORTED](官方帮助+论坛答复)
  - Force component rematch=Yes:"realigns images and cameras to find better connections, using existing camera poses to search for new matches" → 显式要求才做重匹配重解;[VERIFIED] alignsettings.htm
  - CLI `update`:"Update all components and models by a **rigid transformation** to fit actual constraints and control points" → 约束变化只做刚体变换,不重解、不动点间相对结构。[VERIFIED] commandline_1.htm
- 组件合并三策略("Merge using overlaps"/"Use component features"/"Use all image features")说明"重算多少"永远是用户显式选择的档位。[VERIFIED] components.htm
- **结论:桌面 RC 的"修正"以 component 为单位、由显式开关触发(重解=re-align/rematch;拼接=merge;约束=刚体 update),查无任何"逐点静默删除/移动"机制。**

### RS Mobile(只述可见行为,内部=红线)

- 拍摄期:AR Guidance "uses augmented reality to project a **live quality point cloud** over your subject and display real-time photo positions" —— 预览点云实时增长并叠在实物上。[VERIFIED] 官方 1.8 发布说明/realityscan.com/mobile
- 分析期:"Analyzing images calculates camera positions and detects common features from which the point cloud will be created","the point cloud shows up in the camera view **after the initial analysis** in the quality render mode"。[VERIFIED] dev.epicgames.com RealityScan Mobile Step-by-Step Guide(经搜索索引摘录核对;直连多次超时)
- 修正路径 = 整体重跑:"Now you can **re-process** any saved project with just a tap. **Add more images** or redefine the reconstruction region directly on the point cloud to refine your results." → 官方提供的唯一改进机制是加图后再处理,产出新结果。[VERIFIED] realityscan.com 1.7 发布新闻
- 处理位置:模型"generated online"(云端),与既有 dossier "RS 拍摄期=云端增量 SfM"一致。[SUPPORTED]
- 拍摄中单点是否被移动/删除:任何官方文档、发布说明、评测都**没有**描述过逐点修正行为;唯一文档化的更新粒度是"initial analysis 后出云"与"re-process 重出"。→ 内部是否全局重解:[UNRESOLVED]🔴(不许猜);可见行为层面"修正=批量重跑而非点级手术":[SUPPORTED]。

### 蓝图含义(INFERENCE)

预览云允许"只增不改,修正靠段级/全局重解"——这与我们流式 local-BA 云 + finalize 全局 BA 的两段结构同构;不需要为预览实现点级在线修正。

---

## ④ 质量展示层:uncertainty percentile × quality 着色如何组合

| 机制 | 行为 | 过滤还是全量? | 证据级 |
|---|---|---|---|
| Uncertainty(inspection,Relative 法) | "Reference uncertainty region percentile … **The default value is 70**"=70% 的点视为 stable/正确,以此定色标锚;深蓝=更精确、红=更不确定;Color palette radius 为色域倍乘;Absolute 法用场景单位(0.01=1cm) | **全量重着色**:"Points are colored, not hidden or deleted"(与 M 条目互证) | [VERIFIED] rshelp inspection.htm |
| Low-quality 阈值 | "Estimated reference uncertainty (blue) multiplied by this number gives the Low-quality points' threshold (red)"——红端阈值是蓝端锚的倍数,动态算 | 只定义色标端点 | [VERIFIED] 同上 |
| Track length 滑杆 | uncertainty 工具"applicable to points that are displayed w.r.t. the chosen Track length … Use the slider to **restrict the points**" | **展示层过滤**(唯一"少看点"的机制),数据不动 | [VERIFIED] 同上 |
| Quality analysis | tie point 质量"primarily indicates the **camera coverage** for each tie point",色标 green(好)→red(差);可烘到 mesh 顶点/贴图 | display-only,"assessment and visualization rather than automatic filtering" | [VERIFIED] rshelp qualityanalysis.htm |
| Misalignment(advanced) | "Blue colored points represent the correctly aligned points, while red points … are the ones RealityScan calculated as misaligned";相机连通图以蓝→红表边强度 | "identifies problematic alignments visually **without modifying source data**"(与 M16 互证) | [VERIFIED] rshelp inspection.htm |
| RS 2.0 新增 | "RealityScan now shows you where your scan may be incomplete. Using **visual heatmaps**, you can pinpoint areas that need more data before moving to the meshing stage" | 热图=提示补拍,不改数据 | [VERIFIED] realityscan.com 2.0 发布文 |
| Mobile 预览 | Render mode 按钮在 **color / quality** 两模式间切换同一片点云;"Quality is shown using a color scale from red to green, where greener shades mean higher quality",用于"notice parts where the image coverage could be improved" | 可见行为=同一片云整体换色,无文档提到隐藏子集;内部[UNRESOLVED] | [VERIFIED] dev.epicgames RealityScan Mobile 文档(Review Scan/Step-by-Step,索引摘录核对) |

**回答"用户看到的是滤过的还是全量重着色":桌面与 mobile 可见行为一致——全量点云 + 整体重着色;percentile 70 只是定色标锚点的统计量,不是过滤阈值;唯一的过滤是用户手动的展示层 track-length 滑杆。** 这与 M 条目"quality 着色/misalignment 只染色不删"完全互证,且 mobile 的 color/quality 双模式与我们 compare.html 真彩肉眼验收 + 覆盖热图双轨的思路同构。

---

## ⑤ 桌面 RC 对齐默认参数清单(含版本漂移)

⚠️版本注意:RealityCapture 1.x → RealityScan 2.x(2025-06)且 2.0 官宣"New default settings improve image alignment, especially on surfaces with minimal features"[VERIFIED]——**默认值确实跨版本动过**,复刻请以下表"当前值"并自验 UI。

| 参数 | 当前默认 | 旧版/社区值 | 官方推荐 | 证据级 |
|---|---|---|---|---|
| Max features per image | 40,000 | 1.x 时代默认 20,000(社区教程) | — | 当前值[SUPPORTED](官方页索引摘录);旧值[SUPPORTED] |
| Max features per mpx | 10,000 | — | 更多特征→更慢但更少碎组件 | [SUPPORTED](官方页索引摘录) |
| Preselector features | 10,000 | 同(两源一致) | "1/4–1/2 of the detected features" | 默认[SUPPORTED];推荐[VERIFIED] |
| Detector sensitivity | Medium | — | 官方论坛 admin:"the MEDIUM setting is the best case scenario";高档"detects even 'unreliable' points … reliability and precision can be 'worse'"(与既有"RS Ultra 自认含噪点"定案互证);社区:ISO100 好片可 High/Ultra | 默认=Medium[SUPPORTED];机理引文[VERIFIED] |
| Max feature reprojection error | 2 px | — | "set it maximum to **3px**"(与 M 的 ≤3px 一致) | 默认[SUPPORTED];推荐[VERIFIED] |
| Image overlap | Medium | — | 邻图 >60% 重叠 | 默认[SUPPORTED];>60%[VERIFIED] |
| Image downscale factor | 1(精度最佳推荐值) | 社区教程称默认 3(疑与 draft/深度图降采样混淆,存疑不采) | 1 for best precision | 推荐[VERIFIED];"默认3"[UNRESOLVED-矛盾] |
| Force component rematch | No(推断:文档以"When set to Yes…"描述) | 社区常年推荐 Yes | — | 默认[INFERENCE] |
| Merge components only | No(同上推理) | — | 组件碎裂时二/三次对齐再开 | 默认[INFERENCE] |
| Feature detection quality | 未获默认(High 提升精度、更耗时) | — | — | [UNRESOLVED] |
| Draft: Final model optimization | 开关存在,Yes=final BA | — | — | 存在性[VERIFIED];默认[UNRESOLVED] |
| Uncertainty percentile(inspection) | **70** | — | — | [VERIFIED] |

未拿到官方全表逐项数值的原因:rshelp 页面默认值多在 UI 截图/表格里,文本抓取器多次未吐出数值;journalismcourses 的 RC How-To PDF 403;dev.epicgames 知识库页反复超时。→ **复刻前用一台 Mac 装 RealityScan 2.x 抄 UI 默认面板做最终校准**(30 分钟即可把上表全部升级为 VERIFIED),列为蓝图待办 R1-TODO。

---

## 残余 UNRESOLVED 清单(红线内不猜)

1. RS mobile 拍摄期内部:是否增量 SfM、是否重解历史帧、tie point 门限——全部 UNRESOLVED(仅能复刻可见行为)。
2. RC 标准对齐是否存在文档未载的内部点级淘汰(除 reprojection 封顶外)——无证据,不声称。
3. "默认 2px/Medium/40k"未在官方页面文本一手看到数值(见上),留 R1-TODO 实机校准。
4. 椅子底/床底稀疏云的官方视觉样例——未找到可核验截图;行为级证据已足。

## 来源索引

官方:rshelp.capturingreality.com(alignsettings/quickstart_2/quickstart_3/controlpoints/inspection/qualityanalysis/components/mergecomponents/commandline_1/draftalign/reports_fav_components).htm;dev.epicgames.com RealityScan Mobile 文档(Step-by-Step Guide、Review Scan、Camera View、1.7/1.8 Release Notes);realityscan.com(/mobile、2.0 发布文、mobile 1.7 新闻);forums.unrealengine.com(detector-sensitivity #707058、merge-components-only #712035)。
社区/二手:wizardofaz.medium.com 对齐教程×2;dinosaurpalaeo.wordpress.com 教程13;80.lv/cgchannel/digitalproduction 1.8 报道;ai-stager.com;Steam 社区指南;github.com/alicevision/meshroom#755;MDPI Appl.Sci.8(9):1529;datumate.com。
