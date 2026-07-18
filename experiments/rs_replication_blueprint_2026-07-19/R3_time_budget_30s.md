# R3 · 拍完等待时间账审计（≤30s 硬目标 vs 现状 ~74s）

> 性质:只审计、不决策、不自批准。所有省时选项仅列账,是否执行由用户签决。
> 红线:RS Mobile 内部机制 = **[UNRESOLVED]**,本文只引用我们自己的遥测、源码注释与已定案实验;凡涉 RS 只谈可见行为与桌面 RC 公开机制(M1–M16 前期调研)。
> 证据分级:[VERIFIED] / [SUPPORTED] / [INFERENCE] / [UNRESOLVED] / [REJECTED]。

---

## 0. TL;DR(三个决定性事实 + 一个陷阱)

1. **[VERIFIED] 真极点是 stage-1 全局 BA(59.9s),不是 enrich。** enrich 的 AUTO 时间预算就是"stage-1 窗口"(`AETHER_ENRICH_TIME_BUDGET_MS` unset = auto/stage-1 window,见 `aether_sfm_c.h` repair_stats 注释),所以 enrich_ms ≈ stage1_ms + 0.6–0.8s 尾巴在 cap50/cap51 两份遥测里都成立——enrich 是"影子填充",不是独立耗时段。**加速 stage-1 = 直接缩短总墙钟**;单独砍 enrich 几乎不省时间(只省 ~0.8s 尾巴)。
2. **[VERIFIED] 补匹配搬进拍摄期是无损设计且便宜 25 倍。** `aether_sfm_live_repay` 头注释:拍摄期健康 GPU 单对 ~16ms vs finalize 热 GPU 单对 ~410ms(cap46 实测);"db-only……delivered model identical whether a pair was repaid live or at finalize"。机制已存在、已装机,cap51 实际还了 64 对,cap50 还了 0 对(还债机会依赖拍摄空闲与热态)。
3. **[VERIFIED] "先出可用云"曾被产品明确签死。** `aether_sfm_c.h` [FINALIZE-ZEROCOPY 2026-07-11]:live 路径 LOCAL 模型**不发布**("product sign-off: it is never displayed"),refined 是唯一用户可见成果。要走 RS 式 preview-first(先出粗云、后台静默换精),必须由用户**反转这条已有签核**,不是工程细节。
4. **陷阱(本审计最重要的耦合):加速 stage-1 会自动缩小 enrich 窗口。** enrich 窗=stage-1 窗,LAPACK 若把 stage-1 从 59.9s 压到 ~21s,enrich 的补匹配窗口同步缩 2.85×,`enrich_budget_stopped`(预算耗尽后跳过的新鲜匹配尝试,cap50 已达 8,339 次)会进一步膨胀→质量耦合。**任何 stage-1 提速刀必须与拍摄期还债扩展配套评估**,否则"无损提速"暗中变成"有损减 enrich"。

---

## 1. 逐段时间归属表(设备遥测,phase-2 native)

数据源 [VERIFIED]:
- cap50:`data/pocketworld_captures/cap50/device_full_pull_2026-07-17/finalize_segments.json`(finalize 实跑于 2026-07-12 23:47 +0800,139 注册帧,93,356 交付点)
- cap51:`data/pocketworld_captures/cap51/device_full_pull_2026-07-17/finalize_segments.json`(实跑于 2026-07-13 17:11 +0800,105 帧)
- 两跑均 `solver=DENSE_SCHUR, threads=4, mixed=0, stage1_rounds=4, stage2_rounds_budget=1, enrich_budget_mode=1(AUTO), live_reuse=1`。

