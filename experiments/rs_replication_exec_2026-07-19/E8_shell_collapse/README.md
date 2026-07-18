# E8 壳塌缩 = 观测连通性并点(cap50 主 + cap51 验)

日期 2026-07-18(exec 目录沿用 07-19 批次)。研究产物:不改生产、不动 capture 数据、不 git commit(编排者统一提交)。

**一句话诚实结论:塌不动。观测连通性证据够不着壳的 90%+,够得着的部分主要是"壳内孪生互并"而非"壳并回真地板"——双地板带仅 −4.2%/−3.9%,厚度尺子在噪声带内(cap50 +1.3% 成分效应 / cap51 −2.1%),与 cap47 纯空间并的 −3% 同量级。病根确认在出生前(缺 alias 跨边),不在合并机制——与 stage-1 预研定案合流。**

## 方法(并≠删,全程无纯距离并)

- **基线 = v1.1 候选**(用户已批,E6 产物 = E3 存量 + 救回注入;PLY 字节身份 + E6 厚度/覆盖锚全部断言)。
- **扩展 track 图(证据边,两来源)**:
  - **A 共享验证 track**:S1 逐字节同法回收观测(逐帧投影 3px 最近已验证匹配 keypoint),两点的观测触到同一 union-find 分量 → 边。
  - **B 验证对桥**:全部过 S1 规则的验证对(cap50 48,226 / cap51 28,224,**含 G1 被排除的 <2cm 对**)反查:kp1 在 f1 / kp2 在 f2 各自 3px 内最近的投影点,两侧是不同点 → 桥边(该对的 2 个观测并入合并 track 一起受测)。
- **COLMAP Merge 全或无(源码判据)**:试并位 = track 长加权平均;**双方全部观测(+桥对观测)在试并位重投影 ≤4px 且正深度**才并;共识位 = 全观测多视 DLT(须过同一全观测测试且落在成员 bbox±1cm 包络内,否则回退加权位);边表迭代至不动点(3 轮收敛)。
- **距离只作否决**(≤5cm 辅助上限),从不产生并——见"首跑教训"。
- **硬门**:2cm 覆盖格构造性守护(并导致格清空且共识不回填 → 否决);并=观测 union,零删除,member→consensus 全量 provenance 落盘。

## 结果(四把尺子 + 壳指标,before=v1.1 → after=E8)

| 尺子 | cap50 | cap51 |
|---|---|---|
| ①点数 | 103,702 → 94,576(−9,126,−8.8%;全是并成共识,观测零删除) | 70,394 → 65,386(−5,008,−7.1%) |
| ②地板厚度 med cell p90-p10 | 0.048382 → 0.049001(**+1.28%**,成分效应见下) | 0.012159 → 0.011904(**−2.1%**) |
| ②地板厚度 p90 cell | 0.07760 → 0.07733 | 0.04342 → 0.04329 |
| ②b 墙厚代理 med cell(E8 声明尺,非认证) | 0.05226 → 0.05303(+1.5%) | 0.03576 → 0.03337(−6.7%) |
| ③覆盖 2cm 格(**硬门**) | 2,416 → 2,416(**PASS**,构造否决 18 次) | 4,567 → 4,569(**PASS +2**,否决 116 次) |
| ④墙钟(host 代理) | 观测回收 2.1s + 建边 0.1s + 并 1.6s | 1.2s + 0.0s + 0.6s |
| 双地板带(fh∈[−0.06,−0.015)) | 3,917 → 3,752(**−165,−4.2%**) | 6,880 → 6,614(**−266,−3.9%**) |
| 地板下(fh<−0.10) | 0 → 0 | 0 → 0 |
| 椅子 ROI near-floor | 93 → 91 | n/a |
| 成员位移 | p50 2.2mm / p90 15.1mm(孪生尺度) | p50 1.4mm / p90 13.0mm |

并组:cap50 6,457 组(15,583 成员;2 员组 4,881)/ cap51 3,960 组(8,968 成员)。组成分:cap50 纯存量 5,806 / 纯注入 578 / 混合 73;cap51 3,509 / 380 / 71。

## 为什么塌不动(⑤对账:碎片间到底有没有连接对)

