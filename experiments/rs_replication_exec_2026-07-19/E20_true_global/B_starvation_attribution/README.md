# E20-B 设备饿死归因 — 纯遥测对账(不碰设备)

日期:2026-07-18 · python3.11 · 只读输入:cap50/cap51 `device_full_pull_2026-07-17`、E6 rescue_provenance、E9 off runs、E19 runs。
产物:`analyze_starvation.py`(可重跑)、`reconciliation.json`、`db_debt_audit.json`、`missing_theta_stats.json`、本 README。

## TL;DR(判词先行)

**对"设备云缺 8,538(cap51)/15,694(cap50)点"(E6 账本口径):饿死闸解释 0%。**
这批点的全部证据(匹配 + verified two-view geometry)**都在最终设备 db 里**;host 无热、无 rc=7、无预算闸,消费同一 db,同样不出生(track 数平价 ±0.1~1.8%)。缺点对 94~98% 落在 Δf≤6 的窄时域窗——热闸 K12→K6 根本砍不到的窗。真凶 = **出生纪律**(2-view 候选不被 incremental triangulation/track 机制消费),与 E19、鬼层终审"根治只在 stage-1 出生前"同一结论。**解闸/加预算救不回这批点。**

饿死闸真实存在,但它砍的是 **E6 账本之外**的潜在证据(从未进 db 的对):终局 514/324 个时域窗对从未匹配 + 8,339/4,309 次新匹配尝试被时间闸跳过。这正是 E20-A(真全局新配对)的战场,收益须实测,不在本案拍脑袋。

## ① 计数器收集(设备 vs host 回放)

| 计数器 | cap50 设备 | cap51 设备 | host(E9 off ×3 / E19,两 cap) |
|---|---|---|---|
| gpu_retry_attempts / recovered | 233 / 106 | 221 / 107 | 0 / 0 |
| live gpu_match_fail 事件(jsonl) | 48 对 | 39 对 | — |
| thermal_throttle(K12→K6) | frame 31 起,thermal=2 | frame 36 起,thermal=2 | — |
| rematch starved/candidates/attempted/written | 108 / 789 / 451 / 277 | 74 / 484 / 453 / 169 | 全 0 |
| rematch_inliers(budget=800) | 16,881 | 9,638 | 0 |
| repay calls/attempted/written/inliers | 8 / 0 / 0 / 0 | 56 / 88 / 64 / 15,224 | 全 0 |
| enrich_budget_stopped(被跳过的新匹配尝试) | **8,339** | **4,309** | 0 |
| enrich_targeted_tracks / scored | 82,998 / 4,049(4.9%) | 60,974 / 2,579(4.2%) | 0 / 0 |
| upgrade eligible/attempted/accepted | 69,914 / 11,607 / 4,070 | 45,940 / 6,849 / 2,333 | 70,217 / 11,884 / 4,137 · 47,102 / 6,831 / 2,269 |
| stage1_rounds / stage1_ms | 4 / 59,860 | 4 / 59,544 | 0 / ~40ms(host 回放不跑 stage1) |
| stage2_ms(设备 rounds_budget=1) | 12,543 | 12,489 | ~31,000 · ~20,300 |
| enrich_ms | 60,689(≈stage-1 窗即预算) | 60,164 | ~30ms(db 已 enriched,无事可做) |
| theta_pre_n(三角化 track 数) | 93,360 | 64,765 | 93,268–93,274 · 65,927–65,929 |
| 交付点数 | 93,356(ply 92,849) | 64,749(ply 64,392) | 93,268–93,274 · 65,927–65,929 |

计数器语义一手来源:`pocketworld/vendor/aether_ffi/include/aether_sfm_c.h`(enrich_budget_stopped = "fresh match attempts skipped after the budget was exhausted";预算 unset = auto/stage-1 窗;rematch = finalize 饿帧时域窗补配;repay = 拍摄空闲还债,thermal serious/critical 直接拒;retry = rc=7 退避重试)。