| 分段 | cap50 (ms) | cap51 (ms) | 占总比(cap50) | 在干什么 | 动它影响什么质量 |
|---|---:|---:|---:|---|---|
| cache_pre | 176 | 776 | 0.2% | 缓存/预备 | 无(太小) |
| **stage1 全局 BA** | **59,860** | **59,544** | **81%** | rounds=4 全局精化(Cauchy@1.0, DENSE_SCHUR),**与 enrich 并行,是并行块的驱动钟** | 位姿/点精度、双层厚度、drift——refined 云的核心质量来源 |
| enrich(∥stage1) | 60,689 | 60,164 | (与 stage1 重叠) | 饥饿帧补匹配(cap50: 451 对尝试→277 写入→16,881 内点)、2-view→multi 升级(upgrade_ms 仅 224/200ms;4,070/2,333 接受)、targeted track 评分;rc=7 重试 233/221 次(恢复 106/107);**预算耗尽后跳过 8,339/4,309 次新鲜尝试** | 饥饿帧约束强度、track 完整度、覆盖;跳过越多→弱帧越弱 |
| **stage2 BA** | **12,543** | **12,489** | **17%** | 消费 enriched db 的第二轮 Cauchy 全局 BA(轮次预算=1,线程已减半策略) | 新写入观测被吸收进最终解;砍它=enrich 成果白做 |
| temporal | 101 | 159 | 0.1% | temporal detail 收尾遍 | 几乎无时间意义(见 §4-F) |
| 未计分段胶水 | ~318 | ~766 | 0.4% | 快照/发布等 | 无 |
| **total_ms** | **73,827** | **73,898** | 100% | | |

**结构式 [VERIFIED by 数字对账]**:`total ≈ cache_pre + enrich_ms(= stage1 + 0.6–0.8s 尾) + stage2 + temporal + 胶水`。cap50:176+60,689+12,543+101+318=73,827 ✓。

**用户感知等待 ≠ total_ms**:感知等待 = phase-1(live_reuse 交接,毫秒级,[VERIFIED] 头注释)+ phase-2 total(~74s)+ colorize→persist→展示(并行化设计后 ~2s,47 号定案;本次 pull 无 telemetry_dart.jsonl,phase-1/colorize 实际墙钟 **[UNRESOLVED]**)。感知总账约 **76–81s [INFERENCE]**。

**审计缺口 [UNRESOLVED]**:enrich 内部无子计时器(只有 upgrade_ms/frag_ms);减法推得 ~60.5s 主要花在补匹配管线(GPU 对匹配+验证+三角化+评分)[INFERENCE]。若要精确归属,需给 enrich 加子分段计时(规格建议,见 §6)。

---

## 2. RS 的启示:交织进拍摄期——逐段可搬性

RS 可见行为(前期调研,[SUPPORTED]):对齐工作与拍摄交织("上传与初步分析交织"),Review Scan 出的是对齐 tie-point 云,预览先出、精化后到。内部机制 [UNRESOLVED],不作复刻依据。

**我们已经交织的部分 [VERIFIED]**:live 流式 SfM(注册+local BA+空间匹配+覆盖云)全程在拍摄期跑——RS 式"边拍边对齐"我们已有。剩下堆在 finalize 的是:全局精化(stage1)、补匹配债(enrich)、stage2、temporal、colorize。

