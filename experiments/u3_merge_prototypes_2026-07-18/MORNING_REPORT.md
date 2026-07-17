# MORNING_REPORT — U0→U5 审计 + 两批半原型 + 收官分类器 合成晨报

- 生成:2026-07-18(编排者汇编)。诊断/规格性质,**未自批准任何候选进生产**。
- 过夜铁律遵守:全部产物仅落研究 worktree `.../experiments/u3_merge_prototypes_2026-07-18/`,**未碰生产代码、未 reset/clean、未动他人 dirty、未 git commit**(本批 08 留编排者统一提交;night-1/night-2 已 push)。
- 证据强度约定:🟢=实测数据/PLY/viewer/逐点信号支撑;🟡=规格文档(spec,非验证实现);🔴=诚实负面结论/未解决取舍。
- 根目录前缀 `.../` = `/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18`

---

## A. 一句话总账

**U0→U5 的整体架构不需要重新设计——唯一真正的概念缺口是「可逆状态机」(#2);生产管线里藏着约 12 条私有出点通道(temporal_detail 一路灌入约 18k 永不精化的低视差 2 视点,是最大漏网 scope),这是 U3 被低估的治理面;而椅子压扁的病根是结构性的「反证证据缺口」——plane-sweep 候选没有每视独立深度图,拿不到 free-space/opposition 反证,所以四路下游实验(#5 median / #7 离面竞赛 / #4 净票 / #8 合成分类器)全部无法在无损前提下把椅子和真地板分开。**

---

## B. 完备性判决(架构层)

判据:U0→U5 骨架能不能承载「出生—证据—改写—死亡」全生命周期,还是有真概念缺口。

- **可逆状态机(#2)= 唯一真正的架构补丁 🟡🔴**。现管线是「生成后 cleanup 删点」范式,缺一个 `publish = f(evidence_now)` 的可逆生命周期(PROVISIONAL 试用态 + downgrade/undo 回边,无硬 sink)。这是唯一一处现有 U0→U5 桶位无法表达、必须新增的概念。⚠️ 但规格自检通过 ≠ 真实数据验证;cap41 证据 bundle 缺 B/D 真 held-out split,真实数据上 MATURE/RETRACTED 边极少触发(🔴)。
- **~12 条私有出点通道 = U3 被低估的 scope 🟡**。#1 形式化了 13 个通道桶(RestoreTemporalDetail 拆 create/grow/grow-refit 三子路)。三角色骨架:A 评据产出(enrich 1937 / rematch 3197 / repay 6182,只写 TVG 不出点)、B 出生/改写(live create/grow/merge、temporal-detail create/grow/refit、track-upgrade)、C 死亡(live/finalize floater、Dart spatial_two_view_filter)。**最大漏网 = #6 RestoreTemporalDetail** 在 BA 后以 2°/3px 造约 18k 近时低视差 2 视点(永不精化),而 #13 无条件删 frame-gap>temporalK 的远时 2 视点——两条判据都只看 provenance/frame-gap 而非几何证据,是 provenance 压过 evidence 的双标。

### 并入清单(U3 应吸收的项)+ 证据来源分级
| # | 并入项 | 证据来源分级 |
|---|---|---|
| #1 | 13 通道桶治理表 + 映进 U4 `CandidateEvidence`/证据图 | 🟡 grounded-derived(精确行号锚生产源;映射方式为自研) |
| #2 | 可逆生命周期状态机(PROVISIONAL/undo/连续 support 标量) | 🟡 混合:**照抄官方**=ORB-SLAM found-ratio+3KF 试用、3DGS opacity reset、ElasticFusion free-space、BundleFusion de/re-integration、DSO immature、COLMAP 观测过滤;**自研**=状态集、标量形状、全部阈值/权重、gate 3→2 帧放宽 |
| #3 | DSO 逆深度区间**几何段**(可归档为「几何区间门=亚 2° 角门」定案) | 🟢 grounded(数学恒等式+逐点);🔴 光度探针 INCONCLUSIVE |
| #4 | Merrell 净票作「去误杀护栏」 | 🟢 grounded(support 逐字节校验 union;5 张设备端 L1 深度反证) |
| #6 | GLOMAP alias 作「出生前 observation-site 身份标记」 | 🟢 grounded(源码可证 track 重建;空间统计 z=12.1) |
| — | temporal-detail「造 vs 杀」双标 → 合并为**同一条 2-view-point 生命周期规则** | 🟡 grounded-derived;**不预判裁决方向**,留继任者产候选 + 用户签决 |

---

## C. 椅子压扁法医收官(用户最痛点)

评估宇宙统一为 3211 个 depth-scored 点(ROI 2466 = chairFP 642 + 真木地板 1824;区外干净地板 subsample 745)。逐路结论:

| 路 | 机制 | 判决 | 关键数字 | 证据 |
|---|---|---|---|---|
| **#5 median 融合** | ≥5 视图支持下限 + 单像素锁去重 | **判负**:无差别 −73% 全局抽稀,非定点清除 | ROI 内假阳占比 26.0%→27.7% 不降反微升;椅子存活率 21.7% > 真地板 19.8%;门拒 depth=0/normal=0(known-plane 下两关退化) | 🟢 |
| **07 离面深度竞争** | 平行平面 ZNCC 竞赛作出生门 | **判负**:92.1% 杀椅代价是误洞约 70% 真地板 | 椅子 642→51 born(−92%);ROI 真地板保留仅 23.8%、区外干净地板 30.9%;全参扫最高分离积仅 0.41;`floor_ncc−max(competitor)` 分布重叠(干净地板中位 −0.027 vs 椅子 −0.049)=σ_depth 歧义 | 🟢 |
| **#4 Merrell 净票** | support − free-space 反对 | **杀椅 0/515(0.0%)**;但**救误杀 364/364 优秀** | 椅子携强 support(clique 中位 4),5 张 L1 最多 1 张反对且多判 occlusion(Merrell 拒定罪);`roi_all.ply`==`roi_netvote_survivors.ply` 字节相同=零删除铁证 | 🟢 |
| **#3 DSO 区间** | 逆深度区间成熟判据 | **假设②证伪**:几何区间门 = 亚 2° 角门,held=0 | 6 组 (σ,τ) 全 `dso_only_held=0`;抓 floater 更差(2° 门扣 8.6% vs DSO 2.6–6.0%);2-view 视差中位 5.9°,仅 12.9% <2° | 🟢 几何;🔴 光度 INCONCLUSIVE |
| **#6 GLOMAP alias** | 同图多特征塌进同 track | **唯一部分信号**:ROI 富集 3.73× | 全局仅 243 条(track 0.25%),解释不了整个鬼层/双墙;但 ROI 内 28.0% vs 基率 7.50%(z=12.1),三角化紧(spread 0.016m),贴面(最近邻 1.46cm) | 🟢 |
| **#8 合成分类器** | 三信号 ensemble logistic | **PARTIAL**:统计分离但非无损可交付 | 见下 | 🟢 |

### #8 收官结果(填入)🟢🔴
- **表面**(负类=区外干净地板):分离积 0.756、AUC 0.920 —— 🔴 但含**区域混淆**,分类器学的是观测密度(系数 agreement −4.2、occlusion −2.6 主导),非椅子本身。
- **诚实**(负类=同一 ROI 内真木地板):分离积 0.514、AUC 0.810 —— 增益**是真的**:free-space opposition 在 squash 上 3.4× 富集(0.389 vs 0.115)、occlusion 2×,与 off-plane margin 组合 **显著超单信号最优 0.356(+44%)**、超 07 baseline 0.294 与 #5 median 0.28。
- 🔴 **但非干净分离**:能移除椅子压扁层的操作点(杀 81–96% chairFP)**同时误删 37–59% 的 ROI 内真地板**(wood_ret 0.40–0.63 << 0.90 无损门)。chairFP 与欠观测真地板重叠严重,判别力最终仍系于 L1 观测覆盖度。真彩 top-down viewer 直观印证:杀椅子蓝灰带的同时大片棕色真木地板一起被删。
- ⚠️ alias(#6)在此逐点分类器贡献 ≈ 0:243 条经 NN≤3cm 仅 15 命中此 union,是**区域级**信号非逐点。

### 收敛铁结论 🔴(四路 + 收官一致)
**下游已穷尽**:三信号合成把 in-ROI 分离积从 ~0.30–0.36 抬到 0.51,是下游能榨到的极限,但**达不到无损全量交付所需的洁净度**。残余重叠是**上游数据问题**——5 张 L1 深度对 coverage-edge 真地板与 chair-squash 都供证不足。**真解 = 独立的每视稠密深度 free-space(全 CasDiffMVS MVS,非 5 张 L1),让真地板拿到足够观测存活、同时对 squash 供反证。此为有损/改机制的上游动刀,需用户签决(本报告不预判方向)。**

---

## D. 用户晨起该做的裁决(逐项 accept 方向 / rework / reject + 该看哪张图)

> 全部为**建议方向**,不预判签决;标 accept 者仍需继任者产候选 + 你签决后才落地。

1. **【核心签决】椅子压扁要不要投上游真解 = 全 MVS 每视稠密深度 free-space?**
   - 现状:下游四路 + 合成分类器全部证明「无损前提下治不了」(🟢 数据齐)。
   - 建议方向:这是唯一未被证伪的路径,但属有损/改机制的重投资 → **必须签决**。
   - 先看图:`.../07_offplane_depth_competition/viewer_roi_truecolor_before_after.png`(椅子真彩前后,AFTER 蓝×留洞铺满 ROI 及远处真地板)、`.../07_offplane_depth_competition/viewer_clean_floor_retention.png`(干净地板保留仅 31%)、`.../08_combined_classifier/viewer_roi_kill_vs_keep_truecolor.png`(合成分类器 杀 vs 留 真彩;标题 CJK 显方块,计数见 classifier_report.json)。

2. **#4 净票作「去误杀护栏」→ 建议 ACCEPT 方向(二义分开签决)。**
   - ACCEPT:救 ROI 外弱纹理真地板 364/364(🟢);REJECT:作椅子压扁解(杀 0)。
   - 看图:`.../04_merrell_netvote/viewer_netvote_panels.png`(四联图:净票救误杀有效、杀椅无效)。

3. **#1 U3 通道规格 / #2 状态机规格 → 建议 accept 作规格方向、但落地否留签决。**
   - 两者均 🟡 spec,规格≠已验证实现。#1 核心待裁决 = 2-view-point「造 vs 杀」双标归属;#2 核心待裁决 = gate 3→2 帧放宽是否接受(🔴 明确弱于官方出处,为 cap41 稀缺妥协)。
   - 看文档:`.../01_u3_channel_governance/README.md`、`.../02_reversible_lifecycle/README.md`。

4. **#6 alias 作 U3「出生前 observation-site 站点触发器」→ 建议 ACCEPT-with-signoff 方向;REJECT 作鬼层总闸(弱体量)。**
   - `.../06_glomap_alias/u3_site_candidates.jsonl` 已出 243 条(high 68/mid 13/low 162),带来源图+优先级。是否入 U3 出生前裁决门需签决。
   - 看图:`.../06_glomap_alias/overlay_cloud_alias.ply`(点云查看器,ROI 精准点亮)。

5. **#3 DSO 区间 → 建议 REJECT 作鬼点扣留门(数学证伪,方向反转会放宽出生);几何段归档,光度探针 rework(需单应 warp)。**
   - 看图:`.../03_dso_interval/viewer_gate_topdown_and_roi.png`(图上无红点=DSO 扣留=0)。

---

## E. 已 bank / 本批待 commit

- **已 bank(研究仓已 push)**:
  - night-1 `d05ea9f` — median-fusion(椅子压扁 NEG)+ U3 通道治理规格 + 可逆状态机规格。
  - night-2 `0a4a384` — 证据规则原型(#3/#4/07 收敛判负,#6 部分信号)。
- **本收官批待编排者统一 commit 的新文件(仅 08_combined_classifier/ 未 tracked;加本报告)**:
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/MORNING_REPORT.md
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/README.md
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/SHA256SUMS.txt
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/classifier_report.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/combine_classifier.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/joined_points.npz
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/manifest.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/render_viewer.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/roc_like_honest_vs_confound.png
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/sweeps.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/08_combined_classifier/viewer_roi_kill_vs_keep_truecolor.png
```
> 提交由编排者统一执行。night-1/night-2 全部文件已在 `d05ea9f`/`0a4a384` 内,不重复列。

---

## F. 诚实边界

1. **规格 ≠ 已验证实现**:#1/#2 是 🟡 spec,伪实现自检通过不代表真实数据验证。#2 在 cap41 稀缺证据下 MATURE/RETRACTED 边极少触发。
2. **RS mobile 内部机制 UNRESOLVED,不作依据**:任何治法均未拿竞品内部实现当证据。
3. **所有「治不了」都有数据**:#5(门拒统计+存活率)、07(全参扫分离积 0.41+分布重叠)、#4(字节相同零删除)、#3(6 组 held=0)、#8(wood_ret 0.40–0.63 << 0.90 门),非推断。
4. **#8 表面高分是区域混淆**:0.76/AUC0.92 含 better-observed 区外负类,已剥离到诚实 0.514/0.810 并如实标注。
5. **#3 光度探针 INCONCLUSIVE**:单射线块匹配 ZNCC 逐 bin 抖动落回分辨率地板,未据此下结论。
6. **未自批准任何候选进生产**;上游真解(全 MVS 每视深度)为有损/改机制取舍,方向留用户签决,本报告不预判。
