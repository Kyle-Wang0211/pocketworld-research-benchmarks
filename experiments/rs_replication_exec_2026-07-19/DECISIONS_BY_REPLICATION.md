# DECISIONS_BY_REPLICATION — Q1–Q8 按"RS 可证做法"正式裁决记录(可审计)

- 生成:2026-07-19,rs_replication_exec_2026-07-19 执行线裁决员。
- 裁决依据文件(同 worktree,`experiments/rs_replication_blueprint_2026-07-19/`):
  - `RS_REPLICATION_BLUEPRINT.md`(签决单 Q1–Q8,§终表)
  - `R1_rs_tiepoint_discipline.md`(RS/RC tie-point 纪律,联网一手证据)
  - `R2_channel_rs_compliance.md`(22 通道 × RS 纪律对照)
  - `R3_time_budget_30s.md`(≤30s 时间账)
  - `R1_addendum_unresolved_closure.md`(本执行线目录,R1 遗留 UNRESOLVED 联网闭环;引用时标 [R1-ADD])
- 授权基础(记录在案):用户 07-19 授权原话(经编排者转述入执行指令):**"质量无损=唯一硬门:候选必须四把尺子(点数/厚度带/正确覆盖/墙钟)对账并出同 gauge 真彩对比给用户看——但按用户 07-19 授权,执行不阻塞等签决,裁决权=RS 可证做法。"** 即:凡 RS/RC 有 VERIFIED/SUPPORTED 级可证做法的签决项,按 RS 做法裁决并直接执行;RS 证据不足者标 **UNRESOLVED-暂缓**,不许硬裁、不许猜 RS mobile 内部(🔴红线)。
- 编号对账说明(审计必读):编排者执行指令中的已定四项使用了与蓝图签决单不同的临时编号("Q3=plane-sweep 退出预览"、"Q5=显式两态")。本记录**以蓝图签决单 Q1–Q8 编号为准**,并把编排者四项裁决映射到正确条目:编排者 Q1→蓝图 Q1;编排者"Q3 plane-sweep 退出预览"→蓝图 **Q2 案 C**;编排者"Q5 显式两态"→蓝图 **Q4**;编排者 Q7→蓝图 Q7。映射后无冲突、无遗漏。
- 证据分级沿用:[VERIFIED] / [SUPPORTED] / [INFERENCE] / [UNRESOLVED] / [REJECTED]。
- 效力边界:本记录是执行线裁决(裁决权=RS 可证做法),**不豁免验收铁律**——每项候选仍须四把尺子对账 + compare.html 同 gauge 同生产位姿真彩(禁 Sim3)呈用户肉眼;质量或总耗时任一退化 → 该轮不进产品(U5 门)。落地改生产=另开任务,不在本执行线。

---

## Q1 · S1 选案:2-view 生命周期(#6 造 × #13 杀 同批修)

- **问题**(蓝图 §S1.3):案 A"纪律补票"(18k temporal-detail 点过 structure-only refit + 三把尺子)vs 案 B"整体降级 AMBIGUOUS 不发布"。
- **RS 的可证做法**:
  - RS-2"发布点必须活过 BA":RC 标准对齐路径查无任何"绕过 BA 发布"机制;唯一低于 BA 纪律的路径是显式 Draft 档且 final BA 仍可开([VERIFIED] R1 §1.3,draft "Final model optimization" 开关反证)。
  - RS-3"重投影裁剪 ≤3px 量级":官方原话 "set it maximum to 3px"([VERIFIED] R1 §1.1,rshelp alignsettings.htm;默认 2px 已由官方 CLI 键值表 `sfmMaxFeatureReprojectionError=2.0` 升 **CONFIRMED** [R1-ADD §①])。
  - RC **发布 2-view 点**,最小 view 数=2("two or more images",[VERIFIED] R1 §1.2),2 之上无最小 track 长度出生门([SUPPORTED],文档全清单核对后的否定命题)。
  - RS-6"按几何证据裁决不按出身"([INFERENCE] R2 §0,RC 公开机制无 per-source 发布门)。
