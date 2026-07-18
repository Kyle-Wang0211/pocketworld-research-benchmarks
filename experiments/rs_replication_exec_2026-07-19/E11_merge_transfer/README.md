# E11 merge-and-transfer 原型(cap50 主 + cap51 验)

日期 2026-07-18(exec 目录沿用 07-19 批次)。研究产物:不改生产、不 commit(编排者统一)。GPLv3(ORB-SLAM2 Fuse/Replace)**只抄判据语义,零代码 vendor**。

**一句话诚实结论:merge-and-transfer 机制本身全绿(覆盖零损/误杀审计干净/零位姿翘曲/观测守恒逐条对平),但对双地板壳,逐观测转移在跨层的 gate 通过率只有 1.0-1.1%——σ_depth 物理下界在观测粒度上第三次坐实。定数:壳带最多塌 −0.2%(cap50)/−0.07%(cap51)。事后清算这条路的天花板到此钉死(E8 全或无 −4.2% 已是家族上限),−96% 量级只能靠出生前裁决(stage-1 产跨边+定出生)。**

## 语义(SYNTHESIS v2 规格 P0+S1-S6,与 E8 的本质区别)

- **支持比只定胜负,不定生死**(S4):赢家=可回收观测多者,平局退化到自身平均重投影;
- **输家不删**:其观测**逐个**过 gate 链(正深度 → 赢家位置重投影 ≤4px,我们认证 3-4px 口径,χ² σ=1 等效 16 → 视角 <60°防误融,S3/S5);过门观测**转移**给赢家(同帧查重,COLMAP track 语义);
- 赢家用合并观测**冻结位姿多视 DLT 重三角化**(E8 潜水教训双守护:全观测 4px 复测 + bbox±1cm 包络,不过则保位);
- 输家保留没过门的观测;**剩余 <2 才自然消亡**——且**消亡必须由自身支持被转移触发**:0-obs 点(证据不可回收 ≠ 不存在)永不消亡;
- **全程冻结生产位姿 = 构造性零 BA 翘曲**(E9-C 197mm 教训直接绕开;E9-C v2 固定框架复测:before/after gauge shift 逐字相同 0.6mm/5.0mm);
- **小步 N 轮**:每轮只处理最高置信(支持比)~15% 开放竞争组,轮间重三角化,收敛后全量 final pass(cap50 收敛于 7 轮+final,cap51 5 轮+final);
- 硬门构造性:消亡若清空 2cm 覆盖格且赢家不回填 → **整个竞争原子否决**(cap51 触发 1 次);赢家重定位清空独占格 → 跳过重定位。

## 结果(before=v1.1 用户已批基线,PLY 字节身份断言)

| 尺子 | cap50 | cap51 |
|---|---|---|
| ①点数 | 103,702 → 102,591(−1,111 全部=自然消亡;强化赢家 987) | 70,394 → 70,096(−298;强化 278) |
| 观测守恒 | 73,823+1桥 = 71,656留 + 1,581转 + 587随亡弃(**对平**) | 38,510+6桥 = 38,007 + 401 + 108(**对平**) |
| ②地板厚度 med cell | 0.048382 → 0.048310(−0.15%) | 0.012159 → 0.012204(+0.36%,噪声带内) |
| ②p90 cell | 0.077600 → 0.077600 | 0.043416 → 0.043426 |
| ②b 墙厚代理 | 0.05226 → 0.05191 | 0.03576 → 0.03548 |
| ③覆盖 2cm 格(硬门) | 2,416 → 2,416(**PASS,0 否决**) | 4,567 → 4,567(**PASS,1 构造否决**) |
| ④host 代理墙钟 | 转移 3.3s(全程 ~10.5s) | 转移 0.6s |
| **双地板带(v1.1 口径,锚断言过)** | 3,917 → 3,909(**−8,−0.2%**) | 6,880 → 6,875(**−5,−0.07%**) |
| E9-C v2 固定框架 band_below | 3,968 → 3,960(shift 0.6→0.6mm) | 7,793 → 7,787(shift 5.0→5.0mm) |
| below-floor | 0 → 0 | 0 → 0 |
| 椅子 ROI near-floor | 93 → 93 | n/a |
| G1 真地板观测保留 | **99.75%**(真丢弃仅 9 条;亡者赢家 11/15 仍在 ±15mm) | **99.79%**(真丢弃 11 条;30/32 在 ±15mm) |
| 转移重投影 px | p50 3.46 / p90 3.89(χ²5.99@2.45px 只 118/1593) | p50 3.50 / p90 3.89 |

## ⑤三方对账(E8 死处的正面回答)

| 方法 | 壳带 | 覆盖 | 位姿 | 判 |
|---|---|---|---|---|
| E8 全或无 track 并 | −4.2% / −3.9% | 零损 | 冻结 | 增益不配交付层;跨层 44-47% 被 4px 拒 |
| E9 conflict_mv 钝刀 | cap51 **−96.3%** / cap50 **+38.0%**(翘曲反噬) | cap51 **−30.3% FAIL** | 翘曲 p90 197mm | 连坐误杀红判 |
| **E11 逐观测转移** | **−0.2% / −0.07%** | **零损** | **零翘曲(构造性)** | 机制绿、壳增益≈0 |

