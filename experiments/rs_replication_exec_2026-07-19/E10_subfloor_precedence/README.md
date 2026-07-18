# E10 — 地板下否决优先级修复(F2:path-1 泄漏)

日期 2026-07-18(exec 批次 rs_replication_exec_2026-07-19)。产物只写本目录;不改生产、不 commit。python3.11,全程串行(E9 并行编译窗口)。

## 裁决:**PASS**(审计硬门 42/42 正确击杀,误杀=0;cap50/51 回归零变化断言通过)

## 这是什么修复(排序变更,不是新规则)

E3 已批语义:"地板下 = 构造性 100% 全歼,零损"。冻结规则里该否决活在 path-2(net-visibility 投票)内部,而 **path-1(≥3 恢复观测=豁免)排序在它之前**;平面镜虚点恰可多视一致,于是 cap40 有 18/49、cap41 有 163/373 的地板下点靠 path-1 逃生(E7 F2,审计外观=光泽地板反射鬼,fh 中位 −0.15)。修复=把地板下常驻反对票排到 path-1 之前:

```
风险点过 S1 后:
  if floor_h < -0.10:   cull_risk_belowfloor    # 常驻否决,先裁
  elif n_support >= 3:  keep_risk_multiview      # path-1
  else:                 net-visibility 投票       # path-2
```

其余一切逐字节不动(bh=8、march 常量、S1 基线、非风险点)。

## 实现=可证等价的 delta 重放(运行时逐 cap 断言)

不从头重跑,在冻结的 E3/E7 数组上重放。等价性论证:(i) 旧排序下走到 path-2 的地板下点必被杀(below=True ⇒ 全票 −1,票列表非空)——断言"不存在 fh<−0.10 的 keep_risk_netvisible";(ii) 新排序只改判"keep_risk_multiview ∩ 地板下"这一集合——断言地板下幸存者恰等于 path-1 豁免者;(iii) 其余判决与排序无关。故 delta 重放 ≡ 完整重跑,bit-exact。

## 主结果

| | cap40 | cap41 | cap50 | cap51 |
|---|---|---|---|---|
| 地板下风险池(全部/过S1) | 49/45 | 373/365 | 161/159 | 25/25 |
| 旧排序已杀(path-2) | 27 | 202 | 159 | 25 |
| **E10 新杀(path-1 泄漏)** | **18** | **163** | **0(断言)** | **0(断言)** |
| 新杀 fh 范围 | −0.107…−1.205 | −0.101…−1.459 | — | — |
| 候选点数 | 74,190→74,172 | 61,774→61,611 | 不变 | 不变 |

## 审计硬门(步骤②)

cap40 **全量 18 点** + cap41 seeded 抽样 **24/163** = 42 点逐点投真实照片(E7 同配方:回放精化位姿+补丁 K+RAW 3840×2160):

- **42/42 正确击杀,0 真几何**。观测面全部为高光复合地板/衣柜漆面(cap40 17/18、cap41 24/24)或缎面床品(cap40 kill07,唯一非地板观测,fh=−0.329 而床面在地板上 ~0.6m,镜面织物误三角化,已单独披露);无下沉地面、无台阶、无任何低于主地板的真实结构。
- 判据:3D 位置在地板平面下 0.10–1.46m,单层房间构造性不可能存在真物;观测像素全落在已知反射热区。
- 详见 `e10_audit_verdicts.json`、`<cap>/audit_sheet_e10kills_<cap>.jpg`、`<cap>/audit_crops/`。
- 诚实:单评审员(agent)非用户签认;cap41 非穷尽(抽样 14.7%,未审部分 fh 分布与已审样本一致)。

## 四把尺子(步骤④:修复只准动地板下池——已达成,且是断言不是观测)

- 点数:cap40 −18(−0.024%)/ cap41 −163(−0.264%),全部为地板下 path-1 泄漏点。
- 地板厚度 med cell:两 cap **bit-identical**(0.03691 / 0.04012,与 E7 候选完全相同)。
- 地板覆盖:损失 **0.000%**(断言强制:fh<−0.10 严格在 ±6cm slab 之外,slab 成员集不可能变)。
- 墙钟:host delta 重放亚秒级(cap40 0.12s / cap41 0.05s;回归 cap50 0.05s / cap51 0.03s)。

## 回归(步骤③)

