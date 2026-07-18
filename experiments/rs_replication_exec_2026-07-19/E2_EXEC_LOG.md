# E2_EXEC_LOG — E2 批(拖尾法医 / RS 2px 门 / RS 镜面证据 / S1 cap40-41 补齐)

日期:2026-07-19(编排批次)。产物全部落在本目录子目录,未动生产、未 git commit(commit 由编排者统一执行)。同 gauge 禁 Sim3;RS mobile 内部实现保持 UNRESOLVED;vm_stat 自检各子任务均通过。SHA 见各子目录 `SHA256SUMS.txt`。

---

## ① 拖尾判决

### 我们的拖尾在哪、多少、指纹(E2-A 法医,`TRAILS_forensics/`)

- **量**:cap50 候选 **1,004 / 92,849(1.08%)**(S_behind 325 / S_below 161 / S_streak 86(9 串)/ S_out 532;126 簇 + 102 孤点);cap51 **525 / 64,392(0.82%)**。
- **指纹**(cap50 trail vs clean):局部密度中位 **7 vs 398**;tri-angle 中位 **5.7° vs 17.6°**——低视差尾部坐实。"无可恢复观测"两组同为 ~65%,**不是**判别指纹。
- **热区四处(cap50)**:
  1. 墙外长尾 Z −4.3→−9.7:玻璃窗格倒影三角化到玻璃后(cluster06 实锤=窗玻璃里的房间倒影);**但 Z≈−9.1 簇是真门洞外邻室货架=真几何**——墙外是虚点+真景混合体,**不能一刀切**;
  2. **地板下反射层** 161 点(高光木地板把家具脚反射打到地板下 10-15cm,cluster01/04 实锤)=独立于 47 号双层地板的**另一病理**;
  3. 黑钢琴漆柜面后的百叶窗倒影;
  4. 缎面被子(n=205 簇,AMB:高光可形变织物)。
- **误报率(单评审诚实抽查)**:cap50 明确 FP 15%(模糊上界 40%);cap51 FP 35%(上界 60%,主因=白墙/天花弱纹理浮点,非镜面拖尾)。簇级 cap50 审 10 簇 3 FP。
- **裁决:此检测器是取证探照灯,不是裁剪刀。** 真要裁必须走 RS-faithful 机制 + 用户签决。

### 2.0px 是不是 RS 零拖尾的机制答案?——**不是(大部分否证)**(E2-B,`TRAILS_rs2px_gate/`)

基线 = rebuilt@4px(90,755 点,唯一变量=门值),v2 track 空间方法(v1 已自否证归档 `_v1_deprecated_pointanchor/`,4px 控制组自检 0 裁):

| 档 | 存活点 | 拖尾杀灭 | 真面误杀 | 地板覆盖 | 判 |
|---|---|---|---|---|---|
| 4px(现状) | 90,755 | — | — | 2,111 格基线 | 现认证 |
| 3px | 85,083 | 部分 | 有 | **−3.6%** | 非免费,不推荐 |
| 2px(RS 说法) | 71,995(−20.7%) | SIG_ISO 30.5% / hull 外>1m 37-42% | **密集真面核心 17.5%**,红点遍布墙面地板 | **−14.1%**(厚度仅 −7.8%) | **否决** |

- 选择性仅 ~1.7–2×;远拖尾杀不净(hull 外>1m 1,604→962,仍 ~2× 生产云的 489)。
- **意外主发现**:生产云(tri-angle 2°+floater 门)远拖尾 489 vs 纯 reproj@4px 的 1,604——**角度/出生拓扑门的拖尾压制力 ~3.3×,远强于 4px→2px**。拖尾歼灭杠杆在角度/track 拓扑层(与 stage-1"产跨边+定出生"、E2-A 合流),不在全局收紧 reproj。
- 误杀重灾=长 track(per-obs 残差随 track 长升:2-view 中位 0.81px,10+ obs 2.86px/p90 10.3px),与"弱纹理点 reproj 偏大"记忆一致。
- 操作点曲线无甜点(`operating_curve.png`)。**推荐档:维持 4px**;若动 reproj 只考虑分区/分签名门(hull 外/孤立点收紧),须另立实验+签决。质量无损立场:2.0px/3px 均不过无损硬门,照抄=否决。

