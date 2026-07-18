# E7 — bh=8 独立验证(cap40/41 卧室,E3 从未见过的场景)

日期 2026-07-18(exec 批次 rs_replication_exec_2026-07-19)。**验证不是校准:E3 规则常量逐字节冻结,零场景调参**。产物只写本目录;不改生产、不 commit(编排者统一提交)。python3.11;vm_stat 自检过(inactive ~5.2GB 可回收,任务轻量)。

## 裁决:bh=8 **PASS**(带两条新场景诚实披露 F2/F3)

- **真几何存活**:审计 98 个保留点样本 0 误杀;48 个被杀点样本 48/48 为正确击杀(全部 fh≤−0.10 地板下反射鬼点,裁块全部落在高光漆地板/柜门反光面)。
- **四把尺子带内**(基线=E4-B S1 候选,增量只看 E3 新增裁剪):厚度不变、**对 S1 基线地板覆盖损失 0.000%**(两 cap)、点数增量 cap40 −27 / cap41 −202(全部为地板下否决)、墙钟 host 代理秒级。
- **曲线无漂移**:bh 扫描 3..12 在新场景 bh≥7 全平(cap40 310 culls @7..12;cap41 387 @8..12),bh=8 落在鲁棒平台上,不是场景特调的刀尖;**bh=3 红线独立复现**——bh=3 相对 bh=8 多杀的 35 点(cap40 14 + cap41 21)肉眼审计 **35/35 全是真实几何**(床单/被子/床架/床垫侧,走廊擦过床体杂物 3-6 个实体体素),即新场景独立要求 bh≥7,与 cap50 校准结论一致 → **过拟合风险未坐实**。

## 输入(自洽三元组,E4-A Sampson 1.117/0.937px)

`E4_cap4041_host_replay/S1_rerun/inputs/<cap>/`:sfm_sparse.ply(host 真彩回放云)+ sfm_sparse_meta.json(回放精化位姿)+ sfm_live.db(K 补丁副本)。E2-A 四签名(fingerprints/detect_trails)在本目录 verbatim 重跑;PLY SHA 断言一致。地板面=重建的最低主导 y-slab(cap40 −1.161 / cap41 −1.209;⚠️全局 y-hist 峰是**床面**,cap40 −0.564 / cap41 −0.658,锚床面会把真地板整层打成 S_below——已验证并拒绝;这是输入重建非调参,fingerprints_info.json 有披露)。

## 主结果(冻结 bh=8)

| | cap40 | cap41 |
|---|---|---|
| 点数 | 74,500→74,190(−0.42%) | 62,161→61,774(−0.62%) |
| 其中 S1 层(=E4-B 逐数吻合) | 283(283θ) | 185(184θ+1r) |
| E3 风险层新增 | **27(全部地板下否决)** | **202(全部地板下否决)** |
| 走廊票 @bh=8 额外杀 | 0 | 0 |
| 对 S1 基线覆盖损失 | 0.000% | 0.000% |
| 厚度 med cell(重建地板面) | 0.03696→0.03691 | 0.03973→0.04012(S1 层所致,E4-B 已批) |
| E2-A 风险点 | 727(0.98%) | 886(1.43%) |

历史雷区专查:**床底**——床底体积(床面脚印格内、床面下 10cm~地板上 3cm)基线点数双 cap = **0**,留洞正确,无 hallucination 可杀也无误杀;**床边竖列**(S_streak 串)被杀的只有 S1 θ 票(E4-B 已批层),E3 风险层零杀,保留样本全真;**墙面鬼层**(S_behind 存活点)审计 24/24 全真(袜子/被子/枕头/床架),走廊票正确救回 S_behind 误报。

## 两条新场景诚实披露(不放水)

- **F2 地板下 path-1 泄漏(新发现)**:E3 在 cap50/51 报的"地板下常驻反对票=构造性 100% 全歼"**不完全迁移**——冻结规则里 path-1(≥3 恢复观测)优先于地板下否决,而平面镜虚点恰恰可以多视一致。cap40 有 18/49(37%)、cap41 有 163/373(44%)的地板下点经 keep_risk_multiview 存活(fh 中位 −0.15,审计样本外观=光泽地板反射鬼点)。cap50/51 该池为空所以 E3 看不见。**这不是 bh=8 的问题**;若要"地板下否决压过 path-1"属规则变更,须另立签决,E7 未动。
- **F3 走廊票在卧室惰性**:bh=8 下走廊票零额外杀,本场景 E3 增量全部由地板下否决贡献;走廊票的"清理价值"(深穿透镜面拖尾)仍只在 cap50 展示过,本场景它只起保护作用(不误杀)——这一角色它通过了。

其余诚实边界:审计=单评审员(agent)非用户签认;证据恢复非生产 finalize 逐字节;cap40/41 观测恢复覆盖 ~99%(与基线同源的构造效应,跨场景只比四把尺子);march/体素常量是取证参数非认证配置;本目录一切不 ship。

## 复跑同序

```bash
python3.11 e7_fingerprints.py        # E2-A stage-1 verbatim(输入重建披露见 docstring)
python3.11 e7_detect_trails.py       # E2-A stage-2 verbatim
python3.11 e7_birth_discipline.py    # E3 规则冻结重放 + bh 3..12 扫描
python3.11 e7_audit.py               # 审计裁块(规则冻结后运行,零反馈)
python3.11 e7_audit_bh3diff.py       # bh3-vs-bh8 差分点裁块
```

## 用户肉眼 compare 链接(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# cap40 基线(E4-B host-replay 真彩) vs E7 候选
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap40/sfm_sparse.ply&right=E7_bh8_validation/cap40/e7_candidate_cap40.ply"
# cap40 diff(红=杀/绿=赢得存在权/灰=其余)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E7_bh8_validation/cap40/trail_highlight_cap40.ply&right=E7_bh8_validation/cap40/diff_cap40.ply"
# cap41 同构
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap41/sfm_sparse.ply&right=E7_bh8_validation/cap41/e7_candidate_cap41.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E7_bh8_validation/cap41/trail_highlight_cap41.ply&right=E7_bh8_validation/cap41/diff_cap41.ply"
```

静态速览:`<cap>/side_by_side_<cap>.png`、`<cap>/trail_before_after_<cap>.png`、`sweep_compare_cap50_vs_cap4041.png`、`<cap>/audit_sheet_*.jpg`。

## 文件清单(SHA256SUMS.txt 为准)

- 管线:`e7_fingerprints.py`、`e7_detect_trails.py`、`e7_birth_discipline.py`、`e7_audit.py`、`e7_audit_bh3diff.py`;日志 `*_run.log`
- `stats_all.json`(含 S1 对 E4-B 交叉对账 match=true、四尺子、bh 3..12 扫描、荣誉边界)
- `<cap>/`:`e7_candidate_<cap>.ply`、`diff_<cap>.ply`、`e7_arrays.npz`、`stats.json`、`fingerprints.npz`+info、`trail_detect.npz`、`trail_stats.json`、`trail_highlight/trails_only ply`、渲染 PNG、`audit_crops/`(70+/cap)、`audit_sheet_*.jpg`、`e7_audit_manifest.json`、`bh3diff_manifest.json`
- `bh3_vs_bh8_diffset.json`、`sweep_compare_cap50_vs_cap4041.png`、`e7_audit_verdicts.json`(逐组判定+置信)