**host 计数器全 0 的原因**:host 回放消费的是设备**终局** db(已含设备 enrich 写入),回放路径不重跑 enrich/rematch/repay(enrich_targeted_tracks=0)。所以 host≈"同证据、零饿死"的对照——这正是归因所需的对照组。

## ② 逐计数器对账:谁能解释缺点的出生?

| 闸 | 砍掉了什么 | 能否解释 E6 缺的 8,538/15,694 点 |
|---|---|---|
| 热闸 K6(live 窗 12→6) | Δf∈[7,12] 的 live 配对推迟到 finalize | ❌ 缺点仅 1.5%/6.1% 在 Δf7-12 带,且这些对**已被 rematch/repay 救回**(在 db 有 verified geometry,点仍没出生) |
| rc=7 丢命令 | 48/39 对 live 失败 | ❌ 缺点对里 21/8 对曾 fail,但全部已被救回进 db;点仍没出生。终局永久丢失的 15/17 对不在 E6 账本里(E6 只能看 db 内证据) |
| enrich 时间闸(60s) | 8,339/4,309 次新尝试 + 338/31 个 rematch 候选未清 | ❌ 被跳过的对从未进 db → E6 账本看不见它们;账本内的缺点与此闸无关 |
| repay 哑火(cap50) | 债全部推给 finalize | ❌ 同上,影响的是 db 外证据 |
| stage2 rounds_budget=1 | 设备 stage2 12.5s vs host 20–31s | ❌(弱)cap51 host 比设备多 1,163 tracks(+1.8%),cap50 反而少 86(−0.1%);符号混合,非缺点主因 |

**决定性交叉(E6 rescue_provenance,f1/f2 已核实为 0-based frame id)**:

| | cap50 缺点(15,694) | cap51 缺点(8,538) |
|---|---|---|
| Δf≤6(热闸砍不到) | 15,452(98.5%) | 8,016(93.9%) |
| Δf7-12(K6 被砍带,已救回) | 242(1.5%) | 522(6.1%) |
| Δf>12 | 0 | 0 |
| 唯一帧对数 | 499 | 263 |
| 对在最终 db 有 verified geometry | 100%(S1 口径构造性保证) | 100% |
| θ p50 / <3° 占比 | 5.93° / 14.6% | 4.27° / 24.5% |

θ 分布顺带回应铁律①:缺点集**不是掠射主导**(p50 ≈ 4–6°,<3° 仅 15–25%)——这批是健康视差的证据,单纯没被出生机制消费,掠射物理不背这口锅。

## ③ E6 账本交叉:缺点观测对 vs 被闸窗口

- 缺点的 499/263 个对,**零个**落在"从未匹配"集合(终局 db 514/324 个未匹配时域对)里——被闸掉的窗口与缺点集合**不相交**(构造性:E6 只能从 db 内 verified 对refit)。
- 反向:被 K6 制造、后被 rematch/repay 救回的 Δf7-12 对,确实贡献了 242/522 个缺点候选和 153/236 个最终注入点——救回机制在"证据层"是有效的,但救回匹配 ≠ 出生。
- rematch 账本自洽:789 候选 − 277 written = 512 ≈ 514 终局未匹配(cap50,±2);484 − 169 = 315 ≈ 324(cap51,repay 时序有小量重叠)。**遥测计数与 db 实况对上了**。

## ④ 判:饿死主凶排序(针对"db 外证据被砍",非 E6 账本)

