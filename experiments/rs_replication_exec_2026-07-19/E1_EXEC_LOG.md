# E1 执行批日志(rs_replication_exec_2026-07-19)

- 日期:2026-07-18(执行批 E1 汇编)
- 范围:仅研究 worktree 落盘;**未改生产代码、未 git commit/reset/clean、未动他人 dirty**(git status 确认本目录整体 untracked `??`,由编排者统一提交)。
- 环境:python3.11;vm_stat 自检 free ≈450MB(active/inactive 各 ~5.5GB),只读+落盘作业无压力。
- 上游四份输入:S1 原型报告、Q8 env 核查、R1 联网闭环 addendum、DECISIONS_BY_REPLICATION 裁决记录。

---

## ① S1 候选:四把尺子对账(质量无损硬门)

**规则**(裁决 Q1=案A,一把尺子替代 #6 造 + #13 按出身删):恰 2 已验证观测的点 → structure-only DLT refit(生产位姿全冻)→ 裁负深度 / refit 后 reproj>3px(生产 temporal-detail 门)/ θ<2°(生产 floater 门);provenance-blind;幸存者保留生产位置+颜色。

**同 gauge 前置**(禁 Sim3):cap50 rotation-only 0.11°、cap51 0.08°,对齐均不降残差 → PLY 系==meta 位姿系,渲染/统计零对齐。

| 尺子 | cap50 | cap51 | 判定 |
|---|---|---|---|
| 点数 | 92,849→92,312(−537,−0.58%;535 θ<2° + 2 reproj) | 64,392→64,143(−249,−0.39%) | ✅ 近零损,全部有裁决理由 |
| 厚度 | med-cell 0.04843→0.04844m 不变 | med 0.011802→0.011726m 微改善;p90 0.04336→0.04236 改善 | ✅ 不劣化 |
| 正确覆盖 | −0.14%(裁的是离面/低视差点) | −0.14% | ✅ floorband 图肉眼一致 |
| 墙钟 | host 代理 ≈1s 量级 | 同 | ⚠️ 设备 refit 墙钟未实测(已声明) |

附加检查:椅子 ROI(cap50)near-floor 93→93、y 分位不变 → **无压扁恶化**(符合 07-19 方向锚:被遮挡留洞=正确几何,不无中生有)。

**质量门自评:过**(厚度不劣化 + 覆盖近零损 + 无新增浮点)。
**诚实边界:候选 ≠ 已进产品。** 本轮仅 cap50+cap51 两场景;**四场景全过 + 用户同 gauge 真彩肉眼确认才算通过**,且:
- 原型从 sfm_live.db 观测空间恢复证据,非生产 finalize 逐字节复刻;
- cap50 80,573 / cap51 58,781 点观测恢复<2 帧,原样保留未裁决(2-view 占比是下限估计);
- 3px 支持半径只会偏保守(误吸成 multiview→保留),永不多裁;
- 设备端 refit 墙钟须实测后才谈落地。

**用户该看的同 gauge 图**(每次进步必开网页并排对比,compare.html?right=候选 ply):
- 候选 PLY:`S1_twoview_lifecycle/cap50/s1_caseA_cap50.ply`(c4fc0b40…)、`S1_twoview_lifecycle/cap51/s1_caseA_cap51.ply`(81428bfe…);SHA 全在 `S1_twoview_lifecycle/SHA256SUMS.txt`
- 真彩并排(俯视+立面):`S1_twoview_lifecycle/cap50/compare_truecolor_cap50.png`、`cap51/compare_truecolor_cap51.png`
- verdict diff(绿=kept 2-view/红=culled/灰=其余):`cap50/diff_verdict_cap50.png` + `diff_cap50.ply`;cap51 同构
- 地板带特写:`cap50/floorband_culls_cap50.png`、`cap51/floorband_culls_cap51.png`
- rescue 覆盖(仅呈报,**未注入**):`cap50/rescue_overlay_cap50.png` + `rescue_candidates_cap50.ply`(48,226 对通过 / 15,694 点距生产云>2cm);cap51:28,224 / 8,538
- 数字:`S1_twoview_lifecycle/stats_all.json`、各 `cap*/stats.json`

## ② Q8 矛盾清单(装机 env 核实,产物 `Q8_env_audit.md`)

装机臂实测(AetherARKitPlugin.swift L78-118,git 干净):设 7 项(TEMPORAL_ONLY=1 / LIVE_CAND_K_HOT=6 / TRACK_UPGRADE=1 / ENRICH_TARGETED=1 / ENRICH_PAIR_CAP=300 / STAGE1_ROUNDS_CAP=4 / GHOST_MASK=1),注释关停 3 行(TD_GROW_REFIT / FRAG_MERGE / FRAG_MERGE_REPROJ_PX)。E worktree(shutter-v2)setenv 面逐行相同,**无 env 漂移**。

矛盾/红标:
1. 🔴 **FRAG_MERGE 记忆锚打架**:07-11 "签决 ship(cap45 0.0059)" vs cap47 法医判死维持。装机现实=OFF,**以 cap47 为准**;凡引用 cap45 配方数字须显式补 FRAG_MERGE=1+4px,否则对不上账。
2. ⚠️ **TEMPORAL_ONLY 是反向开关**:unset 时 C++ 走未验证 spatial-first;host 复现漏设即非装机臂(S1 复现口径已按此对齐)。
3. ⚠️ **K_HOT=6 口径不同源**:C++ 注释判 ship DISABLED(+2.4% 超带),Swift 注释引另一组带内数据后 opt-in;且启 spatial-first 前须重跑热调速 A/B。
4. ⚠️ **"A 判 OFF" 无法从代码单方面对号**具体开关(UNRESOLVED 红线不猜),由编排者按 ABCDE 权威文件对号。

## ③ UNRESOLVED 剩余清单

- **Q3**(全 MVS free-space 重投资):RS 无可证做法 → 暂缓,核心签决留用户。
- **Q5**(rounds 4→3):RS 无证据;有损须九门签决;B 未落地 → 暂缓。
- **Q6**(改热闸):暂缓;闸内加码免签先行(db-only SHA 一致为 accept 硬条件)。
- **Q8 归属**:env 核实已完成(见②),矛盾呈用户,不私自扳开关。
- **RS 房间级椅下/床下洞截图证据**:检索零命中,维持 UNRESOLVED 不硬凑(物体级已 SUPPORTED:engineering.com 遮挡立柱缺失一手实测)。
- **RS mobile 内部机制**(拍摄期旧点是否重定位/删除):永久 UNRESOLVED 红线,全文未据其裁决。
- **S1 <2 帧观测点**(cap50 80,573 / cap51 58,781):未裁决原样保留,待生产 finalize 路径对齐后重估。
- **rescue 注入与否**:单独裁决留用户(生产 colorize+身份路径不可复现,当前仅呈报)。
- **设备端 refit 墙钟**:host 代理 ≈1s,真机未实测。

## ④ 下一执行批建议(E2)

1. **S3 时间刀(先行,证据已足)**:
   - 还债闸内加码(Q6 免签部分):live 空闲还债通道内提额,accept 硬条件=db-only SHA 一致;不动热闸本体。
   - LAPACK 收尾 A16 实测:记忆定案"可安全搬"(两行 CMake,运行时开关已在库),Mac −65% 幅度须 A16 实测定价;热受控计时(同进程 back-to-back,单次墙钟 ±30% 不可信)。
2. **S4 显示层 color/quality 双模式**(Q7 裁决落地):RS mobile 仅双模式 [VERIFIED],无 track-length 滑杆(禁滑杆红线保住);纯显示层,数据全量不动。
3. **S1 收尾依赖**:用户 compare.html 肉眼批准 cap50/cap51 → 补足四场景 → rescue 单独裁决 → 真机 refit 墙钟,之后才谈装机(Q4 两态属 07-11 签核反转,呈报包出齐+肉眼确认才装机)。

## ⑤ 待 commit 文件全清单(git status:目录整体 untracked,编排者统一提交)

根:`experiments/rs_replication_exec_2026-07-19/`
```
DECISIONS_BY_REPLICATION.md
E1_EXEC_LOG.md            ← 本文件
Q8_env_audit.md
R1_addendum_unresolved_closure.md
S1_twoview_lifecycle/README.md
S1_twoview_lifecycle/SHA256SUMS.txt
S1_twoview_lifecycle/build_candidate.py
S1_twoview_lifecycle/probe_gauge.py
S1_twoview_lifecycle/probe_gauge_cap.py
S1_twoview_lifecycle/render_views.py
S1_twoview_lifecycle/stats_all.json
S1_twoview_lifecycle/cap50/compare_truecolor_cap50.png
S1_twoview_lifecycle/cap50/diff_cap50.ply
S1_twoview_lifecycle/cap50/diff_verdict_cap50.png
S1_twoview_lifecycle/cap50/floorband_culls_cap50.png
S1_twoview_lifecycle/cap50/probe_R.npy
S1_twoview_lifecycle/cap50/probe_R_noT.npy
S1_twoview_lifecycle/cap50/probe_t.npy
S1_twoview_lifecycle/cap50/render_arrays.npz
S1_twoview_lifecycle/cap50/rescue_candidates_cap50.ply
S1_twoview_lifecycle/cap50/rescue_overlay_cap50.png
S1_twoview_lifecycle/cap50/s1_caseA_cap50.ply
S1_twoview_lifecycle/cap50/stats.json
S1_twoview_lifecycle/cap51/compare_truecolor_cap51.png
S1_twoview_lifecycle/cap51/diff_cap51.ply
S1_twoview_lifecycle/cap51/diff_verdict_cap51.png
S1_twoview_lifecycle/cap51/floorband_culls_cap51.png
S1_twoview_lifecycle/cap51/probe_R.npy
S1_twoview_lifecycle/cap51/probe_R_noT.npy
S1_twoview_lifecycle/cap51/probe_t.npy
S1_twoview_lifecycle/cap51/render_arrays.npz
S1_twoview_lifecycle/cap51/rescue_candidates_cap51.ply
S1_twoview_lifecycle/cap51/rescue_overlay_cap51.png
S1_twoview_lifecycle/cap51/s1_caseA_cap51.ply
S1_twoview_lifecycle/cap51/stats.json
```
备注:`.npy`/`.npz`/`render_arrays` 为中间产物,是否入库由编排者定(建议至少入 PLY/PNG/json/py/md+SHA256SUMS)。
