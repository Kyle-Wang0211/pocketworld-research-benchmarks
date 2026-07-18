# R2 · 本地对照 — 22 条生产出点通道 × RS 纪律逐条判(keep / demote / fix)

- 生成:2026-07-19(R2 子任务;调研+规格,**不改任何代码、不自批准、不跑管线**)。
- 铁律遵守:本文件是本子任务唯一落盘产物,仅写研究 worktree 本目录;未碰生产、未 reset/clean、未动他人 dirty、未 git commit(编排者统一提交)。
- 证据分级:**[VERIFIED]**=一手源码行号/已落盘实验数据;**[SUPPORTED]**=既有战役定案/记忆锚(有数据但非本次复核);**[INFERENCE]**=由上述推导的映射/预期;**[UNRESOLVED]**=未解决。
- 🔴 红线:**RS mobile 内部机制 = UNRESOLVED**。本文对照的"RS 纪律"只来自(a)RS mobile 可见行为、(b)桌面 RealityCapture 公开机制 M1–M16(此前调研 VERIFIED)。全文不声称 RS 内部算法。

---

## 0. RS 纪律基线(判据,来自桌面 RC 公开机制,VERIFIED;mobile 内部 UNRESOLVED)

发布到预览/交付云的每个点必须同时满足:

| 编号 | 纪律 | 出处强度 |
|---|---|---|
| RS-1 | **真实特征匹配起源**:点 = 真实 2D 特征跨帧匹配的三角化,从不无中生有(无 prior 铺点、无学习模型幻觉点) | [VERIFIED] 桌面 RC tie-point 语义 |
| RS-2 | **活过 BA**:发布位置是 BA 精化后的位置;从不发布"未精化/冻结位姿纯 DLT"点 | [VERIFIED] |
| RS-3 | **重投影裁剪**:BA 后按残差裁(≤3px 量级) | [VERIFIED] M-系(≤3px 裁剪) |
| RS-4 | **错位点染色不删**:misalignment/uncertainty 走着色(quality coloring、uncertainty percentile 70%),数据不动 | [VERIFIED] M-系(display-only) |
| RS-5 | **未观测 = 留洞**:unseen ≠ surface;不为"看起来该有面"补点 | [VERIFIED] 行为层(RS 预览洞是常态)+ 07-19 用户裁决① |
| RS-6 | **裁决按几何证据,不按出身**:culling 判据是残差/角度/不确定性,不是"哪条通道产的" | [INFERENCE] 由 M-系机制归纳(RC 公开机制中无 per-source 发布门) |

用户 07-19 四连指令(签决方向,作为硬约束):①各归其位(椅子观测出生在椅子、被遮挡地板留洞、plane-sweep 只补可见+验证);②拍完等待 ≤30s(现 finalize ~74s、stage1 全局 BA ~59s);③预览保持稀疏、复刻 RS 对齐 tie-point 云;④每视 CasDiffMVS ≈80s 判死不进预览(留正式稠密段)。

---

## 1. 22 条通道对账(与 13 通道桶的关系)

