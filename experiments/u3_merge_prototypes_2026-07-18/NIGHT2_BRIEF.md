# NIGHT2 晨间简报 — U3 合并原型第二批(4 份上游)

日期:2026-07-18 编译:过夜第二批(diagnostic-only,未 git commit,未碰生产代码)
根目录:`/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/`

> 🔴 全部为**规格/诊断原型**,不等于已验证的生产实现。所有候选**未自批准**,只出脚本/数字/viewer/manifest+SHA。签决方向本简报不预判。

---

## ① 每件产出 + 子目录 + 关键 SHA

| # | 主题 | 子目录 | 核心产物(关键 SHA-256 前 12) | 证据强度 |
|---|---|---|---|---|
| #3 | DSO 逆深度区间成熟判据 | `03_dso_interval/` | `dso_interval_gate.py` `5f88c41b0ff7`;`gate_stats.json` `8734ebb3d909`;`tracks.npz` `7243ce97b7c0`;viewer `9718e6fabd70` | 🟢几何段强(数学恒等式+逐点);🔴光度探针 INCONCLUSIVE |
| #4 | Merrell 净票(support − free-space 反对) | `04_merrell_netvote/` | `merrell_netvote_prototype.py` `e1b0794ade32`;`netvote_candidates.ply` `75c4a15c69cd`;`stats.json` `1716d3f8e988`;viewer `e449fb6e01fc`;零删除对照 `roi_all.ply`=`roi_netvote_survivors.ply`=`efd729477d73` | 🟢强(support 逐字节校验 union;5 张设备端 L1 深度图做反证) |
| #6 | GLOMAP 同图多特征 alias 触发器 | `06_glomap_alias/` | `build_tracks_alias.py` `4dca4870db2d`;`tracks_summary.json` `7a018caba211`;`u3_site_candidates.jsonl` `b22c25501d69`;overlay `41f9842ce1ea` | 🟢强(源码可证 track 重建;空间统计 z=12.1) |
| #7 | 离面深度竞争(诊断) | `07_offplane_depth_competition/` | `offplane_depth_competition.py` `4a4d6ff8e57e`;`decision_sweep.json` `d4a93918926`;`stats.json` `691deb726620`;3 张 viewer(真彩 `4a134df4757e`) | 🟢强(机制本存 pinned 源;0/3211 逐位复现) |

内存自检:#3 主 0.13GB/#3 探针 1.34GB/#4 0.09GB/#7 1.80GB,均 <6GB 守卫,4K 图串行加载后释放。全部确定性(#4 两跑字节一致)。

---

## ② 核心收敛结论 — 下游规则 vs 上游竞争,能不能治椅子压扁?