cap50/51 同修复重放:地板下多视池 = **0**(全部 159/25 已在旧排序被 path-2 杀),`assert n_delta == 0` 通过,候选与 E3 逐 SHA 不变(stats.json 记录 E3 候选 SHA,不重复写盘)。

## ⚠️ 多层地板风险(步骤⑤,适用边界,如实披露)

本修复(连同 E3 原地板下语义)默认**主地板平面之下无真物**:

- **成立**:单层平地室内——四个标准场景(cap40/41 卧室、cap50/51 起居室)均属此类。
- **会误杀**:错层/下沉客厅/台阶/楼梯井/地台边缘——低于主地板的真实几何会被构造性全歼,且 path-1 豁免通道已被本修复关闭,**无自救路径**。
- **强制检查项**:U5 泛化盲测必须先判场景是否单层;多层场景该规则须降级或按层分别锚地板面后再用。此边界随规则走,进入任何签决文书。

## 四场景"出生纪律 v1"总账(步骤⑥:S1 + E3 + E7 + E10)

| | cap40(卧) | cap41(卧) | cap50(起) | cap51(起) |
|---|---|---|---|---|
| 原始基线点数 | 74,500 | 62,161 | 92,849 | 64,392 |
| S1 两视生命周期裁 | 283(283θ) | 185(184θ+1r) | 537(535θ+2r) | 249(247θ+2r) |
| E3 风险层裁 @bh=8 | 27(全地板下) | 202(全地板下) | 180(159地板下+21遮挡) | 26(25地板下+1遮挡) |
| E10 地板下优先级裁 | 18 | 163 | 0 | 0 |
| **最终候选** | **74,172(−0.44%)** | **61,611(−0.88%)** | **92,132(−0.77%)** | **64,117(−0.43%)** |
| 地板覆盖损失(对各自基线) | 0.494%(E7)+0.000%(E10) | 0.849%(E7)+0.000%(E10) | 0.137% | 0.137% |
| 地板厚度 | 不变 | S1层所致微动(E4-B已批) | 不变 | 不变 |
| 审计误杀 | 0(E7 98保留+48杀;E10 18杀) | 0(E7 同批;E10 24/163杀) | 0(E3+E2-A审计) | 0 |
| 出处 | E4-B+E7+E10 | E4-B+E7+E10 | S1+E3 | S1+E3 |

层级语义:S1=无差别两视生命周期(用户已批);E3=风险层"挣存在权"(bh=8 冻结);E7=bh=8 跨场景独立验证(发现 F2);E10=F2 修复,恢复已批地板下语义的完整迁移。

## 用户肉眼 compare 链接(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# cap40:E7 候选(修复前) vs E10 候选(修复后)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E7_bh8_validation/cap40/e7_candidate_cap40.ply&right=E10_subfloor_precedence/cap40/e10_candidate_cap40.ply"
# cap40 diff(黄=E10新杀18点,红=先前S1/E3杀,绿=风险点挣得存在权,灰=其余)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap40/sfm_sparse.ply&right=E10_subfloor_precedence/cap40/diff_cap40.ply"
# cap41 同构
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E7_bh8_validation/cap41/e7_candidate_cap41.ply&right=E10_subfloor_precedence/cap41/e10_candidate_cap41.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap41/sfm_sparse.ply&right=E10_subfloor_precedence/cap41/diff_cap41.ply"
```

## 复跑同序

```bash
python3.11 e10_subfloor_precedence.py   # 4 cap delta 重放 + 等价性/回归断言 + 四尺子
python3.11 e10_audit.py                 # 新杀点投照片(规则冻结后运行,零反馈)
```

## 文件清单(SHA256SUMS.txt 为准)

- `e10_subfloor_precedence.py` / `e10_audit.py`;日志 `e10_run.log` / `e10_audit_run.log`
- `stats_all.json`(逐 cap:等价性证明、池统计、四尺子、逐点 kill 元数据、诚实边界)
- `e10_audit_verdicts.json`(42 点逐组裁决)
- `cap40|cap41/`:`e10_candidate_<cap>.ply`、`diff_<cap>.ply`、`e10_arrays.npz`、`stats.json`、`audit_sheet_e10kills_<cap>.jpg`、`audit_crops/`、`e10_audit_manifest.json`
- `cap50|cap51/`:`stats.json`(回归零变化记录 + E3 候选 SHA)

其余诚实边界:证据数组承自 E7/E3(非生产 finalize 逐字节);march/体素常量是取证参数非认证配置;本目录一切不 ship,进生产须用户签决。