1. **证据饥饿(主因)**:交付云 66%/72% 的存量点 **0 条可回收观测**、21%/20% 仅 1 条(与 S1 keep_unmatched_honest=87% 一致)——db 里的验证匹配够不着 live 出生的大多数点。壳带内更饿:**≥2 观测的带内点仅 99/3,917(2.5%)与 341/6,880(5.0%)**;触到任何证据边的仅 10%。
2. **够得着的连接主要是壳内孪生**:含带内成员的并组,共识 **87%/95% 仍留在带内**(cap50 97/111、cap51 211/222;并上真地板的只有 13/11 组)——连接对连的是"壳里的重复出生",不是"壳↔真地板"。
3. **跨层并被 4px 全或无正确拒绝**(44%/47% 尝试死于 reproj>4px):两层各自 4px 自洽,层间 2-3.5cm 深度差在本场景下折合 >4px——**这正是 COLMAP/生产当初就没把它们并起来的原因**。合并机制没有病;壳的病根在出生前。
4. **cap47 对账**:纯空间并 −3% 判死;本法(连通性前提)带 −4%、厚度 ±2% 内——同量级。差别在本法零误伤(硬门全过、below-floor 0、覆盖不掉),但**增益不配作为交付层**。
5. **战略合流**:与 stage-1 预研定案一致——"鬼层不自愈 = 缺 alias 跨边,非缺合并机制;最小形态 = 产跨边 + 定出生"。E8 用实测把"事后并"这条路的天花板钉死了:**塌壳须在出生前裁决,事后并救不了**。

厚度成分效应审计(逐格对账):成员未变的被测格 **181/181、368/368 全部 spread 逐位相同**;被并触及的格 140:62 / 270:115 变厚:变薄,med +0.5mm/+0.2mm——并掉格内中部密集点后 p90-p10 分位变宽,是量尺组成效应,非新增物理厚度(p90 cell 与带内点数都在降)。

## 首跑教训(已披露不粉饰,规则改在产物交付之前)

无距离辅助上限、DLT 无包络守护的首跑(`run_cap50_v0_dltdive_lesson.log`):4px 全或无约束不了低视差观测 union 的深度 → 成员位移 p90=0.39m、**490 个新地板下点**(DLT 沿射线"潜水")。修正:①距离 ≤5cm 只作否决;②DLT 共识位须过全观测测试且落成员 bbox±1cm,否则回退 COLMAP 自己的加权平均位。修正后 below-floor 0→0、位移 p90=15mm。

## 肉眼并排(同 gauge 直出,禁 Sim3)

关键证据图:`cap50/ghost_crosssection_floor_cap50.png`(E2-A 口径:地板 ±60mm 切片侧视,上=v1.1 厚板,下=E8 后——肉眼可见厚板基本原样,绿=共识点)。墙切片 `ghost_crosssection_wall_*.png`、真彩俯视+立面 `side_by_side_*.png` 同目录。

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# v1.1(用户已批基线) vs E8 候选(真彩)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply&right=E8_shell_collapse/cap50/e8_candidate_cap50.ply"
# diff:红=被并孪生(原位),绿=共识点,灰=未动
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply&right=E8_shell_collapse/cap50/diff_collapse_cap50.ply"
# cap51 同法
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap51/v1_1_candidate_cap51.ply&right=E8_shell_collapse/cap51/e8_candidate_cap51.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap51/v1_1_candidate_cap51.ply&right=E8_shell_collapse/cap51/diff_collapse_cap51.ply"
```

## 文件清单(SHA256SUMS.txt 为准)

- `e8_shell_collapse.py` — 全管线(python3.11;S1/E6 常量逐字复用;上游 SHA 断言 + E6 厚度/覆盖/带回归锚断言;pair 重提取与 E6 provenance 全等断言)
- `e8_post_analysis.py` — 逐格厚度成分审计 / 并组成分 / 带内塌向对账
- `cap50/`,`cap51/`:`e8_candidate_<cap>.ply`(E8 候选真彩)、`diff_collapse_<cap>.ply`(红/绿/灰)、`ghost_crosssection_floor|wall_<cap>.png`、`side_by_side_<cap>.png`、`collapse_provenance_<cap>.npz`(rep_of/group_of/共识位/观测数/位移——观测零删除的完整家谱)、`stats.json`、`analysis_<cap>.json`
- `stats_all.json`、`run_cap50.log`、`run_cap51.log`、`run_cap50_v0_dltdive_lesson.log`(首跑教训证据)

## 诚实边界

- 观测自 sfm_live.db 观测空间回收(S1 同法),**非生产 finalize 逐字节复刻**;87%+ 存量点观测不可回收 → 本实验测的是"可回收证据下的天花板",不能断言"全量观测下也塌不动"——但生产若有全量 track,COLMAP 自己的 Merge 早就跑过了(见"跨层并被 4px 正确拒绝"),方向性结论稳。
- 共识位多视 DLT + 包络守护是 E8 取舍声明(COLMAP Merge 原生用加权平均不重三角化);距离 ≤5cm 否决上限、bbox±1cm 包络同为声明,**非认证配置**;本目录一切不 ship,合入生产须签决。
- 墙厚代理尺(主竖直平面冻结于 before 云)是 E8 声明尺,非认证指标,只作方向参考。
- 点数 −8.8%/−7.1% 大头是致密区存量-存量与注入-注入去重(非壳);若用户只要壳处理,provenance npz 可按 floor_h 掩码构造子候选,无需重跑。
- 墙钟是 host python 代理,非设备数。
