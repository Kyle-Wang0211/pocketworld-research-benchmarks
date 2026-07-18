# RS 复刻蓝图(RS_REPLICATION_BLUEPRINT)— 可执行分阶段方案 S0→S4

- 生成:2026-07-19(合成 R1 纪律调研 + R2 通道对照 + R3 时间账;上游三文件同目录)。
- 性质:**规格+路线图,不自批准任何裁决**。所有选案(S1 两案、S2 三案、S3 签决项)全部留用户签决;本文只给候选怎么产、图怎么看、accept/rework 判据。
- 🔴 红线(全程有效):
  1. **RS mobile 内部机制 = UNRESOLVED**。复刻对象 = RS 可见行为 + 桌面 RealityCapture 公开机制(M1–M16 + R1 补充),全文不声称 RS 内部算法。
  2. **每步必须同 gauge、同生产位姿、真彩并排(compare.html?right=候选ply,禁 Sim3),用户肉眼批准才进下一步**。
  3. **质量或总耗时任一退化 → 该轮不进产品**(U5 门第 6 条原文语义)。
  4. 质量取舍必须签决(北极星:质量无损);不许拿"快"为理由私自引入有损。
  5. 研究只落研究 worktree;生产改动须走签决后另开落地任务;不 reset/clean 他人 dirty。
- 证据分级沿用:[VERIFIED] / [SUPPORTED] / [INFERENCE] / [UNRESOLVED] / [REJECTED];引用上游时标注来源文件。

---

## 全局图景(为什么是这四步)

用户 07-19 四连裁决(硬约束):①各归其位(椅子观测出生在椅子、被遮挡地板留洞、plane-sweep 只补可见+验证);②拍完等待 ≤30s;③预览保持稀疏、大方向复刻 RS 不盲目创新;④CasDiffMVS 判死不进预览(留正式稠密段,[判死,记档] R3 §4)。

三份上游收敛出的执行序:

```
S0 纪律基线(定义+映射,零代码)                     ← 立即可做,无签决
S1 第一刀:2-view 生命周期(#6 造 × #13 杀 同批修)  ← 最违反纪律+可肉眼验证,两案签决
S2 plane-sweep 归位(#22)                          ← 椅子压扁病根,三案签决
S3 时间线:≤30s 组合路径(A/B/C/D 排序)            ← 免费先行,有损/反转签核者签决
S4 展示层复刻(uncertainty+quality 着色)            ← RS 可见行为,收编已有 ghost mask
```

S1/S2 是质量线(RS 纪律),S3 是时间线,S4 是展示线;三线可部分并行,但**每条线内部严格串行:上一步用户批准才进下一步**。

---

# S0 · 纪律基线:"RS 纪律"正式定义 + 与 U0→U5 的关系

## S0.1 RS 纪律六条(正式定义,采自 R2 §0,证据链落在 R1)

发布到预览/交付云的每一个点必须同时满足:

| 编号 | 纪律 | 证据 |
|---|---|---|
| RS-1 | **真实观测起源**:点 = 真实 2D 特征跨帧匹配的三角化;无 prior 铺点、无模型幻觉点、无中生有禁止 | [VERIFIED] R1 §1(tie point 官方定义 = "two or more images" 的真实对应) |
| RS-2 | **活过 BA**:发布位置是 BA 精化后的位置;从不发布"未精化/冻结位姿纯 DLT"点。RC 连"跳过最终 BA"都只存在于显式 Draft 降质档 | [VERIFIED] R1 §1.3(draft "Final model optimization" 开关反证) |
| RS-3 | **重投影裁剪**:BA 后按残差裁(≤3px 量级;RC 推荐 ≤3px、默认 2px) | [VERIFIED]/[SUPPORTED] R1 §1.1 |
| RS-4 | **错位染色不删**:misalignment/uncertainty/quality 走 display-only 重着色(percentile 70 只是色标锚),数据全量不动;唯一"少看点"是展示层 track-length 滑杆 | [VERIFIED] R1 §4 |
| RS-5 | **未观测留洞**:unseen ≠ surface;RC 有主动"相机与云之间有遮挡就不建"机制;椅底/沙发后留洞是全行业一致行为 | [SUPPORTED] R1 §2 + 07-19 用户裁决① |
| RS-6 | **按几何证据裁决,不按出身**:culling 判据是残差/角度/不确定性/held-out,不是"哪条通道产的" | [INFERENCE] R2 §0(由 RC 公开机制归纳,无 per-source 发布门;单独标注,不与 VERIFIED 混用) |