- **裁决:案 A**。即:`RestoreTemporalDetail` 后追加 structure-only refit(位姿全冻,只动新点)+ 重投影 ≤3px 裁剪 + θ 绝对下限(cap47 教训:无门 refit 救活鬼点,ghost 4.3%→5.5% [SUPPORTED]),幸存者发布。理由:RS 的可证行为是"2-view 点可以发布,但必须精化+裁剪后发布"——案 A 与之逐关同构;案 B(2-view 一律不发布)反而**超出** RS 纪律(RC 并无 2-view 禁发门),不是复刻是加严。
- **#13 随批(统一规则,同批落地)**:`filterFinalSpatialTwoViewPoints` 的"frame-gap>K + 恰 2 观测无条件硬删"废除(RS-6+RS-4 双违,[VERIFIED] `sfm_live_recon.dart:181–229/1304–1315`),替换为**同一条 2-view 生命周期规则**:同一把尺子(refit 残差/θ/held-out)只裁一次;强 support 远时真点必须活;处置从 DeletePoint3D 改为不发布/染色(复用 #16 ghost mask,→S4/Q7 关联)。不删观测,TVG 对全保留(R2 §4)。
- **对质量无损硬门的影响**:厚度原料(双墙/歧义壳,cap47 [SUPPORTED])直接减薄;点数下降幅度 [UNRESOLVED] 须四把尺子对账定价;案 A refit 墙钟"秒级"是 [INFERENCE],**必须实测,不许估时当承诺**(蓝图 rework 触发原文)。同 gauge 真彩并排 + 裁/降/救三向着色图必出。

## Q2 · S2 选案:plane-sweep 归位(R2#22)

- **问题**(蓝图 §S2.2):案 A 收窄"可见+多视验证"补点 vs 案 B 降级显示层 vs 案 C 退出预览归稠密段。
- **RS 的可证做法**:
  - RS-1:tie point = 真实 2D 特征跨帧匹配的三角化,无 prior 铺点、无中生有([VERIFIED] R1 §1,官方 tie-point 定义)。plane-sweep 点无逐点真实匹配血统,是 prior 外推 → 构造性违反([VERIFIED] R2 §3.3)。
  - RS-5:未观测留洞。RC 显式"相机与云之间有遮挡就不建"机制([SUPPORTED] R1 §2);椅底/沙发后留洞是全行业一致行为(多源 [SUPPORTED]);无任何来源显示 RS/RC 在遮挡处填充/外推表面。增补一手实测:engineering.com RS Android 评测——被座面遮挡的座椅立柱直接缺失("the seat post was missing"),RS 不发明看不见的几何([R1-ADD §②,SUPPORTED];官方 quality 红色欠覆盖的解法=回去补拍而非算法补洞,CONFIRMED 设计意图旁证)。
  - 用户 07-19 裁决③原语义:"预览保持稀疏、大方向复刻 RS 不盲目创新";椅子压扁已被用户肉眼否决([VERIFIED] cap50 13,488 版否决记录)。