| finalize 分段 | 可搬性 | 依据 |
|---|---|---|
| cache_pre | 可搬但无意义 | 0.2–0.8s,不值得 |
| enrich·饥饿帧补匹配 | **部分可搬,机制已存在** | [VERIFIED] `aether_sfm_live_repay`:拍摄空闲还债,16ms/对 vs finalize 热 GPU 410ms/对(25×便宜);db-only,交付模型逐位同一(设计承诺);热闸 serious/critical 拒还(47 号重议:thermal=2 清洁小额还,≥3 全拒);每对每 session 只试一次;finalize 补匹配保留为安全网。cap51 证明有效(还 64 对),cap50 证明依赖拍摄节奏(还 0 对)。**扩展余地=还债 tick 的激进度与配对范围;改热闸/节奏参数须签决**(拍摄期 GPU 背压是相机冻结旧案的病灶,[VERIFIED] 44 号定罪) |
| enrich·upgrade/frag/评分 | 不值得搬 | upgrade 仅 224ms;frag 本跑为 0 |
| **stage1 全局 BA** | **不可搬(现有形态已判死)** | [REJECTED] 交接书 §6:滚动增量全局 BA(every25/window40/frozen anchors/80k obs)cap51 正式结果——floor thickness 6.754→46.858mm、end drift 30.91→95.39mm,ON+finalize5 也没救回;verdict=KEEP_PRODUCTION_DEFAULT_OFF。§6 同时警告不得泛化为"所有增量 BA 永远无效",但**当前没有可用的搬运形态**,只能就地加速(§4-B/D) |
| stage2 BA | 不可搬 | 依赖 stage1 后位姿 + enriched db,时序上无法前移;可就地加速(§4-B) |
| temporal | 不值得搬 | 0.1s |
| colorize(segments 外) | 已部分搬 | [SUPPORTED] 47 号并行设计 6.8→~2s |
| 相机关闭时点 | 已在 E 语义中 | [VERIFIED] 交接书 §5.1 第 9 条:finish 后先关相机/ARSession 再后台 SfM(释放前台热与内存);⚠️当前正式入口仍走原稀疏链(§5.4),装机包算法身份 [UNRESOLVED],此语义是否在现产线生效未证 |

**结论**:真正"可搬"的只有补匹配债(已有机制、无损设计、25× 便宜),但它搬走的是**质量成本**(减少窗口缩水时被跳过的尝试),不是墙钟本身——因为 enrich 是影子窗口,墙钟由 stage1+stage2 决定。

---

## 3. 到 ≤30s 的路径选项账(只列账,不决策)

