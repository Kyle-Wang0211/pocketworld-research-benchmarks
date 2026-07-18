# E3 出生纪律刀:"点必须赢得存在权"(cap50 主 + cap51 验)

日期 2026-07-18(exec 目录沿用 07-19 批次)。研究产物:不改生产代码、不动 capture 数据、不 git commit(编排者统一提交)。
上游定向(E2):拖尾杠杆在出生纪律层;RS 机制 = 点必须是多视 BA 幸存 tie-point,失败形态 = 留洞非伪影;2px 全局收紧已否决(E2-B:全局刀必误杀)。

## 规则(分层门,不全局收紧)

- **基线(全体点)= S1 统一规则逐字复用**(常量逐字节同 `../S1_twoview_lifecycle/build_candidate.py`):≥3 恢复观测=multiview 保留;恰 2 观测且传递匹配 → structure-only DLT refit(位姿/K 冻结)+ 负深度 / reproj>3px / θ<2° 裁剪;观测恢复不足如实保留计数。provenance-blind。
- **风险层 = E2-A 四签名并集逐字复用**(直接消费 `../TRAILS_forensics/<cap>/trail_detect.npz` 的 S_behind|S_below|S_streak|S_out,输入 PLY SHA 断言一致)。命中签名且过了 S1 的点必须**赢得存在权**:
  - 路 1:**≥3 恢复观测**(多视支持);或
  - 路 2:**净可见票 ≥ 0**:每个恢复观测帧按**它自己的视线走廊**投票——干净(实体体素穿越 < 阈值,march 逐字 E2-A 常量:5cm 体素≥6 点=实体、步长 4cm、起点 25cm、距点 20cm 截停)= +1;被挡 = −1;**穿生产地板平面记为常驻反对票**(fh<−0.10,双地板带之下物理不可能,补 E2-A march 截停看不到地板的盲区);0 观测点用最近相机单票代理(标记)。
- 非风险点 S1 判决原样不动。

## 🔴 操作点的诚实声明(不粉饰)

规格原样的反对票阈值 = 3(E2-A 取证常量)会**杀死已审真几何**:背包簇 r09 死 17/19、门洞货架 r12 死 1/15 → check (a) 红线 FAIL。扫描曲线(`sweep_curve_cap50.png`)显示保护簇零误杀要求阈值 ≥8,**且主刀口(bh=8)是在保护簇上校准的——它不能再兼任自己的验证集**(cap51 无已审保护簇,只能弱迁移检验)。机制层结论:

1. **地板下常驻反对票 = 构造性完胜**:cap50 161/161、cap51 25/25 全歼,四把尺子零损——这是出生纪律层的可行核;
2. **走廊遮挡票有机制天花板**:真背包(疑似拍摄中被移动的实物)与缎面被镜面拖尾在 blocked-hits 证据空间**同分布**——阈值 3→8 之间保护簇误杀 18→0 与被子杀灭 163→9 同步塌缩,是前沿不是免费午餐;
3. **窗玻璃/钢琴漆拖尾对走廊测试天然免疫**(反射面自身几乎无实体体素,任何阈值 0-6% 杀灭)——这两个热区需要**不同证据**(光度一致性 / detector-free 稠密验证),不是本层阈值能解。

## 三条硬校验(主操作点 bh=8)

**(a) 已审真几何簇必须存活:PASS(70/70 全活)** — r05 天花 36/36、r09 背包 19/19、r12 门洞货架(Z≈−9.1)15/15。门洞货架靠净可见票天然过门(走廊穿真门洞=干净),与"真门洞非有界镜"裁决一致。cap51 无已审保护簇(n/a,如实)。

**(b) 四把尺子:PASS(两 cap)**

| 尺子 | cap50 | cap51 |
|---|---|---|
| ①点数 | 92,849 → 92,132(−717,−0.77%) | 64,392 → 64,117(−275,−0.43%) |
| ②地板厚度 med cell p90-p10 | 0.04843 → 0.04844 m(带内不变) | 0.011802 → 0.011726 m(微薄) |
| ②厚度 p90 cell | 0.07748 → 0.07754 m | 0.04336 → 0.04236 m(改善) |
| ③正确覆盖(2cm 格) | 损失 0.137%(门 ≤1%)| 损失 0.137%(门 ≤1%)|
| ④墙钟(host 代理) | 支持恢复 0.7s + S1 0.1s + 走廊票 0.1s | 0.4s + 0.0s + 0.1s |
| 椅子 ROI near-floor | 93 → 93(无压扁恶化) | n/a |

裁决构成 cap50:S1 基线 537(535 θ<2° + 2 reproj)+ 风险层 180(159 地板下 + 21 走廊深穿透);cap51:249 + 26。

**(c) 拖尾杀灭对账(E2-A 候选,剔保护簇)** — cap50 188/934(20.1%),cap51 28/525:

| 热区(cap50) | 杀/总 | 说明 |
|---|---|---|
| 地板下反射层 | **161/161(100%)** | 高光地板反射鬼点,全歼 |
| 缎面被(AMB) | 9/205(4.4%) | 与背包不可分,bh=8 下多数存活 |
| 钢琴漆 | 2/69(2.9%) | 走廊免疫区(见上) |
| 窗玻璃倒影 | 0/112(0%) | 走廊免疫区(见上) |
| 其余 | 16/387 | 多为深穿透 S_behind |

对照:规格原样 bh=3 杀 443/934(47.4%)但保护簇死 18/70 → FAIL;完整扫描表在 `<cap>/stats.json` 的 `sweep_vote_block_hits`。

## 肉眼并排(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=E3_birth_discipline/cap50/e3_candidate_cap50.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=TRAILS_forensics/cap50/trail_highlight_cap50.ply&right=E3_birth_discipline/cap50/diff_cap50.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap51/device_full_pull_2026-07-17/sfm_sparse.ply&right=E3_birth_discipline/cap51/e3_candidate_cap51.ply"
```

## 文件清单(SHA256SUMS.txt 为准)

- `e3_birth_discipline.py` — 全管线(python3.11,复跑同序;S1 常量与 E2-A march 常量逐字复用)
- `cap50/`, `cap51/`:`e3_candidate_<cap>.ply`(候选,幸存点保生产位置+真彩)、`diff_<cap>.ply`(红=杀、绿=风险点赢得存在权、灰=非风险保留)、`side_by_side_<cap>.png`(基线 vs 候选真彩,俯视+立面)、`trail_before_after_<cap>.png`(拖尾高亮 before/after)、`sweep_curve_<cap>.png`(分层阈值扫描曲线)、`stats.json`(含 verdicts/三校验/扫描全表/SHA)、`e3_arrays.npz`
- `stats_all.json` — 两 cap 汇总

## 诚实边界

- 证据恢复自 sfm_live.db 观测空间重建,**非生产 finalize 逐字节复刻**;3px 支持半径只会偏保守(偏保留);
- cap50 79,671 / cap51 58,297 点观测恢复不足 2(S1 已知 ~65% 地板),其中风险点只有最近相机单票代理——对被移动物体(r09 型)方向可能错;
- **bh=8 在保护簇上校准 = 披露的过拟合风险**;若要作为生产方向,需新场景已审真几何做独立验证 + 用户签决;
- E2-A 签名点级 FP 15-35%(单评审员)——分层门+净可见票就是缓解手段,但缎面被 AMB 区真伪混杂未解;
- march/体素阈值是取证参数非认证配置;**本目录一切不 ship,生产落地须签决**;
- 墙钟是 host python 代理,非设备数。