**数据判决:下游删除规则(#4 净票 / 前批 #5 median 融合)都治不了 plane-sweep 椅子压扁假阳;上游离面深度竞争(#7 诊断)能打椅子但作地板出生门太钝,同门槛下误伤 ~70% 真地板。四路独立实验一致收敛:根因在上游缺每视 free-space/opposition 反证证据,不是任何下游过滤门。**

逐条数据:

- **#4 Merrell 净票 —— 对椅子判死 0/515(0.0%)。** 椅子压扁点携强 support(clique 中位 4);5 张设备端 L1 深度图对每个压扁点最多给 1 张 free-space 反对,多数把压扁点看成 occlusion(藏在真椅子后,Merrell 论文明确拒绝定罪)。净票判死需反对 > support(≥4 张反对),结构性不可能。整 ROI 2466 点净票删 0。`roi_all.ply` 与 `roi_netvote_survivors.ply` 字节相同(104,076)即零删除铁证。
  - 但 #4 作**去误杀护栏**有效:ROI 外弱纹理真地板误杀 364/364 全救活(support 中位 5 vs 反对 1)。
- **#5 median 融合(前批)—— 干净地板保留仅 28%,同样烂。**(#7 复核对齐此数)
- **#7 离面深度竞争 —— 椅子假阳杀灭 92.1%(642→51 born),但代价:ROI 真地板保留仅 23.8%、ROI 外干净地板保留 30.9%(69% 被误留洞)。** `decision_sweep.json` 全参扫(view 规则×方向×margin 0.02–0.20)最高分离积仅 **0.41**;无任何操作点能把椅子和干净地板分开。根因=**最坏地板优势 `floor_ncc − max(competitor_ncc)` 分布重叠**:干净地板中位 −0.027(连真地板自身地板深度都不是 ZNCC 唯一极大)、椅子假阳中位 −0.049,几乎完全重叠。物理根因=低视差+木纹重复纹理自相似(记忆里 doublewall 的 σ_depth 歧义)。逐 offset 归因:最频繁"胜出"备选是 +0.50m(591 中 123),半米外平面能压过地板 = 重复纹理 alias 光度巧合,非真结构。

**综合裁决(留用户签决,不预判):** 真正修法需**独立的每视深度/遮挡证据**(free-space carving / per-view 深度图 / opposition 票),让"贴错深度"在某些视产生反对再被消费——正是前批 #5 指出的缺口(plane-sweep 候选无 free-space/opposition 证据)。光度平行平面竞赛和下游 support 过滤都绕不过这个上游空档。

---

## ③ #3 DSO 区间对低视差鬼点的扣留效果

**🔴 证伪:DSO 逆深度区间门抓不住这些鬼点,"几何区间扣住高视差鬼点"假设不成立。**

- 几何恒等式:`w_rel≤tau ⟺ alpha≥arcsin(sigma_px/(f·tau))` → 几何区间门在数学上**就是**一个亚 2° 角度门。4K(f=2558.97px)下 2° 视差逆深度精度已达 ~1.1%(sigma=1px)。
- 所有 6 组 (sigma,tau) 配置 `dso_only_held=0`:DSO 几何门等价角(0.11°–1.34°)恒低于固定 2° 门,**扣不住任何 2° 门放行的点**,只会更宽松地多产 sub-2° 点。viewer 图上无红点即肉眼版。
- 抓 floater 严格更差:固定 2° 门扣 8.6%(2-view 内 19.9%),DSO 几何门只扣 2.6%–6.0%。
- median-17° 仍错的点视差高→几何区间**窄**→照样放行。2-view 视差中位 5.9°、仅 12.9% <2°,低视差不是判别量。
- 光度区间探针:单射线块匹配 ZNCC 曲线逐 bin 剧烈抖动,落回分辨率地板,**INCONCLUSIVE 不据此下结论**。但前批 §7.5 已正经测过 plane-sweep 鬼点光度区间也窄(floor 假设 8/10 以 ≥0.164 中位 ZNCC 击败抬高假设)→ 光度单射线区间同样扣不住。
- **方向反转警告:** 区间机制对 SfM 唯一真实作用是按"实际逆深度精度"决定出生,会把 sub-2° 但 4K 下几何足够精的点判为**可出生**(放宽而非收紧)。是否可取需签决。

---

## ④ #6 alias 与鬼层的关联度

**弱体量、强空间特异 —— alias 无法当鬼层总闸,但精准点亮椅子 ROI,适合做出生期站点身份标记。**

- 全局 alias 极稀少:243 条(占 track 0.25%)。全局 alias 地板带占比 11.9% **低于**生产云基率 16.1%,双墙(低视差深度噪声壳)无 alias 信号 → **alias 解释不了整个鬼层/双墙**。
- 但 alias 是强空间特异信号:椅子压扁 ROI 富集 **3.73×**(28.0% vs 基率 7.50%,二项 z=12.1 极显著);ROI 内 alias 三角化很紧(spread 中位 0.016m vs ROI 外 0.047m),23.5% 落地板带。alias 点贴重建面(最近邻中位 1.46cm,88.5% 在 5cm 内)=真点非飞点。
- 典型候选 [0.55,−0.21,−1.19]:21 观测/17 图,4 张图各贡献 2 特征塌进同 track = 教科书式重复纹理 alias,恰是 #5/#4 所指"强 support 无反证、下游杀不掉"的过支持鬼团。
- **定位:** alias 是一个**出生前 observation-site 身份标记**,补 #5 证明的"plane-sweep 候选无每视深度图→无 free-space/opposition 反证"空档。`u3_site_candidates.jsonl` 已出 243 条候选(high 68/mid 13/low 162),带来源图+优先级,`u3_action=mark_observation_site_candidate`。是否采纳为出生前裁决门需签决。

---

## ⑤ 用户晨起看哪几张图 + 每项 accept/rework/reject 建议

**优先看图(4 张,按信息密度排序):**

1. `07_offplane_depth_competition/viewer_roi_truecolor_before_after.png` — 椅子压扁真彩前后。看 AFTER 蓝×留洞铺满整个 ROI 及远处真地板 = 深度竞争作出生门的代价一目了然。
2. `07_offplane_depth_competition/viewer_clean_floor_retention.png` — 干净地板保留仅 31%,证明无操作点能分开椅子与地板。
3. `04_merrell_netvote/viewer_netvote_panels.png` — 四联图:A 全景/B 椅子净票 0 删/C 椅子一票定罪 459/D 真点误杀救回 364。一眼看清净票"救误杀有效、杀椅子无效"。
4. `06_glomap_alias/overlay_cloud_alias.ply`(点云查看器)或 `03_dso_interval/viewer_gate_topdown_and_roi.png`(图上无红点=DSO 扣留=0)。

**每项建议(仅建议,待签决):**

- **#3 DSO 区间:REJECT 作鬼点扣留门**(数学证伪,方向反转会放宽出生)。几何段结论强、可归档;光度探针 rework(需单应 warp,当前单射线不足以下结论)。
- **#4 Merrell 净票:ACCEPT 作"去误杀护栏"(救真地板),REJECT 作椅子压扁解。** 二义分开签决。
- **#6 alias 标记:ACCEPT-with-signoff 作出生前 observation-site 身份标记候选**(强空间特异,补上游反证空档);REJECT 作鬼层总闸(弱体量)。需编排者/用户签决是否入 U3 出生前裁决门。
- **#7 离面深度竞争:REJECT 作 cap50 地板出生门**(认证 margin 下误洞 ~70% 真地板)。诊断价值强、归档为"下游光度竞赛治不了压扁"的定案证据。

**跨批统一信号:** 修压扁必须上游动刀,给 plane-sweep 候选补 per-view free-space/opposition 证据(#6 alias 站点标记 + 每视深度图),而非下游过滤或光度平行平面竞赛。

---

## ⑥ 全部待 commit 新文件(绝对路径)

### 03_dso_interval/
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/README.md
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/SHA256SUMS.txt
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/dso_interval_gate.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/gate_stats.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/manifest.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/photometric_interval_probe.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/photometric_probe.jsonl
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/photometric_probe_summary.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/probe.resource.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/probe.stdout.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/probe_manifest.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/run.resource.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/run.stdout.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/tracks.npz
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/viewer_gate_topdown_and_roi.png
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/viewer_photometric_profiles.png
```

### 04_merrell_netvote/
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/README.md
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/SHA256SUMS.txt
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/merrell_netvote_prototype.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/netvote_candidates.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/probe_depth_calib.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/render_viewer.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/rescued_true_floor.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/roi_all.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/roi_netvote_survivors.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/stats.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/viewer_netvote_panels.png
```

### 06_glomap_alias/
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/alias_points.csv
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/alias_points.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/alias_tracks.jsonl
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/build_tracks_alias.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/make_overlay_and_manifest.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/manifest_sha256.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/overlay_cloud_alias.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/tracks_summary.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias/u3_site_candidates.jsonl
```

### 07_offplane_depth_competition/
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/README.md
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/SHA256SUMS.txt
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/decision_sweep.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/decision_sweep.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/depth_competition.jsonl
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/manifest.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/offplane_depth_competition.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/render_viewers.py
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/roi_all_scored.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/roi_holes_pinned.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/roi_survivors_pinned.ply
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/run.resource.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/run.stdout.log
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/stats.json
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/viewer_clean_floor_retention.png
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/viewer_roi_falsepos_holes.png
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/viewer_roi_truecolor_before_after.png
```

### 本简报
```
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/NIGHT2_BRIEF.md
```

> 提交由编排者统一执行(本批未 git commit,未 reset/clean,未动他人 dirty)。