U3 治理规格(`../u3_merge_prototypes_2026-07-18/01_u3_channel_governance/README.md`)已形式化 **13 条**"原 SfM 来源"通道(#1–#13,精确行号锚,本文不重做)。R2 的 22 条 = 那 13 条 + 下列 9 条本次行号复核补齐的通道([VERIFIED] 均在生产源码/既有实验落盘;"22"的枚举口径是本文自建,[INFERENCE]):

| R2# | 补充通道 | 源锚 |
|---|---|---|
| 14 | live/global-refine 两段 BA(pose BA + structure-only refit) | `aether_sfm_c.cc` `aether_sfm_global_refine`(~5750–5831) |
| 15 | MergeFragmentTracks 碎片合并(env `AETHER_FRAG_MERGE`) | `aether_sfm_c.cc:2755–3040`,调用 4385 |
| 16 | MaybeWriteGhostMask 显示掩码 sidecar(env-gated) | `aether_sfm_c.cc:4389`(GHOST-MASK 2026-07-12) |
| 17 | COLMAP mapper 三角化 Create/Continue(Retriangulate;creation min_angle 2.0°) | `aether_sfm_c.cc:3548–3560` 注释 + 4305–4306/4320 |
| 18 | COLMAP mapper CompleteTracks(Complete,4px) | 同上(CompleteAndMergeTracks) |
| 19 | COLMAP mapper MergeTracks(Merge) | 同上 |
| 20 | COLMAP mapper FilterPoints + FilterFrames(BA 后过滤) | `aether_sfm_c.cc:4321` + stage2 `RefineReconstruction`(4373–4376) |
| 21 | finalize stage1/stage2 全局 BA(AdjustGlobalBundle / RefineReconstruction) | `aether_sfm_c.cc:4253–4376` |
| 22 | B plane-sweep 地板增密器(候选通道,用户已否决 cap50 13,488 版) | `experiments/floor_plane_sweep_densifier_2026-07-13` + U4 `11_planesweep_candidate_adapter` |

编号约定:R2#1–#13 与治理规格 #1–#13 一一对应;R2#14–#22 如上。

**边界(不计入 22,但须声明)**:①每视 CasDiffMVS 深度 → 07-19 ④ 已判死不进预览,归正式稠密段,不在本对照范围;②D detector-free 救援(LoFTR/ELoFTR)= 研究候选,非生产通道;③coverage 覆盖云 = 纯显示层策略(0 照片=0 点,与 SfM 解耦,SUPPORTED 既有定案),不发布交付点,天然合规,不占对照名额;④colorize 取色不产点。

---

## 2. 总判表(keep / demote / fix)

处置词义:**KEEP**=机制本身符合 RS 纪律,收编时仅换证据图表达;**FIX**=违反 RS 纪律,必须改语义;**DEMOTE**=不删机制但降级其权力(出生权/发布权收走);**GRAY**=灰色,按 A 类评据收编即合规。

| R2# | 通道 | 一句话现状 | RS 纪律判 | 处置 | U 映射 |
|---|---|---|---|---|---|
| 1 | live create(2 视新建) | 真匹配+三角化+2°/reproj 门,后续入窗内 BA | 合规(RS-1/2/3 全过) | **KEEP** | U3-B类 |
| 2 | live grow(加观测) | 门在"当前未精化点位"量 4px | 半合规(RS-1 过;判据用错点位,近 RS-6 瑕疵) | **KEEP+fix-lite** | U3-B类 |
| 3 | live merge(union refit) | disjoint-images + union refit 残差门 | 合规(且是"按证据定位"的正确雏形) | **KEEP** | U3-B类/U4 |
| 4 | live 窗内浮点清理 | BA 后 neg-depth/4px/2° 硬删 | 合规主体(RS-3);"硬删"与 RS-4 张力 | **KEEP+demote删权** | U3-C类 |
| 5 | finalize 全局浮点清理 | 同 #4 全局施加 | 同 #4 | **KEEP+demote删权** | U3-C类 |
| 6 | temporal-detail create | **BA 后灌 ~18k 永不精化 2 视点** | 🔴 **违反 RS-2**(从不活过 BA)+RS-6 | **FIX(两案见 §3.1)** | U3-B类+2视裁决 |
| 7 | temporal-detail grow | BA 后按"当前点位 3px"加观测,不再精化 | 违反 RS-2(轻度,寄生于 #6) | **FIX(随 #6)** | U3-B类 |
| 8 | td grow-refit(env OFF) | union refit 语义,默认关 | 机制合规;无 θ 底线会救活鬼点(cap47) | **KEEP OFF→升为默认聚合规则** | U3/U4 |
| 9 | enrich 空间补对 | 只写验证过的 TVG 对,不出点 | 合规(A 类评据;下游走 mapper+BA+裁剪) | **GRAY→KEEP** | U3-A类/U4预算 |
| 10 | rematch starved 补对 | 同 #9,为热降频帧补 K 拓扑 | 合规(A 类) | **GRAY→KEEP** | U3-A类 |
| 11 | repay capture-idle 补对 | 同 #9,热闸控速 | 合规(A 类) | **GRAY→KEEP** | U3-A类 |
| 12 | track upgrade(env OFF) | 给低视差点补第三视+union refit | 机制合规(专救 #6 的病人) | **KEEP OFF→并入 #8 统一规则** | U3-B类 |
| 13 | Dart spatial_two_view_filter | **按 frame-gap>K + 恰 2 观测硬删,不看几何** | 🔴 **违反 RS-6**(按出身删)+RS-4(删非染) | **FIX(见 §3.2)** | U3-C类+2视裁决 |
| 14 | global-refine 两段 BA | pose BA + structure-only refit | 合规(RS-2 的执行者) | **KEEP** | U3/U4 |
| 15 | 碎片合并(env) | all-union-obs reproj 门 + θ 严格变宽 + 守恒不变量 | 合规(纪律模范:每合并全证据验证) | **KEEP**(核实生产臂) | U4 融合 |
| 16 | ghost mask 显示 sidecar(env) | 疑鬼点打显示 flag,数据全量不动 | 合规(正是 RS-4"染色不删"同构) | **KEEP→升产品层** | U5 |
| 17 | mapper Create/Continue | 标准链:匹配→三角化→BA 轮→过滤;creation 2.0° | 合规(RS-1/2/3 教科书);低视差尾也生于此(cap47:25.9% 原生 2 视<3°) | **KEEP** | U3 参照链 |
| 18 | mapper Complete | 未三角化观测回补进 track(4px) | 合规 | **KEEP** | U3 |
| 19 | mapper Merge | track 归并(mapper 配方) | 合规 | **KEEP** | U3/U4 |
| 20 | mapper FilterPoints/Frames | BA 后按残差/角度过滤 | 合规(RS-3 执行者);删权同 #4 张力 | **KEEP+demote删权** | U3-C类 |
| 21 | stage1/2 全局 BA | ~59s,≤30s 目标的头号墙钟 | 合规(RS-2 执行者);问题是性能非纪律 | **KEEP(U4 提速)** | U4 |
| 22 | B plane-sweep 增密 | **从拟合平面 prior 铺点(无逐点真匹配)** | 🔴 **违反 RS-1(无中生有)+RS-5**;椅子压扁是其病 | **FIX/DEMOTE(三案见 §3.3)** | U2+U4 |

统计:KEEP(含 fix-lite/demote删权)16 条;GRAY→KEEP 3 条;🔴 FIX 3 条(#6 temporal-detail、#13 spatial_two_view_filter、#22 plane-sweep)——与任务预判完全一致。

---

## 3. 三条违反通道的深判(现状→判→fix→代价→U 映射)

### 3.1 R2#6 temporal-detail create(+寄生的 #7 grow)— 违反 RS-2

**现状** [VERIFIED,治理规格 #6 行号 2340–2371/2056]:finalize 在 stage-2 BA **之后**调 `RestoreTemporalDetail`,从时序 K 邻 TVG inlier 里以 2°/3px 纯 DLT 造 ~18k 2 视点,位姿/内参冻结,**建后永不精化、永不被三把尺子过滤**(worker 路径里它跑在 `RefineReconstruction` 之后,无任何后续 BA/filter,[VERIFIED] 4376–4382)。这正是交付云厚度(双墙/歧义壳)的主要原料(cap47 SUPPORTED)。

**RS 纪律判**:RS-2 铁律"发布点必须活过 BA"被构造性违反——不是个别漏网,是整条通道设计成 BA 后灌入。同时 RS-6:它免检的唯一理由是"我造的"(provenance 特权)。RS 桌面构造性无此病:tie-point 全部经 BA+裁剪后发布。

**Fix 两案(按任务要求给代价分析;不预判选哪案,留签决)**:

- **案 A:让它们过 BA + 裁剪(纪律补票)。** RestoreTemporalDetail 后追加一次 **structure-only refit(位姿冻结,只动新点)+ 三把尺子(neg-depth/reproj/θ)只对新点跑一遍**。生产已有同构代码:`aether_sfm_global_refine` 的 stage-2 structure-only 模式([VERIFIED] ~5800)。
  - 墙钟代价:structure-only、~18k 点、位姿全冻 → 秒级([INFERENCE],DENSE 结构-only 对 2 视点是近闭式;须真机实测,不许估时当承诺)。对 ≤30s 目标近中性。
  - 点数代价:refit 后 θ<2° 或 reproj>3px 的子集被裁 → 交付点数下降(幅度未测,[UNRESOLVED];cap47 提示低视差子集显著)。**质量收益:双墙/歧义壳原料直接减薄;且消灭 "#6 在 BA 后造 2° 点 / #5 用 2° θ 门删低视差点"的一造一删自相矛盾——同一把尺子只裁一次。**
  - 风险:refit 会把部分低视差点"救活"到门内(cap47:grow-refit 臂 ghost 4.3%→5.5% SUPPORTED)→ θ 绝对下限必须保留,不许无门 refit。
- **案 B:降级 AMBIGUOUS 不发布(各归其位)。** 这 ~18k 点整体进证据图为 `AMBIGUOUS`(带 `missing: independent_holdout` + 低视差 opposition 风险标记),不进交付 PLY;等 enrich/rematch/track-upgrade 类支持证据到位、arbiter 判 VERIFIED 才 BORN。
  - 墙钟代价:≈0(不加 BA);点数代价:交付立减 ~18k(观感冲击大);质量收益:最彻底——厚度原料清零且**零删除**(点没死,留在候选层,完全符合"各归其位":不是杀点,是不让未证明的点占用户可见身份)。
  - 风险:预览密度骤降,可能低于用户可接受观感;需四场景肉眼验收决定。
- 两案共同要求:**不删观测**。TVG 对/观测全保留(A 类证据资产),变的只是"出生权"。

**U 映射**:U1(先给这 18k 点上 provenance 账本量化)→ U3-B 类收编(SurfaceHypothesis+support,出生权归 arbiter)→ 与 #13 合并为同一条 2-view 生命周期规则(§4)。#7 grow 同法:接受判据从"当前点位 3px"换成"union refit 后残差"(U3)。

### 3.2 R2#13 Dart filterFinalSpatialTwoViewPoints — 违反 RS-6 + RS-4

**现状** [VERIFIED,治理规格 #13,`sfm_live_recon.dart:181–229/1304–1315`]:交付前无条件删"恰 2 观测且 frame-gap>temporalK"的点。判据是**出身(哪个匹配阶段产的、帧隔多远),不是这个点自己的几何证据**(θ_max、残差、held-out)。

**RS 纪律判**:双重违反——RS-6(按 provenance 删:一个远时但大视差、多帧 reproj 干净的 2 视点可能是真表面,被秒杀;近时低视差噪声点反而被 #6 制造保留)+ RS-4(处置手段是删,不是染色/降级)。RS 桌面对错位/低质点走 quality coloring + uncertainty percentile,不按来源清洗。

**Fix 方案**:删除判据换成证据判据,处置换成降级:
1. "time-far + 仅 2 视 + 无 held-out" → 记 **opposition/`missing: independent_holdout`**,arbiter 默认不予出生(留 AMBIGUOUS)——效果上多数今天被删的点仍不发布,但**理由变成几何证据**;
2. 若该点另有强 support(大 θ_max、干净 union 残差、held-out 确认)→ **必须活**(今天被误杀的 loop 真点被救回);
3. 处置不再是 DeletePoint3D,而是不发布/染色(与 #16 ghost mask 同一显示层机制可复用)。

**预期影响** [INFERENCE]:交付点数近中性偏正(误杀救回 ≳ 新增降级);质量:loop 闭合区表面完整性提升;墙钟 ≈0(Dart 过滤本就在交付端)。**注意:此 fix 必须与 #6 的 fix 同一批落地**,否则只修一头会加剧双标(见 §4)。

**U 映射**:U3-C 类(删权收归 arbiter)+ §4 统一 2-view 规则;显示层降级复用 U5 产品门。

### 3.3 R2#22 B plane-sweep 地板增密 — 违反 RS-1 + RS-5

**现状** [VERIFIED,cap50 落盘 + U4 `11_planesweep_candidate_adapter` + 用户否决记录]:从认证平面 prior 沿射线 ZNCC 铺点;cap50 13,488 版把椅子压扁进地板(候选点不是"椅子表面观测",是"平面假设在椅子投影处的错误落点")。用户已肉眼否决。过夜四路法医收敛结论 [VERIFIED,MORNING_REPORT §C]:下游分类/竞赛在无损前提下分不开椅子与欠观测真地板(诚实 AUC 0.810、无损门 wood_ret 0.40–0.63 << 0.90)。

**RS 纪律判**:RS-1"无中生有禁止"被构造性违反——发布的点没有逐点的真实特征匹配+三角化血统,是 prior 的几何外推;RS-5 被违反——被椅子遮挡的地板在 RS 纪律下应留洞(unseen≠surface),plane-sweep 恰恰把洞填成面。**椅子压扁是我们自创通道的病,RS 构造性无此病**(07-19 ③,用户裁决)。

**Fix 三案**(方向已由 07-19 ① 圈定,细案留签决):

- **案 A:收窄为"可见+多视验证"补点。** 只在(i)≥N 独立视图 ZNCC 验证通过、(ii)free-space/occlusion 证据不反对(不穿过任何已确证表面、不落在被遮挡区)、(iii)与 SfM 已证表面不冲突 的像素处补点;遮挡区留洞。
  - 代价:cap50 的 +112% 地板增益(2.75→5.84m², SUPPORTED)会显著缩水(幅度未测 [UNRESOLVED]);但保留的是"诚实的密"。
  - 风险:法医已证 5 张 L1 深度的反证供给不足([VERIFIED] §C 收敛铁结论)→ 案 A 的 occlusion 判据在当前证据密度下可能仍分不开椅子;真解(全 MVS 每视深度 free-space)是上游重投资,已列核心签决,本文不预判。
- **案 B:整体降级为显示层。** plane-sweep 结果不进交付 PLY,只作预览观感层(如地板补面渲染/覆盖提示),数据层零污染——与 RS"预览=tie-point 云 + 视觉修饰"的边界一致([INFERENCE] 自 RS 可见行为,内部 UNRESOLVED)。代价:交付地板密度回到 SfM 原生;收益:椅子压扁从数据层构造性消失。
- **案 C:退出预览,归正式稠密段。** 地板增密延后到 dense(CasDiffMVS/TSDF)阶段,预览保持纯稀疏(07-19 ③"预览保持稀疏"最直接的读法)。代价:预览地板洞照旧;收益:预览完全对齐 RS 纪律,零新风险,≤30s 目标零负担。
- 三案共同底线:**平面 prior 在 U4 原计划中的正确身份是"缩小弱纹理搜索区的先验",不是点生成器**([VERIFIED] 交接书 §8.6"B 平面先验缩小弱纹理搜索区")——无论选哪案,B 的长期归宿都是 prior,不是 emitter。

**U 映射**:U2(B 候选统一管理,禁 direct append——这正是 U2 的原始定义)→ U4(B 降级为搜索先验/共享证据累计)→ U5(任一场景床底幻觉/椅子压扁 = 整轮不进产品)。

---

## 4. 统一裁决:2-view 点生命周期(#6 造 × #13 杀,必须一起修)

治理规格已把"一造一杀"形式化(本文不重做,引用其结论):#6 造"近时低视差"2 视点、#13 杀"远时"2 视点,两个判据都只看 provenance/frame-gap。**R2 的增量判**:这不只是内部不一致,而是对 RS-6 的镜像双违——修复必须是**同一条规则**:每个 2 视候选统一发 support(θ_max、观测数、union 残差)+ opposition(低视差歧义、time-far 无 held-out)+ `missing: independent_holdout`,arbiter 用同一把尺子判 AMBIGUOUS/VERIFIED/BORN;近时/远时只是证据强度输入。裁决方向(§3.1 案 A vs B × §3.2)留候选 PLY + 四场景肉眼 + 用户签决。

---

## 5. ≤30s 硬目标侧注(fix 与预算的交点)

现状 finalize ~74s、stage1 全局 BA ~59s(07-19 ②)。本对照的 fix 对预算的影响 [INFERENCE,均须真机实测]:

- 帮忙:#22 案 B/C(预览少做事)、#6 案 B(不加 BA)、#11 repay(capture-idle 预付,已在产)、#9 enrich AUTO 时间闸(已在产)。
- 近中性:#6 案 A(structure-only 秒级)、#13 fix(Dart 端换判据)。
- 不归本对照管但是主战场:#21 stage1/2 BA 的 ~59s——归 U4 性能合并;⚠️记忆锚:并行语境砍 rounds=砍免费时间,只 CAP=4 中性(SUPPORTED),不许拿砍轮次凑 30s。
- 🔴 任何 fix 不得以"快"为由引入有损:质量取舍必须走签决(北极星)。

---

## 6. 诚实边界

1. "22 条"的枚举口径是本文自建对账(13 形式化 + 9 补充),每条通道的存在与机制均 [VERIFIED] 行号锚;但"恰好 22"不是生产代码里的自然常数。
2. #15 碎片合并 / #12 track upgrade / #8 grow-refit / #16 ghost mask 源码默认 env OFF([VERIFIED] `FragMergeEnabled` 等,unset=bit-identical);cap45 有"碎片合并@4px 组合签决 ship"记忆锚(SUPPORTED)——**生产臂的实际 env 状态未在本次核实,[UNRESOLVED],落地前须查装机配置**。
3. 所有"预期影响"中未标数字的幅度均未实测;本文不产候选 PLY、不跑 A/B,fix 选案全部留用户签决。
4. RS mobile 内部机制 UNRESOLVED;RS-6 是对 RC 公开机制的归纳([INFERENCE]),已单独标注,不与 VERIFIED 混用。
5. 每视 CasDiffMVS 判死不进预览(07-19 ④)是用户裁决,本文遵守,不重开。