1. **主凶 = 热闸 K6 制造债 + enrich 时间闸不清债的组合**。K6 从 frame 31/36 起把 78%/66% 的帧变成饿帧(108/74),制造 789/484 个欠配对;finalize rematch 预算名义 800 对,但**时间闸先死**(enrich_ms ≈ 60s = stage-1 窗),只清了 277/169,终局留下 514/324 个从未匹配的时域对(= K12 窗对总数的 32%/27%)。证据:rematch attempted < candidates < budget;never-matched 集中在 Δf7-12 post-throttle(404/514、203/324)。
2. **次凶 = enrich 新尝试跳过 8,339/4,309 次**(spatial revisit 类新对)。按设备实测产率(written/attempted 37–61%,57–61 inliers/对)这是数千个潜在新 verified 对的量级——但新对→新出生的转化率必须由 E20-A 实测(E19-B 已证旧对重塞=空操作,E2 先例 +158 宽基线对有效)。
3. **三号 = rc=7 永久丢失**:48→15(cap50)、39→17(cap51)对在 retry+repay+rematch 三层安全网后仍不在 db。量小但纯损失。
4. **repay 机制对拍摄节奏敏感**:cap50 8 次调用全 attempted=0(债 0 清偿),cap51 56 次调用还了 64 对(15,224 inliers)——同一机制,两种命运;repay_skipped_thermal=0 排除热拒,推测 cap50 无空闲窗/调用早于债累积(见 UNRESOLVED)。
5. **stage2 rounds_budget=1**:与 host 差 ±0.1~1.8% tracks,符号混合,不定罪。

## ⑤ 热下修法方向(铁律:热是常态,修=热下优雅降级)

| 修法 | 机制 | 代价 | 需签决? |
|---|---|---|---|
| A. rematch 债优先于新尝试 | enrich 预算内先清 starved 债(789 对 ~800 预算本可清完),清零后才花在 spatial revisit 新对上 | 新对尝试更少(8,339→更多被跳过);无墙钟代价 | 否(纯调度序,质量单调不降) |
| B. enrich 闸"降速不砍量" | 预算耗尽后不 skip,降为低占空续跑(交错提交、让出 GPU 防 rc=7),直到债清零 | finalize 墙钟 ↑(现 74s;与"拍完≤30s"方向冲突) | **是**(时间 vs 证据完整性) |
| C. rc=7 重试升级 | 对 fail streak 指数退避 + 队尾重排 + finalize 末尾冷却后最后一轮;目标终局丢失 15/17→0 | 每对多 1–2 次重试,墙钟 +秒级 | 否(可暗 A/B) |
| D. repay 债跨 session 续还 | 债账本落盘(sidecar),resume/下次空闲/finalize 前续还;修 cap50 式哑火 | 持久化+一致性工程;删拍照时账本同步 | **是**(新持久状态) |
| E. E6 那批缺点(8.5k/15.7k) | **不属于饿死战场**:归 stage-1 出生前裁决线(alias/跨边),与 Jul17 stage1-alias 并行线协调,防撞车 | — | 已有并行线 |

## 诚实申报 / UNRESOLVED

- **UNRESOLVED-1**:338/31 个未尝试 rematch 候选的具体对列表遥测不存(只有计数);但由终局 db 反推的 514/324 未匹配对与 789−277/484−169 对齐(±2/±9),计数层面已闭环。
- **UNRESOLVED-2**:cap50 repay 哑火确切原因(8 calls 全 attempted=0,非热拒)。无每调用时间戳,需设备批取证(加 repay 调用时刻遥测)。
- **UNRESOLVED-3**:cap51 设备 vs host track 差 +1,163 / cap50 −86 符号混合,stage1(4 轮 vs 0)与 stage2(1 轮 vs 满)轮次差未逐位归因;不影响本案判词(两侧都不出生 E6 缺点)。
- **口径申明**:host 回放未重跑 enrich(db 已 enriched),所以"host 无闸"对照只对**出生机制**有效,对"闸砍了多少匹配"无对照力——后者用设备 db 终局实况直接审计(db_debt_audit.json)。
- Δf 带划分用时域窗语义(K12/K6);生产 live 候选含 spatial-first 分量,Δf>12 的 spatial 对在 E6 候选里为 0,故不影响结论。
