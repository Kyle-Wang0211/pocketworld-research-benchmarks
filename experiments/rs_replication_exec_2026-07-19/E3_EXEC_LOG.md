# E3 执行日志 — 出生纪律刀:"点必须赢得存在权"

日期 2026-07-18(exec 批次 rs_replication_exec_2026-07-19)。产物目录:`E3_birth_discipline/`(SHA256SUMS.txt 全量核验通过;git 仅 untracked,不 commit,编排者统一提交)。墙钟秒级(host python 代理),内存无压力。

## ① 规则定义与 RS 出生纪律的对应

RS 机制(E2 定向):预览每点 = 真实匹配 + BA 幸存 tie-point,失败形态是留洞不是伪影。E3 把这条纪律翻译为分层门(**不做全局收紧**,E2-B 已证全局刀必误杀):

- **基线 = S1 统一规则逐字节复用**(常量同 `S1_twoview_lifecycle/build_candidate.py`):≥3 恢复观测=multiview 保留;恰 2 观测且传递匹配 → structure-only DLT refit(位姿/K 冻结)+ 负深度 / reproj>3px / θ<2° 裁剪;观测恢复不足如实保留。provenance-blind。
- **风险层 = E2-A 四签名并集逐字消费**(`TRAILS_forensics/<cap>/trail_detect.npz` 的 S_behind|S_below|S_streak|S_out;输入 PLY SHA 断言一致)。命中签名且过 S1 的点必须赢得存在权,二选一:
  - 路 1:≥3 恢复观测(多视支持);
  - 路 2:净可见票 ≥0 — 每个恢复观测帧按自己的视线走廊投票(E2-A march 常量逐字:5cm 体素≥6 点=实体、步长 4cm、起点 25cm、距点 20cm 截停);干净 +1、被挡 −1;**穿生产地板平面(fh<−0.10)= 常驻反对票**(补 march 20cm 截停看不到地板的盲区);0 观测点用最近相机单票代理(标记)。
- 非风险点 S1 判决原样不动。主操作点反对票阈值 **bh=8**(规格原样 bh=3 触红线,见③)。

## ② 拖尾杀灭 × 四热区账 + 真几何存活校验

**check (a) 已审真几何簇:PASS 70/70 全活**(bh=8)— r05 天花 36/36、r09 背包 19/19、r12 门洞货架(Z≈−9.1)15/15(货架靠净可见票天然过门,走廊穿真门洞=干净)。cap51 无已审保护簇(n/a,如实)。

**check (c) 拖尾杀灭对账(E2-A 候选,剔保护簇)** — cap50 杀 188/934(20.1%),cap51 28/525:

| 热区(cap50) | 杀/总 | 结论 |
|---|---|---|
| 地板下反射层 | **161/161(100%)** | 构造性全歼 = 本层可行核(cap51 25/25 同) |
| 缎面被(AMB) | 9/205(4.4%) | 与真背包在走廊证据空间同分布,bh=8 下多数存活 |
| 钢琴漆 | 2/69(2.9%) | 走廊免疫区(反射面无实体体素) |
| 窗玻璃倒影 | 0/112(0%) | 走廊免疫区(同上) |
| 其余 | 16/387 | 多为深穿透 S_behind |

对照:规格原样 bh=3 杀 443/934(47.4%)但屠保护簇 18/70(背包死 17/19)→ FAIL;3→8 全扫描曲线在 `sweep_curve_cap50.png` + `<cap>/stats.json` 的 `sweep_vote_block_hits`。

裁决构成:cap50 = S1 基线 537(535 θ<2° + 2 reproj)+ 风险层 180(159 地板下 + 21 走廊深穿透);cap51 = 249 + 26。

## ③ 四把尺子过/不过(诚实)

**check (b) PASS(两 cap)**:

| 尺子 | cap50 | cap51 |
|---|---|---|
| ①点数 | 92,849→92,132(−0.77%) | 64,392→64,117(−0.43%) |
| ②地板厚度 med p90-p10 | 0.04843→0.04844 m(带内不变) | 0.011802→0.011726 m(微薄) |
| ②厚度 p90 cell | 0.07748→0.07754 m | 0.04336→0.04236 m(改善) |
| ③正确覆盖损失(2cm 格) | 0.137%(门≤1%) | 0.137%(门≤1%) |
| ④墙钟(host 代理) | 0.7+0.1+0.1 s | 0.4+0.0+0.1 s |
| 椅子 ROI near-floor | 93→93 | n/a |

