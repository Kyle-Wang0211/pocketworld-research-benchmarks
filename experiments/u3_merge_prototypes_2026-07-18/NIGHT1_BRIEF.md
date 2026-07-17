# NIGHT1_BRIEF — 过夜第一批晨间简报

- 生成时间:2026-07-18(编排者汇编,只写文件,未 git commit)
- 铁律遵守:全部产物仅落研究 worktree `.../experiments/u3_merge_prototypes_2026-07-18/`,未碰生产代码、未 reset/clean、未动他人 dirty、未 commit(留编排者统一提交)。
- 证据强度标注约定:🟢=有实测数据/PLY/viewer 支撑;🟡=规格文档(spec,非验证实现);🔴=诚实的负面结论/未解决取舍。

---

## ① 三件产出摘要(产了什么、落在哪、关键 SHA)

### #5 median 融合 —— 🟢 有实测(PLY + viewer + 门拒统计)
子目录:`05_median_fusion/`
- `median_fusion.ply` SHA `11bcb0befd2b7ffe063fb1d7e815e6004bf3c13c6a00fd43cb03850e5c2e3d6c`(3,633 点)
- `union_baseline.ply` SHA `fdf5b105e55243d1b6599f640a2fe61727ca3c81197c56644f5304b3927d4c34`(13,488 点,逐字节复刻冻结产物,与 historical_exact 一致)
- 脚本:`median_fusion_prototype.py`(`77d650ba…`)、`compare_and_render.py`(`8fed5fa6…`)
- 报告:`run_manifest.json`(`a2f4c9f9…`)、`stats.json`(`5cad3d95…`)、`SHA256SUMS.txt`
- 峰值 RSS 1.88GB,内存安全。

### #1 U3 通道规格 —— 🟡 规格文档(spec only,未产 PLY/未跑管线)
子目录:`01_u3_channel_governance/`
- `README.md` SHA `7dec109ebb900f5017cd86208c357b35b427e78551f06367a82bf6b510bfd23e`(19362 B)
- `manifest.json` SHA `82ad5a46e614434c7fd9e85e6ef96a3870110dd1a7180823e122afc87cef3dbf`(记被审计源只读 SHA)

### #2 状态机规格 —— 🟡 规格文档 + 可跑伪实现(非真实数据验证)
子目录:`02_reversible_lifecycle/`
- `README.md` SHA `1f3cfcace7f74fdce811c29187b4ae838be67823fa2ef36ffd3e40035e841151`(16007 B)
- `state_machine_ref.py` SHA `52c66ea4361c5ddab835e4b58a70ba4bce8522488cf4f1df7ad5c8b1151fde7f`(15040 B,纯函数确定性 runnable,自检覆盖全部边、两跑字节一致)
- `manifest.json` SHA `584548aa7db7884120c125248bf1b76925aa33b3a8ba3ccf0f4e45a334c7f01f`

---

## ② 🔴 #5 椅子压扁 median 融合:到底治没治好?—— 没治好

诚实结论:**median 融合没治好椅子压扁**。它是一次无差别的 ~73% 全局抽稀,不是针对椅子的定点清除。椅子/跑步机的压扁鬼影原样保留、只是变稀;相对假阳密度反而略升;同时误杀了 ~72% 的合法地板点。

### 数据(🟢 实测)
保真锚点:union 13,488 点(SHA `fdf5b105…`,逐字节复刻)→ median 3,633 点(SHA `11bcb0be…`),总量 **−73.1%**。簇尺寸 min5/中值6/max15(min_num_pixels=5 生效)。

椅子/跑步机 ROI(X∈[0.25,1.05], Z∈[−1.70,−0.55]):

| 指标 | before(union) | after(median) | 变化 |
|---|---|---|---|
| ROI 总点 | 2,466 | 501 | −79.7% |
| ROI 非木质假阳(蓝灰=椅子涂抹) | 642 | 139 | −78.3% |
| **ROI 内假阳占比** | **26.0%** | **27.7%** | **不降反微升** |
| 好区(ROI 外地板)保留 | 11,022 | 3,132 | 仅留 28.4% |

关键对照:ROI 内假阳存活率 **21.7%(139/642)> ROI 木质地板存活率 19.8%(362/1824)** —— 椅子鬼影不但没被优先杀,反而比周围真地板活得略好。

### 根因(🟢 门拒统计 + 有官方依据的机制解释)
融合门拒:`reproj=697,153,depth=0,normal=0,pixel_locked=0`。COLMAP fusion.cc 三关里,深度误差≤1% 和法线 cos≥cos10° 两关在"已知平面 plane-sweep"下完全退化(0 拒)——每个候选被钉死在认证地板平面,测量深度/法线恒等。真 MVS 里正是这两关剔除"贴错深度的离面结构"(椅子),这里失灵。只剩 reproj≤2px 在工作,它只把同表面位置的多视测量聚簇,无法分辨真地板点 vs 被 ZNCC 误收在地板深度的椅子纹理。融合退化为「≥5 视图支持下限 + 单像素锁去重」,凡 union 阶段已拿到 ≥5 一致视图的椅子鬼影原封穿过(3,633 ≈ union 里 nviews≥5 的 3,641)。known-plane sweep 没有独立每视深度图,COLMAP 的鉴伪杠杆天然缺席。

### 用户该看的图(晨起肉眼)
- `05_median_fusion/viewer_roi_falsepos_before_after.png` ← **最直接**:那条对角蓝灰"压扁椅子"条带在 after 面板清晰依旧。
- `05_median_fusion/viewer_roi_chair_before_after.png`(ROI 真彩)
- `05_median_fusion/viewer_topdown_before_after.png`(全局俯视)