目标拆解:总墙钟 = cache_pre + (stage1' + enrich尾) + stage2' + temporal + 胶水 ≈ stage1' + stage2' + ~1.5s。**要 ≤30s,须 stage1' + stage2' ≤ ~28.5s**(现 72.4s)。

### A. 渐进交付 / preview-first(RS 式,感知层解法)
- **省多少**:感知等待 74s → ~3–5s(先出 live local-BA 云 + colorize,refined 后台静默换入)。总算量不变。**唯一单项即可达标的选项。**
- **基础设施**:LOCAL_READY 状态、resume 路径的 LOCAL 发布、事件协议里 "refined model silently swapped in" 注释均已存在 [VERIFIED `sfm_live_recon.dart` / `aether_sfm_c.h`]。
- **质量风险**:先展示的是未精化云(历史账:live 未精化云厚度全超带 [SUPPORTED]);选区/编辑落在粗云上与换入后精云的一致性;换入瞬间点云跳变的观感。
- **签决**:**必须**。它直接反转 [FINALIZE-ZEROCOPY 2026-07-11] 的产品签核("LOCAL 永不显示")。另:若用户中途退 App,后台续跑降速 7.4×(E 核,后台伞 recipe [SUPPORTED])→ refined 可能从 74s 变 ~9min;留在 App 内前台看粗云则无此惩罚。

### B. LAPACK/Accelerate 收尾(stage1+stage2 就地加速,无损候选)
- **省多少**:Mac 'o' 实测 −65%(底层本就是 Accelerate/AMX,A16 同库同机制 [SUPPORTED,LAPACK iOS 定案])。若幅度迁移:stage1 59.9→~21s、stage2 12.5→~4.4s → **总账 ~27s ≤ 30s [INFERENCE,A16 幅度必须实测]**。
- **成本**:iOS 重编 ceres(两行 CMake 补丁);运行时开关已在库,可暗 ship 设备 A/B [SUPPORTED]。`_lapackbench/SfmLapackBench.xcodeproj` harness 已存在。
- **质量风险**:数值后端更换,须按验证文化落在 run-to-run 噪声带内(带内=无损);dpotrf info>0→LM 重试路径已论证不崩 [SUPPORTED]。**真正的风险是 §0-4 耦合:enrich 窗随 stage1 缩 2.85×,skipped 尝试膨胀** → 必须与 C 配套或接受 enrich 减量并肉眼验收。
- **签决**:带内则非有损,可先 A/B 实测;但因 enrich 窗耦合改变交付云内容的可能性存在,**装机前须同 gauge 肉眼批准**(铁律)。

### C. 拍摄期还债扩展(repay 加码)
- **省多少**:直接墙钟 ≈ 0–1s(enrich 是影子窗口)。**它的价值是给 B/D 解毒**:债在拍摄期以 16ms/对预付,窗口缩水时被跳过的就只剩残尾。47 号:空闲还债已使债 −59% [SUPPORTED]。
- **质量风险**:拍摄期 GPU 加载与快门背压/热的旧案(44 号相机冻结=热压 GPU 丢命令 [VERIFIED])——扩展必须尊重现有热闸与背压闸。
- **签决**:维持现闸内加码=免费;**改热闸阈值/还债节奏参数须签决**(47 号已重议过一轮)。

### D. stage1 rounds 4→3(或更低)
- **省多少**:上限 ~15s(若 4 轮等成本;每轮成本无遥测,[UNRESOLVED])。47 号记忆锚:并行语境下砍轮次=同时砍 enrich 免费窗,CAP=4 中性。**只有在 B 落地、stage1 已成短极点后才有讨论价值**;rounds 历史有前科(rounds=1 撤销;rounds3+ftol 曾全门过,是另一语境)。
- **质量风险**:收敛不足→精度/厚度回归。
- **签决**:**必须**,九门+同 gauge 肉眼。

### E. enrich 时间闸收紧(固定预算 < AUTO 窗)
- **省多少**:**~0.8s(只有尾巴)**。enrich 与 stage1 并行,把 60.7s 压到 30s 不改变 max(enrich, stage1)≈stage1 的并行块长度。**它不是时间杠杆,是质量旋钮**——收紧只会多跳过尝试。诚实结论:此选项在现结构下对 30s 目标无贡献,列出仅为纠正直觉。
- **签决**:有损(减 enrich 内容),若真要动须签决;但没有省时理由。

### F. temporal_detail 降级(若 R2 判降)
- **省多少**:**101–159ms**。可忽略,不构成 30s 路径的组成部分。R2 若降级它,理由只能是质量(鬼点/来源治理),时间账上诚实记零。

### G. 增量全局 BA 搬进拍摄期
- **[REJECTED]**,交接书 §6,不可用(见 §2 表)。列此仅防复活。

### 组合账(全部 [INFERENCE],每个数字都要真机 A/B)
- **B(+C 配套)**:~0.2 + (21+0.8) + 4.4 + 0.1 + 0.3 ≈ **26.8s ≤ 30s**,候选无损硬达标路径;A16 幅度、噪声带、enrich 减量影响三件事必须实测。
- **B+D**:~19s,但双重风险叠加,须双签决。
- **A**:感知 ~3–5s,与 B/C 不互斥——RS 可见行为本就是"先出预览、精化后到",A+B 同做则粗云只挂 ~27s 就被精云换掉。

---

## 4. CasDiffMVS 每视深度:时间判死账(写死在案)

- 单帧成本:**709ms/帧**(A16,GPU 推理+CPU 融合重叠管线,前期实测定案 [SUPPORTED];热受控热身后口径,拍摄刚结束的热态只会更差 [INFERENCE])。
- 逐 cap 账:

| 帧数 N | 709ms × N | vs 30s 预算 |
|---:|---:|---|
| 42(极小拍摄) | 29.8s | ≈ 吃光全部预算 |
| 93(cap46 级) | 65.9s | 2.2× 爆 |
| 105(cap51) | 74.4s | 2.5× 爆 |
| 139(cap50 实际) | 98.6s | 3.3× 爆 |

- 即便按无损提速调研上限 2–3×(fp16 会引入 6% 地板=有损,持久 session/缓存/批处理为无损项 [SUPPORTED])做到 ~250ms/帧:93 帧仍要 ~23s,吃掉预算 77% 且只买到深度、没买到任何 BA/交付;fp16 之外的组合未在真机验证 [UNRESOLVED]。
- 叠加用户 07-19 指令③(预览保持稀疏)与④(判死):**CasDiffMVS 不进预览路径,永久留在正式稠密段。[判死,记档]**

---

## 5. 诚实分级:哪些免费、哪些有损须签决、哪些已死

| 选项 | 时间收益 | 性质 | 签决? |
|---|---|---|---|
| A 渐进交付 | 感知 −70s | 感知层免费(总算量不变),但反转 07-11 产品签核 | **须签决** |
| B LAPACK 收尾 | 总墙钟 −45s 级 [INFERENCE 待实测] | 无损候选(带内验证前不许宣称) | A/B 实测免签;装机须同 gauge 肉眼批准;enrich 窗耦合须一并呈报 |
| C 还债扩展(闸内) | 墙钟 ~0;为 B/D 解毒 | 无损设计([VERIFIED] db-only 同一交付) | 闸内免签;**改闸须签决** |
| D rounds 砍 | ≤15s(仅 B 后有意义) | **有损风险** | **须签决+九门** |
| E enrich 闸收紧 | ~0.8s | 有损且无省时理由 | 不建议进入议程(诚实:非杠杆) |
| F temporal 降级 | ~0.1s | 时间上为零 | 归 R2 质量管辖 |
| G 增量全局 BA | — | [REJECTED] | 不可复活 |
| CasDiffMVS 进预览 | — | [判死] §4 | 不可复活 |

---

## 6. 审计缺口与建议的下一步实测(规格,不决策)

1. **enrich 子分段计时缺失 [UNRESOLVED]**:建议 native 给 enrich 加 `rematch_ms / triangulate_ms / scoring_ms` 子计时,归属才可从减法推断升级为实测。
2. **A16 LAPACK 幅度 [UNRESOLVED]**:`_lapackbench` harness 已在 `~/Developer/Aether3D-cross/_lapackbench/`;真机热受控 back-to-back 实测(±30% 单次墙钟不可信,铁律)。
3. **phase-1 与 colorize 真机墙钟 [UNRESOLVED]**:本次 pull 缺 telemetry_dart.jsonl;感知总账(§1)需补齐。
4. **stage1 每轮成本曲线 [UNRESOLVED]**:D 选项定价前提。
5. **repay 扩展的债覆盖率**:cap50(还 0)vs cap51(还 64)差异说明还债机会强依赖拍摄节奏;需统计多 cap 的"闸内可还上限"。

## 证据清单

- `data/pocketworld_captures/cap50/device_full_pull_2026-07-17/finalize_segments.json`、`.../cap51/.../finalize_segments.json` [VERIFIED]
- `~/Developer/pocketworld/lib/capture/sfm_live_recon.dart`(S3.5 恢复注释、finalize 流程、还债 tick 停止语义、refined=唯一用户可见)[VERIFIED]
- `~/Developer/Aether3D-cross/aether_cpp/include/aether_sfm_c.h`(两阶段 finalize、FINALIZE-ZEROCOPY 产品签核、live_repay 16ms vs 410ms、enrich AUTO=stage-1 window、repair_stats 字段语义)[VERIFIED]
- 交接书 `handoffs/POCKETWORLD_MASTER_HANDOFF_PROMPT_2026-07-18.md` §5(E 语义/§5.4 装机身份 UNRESOLVED)、§6(增量全局 BA REJECTED)[VERIFIED 文档]
- 前期定案(memory,标 [SUPPORTED]):LAPACK iOS 定案、47 号提速包/colorize 并行/repay 热闸、44 号相机冻结定罪、CasDiffMVS 709ms 重叠定案、后台伞 7.4×、rounds 家谱。