### RS 侧证据链闭环(E2-C,`TRAILS_rs_evidence/`,README SHA 6ce16563…97fae)

- RS/RC 被报告的镜面失败形态只有:**洞 / 整体错位 / 镜像世界**(Whelan et al. SIGGRAPH 2018 一手 [B]);**沿视线 smear 零报告 [D 负证据]**。
- 官方:镜面预期"不出点",解法=喷剂/mask [A/C];Alignment 官方 reproj 上限是 **3px 不是 2px**(2px 无官方出处);Ultra 档官方自认含噪点 [A]。
- 机制:RS 零 smear 是三道闸构造性结果——多视 tie-point 出生权 + reproj≤3px + 灵敏度上游滤伪;smear 归属逐视 plane-sweep 稠密深度的歧义病,稀疏三角化+BA 构造性不产。
- 两记忆锚裁决:"RS 对镜面本质无解"(召回维)与"RS 完全没拖尾"(伪影形态维)**正交不矛盾**。
- **三线合流结论:复刻靶心是"点必须赢得存在权"的出生纪律(角度/track 拓扑),不是收紧全局 reproj,也不是事后裁剪刀。** 与 07-19 记忆锚"椅子观测出生在椅子=正确几何"一致。

---

## ② S1 四场景总账(四把尺子 × 4 cap)

方法:db two_view_geometries 观测恢复 + 冻结生产精化位姿 refit,3px 支持门 + θ2° 门,provenance-blind。

| | cap50 | cap51 | cap40 | cap41 |
|---|---|---|---|---|
| 有效性 | ✅ | ✅ | 🔴 **INVALID** | 🔴 **INVALID** |
| 尺1 点数 | 92,849→92,312(−0.58%) | 64,392→64,143(−0.39%) | (−3,存档) | (−5,存档) |
| 裁决构成 | θ<2° 535 + reproj>3px 2 | θ<2° 247 + reproj>3px 2 | θ 3 | θ 5 |
| 尺2 地板厚(cell p90-p10 中位) | 0.04843→0.04844(持平) | 0.01180→0.01173(持平) | n/a | n/a |
| 尺3 覆盖(2cm 格) | 2,185→2,182(−0.14%) | 4,369→4,363(−0.14%) | 2,420→2,420 | 818→818 |
| 尺4 墙钟 | host 代理 ~1.0s(恢复0.9+refit 0.1;非设备数) | 同左量级 | — | — |
| obs 可恢复率 | 65% 不可恢复(诚实保留) | 类似 | **99.0% 不可恢复** | 88.0% 不可恢复 |

**cap40/41 INVALID 根因(非脚本问题)**:pulled db 匹配与 meta 精化位姿几何不一致(Sampson p50 15.7/14.2px vs cap50 对照 1.4px;track DLT reproj 14.6/17.9px vs cap50 0.56px)。穷举位姿分配证明**非索引 bug**。根因指向 finalize 路径差异:cap50/51 是 `phase1: live_reuse`(位姿与 live db 连续),cap40/41 是全量重解(solve_ms 57.6s/25.3s)。另 cap41 db mtime(07-17)晚于 ply/meta(07-10),不排除被后续 resume 触碰。诊断落盘 `S1_twoview_lifecycle/cap4{0,1}/db_meta_consistency.json`,stats.json 已标 `valid_for_acceptance: false`。
**四场景验收现状:有效场景 = cap50/51 两个。** cap50/51 上 S1 裁决四把尺子全部带内(点数 <0.6%、厚度/覆盖 ~持平),质量无损立场成立。

---

## ③ 用户肉眼审查入口

服务器:repo 根(pocketworld-repro-contract-20260714)起 `python3.11 -m http.server 8123`,基址 `http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html`。