- **裁决:案 C — plane-sweep 退出预览,归正式稠密段**(即编排者已定项"plane-sweep 退出预览";RS 构造性无此通道,预览=纯 tie-point 云)。案 A 附带出局理由:法医铁结论 [VERIFIED,晨报 §C] 5 张 L1 反证供给不足(分离积极限 0.51/AUC 0.810,杀 81–96% chairFP 必误删 37–59% 真地板),其判别力预检在当前证据密度下无通过前景;案 B(显示层)不采,因 RS mobile 预览可见行为只有 color/quality 双 render mode([VERIFIED] R1 §4),无"数据外观感补面层"的可证先例。
- **零回归注记(审计要点)**:plane-sweep **本就未在生产管线**(R2#22 = 候选通道,`experiments/floor_plane_sweep_densifier_2026-07-13` + U4 adapter,用户已否决 13,488 版)——本裁决=不收编该候选,生产交付 PLY 字节不变,**零回归、零墙钟代价**,≤30s 目标零负担。
- **共同底线保留**([VERIFIED] 交接书 §8.6):平面 prior 长期归宿 = U4"缩小弱纹理搜索区的先验",不是点生成器;稠密段(CasDiffMVS/TSDF)如何用它另案。
- **对质量无损硬门的影响**:交付=stock 基线,四把尺子恒等通过(SHA 级);代价是预览地板洞照旧——与 RS 同律([SUPPORTED] R1 §2),观感代价呈用户肉眼确认(s2_caseC 候选=基线本身,"洞的观感"照蓝图呈报)。

## Q3 · 上游全 MVS 每视深度 free-space 要不要投(重投资)

- **问题**:椅子压扁的"真解"是否投上游全 MVS free-space(核心签决,蓝图明示"勿在本蓝图内偷跑")。
- **RS 的可证做法**:**无**。这是我方管线内部的稠密段重投资取舍;RS mobile 内部机制=UNRESOLVED(🔴红线不许猜),桌面 RC 公开机制不含可迁移的"每视深度 free-space 供给"成本/收益证据;R2 §3.3 明确"上游重投资,属核心签决,本文不预判"。
- **裁决:UNRESOLVED-暂缓**。不硬裁。且 Q2=案 C 后紧迫性下降(预览层病根已构造性移除,free-space 只关系正式稠密段质量)。留待:独立定价 spike(成本/收益,[UNRESOLVED] 蓝图 §S2.3)完成后呈用户核心签决。
- **对质量无损硬门的影响**:暂缓=零改动,零影响。

## Q4 · 渐进交付 / preview-first(反转 07-11 "LOCAL 永不显示"签核)

- **问题**:感知等待 74s→~3–5s 的唯一单项达标选项(R3 §3-A),但直接反转 [FINALIZE-ZEROCOPY 2026-07-11] 产品签核([VERIFIED] `aether_sfm_c.h`)。
- **RS 的可证做法**:
  - RS 可见行为=preview-first:"live quality point cloud" 实时增长叠加实物、initial analysis 后即出云、精化后到([VERIFIED] R1 §3,官方 1.8 发布说明 / dev.epicgames Step-by-Step)。
  - RS-8"降质快路必须显式":RC 把"跳过 final BA"做成显式 Draft 档 + final BA 开关([VERIFIED] R1 §1.3)——降质档从不静默。
  - RS-7"修正=批量重解非点级手术"([VERIFIED/SUPPORTED] R1 §3):与我们"粗云→refined 整体换入"的两段结构同构。
  - 两态时序官方钉死([R1-ADD §③,CONFIRMED]):20 张自动分析冷启动→拍摄期点云滚动叠加(quality 配色)→Review Scan 自由环视(color/quality 双模式、可回拍、Process 前划 reconstruction region)→Process 整体重建;1.7 起可整体 re-process([SUPPORTED])。即 RS 可见行为=增量分析(拍摄期)+ 全量重处理双轨,与我方"流式 local-BA 预览 + 全局 BA refined 换入"逐点同构;拍摄期旧点是否被重算=内部机制,维持 UNRESOLVED 不据其裁决。
- **裁决:显式两态**(编排者已定项"Q5=显式两态"映射至此):preview 态(live local-BA 云+colorize,显式标注为未精化预览档,RS Draft 范式)→ refined 态(全量 BA 后静默换入,唯一交付身份)。**禁止静默降质**;refined 仍是唯一进"交付/分享/编辑落点"的云。
- **签核反转注记(审计要点)**:本裁决在"裁决权=RS 可证做法"授权下作出——RS 的 preview-first 是 [VERIFIED] 可见行为,且 RS-8 显式两态恰好化解 07-11 签核当年的病根("LOCAL 永不显示"防的是未精化云冒充成品;显式两态下它不再冒充)。但这是**产品签核反转**,呈报包(live 未精化云厚度历史账[全超带 SUPPORTED]、换入瞬间跳变观感 demo、退 App 后台 7.4× 降速账[refined 74s→~9min SUPPORTED]、选区/编辑粗↔精一致性方案)仍须按蓝图 S3 第 3 步完整出给用户肉眼确认后才装机。
- **对质量无损硬门的影响**:总算量不变、refined 云内容不变(感知层解法);硬门体现在换入观感与两态一致性,由呈报包+肉眼验收把守。

## Q5 · D:stage1 rounds 4→3(有损风险)

- **问题**:B(LAPACK)落地后 stage1 成短极点才有意义的 ≤15s 上限项。
- **RS 的可证做法**:**无**。RC 的 BA 轮次/收敛内部参数无任何公开文档([UNRESOLVED]);R1 §5 参数表不含轮次项。无 RS 证据可援引。
- **裁决:UNRESOLVED-暂缓**。且叠加三重前置未满足:①B 未落地(stage1 尚非短极点,R3 §3-D 原文);②stage1 每轮成本曲线无遥测([UNRESOLVED] R3 §6.4);③记忆锚:并行语境砍轮次=砍 enrich 免费窗、rounds=1 有撤销前科。属有损风险,即便日后重启也须九门+用户签决,不在"RS 可证做法"授权范围内。
- **对质量无损硬门的影响**:暂缓=零改动。防复活记录:不许拿砍轮次凑 30s(R2 §5 🔴)。

## Q6 · 改还债热闸/节奏参数(repay 加码超出闸内)

- **问题**:若闸内加码不够,是否改热闸阈值/还债节奏(R3 §3-C)。
- **RS 的可证做法**:**无**。RS mobile 拍摄期内部调度=UNRESOLVED 红线;RC 桌面无对应机制。我方独有约束:44 号相机冻结=热压 GPU 丢命令([VERIFIED] 定罪),47 号热闸已重议过一轮(thermal=2 清洁小额还,≥3 全拒)。
- **裁决:UNRESOLVED-暂缓(改闸部分)**;**闸内加码先行**(R3 第 1 步,免签):补多 cap"闸内可还上限"统计 + 交付 PLY SHA 对账(db-only 承诺:还与不还交付逐位一致,[VERIFIED] `aether_sfm_live_repay` 头注释)。统计出来若证明闸内不够,再携数据呈用户签决改闸。
- **对质量无损硬门的影响**:闸内加码=无损设计([VERIFIED] db-only 同一交付),SHA 一致 + 无相机冻结/背压回归是 accept 硬条件;它是 B(LAPACK)enrich 窗缩水的解毒剂(R3 §0-4 耦合陷阱),与硬门同向。

## Q7 · track-length 展示滑杆是否触碰"禁质量滑杆"红线

- **问题**(蓝图 §S4.1 ⚠️):RC 桌面 inspection 有 track-length 展示滑杆(唯一"少看点"手段,[VERIFIED] R1 §4);我方有"禁止用户可见质量滑杆/档位"签决红线。
- **RS 的可证做法(以 mobile 为准,因我们是 mobile 产品)**:RS **mobile** 可见行为**没有** track-length 滑杆——预览只有 color / quality 两个 render mode 切换同一片云([VERIFIED] R1 §4,dev.epicgames RealityScan Mobile 文档);滑杆只存在于桌面 RC inspection 工具。
- **裁决:不做 track-length 滑杆**(编排者已定项)。复刻对象是 RS mobile 可见行为,mobile 无滑杆 → 不引入;"禁用户可见质量滑杆"红线原样保住,连"是否算展示过滤"的解释争议都不必发生。S4 只做:真彩 / quality / uncertainty 着色模式切换(display-only,全量重着色不过滤,percentile 70 只是色标锚,[VERIFIED] R1 §4)+ ghost mask sidecar 收编为 misalignment 蓝红范式([VERIFIED] R2#16)。
- **对质量无损硬门的影响**:零——display-only 铁证:着色前后交付 PLY SHA 相同(蓝图 S4 accept 原文),数据全量不动。

## Q8 · env-OFF 通道生产臂状态核实后的开关归属

- **问题**:frag merge(#15)/ track upgrade(#12)/ grow-refit(#8)/ ghost mask(#16)源码默认 env OFF([VERIFIED] `FragMergeEnabled` 等,unset=bit-identical),与 cap45"碎片合并@4px ship 签决"记忆锚存在张力([UNRESOLVED] R2 §6.2)——生产臂实际 env 状态未核实,核实后开关归谁管。
- **RS 的可证做法**:不适用——这是我方装机配置**事实对账**问题,不是行为复刻问题;RS 证据体系对此无发言权。
- **裁决:UNRESOLVED-暂缓(裁决部分),核实先行(事实部分)**。作为 S1 前置(蓝图原定位):落地前必查装机配置(装机包 880feaee 起的实际 env / `AETHER_FRAG_MERGE` 等),对账 cap45 签决记录。核实结果三种走向预登记:①若生产臂 ON 与签决一致 → 归属维持既有签决,S1 候选生产时该臂状态照抄生产(U0 冻结输入原则);②若 OFF 与 cap45 签决矛盾 → 呈用户,属签决执行落空事故,不许在本执行线私自扳开关;③ghost mask 的归属已由 Q1/#13 fix + S4 决定升 U5 产品层,但**开关本身**仍待核实后随①/②走。
- **对质量无损硬门的影响**:核实=只读,零改动。未核实前 S1 候选 PLY 必须显式记录所用 env 全量(sidecar 账本,U1 语义),保证 baseline 与候选同臂同配置,否则四把尺子对账无效。

---

## 裁决汇总表

| Q | 条目 | 裁决 | 依据强度 | 状态 |
|---|---|---|---|---|
| Q1 | S1 选案 | **案 A**:refit(位姿冻)+ reproj≤3px + θ 底线,幸存者发布;#13 同批换证据判据(统一 2-view 规则) | RS-2/RS-3 [VERIFIED],RS-6 [INFERENCE] | 已裁决,执行 |
| Q2 | S2 选案 | **案 C**:plane-sweep 退出预览归稠密段(本就未在生产,零回归) | RS-1 [VERIFIED],RS-5 [SUPPORTED],07-19③用户裁决 | 已裁决,执行 |
| Q3 | 全 MVS free-space 重投资 | **UNRESOLVED-暂缓**(RS 无可证做法;核心签决留用户) | — | 暂缓 |
| Q4 | 渐进交付反转 07-11 签核 | **显式两态**(preview 显式降质档 → refined 静默换入;RS Draft 范式);呈报包出齐后肉眼确认才装机 | preview-first 可见行为 + RS-8 [VERIFIED] | 已裁决,呈报包待出 |
| Q5 | rounds 4→3 | **UNRESOLVED-暂缓**(RS 无证据;有损须九门签决;B 未落地) | — | 暂缓 |
| Q6 | 改还债热闸/节奏 | **UNRESOLVED-暂缓(改闸)**;闸内加码免签先行 + 多 cap 上限统计 | 闸内 db-only 无损 [VERIFIED] | 暂缓(改闸)/执行(闸内) |
| Q7 | track-length 滑杆 | **不做**(RS mobile 无此滑杆,只 color/quality 双模式;禁滑杆红线保住) | R1 §4 [VERIFIED] | 已裁决 |
| Q8 | env-OFF 生产臂归属 | **UNRESOLVED-暂缓(归属)**;装机 env 核实先行(S1 前置),矛盾即呈用户 | 配置事实问题,RS 不适用 | 暂缓(归属)/执行(核实) |

## 全程效力重申

1. 本记录的四项"已裁决"(Q1/Q2/Q4/Q7)裁决权来自用户 07-19 授权("执行不阻塞等签决,裁决权=RS 可证做法"),四项均锚定 [VERIFIED] 级 RS 证据;四项"暂缓"(Q3/Q5/Q6/Q8)均因 RS 证据不足或不适用,按指令标 UNRESOLVED-暂缓,未硬裁。
2. 任何裁决都不豁免:四把尺子(点数/厚度带 0.060–0.063/正确覆盖/墙钟热受控中位)对账 + compare.html?right=候选ply 同 gauge 同生产位姿真彩(禁 Sim3)四场景四视角呈用户肉眼;**质量或总耗时任一退化 → 该轮不进产品**。
3. RS mobile 内部机制 = 永久 UNRESOLVED 红线,本记录全文未据其裁决任何一项。
4. 产物仅落本研究 worktree;生产落地=签决后另开任务;本执行线不 commit(编排者统一提交)。