---

## ③ #1 / #2 规格要点(🟡 均为 spec,非验证实现)

### #1 U3 通道规格
- 形式化 13 个通道桶(RestoreTemporalDetail 拆 create/grow/grow-refit 三子路),每条给:①现私有门判据(精确行号)②应发的 support/opposition/occlusion 证据 ③映进 U4 `CandidateEvidence` / `AMBIGUOUS→VERIFIED→BORN` 证据图的方式。
- 三角色骨架:A 评据产出(enrich 1937 / rematch 3197 / repay 6182,只写 TVG 对不出点)、B 出生/改写(live create/grow/merge、temporal-detail create/grow/refit、track-upgrade)、C 死亡(live/finalize floater、Dart spatial_two_view_filter)。
- 🔴 自相残杀标注:#6 RestoreTemporalDetail 在 BA 后以 2°/3px 造 ~18k 近时低视差 2 视点(永不精化);#13 无条件删 frame-gap>temporalK 的远时 2 视点。两者判据都只看 provenance/frame-gap 而非几何证据 → provenance 压过 evidence 的双标。规格建议 U3 把"造"与"杀"合并成同一条 2-view-point 生命周期规则,**明确不预判裁决方向**,留继任者产候选 + 用户签决。

### #2 可逆生命周期状态机规格
- 新增 `PROVISIONAL` 试用态 + downgrade/undo 回边(`PUBLISHED→RETRACTED` 等),无硬 sink。
- 连续 support 标量 `S(t)=clamp(Σ支持−Σ反对)`,单位=独立生产帧;alias 计 0、held-out +0.5、found-ratio<0.25 按比例衰减、反对权重 1.5;promote/demote 阈值带 hysteresis 防抖。
- 明确"不是生成后删点":`publish=f(evidence_now)`,状态变因是证据图变(free-space 认证 / pose 修正 de-integration / BA outlier / found-ratio 崩),非 cleanup pass;对齐 AGENTS.md(无 source-private gate、100% 注册不动)。
- 诚实标注:照抄官方=ORB-SLAM found-ratio+3KF 试用、3DGS opacity reset、ElasticFusion free-space、BundleFusion de/re-integration、DSO immature、COLMAP 观测过滤;我方设计=具体状态集、标量形状、全部阈值/权重数字、单一 source-agnostic 路由,以及把 gate 从 3 帧放宽到 2 帧(明确弱于出处,为 cap41 稀缺妥协)。
- 🔴 限制:任务称"9 成熟系统",实际只 grounding 6 个,未凑数捏造;cap41 证据 bundle 缺 B/D 真 held-out split,真实数据上 MATURE/RETRACTED 边极少触发。**伪实现自检通过 ≠ 真实数据验证**。

---

## ④ 用户晨起该做什么(裁决清单)

1. **先肉眼看** `05_median_fusion/viewer_roi_falsepos_before_after.png` —— 确认椅子条带 after 仍在。
2. **对 #5 裁决**:median 融合作为"去过采样/去冗余"手段 accept?但对"椅子压扁"应判 **无效(reject 作为压扁解)**。要治压扁需上游动刀(二选一,均为有损/改机制,须签决):
   - 给 plane-sweep 加离面深度竞争(`depth_competition_offsets_m` 当前为空 → 填非零 offset 让椅子深度与地板深度竞争 ZNCC);
   - 或引入真正的每视独立深度图再做 COLMAP 融合。
3. **对 #1 / #2 裁决**:两者均为 🟡 规格,**accept 作为规格 / rework 方向 / reject** 三选一;规格明确未预判裁决方向,若认可需继任者产候选 PLM + 你签决后才落地。#1 的核心待裁决点 = 2-view-point「造 vs 杀」双标归属;#2 的核心待裁决点 = gate 3→2 帧放宽是否接受。

**编排者建议**:三件都还未到"可 ship"门槛。#5 是明确的负面结论(压扁未解,给出上游方向);#1/#2 是规格草案待你认可方向后才进产候选阶段。

---

## ⑤ 还没做的(留给第二批)
- #3 DSO 区间(immature point 深度区间机制预研)
- #4 Merrell 净票(去鬼层投票机制)
- #6 GLOMAP alias(跨边 alias / 出生裁决)

---

## ⑥ 待编排者统一 commit 的新文件(全绝对路径)

```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/NIGHT1_BRIEF.md

# 01_u3_channel_governance/
.../01_u3_channel_governance/README.md
.../01_u3_channel_governance/manifest.json

# 02_reversible_lifecycle/
.../02_reversible_lifecycle/README.md
.../02_reversible_lifecycle/state_machine_ref.py
.../02_reversible_lifecycle/manifest.json

# 05_median_fusion/
.../05_median_fusion/median_fusion_prototype.py
.../05_median_fusion/compare_and_render.py
.../05_median_fusion/union_baseline.ply
.../05_median_fusion/median_fusion.ply
.../05_median_fusion/run_manifest.json
.../05_median_fusion/stats.json
.../05_median_fusion/SHA256SUMS.txt
.../05_median_fusion/run.resource.log
.../05_median_fusion/run.stdout.log
.../05_median_fusion/viewer_topdown_before_after.png
.../05_median_fusion/viewer_roi_chair_before_after.png
.../05_median_fusion/viewer_roi_falsepos_before_after.png
```

(前缀 `.../` = `/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18`)