**compare_any.html 参数(逐条)**:
- 拖尾高亮 cap50(拖尾红/其余真彩):`?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=TRAILS_forensics/cap50/trail_highlight_cap50.ply`
- 拖尾高亮 cap51:`?right=TRAILS_forensics/cap51/trail_highlight_cap51.ply`(left 同上换 cap51 生产 ply)
- 仅拖尾点:`?right=TRAILS_forensics/cap50/trails_only_cap50.ply`
- 2px 候选 vs 4px 基线:`?left=TRAILS_rs2px_gate/ours4px_cap50.ply&right=TRAILS_rs2px_gate/rs2px_cap50.ply`
- 2px 杀掉的点(看误杀分布):`?left=TRAILS_rs2px_gate/ours4px_cap50.ply&right=TRAILS_rs2px_gate/diff_killedby2px_cap50.ply`
- S1 候选 vs 生产:`?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=S1_twoview_lifecycle/cap50/s1_caseA_cap50.ply`(cap51 同理)

**PNG 直看**(相对本目录):
- `TRAILS_forensics/{cap50,cap51}/trails_topview_elev_<cap>.png`、`fingerprint_dists_<cap>.png`、`audit_rand_sheet.png`、`audit_crops/`+`audit_verdicts.json`
- `TRAILS_rs2px_gate/compare_truecolor_top.png`、`compare_truecolor_elev.png`、`diff_killedby2px.png`、`operating_curve.png`
- `S1_twoview_lifecycle/{cap40,cap41,cap50,cap51}/` 各 4×PNG(真彩并排/verdict diff/rescue/floorband)

---

## ④ 下一步建议

1. **主线定向**:拖尾歼灭走**出生纪律层**(tri-angle/track 拓扑,与 stage-1"产跨边+定出生"合流),不做全局 reproj 收紧;E2-A 检测器只做取证/度量,不做裁剪。
2. **cap40/41 解除阻塞**(编排者/用户裁决):(a) 真机重跑一次 live_reuse finalize 后重 pull(推荐);(b) 重拍;(c) pulled db 自解位姿(破同 gauge 硬门,不建议)。
3. **地板下反射层**(161 点,独立病理)可考虑窄门:全局地板平面下 >10cm + 反射几何签名,属"分区/分签名门"范畴,须另立实验+四把尺子+签决。
4. 若探索分签名 reproj 门(hull 外/孤立点收紧),另立实验,不与主线混。
5. 用户肉眼批准流程:按 ③ 链接并排看拖尾高亮与 2px diff,确认"2px 否决 + 出生纪律主线"裁决。

## ⑤ 待 commit 清单(编排者统一提交,本批零 git 操作)

- `TRAILS_forensics/`(99 文件,SHA256SUMS.txt 已记):README.md、{cap50,cap51}/trail_stats.json、trail_highlight_*.ply、trails_only_*.ply、trails_topview_elev_*.png、fingerprint_dists_*.png、audit_crops/、audit_verdicts.json、audit_rand_sheet.png
- `TRAILS_rs2px_gate/`(SHA256SUMS.txt 已记):rs2px_cap50.ply、mid3px_cap50.ply、ours4px_cap50.ply、diff_killedby2px_cap50.ply、4×PNG、stats_v2.json、aux_checks.json、color_fallback.json、rs_gate_sweep_v2.py、aux_checks.py、finalize_renders.py、README.md、`_v1_deprecated_pointanchor/`
- `TRAILS_rs_evidence/README.md`(SHA 6ce1656399546f7f561714e6ebc3bd6c7acd56d5c6d7feee059f18aa6b797fae)
- `S1_twoview_lifecycle/cap40/`、`cap41/`(各:s1_caseA_*.ply、diff_*.ply、rescue_candidates_*.ply、4×PNG、stats.json〔含 valid_for_acceptance:false〕、db_meta_consistency.json、render_arrays.npz)、`run_cap40_41.py`、更新后的 `stats_all.json`、追加的 `SHA256SUMS.txt`
- 本文件 `E2_EXEC_LOG.md`