**🔴 不粉饰的三条机制结论**:
1. 规格原样 bh=3 → check (a) 红线 FAIL(屠背包 17/19),操作点被迫上移到 8;
2. **bh=8 是在保护簇上校准的 = 披露的过拟合风险**——它不能兼任自己的验证集;cap51 无保护簇只能弱迁移验证;生产落地需新场景已审真几何独立验证 + 用户签决;
3. 真背包与缎面被在走廊证据空间**同分布(不可分前沿)**;窗玻璃/钢琴漆对走廊测试**天然免疫**——这两热区需光度一致性 / detector-free 稠密验证类新证据,非本层阈值能解。

其余诚实边界:观测恢复自 sfm_live.db 非生产 finalize 逐字节复刻(3px 支持半径偏保守=偏保留);cap50 79,671 / cap51 58,297 点观测恢复不足 2,其中风险点仅最近相机单票代理(对被移动物体 r09 型方向可能错);E2-A 签名点级 FP 15-35%(单评审员);march/体素阈值是取证参数非认证配置;本目录一切不 ship。

## ④ 用户该看的 compare 链接(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# 1) cap50 基准 vs E3 候选
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=E3_birth_discipline/cap50/e3_candidate_cap50.ply"
# 2) cap50 拖尾高亮 before vs after(红=杀/绿=赢得存在权/灰=其余)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=TRAILS_forensics/cap50/trail_highlight_cap50.ply&right=E3_birth_discipline/cap50/diff_cap50.ply"
# 3) cap51 基准 vs E3 候选
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap51/device_full_pull_2026-07-17/sfm_sparse.ply&right=E3_birth_discipline/cap51/e3_candidate_cap51.ply"
```

静态速览:`E3_birth_discipline/<cap>/side_by_side_<cap>.png`、`trail_before_after_<cap>.png`、`sweep_curve_<cap>.png`。

## ⑤ 与 S1 合并成"预览出生纪律 v1"的建议

三条硬校验(a)(b)(c)在主操作点 bh=8 下全 PASS → **建议有条件合并**:

- **立即可并入 v1 的部分(无争议)**:S1 统一规则 + **地板下常驻反对票**(cap50 161/161、cap51 25/25 构造性全歼,四把尺子零损,不依赖 bh 校准)。这是本层可行核。
- **带过拟合披露并入的部分**:走廊净可见票 @bh=8(cap50 额外净杀 21 深穿透,保护簇零误杀)——但 bh=8 校准于保护簇,**合并前需一个新场景的已审真几何做独立验证,且须用户签决**。
- **明确不并入/移交下游**:缎面被 AMB 区(与真几何不可分前沿)与窗玻璃/钢琴漆(走廊免疫)——挂到光度一致性 / detector-free(ELoFTR 类)证据轨,本层不再加阈值。

## ⑥ 待 commit 清单(编排者统一提交)

`experiments/rs_replication_exec_2026-07-19/E3_birth_discipline/` 全目录(均 untracked,SHA 见 SHA256SUMS.txt):

- `README.md`、`SHA256SUMS.txt`、`stats_all.json`、`e3_birth_discipline.py`(python3.11,复跑同序)
- `cap50/`:`e3_candidate_cap50.ply`、`diff_cap50.ply`、`e3_arrays.npz`、`stats.json`、`side_by_side_cap50.png`、`trail_before_after_cap50.png`、`sweep_curve_cap50.png`
- `cap51/`:同构 7 件
- 本文件 `E3_EXEC_LOG.md`

---
## 用户肉眼判定(2026-07-19)
用户在 compare_any.html 同 gauge 并排(cap50, overview)查看 E3 候选 vs 生产原版后判定:
**"鬼层确实压缩了一些。继续"** → E3 出生纪律刀 [USER-VISUAL PASS],授权继续执行。
(bh=8 走廊票的过拟合披露与新场景独立验证要求维持不变。)