**E8 死处(跨层 44-47% 全或无被拒)的逐观测答案:cap50 跨层竞争共 6,768 条观测过 gate 尝试,只 70 条通过(1.03%);cap51 2,294 条只 25 条(1.09%)。**不是全或无太严——是跨层观测在赢家表面位置上真的投不进 4px(两层各自 4px 自洽、层间 2-3.5cm 折合 >4px,与 COLMAP 当初不并它们同一物理)。逐观测粒度把"机制问题"这个假设彻底排除:**这是 σ_depth 物理,不是裁决器工程**。

E11 消亡数(1,111)远小于 E8 并组成员(9,126)的原因是构造性的:E11 拒绝在证据不可回收时杀点(66%/72% 存量点 0-obs → 永生),消亡必须"自身支持被转移"触发。E8 的 −4.2% 大头本就是壳内孪生互并,非壳→真地板。

## ⑥误杀审计(kill_audit_*.png/json)

36/1,111(cap50)与 36/298(cap51)随机抽样(seed 固定),逐个投真实照片(3840×2160,与 SfM 同分辨率):红圈=消亡输家投影,绿圈=承继赢家投影。**红绿圈同像素位(分离 p50 3.5/3.7px),空间距 p50 9.7/8.9mm——全部是壳内/致密区同位多胞胎,非真几何**。cap50 亡者分布:1,079/1,111 在家具/床面(fh>60mm 致密区孪生)、带内仅 8、真地板 15(其赢家 11/15 仍在 ±15mm,真丢弃观测共 9 条)。cap51 样本含 4 个真地板亡者,全部为真地板面内孪生固化(赢家在 ±15mm 内)。

## 诚实边界

- 观测自 sfm_live.db 可回收空间(S1 同法),87% 存量点观测饿死 → 本实验测的是**可回收证据下的天花板**;生产全量 track 会解锁更多竞争组,但跨层 4px 物理不会变——壳增益的定数(−0.2%/−0.07%)方向性稳。
- 视角门 60°(cos 0.5)几乎不触发(55/5 次)——同向重复壳法线相同,该门只防真双面误融,符合 M16 预判。
- 转移重投影 p50≈3.5px 紧贴 4px 门:若按 χ²5.99(≈2.45px)口径,93% 的转移会被拒——**gate 数值重标(SYNTHESIS 5.1"须按 'o' 认证口径重标")在 ship 前必须做**,本原型 4px 是 E8 连续性选择。
- 墙钟为 host python 代理,非设备数;桥观测跨 track 复用(同 (fid,node) 可能同时在别的存量 track)是原型声明的简化。
- 本目录一切不 ship;合入生产须签决。

## 肉眼并排(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# v1.1(用户已批基线) vs E11 候选(真彩)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply&right=E11_merge_transfer/cap50/e11_candidate_cap50.ply"
# diff:红=自然消亡输家(原位),绿=被强化赢家(新位),灰=未动
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply&right=E11_merge_transfer/cap50/diff_transfer_cap50.ply"
# cap51 同法
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap51/v1_1_candidate_cap51.ply&right=E11_merge_transfer/cap51/e11_candidate_cap51.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E6_rescue_inject/cap51/v1_1_candidate_cap51.ply&right=E11_merge_transfer/cap51/diff_transfer_cap51.ply"
```

关键证据图:`cap50/ghost_crosssection_floor_cap50.png`(上=v1.1 真彩切片,下=E11 后)、`ghost_crosssection_diff_*.png`(红/绿/灰)、`kill_audit_*.png`(误杀审计照片拼版)、`side_by_side_*.png`。

## 文件清单(SHA256SUMS.txt 为准)

- `e11_merge_transfer.py` — 全管线(python3.11;S1/E6/E8 常量与断言逐字复用;v1.1 字节身份+带锚+E6 厚度/覆盖锚断言;硬门 assert)
- `cap50/`,`cap51/`:`e11_candidate_<cap>.ply`、`diff_transfer_<cap>.ply`、`transfer_provenance_<cap>.npz`(alive/heir/位置/观测计数/竞争日志全家谱)、`ghost_crosssection_floor|diff_<cap>.png`、`side_by_side_<cap>.png`、`kill_audit_<cap>.png/json`、`stats.json`
- `stats_all.json`、`run_cap50.log`、`run_cap51.log`

## 给 stage-2 裁决器 v2 的机制结论(与壳增益分开记账)

机制五件套全部实测可用:①逐观测 gate 构造性满足"转移非删除"(观测守恒对平);②冻结位姿+重三角化双守护 = 零翘曲零潜水;③小步轮次收敛快(≤7 轮);④构造性覆盖守护零成本(0/1 次否决);⑤照片级误杀审计范式可复用。**该机制的正确宿主是 stage-1 产出跨边之后的存量清算,不是没有跨边证据时的事后自愈。**