补充两条**行为级**纪律(增量与预览):

- RS-7 **修正是批量重解,不是点级手术**:桌面 RC 以 component 为单位、显式开关触发(re-align/rematch/merge/刚体 update);mobile 可见行为 = 预览只增长,修正 = re-process 整体重跑。[VERIFIED/SUPPORTED] R1 §3 → 我们的流式 local-BA + finalize 全局 BA 两段结构与此同构,**不需要为预览实现点级在线修正**。
- RS-8 **降质快路必须显式**:RC 把"跳过 final BA"做成显式 Draft 档;我们任何 ≤30s 的轻量路径同理必须是**显式降质档 + 正式段补全量 BA**,不许静默省略。[VERIFIED] R1 §1.3。

## S0.2 RS 纪律 = 统一出生架构(U0→U5)的实例化,不是推翻

对应关系(逐条映射,U 定义以交接书 §8 原始附件为准,U0→U5 六阶段):

| RS 纪律 | U 桶位 | 说明 |
|---|---|---|
| RS-1(真实观测起源) | U2/U3 | 正是 U2 "B/D 不得 direct append、未证明候选不发布" + U3 "从原 feature/track 出生" 的判据化表述 |
| RS-2(活过 BA)+ RS-3(重投影裁剪) | U3 出生门 | SurfaceHypothesis 的 BORN 前置条件:必须经精化+残差裁;#6 的病 = 绕过此门 |
| RS-4(染色不删)+ RS-5(留洞) | U5 产品门 + 显示层 | ghost mask sidecar([VERIFIED] R2 #16)正是 RS-4 同构机制,直接升 U5 |
| RS-6(证据不问出身) | U3 arbiter | source-agnostic surface hypothesis 的原始定义;#6/#13 双标 = 对它的镜像双违 |
| RS-7(批量重解) | U0 冻结 + 现两段结构 | 无需新机制,现结构已同构 |
| RS-8(显式降质档) | S3 时间线的产品约束 | preview-first 若做,必须显式标注 + refined 静默换入 |

**结论:本蓝图不新建架构。S1/S2/S4 全部是把现有私有通道收编进 U1(账本)→U2(候选统一管理)→U3(证据出生)→U5(展示/产品门)的既有桶位;S3 归 U4(性能合并)。**唯一确认过的概念补丁是可逆状态机(u3_merge #2,晨报 §B),它承接 RS-4"降级不删"的状态表达,仍属 U3 生命周期内部。

## S0.3 S0 交付物与 accept 标准

- 产出:本节即交付物(纪律定义 + 映射表),另加一页给用户的裁决单(见每阶段"签决点"汇总,§终表)。
- 给用户看什么:本文件;无图(S0 零代码零候选)。
- accept 标准:用户认可六+二条纪律作为后续所有候选的判据基线。
- rework 触发:用户对任一条纪律表述有异议(尤其 RS-6 是 INFERENCE 级) → 改判据后 S1 起全部重排。
- R1-TODO(继续深度调研,不阻塞 S0):装一台 Mac 版 RealityScan 2.x 抄 UI 默认面板,把 R1 §5 参数表(40k/10k/10k/Medium/2px 等)从 SUPPORTED 升 VERIFIED,~30 分钟。

---

# S1 · 第一刀:2-view 点生命周期(R2#6 temporal-detail × R2#13 spatial filter,同批修)

## S1.1 为什么它是第一刀

- **最违反纪律**:R2 判决 22 条通道仅 3 条 🔴 FIX,#6 是其中对 RS-2 的**构造性**违反——finalize 在 stage-2 BA 之后灌 ~18k 永不精化的 2 视点(位姿/内参冻结、纯 DLT、永不被三把尺子过滤,[VERIFIED] 行号 2340–2371/4376–4382),是交付云厚度(双墙/歧义壳)的主要原料(cap47 [SUPPORTED])。
- **必须连修 #13**:Dart `filterFinalSpatialTwoViewPoints`([VERIFIED] `sfm_live_recon.dart:181–229/1304–1315`)按 frame-gap>K + 恰 2 观测**无条件硬删**,判据是出身不是几何 → RS-6+RS-4 双违。#6 造"近时低视差"、#13 杀"远时"——镜像双标,只修一头会加剧双标(R2 §4),**同批落地为同一条 2-view 生命周期规则**。
- **可肉眼验证**:18k 点占交付云 ~19–29%(93k/63k 级交付),厚度变化在 compare.html 侧视图直接可见;且时间代价近零(见 S1.4),不与 S3 冲突。

## S1.2 统一规则(两案共同骨架)

每个 2-view 候选(不问出身:live create 也好、temporal-detail 也好、远时空间对也好)统一发:

- **support**:θ_max(视差角)、观测数、union refit 残差、held-out 确认;
- **opposition**:低视差歧义(θ<门限)、time-far 无独立 held-out;
- **missing**:`independent_holdout`;

arbiter 用**同一把尺子**判 AMBIGUOUS / VERIFIED / BORN;近时/远时只是证据强度输入,不再是生杀判据。两案共同底线:**不删观测**——TVG 对/观测全保留(A 类证据资产),变的只是"出生权/发布权"。θ 绝对下限必须保留(cap47 教训:无门 refit 会救活鬼点,grow-refit 臂 ghost 4.3%→5.5% [SUPPORTED])。

## S1.3 两案(不预判,留签决)

### 案 A:纪律补票 — 让 18k 点过 BA + 裁剪
- 改法:`RestoreTemporalDetail` 后追加一次 **structure-only refit(位姿全冻,只动新点)+ 三把尺子(neg-depth / reproj≤3px / θ 下限)只对新点跑一遍**。生产已有同构代码(`aether_sfm_global_refine` stage-2 structure-only 模式,[VERIFIED] ~5800)。
- 墙钟:structure-only、18k 点、位姿冻结 → 预期秒级([INFERENCE],**须真机实测,不许估时当承诺**);对 ≤30s 近中性。
- 点数:refit 后 θ/reproj 出门子集被裁 → 交付点数下降,幅度 [UNRESOLVED](cap47 提示低视差子集显著:25.9% 原生 2 视 <3°)。
- 质量:厚度原料直接减薄;**消灭"一造一删"自相矛盾**(同一把尺子只裁一次)。

### 案 B:各归其位 — 整体降级 AMBIGUOUS 不发布
- 改法:18k 点整体进证据图为 `AMBIGUOUS`(带 `missing: independent_holdout` + 低视差 opposition 标记),不进交付 PLY;等 enrich/rematch/track-upgrade 支持证据到位、arbiter 判 VERIFIED 才 BORN(可逆状态机语义,晨报 #2)。
- 墙钟 ≈0;点数:交付立减 ~18k(观感冲击大);质量:最彻底且**零删除**(点留候选层,不占用户可见身份)。
- 风险:预览密度骤降是否低于可接受观感 → 唯一判据是四场景肉眼。

### #13 的 fix(两案下相同)
1. "time-far + 仅 2 视 + 无 held-out" → 记 opposition/`missing`,arbiter 默认不予出生(效果上多数今天被删的点仍不发布,但**理由变成几何证据**);
2. 有强 support(大 θ_max、干净 union 残差、held-out 确认)的远时真点 → **必须活**(loop 闭合区误杀救回);
3. 处置从 DeletePoint3D 换成不发布/染色(复用 #16 ghost mask 显示层,→S4)。
- 预期 [INFERENCE]:交付点数近中性偏正;loop 区表面完整性提升;墙钟 ≈0。

## S1.4 候选怎么产 / 给用户看什么 / accept / rework

**候选 PLY 生产**(研究 worktree,禁碰生产;U0 冻结输入:cap40/41/50/51 四场景、设备生产位姿、production finalize 配置、同 gauge):

| 候选 | 内容 |
|---|---|
| `baseline.ply` | 现生产 finalize 直出(各 cap 已有 device-exact 基线) |
| `s1_caseA_<cap>.ply` | 案 A:harness 复现 finalize → RestoreTemporalDetail 后接 structure-only refit + 三把尺子(只裁新点)→ 同时 #13 换证据判据 |
| `s1_caseB_<cap>.ply` | 案 B:18k 整体 AMBIGUOUS 不发布 + #13 换判据 |
| 附带 sidecar | 每候选出 per-point provenance/裁决账本(U1 语义):被裁/被降级/被救回三个子集各自计数与着色 PLY |

**给用户看什么**:
1. compare.html?right=候选 ply,左 baseline 右候选,**同 gauge 同生产位姿真彩,禁 Sim3**;四场景 × 四视角(含侧视看厚度、loop 闭合区特写看 #13 救回)。
2. 三张差异着色图:`裁掉的点`(案 A)/`降级的点`(案 B)/`救回的点`(#13),让"少了什么、多了什么"一眼可查。
3. 数字表:交付点数、双层厚度(SV 口径,噪声带 0.060–0.063 [SUPPORTED])、reproj 分层统计(⚠️mean 有成分效应必须分层看 [SUPPORTED])、finalize 墙钟(热受控 back-to-back,单次 ±30% 不可信)。

**accept 标准**(全部满足才进产品落地任务):
- 用户肉眼:四场景无一处新增浮点/竖线/床底幻觉/墙错位/正确覆盖下降;厚度侧视可见改善或至少不劣化;
- 数字:厚度 ≤ 基线(或带内);总墙钟不增(案 A 的 refit 秒级承诺须实测兑现);
- 无误杀:强 support 远时真点存活抽查(loop 区特写);
- 用户在 A/B 之间签字选案(或要求混合/第三案)。

**rework 触发**:
- 案 A refit 实测超秒级量级 → 回炉(改增量式/预算化 refit);
- 案 A 救活鬼点(ghost 占比升出带)→ θ 下限收紧重跑;
- 案 B 观感被否 → 转案 A 或分级发布(强证据 2-view 先 BORN);
- 任一场景质量退化 → 整轮不进产品(U5 门)。

**[UNRESOLVED] 待核(落地前必查)**:frag merge / track upgrade / grow-refit / ghost mask 的生产臂实际 env 状态(源码默认 OFF,与 cap45 "碎片合并@4px ship 签决"记忆锚存在张力,[UNRESOLVED] R2 §6.2)。

---

# S2 · plane-sweep 归位(R2#22):可见+验证才补,遮挡留洞

## S2.1 病根与判决

- 现状 [VERIFIED]:从认证平面 prior 沿射线 ZNCC 铺点,cap50 13,488 版把椅子压扁进地板;用户已肉眼否决。
- RS 纪律判:RS-1(点无逐点真实匹配血统,是 prior 外推)+ RS-5(把被遮挡区的洞填成面)双违。**椅子压扁是自创通道的病,RS 构造性无此病**(07-19 ③,用户裁决)。
- 法医铁结论 [VERIFIED,晨报 §C]:下游四路+合成分类器已穷尽——in-ROI 分离积极限 0.51/AUC 0.810,杀 81–96% chairFP 必误删 37–59% 真地板(wood_ret 0.40–0.63 << 0.90 无损门);病根 = 5 张 L1 深度反证供给不足,真解(全 MVS 每视深度 free-space)是上游重投资,属**核心签决**,本文不预判。

## S2.2 三案(方向已由 07-19 ① 圈定为"各归其位",细案留签决)

| 案 | 内容 | 代价 | 收益 | 关键风险 |
|---|---|---|---|---|
| A 收窄为"可见+多视验证"补点 | 只在 (i)≥N 独立视图 ZNCC 通过 (ii)free-space/occlusion 不反对 (iii)与已证表面不冲突 的像素补点;遮挡区留洞 | +112% 地板增益(2.75→5.84m² [SUPPORTED])显著缩水,幅度 [UNRESOLVED] | 保留"诚实的密" | **判别力存疑**:法医已证 5 张 L1 反证供给不足 → 案 A 的 occlusion 判据在当前证据密度下可能仍分不开椅子;须先跑判别力预检(见 S2.3) |
| B 降级为显示层 | 结果不进交付 PLY,只作预览观感层(地板补面渲染/覆盖提示),数据层零污染 | 交付地板密度回到 SfM 原生 | 椅子压扁从数据层构造性消失;与 RS"tie-point 云+视觉修饰"边界一致([INFERENCE]) | 观感层与数据层的一致性沟通成本 |
| C 退出预览归稠密段 | 地板增密延后到 dense(CasDiffMVS/TSDF);预览纯稀疏 | 预览地板洞照旧 | 完全对齐 RS 纪律 + 07-19 ③"预览保持稀疏"最直接读法;≤30s 零负担、零新风险 | 弱纹理地板预览观感与竞品差距(RS 同样留洞,[SUPPORTED] R1 §2) |

三案共同底线 [VERIFIED 交接书 §8.6]:**B 的长期归宿是 U4 的"缩小弱纹理搜索区的先验",不是点生成器**——无论选哪案,plane prior 都降级为 prior,不再 emit。

## S2.3 候选怎么产 / 给用户看什么 / accept / rework

**先跑一个判别力预检(案 A 的生死关,研究性,免签决)**:在 cap50 冻结 ROI 上,用"≥N 视 ZNCC + 现有 free-space 证据"跑案 A 门,输出 chairFP 通过率 vs 真地板通过率。若分离仍 ≤ 法医极限(≈0.51)→ **案 A 在当前证据密度下自动出局**,只呈 B/C 两案 + "上游全 MVS free-space 要不要投"的核心签决。

**候选**:
- `s2_caseA_<cap>.ply`(若预检过关):stock + 收窄后补点,补点单独着色;
- `s2_caseB_<cap>`:交付 PLY = stock 原样 + 一份显示层渲染 demo(截图/网页);
- `s2_caseC_<cap>.ply`:= stock(即基线,呈现的是"洞的观感");
- 每案附椅子 ROI 特写(真彩 top-down + 侧视)与地板覆盖面积数字(m² 口径同 cap50)。

**给用户看什么**:compare.html 四场景四视角 + 椅子 ROI 前后特写;案 A 另附"补点通过/被拒"着色图;案 B 附显示层效果示意。

**accept 标准**:
- 硬门:**任一场景床底幻觉/椅子压扁 = 整轮不进产品**(U5 门原文);
- 案 A:chairFP 漏过 ≈0 且真地板补点保留可观(数字由预检定价后用户裁);
- 案 B/C:用户接受相应观感代价;
- 时间:案 A 补点管线不使 finalize 超预算(与 S3 对账);B/C 天然为负成本。

**rework 触发**:预检分离不足→案 A 出局;显示层示意被否→回 C;用户决定投上游全 MVS free-space → 另开重投资任务(核心签决,勿在本蓝图内偷跑)。

**[UNRESOLVED]**:案 A 收窄后增益幅度;全 MVS free-space 的成本/收益定价(须独立 spike)。

---

# S3 · 时间线:≤30s 组合路径(免费先行 / 须签决,只排序不决策)

## S3.1 时间账事实(R3,[VERIFIED])

- total ~73.8s = cache_pre 0.2 + **并行块 max(stage1 BA 59.9, enrich 60.7)** + stage2 12.5 + temporal 0.1 + 胶水 0.3;感知另加 phase-1(毫秒)+ colorize(~2s)≈ 76–81s [INFERENCE]。
- **真极点 = stage1(81%)+ stage2(17%)**;enrich 是 stage-1 窗口的影子填充,单独砍只省 ~0.8s 尾巴。
- **耦合陷阱**:stage1 提速自动缩 enrich 窗(cap50 已跳过 8,339 次尝试)→ 任何 stage1 提速刀必须与拍摄期还债扩展(C)配套评估,否则"无损提速"暗变"有损减 enrich"。
- 已死项(防复活):增量全局 BA 搬拍摄期 [REJECTED 交接书 §6];CasDiffMVS 进预览 [判死 07-19④,42 帧即 29.8s 吃光预算];E enrich 闸收紧(非杠杆,~0.8s);F temporal 降级时间记零(归 S1 质量管辖)。

## S3.2 执行序(严格按"免费先行→无损候选→反转签核→有损"排)

### 第 1 步(免费,闸内免签):C 还债扩展(现有热闸/背压闸内加码)
- 机制已在产([VERIFIED] `aether_sfm_live_repay`,16ms/对 vs finalize 410ms/对,db-only 交付逐位同一)。cap51 还 64 对 / cap50 还 0 对 → 先补统计:多 cap "闸内可还上限"(R3 §6.5)。
- 交付:还债覆盖率报告 + 交付 PLY SHA 对账(db-only 承诺验证:还与不还交付逐位一致)。
- accept:SHA 一致 + 无相机冻结/背压回归(44 号病灶红线);**改热闸阈值/节奏参数须签决**,本步不碰。

### 第 2 步(无损候选,A/B 实测免签、装机须肉眼批准):B LAPACK/Accelerate 收尾
- 预期:stage1 59.9→~21s、stage2 12.5→~4.4s → **总账 ~26.8s ≤ 30s**([INFERENCE],Mac −65% 迁移假设,**A16 幅度必须实测**;harness 已在 `~/Developer/Aether3D-cross/_lapackbench/`)。
- 顺序:先 harness 热受控 back-to-back 实测幅度 → 再整链 A/B(runtime 开关已在库,可暗 ship 设备 A/B [SUPPORTED])。
- accept 三件套(缺一不可):①数值落 run-to-run 噪声带内(带内=无损,SV 门锚 ≤0.0630);②总墙钟实测 ≤30s 量级;③**enrich 窗缩水影响呈报**:窗从 ~60s→~21s,skipped 膨胀多少、第 1 步的还债预付能否覆盖、交付云同 gauge 肉眼无退化。
- rework:带外 → 判死此路;enrich 减量致肉眼可见退化 → 加码 C 或回炉。

### 第 3 步(感知层,**须签决**——反转 07-11 产品签核):A 渐进交付 / preview-first
- 感知等待 74s → ~3–5s(先出 live local-BA 云 + colorize,refined 后台静默换入);基础设施已存在([VERIFIED] LOCAL_READY/resume/事件协议)。**唯一单项即可达标的选项**,且与 B 不互斥(A+B:粗云只挂 ~27s 即被精云换掉)。
- 它直接反转 [FINALIZE-ZEROCOPY 2026-07-11] "LOCAL 永不显示"签核 → **必须用户显式签决**,并按 RS-8 做成显式两态(preview→refined 换入),不许静默降质。
- 呈报时须附:live 未精化云厚度历史账(全超带 [SUPPORTED])、换入瞬间跳变观感 demo、退 App 后台 7.4× 降速账(refined 74s→~9min [SUPPORTED])。
- accept:用户签字反转 + 换入观感 demo 肉眼过 + 选区/编辑在粗云↔精云的一致性方案过。

### 第 4 步(有损风险,**须签决+九门**,仅 B 落地后才有意义):D stage1 rounds 4→3
- 上限 ~15s;⚠️记忆锚:并行语境砍轮次=砍 enrich 免费窗,CAP=4 中性;rounds=1 有撤销前科。B 后 stage1 已成短极点才值得谈;定价前提 = stage1 每轮成本曲线([UNRESOLVED],先补遥测)。

### 与 S1/S2 对账
- S1 案 A(structure-only refit)近中性但须实测;S1 案 B / S2 案 B/C 为负成本(少做事)——质量线与时间线同向,无冲突。

## S3.3 验收总口径(每步相同)
- 时间:热受控 back-to-back / 交替对照,取中位;单次墙钟 ±30% 不可信;
- 质量:同 gauge 真彩并排 + SV/厚度/覆盖数字带内;
- 双门齐过才进下一步;**任一退化 → 该步不进产品**。

**[UNRESOLVED] 清单(S3)**:enrich 子分段计时(建议加 rematch_ms/triangulate_ms/scoring_ms);A16 LAPACK 幅度;phase-1/colorize 真机墙钟(补 telemetry_dart.jsonl);stage1 每轮成本曲线;多 cap 还债上限统计;§5.4 装机包算法身份。

---

# S4 · 展示层复刻:uncertainty percentile + 质量着色(RS 可见行为)

## S4.1 复刻对象(全部 [VERIFIED] R1 §4,display-only,数据全量不动)

| RS/RC 机制 | 我们的对应 | 状态 |
|---|---|---|
| Uncertainty 着色:percentile **70** 定色标锚(70% 视为 stable),深蓝=精确、红=不确定;全量重着色不过滤 | 新增:预览/交付云 per-point 不确定性着色模式(σ 来源:reproj 残差/θ/track 长度组合,口径 S0 纪律下定义) | 新建(轻,显示层) |
| Quality 着色:camera coverage 红→绿 | 覆盖云已有同范式(RS 式覆盖云定案 [SUPPORTED]);补 per-point coverage 染色到交付云查看器 | 半已有 |
| Misalignment:蓝对红错,只染色不删 | **ghost mask sidecar 正是同构**([VERIFIED] R2#16,env-gated,数据全量不动)→ 升 U5 产品层,作为 S1 #13 降级点/疑鬼点的统一显示通道 | 已有,收编 |
| Track-length 滑杆:唯一"少看点"手段,展示层过滤 | 查看器加 track-length 显示滑杆(数据不动) | 新建(轻) |
| Mobile 双 render mode:同一片云 color/quality 切换 | 预览 UI:真彩 / quality / uncertainty 三模式切同一片云 | 新建(UI) |
| RS 2.0 补拍热图 | 覆盖云已承担;不重复建 | 已有 |

⚠️ 约束:**禁止用户可见质量滑杆/档位**(签决记忆锚)指的是质量取舍旋钮;RS 式 track-length 滑杆是"看哪些点"的展示过滤,不改数据不改算法——是否触碰该签决红线,**呈用户裁决,不自行认定**。

## S4.2 候选 / 看什么 / accept / rework

- 候选:四场景查看器新增三着色模式截图集(真彩/quality/uncertainty 并排),ghost mask 点以 misalignment 蓝红范式渲染;交付 PLY 字节不变(display-only 铁证:着色前后 PLY SHA 相同)。
- accept:SHA 不变 + 用户认可着色语义直观(红=该补拍/不确定,不是"坏点被删");滑杆裁决过;
- rework:着色被解读为质量下降暗示 → 调色标/文案;percentile 锚在我们数据分布上失真 → 重定锚统计量(记录偏离 RS 的理由)。

---

# 全程规则与总裁决单

## 验收铁律(每阶段重复,不豁免)
1. compare.html?right=候选ply,同 gauge、同生产位姿、真彩、四场景四视角、禁 Sim3;
2. 用户肉眼批准才进下一步;蓝图内任何"预期/建议"都不是批准;
3. 质量或总耗时任一退化 → 该轮不进产品;
4. 数字口径:厚度 SV(带 0.060–0.063)、reproj 分层、点数三向对账(裁/降/救)、墙钟热受控中位;
5. 落地改生产 = 签决后另开任务,遵循共享脏工作树纪律。

## 用户签决点汇总(本蓝图不预判任何一项)

| # | 签决 | 阶段 | 性质 |
|---|---|---|---|
| Q1 | S1 选案:A 补票过 BA vs B 降级 AMBIGUOUS(#13 随批) | S1 | 质量语义 |
| Q2 | S2 选案:A 收窄补点(预检过关才呈)vs B 显示层 vs C 退预览 | S2 | 质量语义 |
| Q3 | 上游全 MVS 每视深度 free-space 要不要投(椅子压扁真解,重投资) | S2 关联 | 核心签决 |
| Q4 | A 渐进交付:反转 07-11 "LOCAL 永不显示"签核 | S3 | 产品签核反转 |
| Q5 | D rounds 4→3(仅 B 落地后;九门) | S3 | 有损风险 |
| Q6 | 改还债热闸/节奏参数(若闸内加码不够) | S3 | 有损风险 |
| Q7 | track-length 展示滑杆是否触碰"禁质量滑杆"红线 | S4 | 产品红线解释 |
| Q8 | env-OFF 通道(frag merge/track upgrade/grow-refit/ghost mask)生产臂状态核实后的开关归属 | S1 前置 | 配置对账 |

## 继续深度调研清单(UNRESOLVED 汇总,不阻塞对应阶段的即可做部分)

1. R1-TODO:Mac 装 RealityScan 2.x 抄默认面板(参数表升 VERIFIED);
2. RS mobile 内部机制:永久红线,只跟踪官方文档/发布说明更新;
3. 生产臂 env 状态核实(Q8 前置);
4. S1 案 A refit 真机墙钟、被裁子集幅度;
5. S2 案 A 判别力预检;全 MVS free-space 定价 spike;
6. S3 五项遥测缺口(enrich 子计时/A16 LAPACK/phase-1+colorize/rounds 曲线/还债上限);
7. 椅底稀疏云官方视觉样例(行为级证据已足,视觉级悬置)。

---

## 引用索引

- R1(纪律):`R1_rs_tiepoint_discipline.md`(同目录)— tie-point 出生纪律、遮挡留洞、增量行为、展示层、默认参数;
- R2(对照):`R2_channel_rs_compliance.md` — RS-1..6 判据、22 通道判决、#6/#13/#22 深判、统一 2-view 规则;
- R3(时间):`R3_time_budget_30s.md` — 分段归属、enrich 影子窗、A–G 选项账、CasDiffMVS 判死账;
- U 定义:`handoffs/POCKETWORLD_MASTER_HANDOFF_PROMPT_2026-07-18.md` §8(U0→U5 原始附件 SHA 已录)、§6(增量 BA REJECTED)、§5;
- 过夜产物:`experiments/u3_merge_prototypes_2026-07-18/`(01 治理规格、02 可逆状态机、MORNING_REPORT §C 法医收官)。
