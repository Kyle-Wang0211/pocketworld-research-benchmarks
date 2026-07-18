# E6-A 救回注入 = v1.1 候选(cap50 主 + cap51 验)

日期 2026-07-18(exec 目录沿用 07-19 批次)。研究产物:不改生产代码、不动 capture 数据、不 git commit(编排者统一提交)。
原则(RS 纪律):**过门的 tie point 就该发布**——救回点过的是与交付云同一把 S1 尺子,不发布反而是漏。但**注入侧必须比存量侧更严,不能更松**。

## 注入门(G0–G7 漏斗,全部注入侧从严)

| 门 | 规则 | 严于存量之处 |
|---|---|---|
| G0 | S1 统一 2-view 规则(验证对 + DLT refit + reproj≤3px + θ≥2°),常量逐字节同 S1 | =同一把尺子(救回定义) |
| G1 | 去重:距任一生产点 >2cm(S1 rescue 定义) | — |
| G2 | 还魂卫兵:距每个 E3 已杀点 ≥5cm | 新增(不得回填用户已批准清理区) |
| G3 | 地板卫兵:仲裁平面 floor_h ≥ −0.015m | 严于存量 −0.10(构造性零新增双地板带/地板下) |
| G4 | 椅子 ROI 卫兵(cap50):ROI 内距地 ≤5cm 不注入 | 新增 |
| G7 | 地板增厚卫兵:地板槽(±6cm)注入只许纯填洞(紧槽 ≤3cm 且 2cm 覆盖格是新格 且 5cm 厚度格 E3 点 <8) | 新增(保护厚度尺子) |
| G5 | 走廊票 bh=8:**两个观测走廊都 march**(E2-A 常量,实体体素=E3 候选云),任一 ≥8 实体穿越即杀;无代理票 | 严于存量 net≥0(存量允许 1/2 被挡+代理票) |
| G6 | 注入后组合云上 E2-A 四签名扫描,**被标记的注入点一律丢弃**,迭代至不动点 | 严于存量(存量允许标记点"赢得存在权",注入点必须零签名) |

注:救回点恰 2 观测,存量的"≥3 观测赢得存在权"路对它天然不可用——注入侧只剩更严的路。

## 漏斗(诚实全表)

| 门 | cap50 | cap51 |
|---|---|---|
| G0 过 S1 规则的验证对 | 48,226 | 28,224 |
| G1 距生产云 >2cm | 15,694 | 8,538 |
| G2 还魂卫兵(杀) | 13,752(−1,942) | 8,205(−333) |
| G3 地板卫兵(杀) | 13,036(−716) | 6,728(−1,477) |
| G4 椅子 ROI(杀) | 13,020(−16) | 6,728(−0) |
| G7 地板填洞限定(杀) | 11,863(−1,157) | 6,435(−293) |
| G5 走廊 bh=8 双观测(杀) | 11,863(−0;614 短走廊记干净,已声明) | 6,434(−1) |
| G6 四签名零容忍(杀,3 轮迭代收敛) | **11,570 注入**(−293) | **6,277 注入**(−157) |

## 取色 = 认证配方逐字对齐生产

`colorize_pipeline.dart` + `representative_color.dart`:观测坐标 −0.5 处全分辨率双线性(COLMAP 约定,越界跳过),代表色=亮度下中位数的**真实样本**(2 样本取更暗者,不合成不平均),round+clamp。keypoint 空间==照片空间(3840×2160,scale=1,已断言)。
**缺照片声明**:两 cap 各 24 个已注册帧无照片。cap50:7,402 点双观测取色 / 3,264 单观测 / **904 点(7.8%)无任何样本→最近生产点颜色 NN 回退**;cap51:4,048 / 1,785 / **444(7.1%)NN 回退**。

## 四把尺子(before=E3 候选(用户已批),after=v1.1)

| 尺子 | cap50 | cap51 |
|---|---|---|
| ①点数 | 92,132 → **103,702(+11,570,+12.6%)** | 64,117 → **70,394(+6,277,+9.8%)** |
| ①对生产基线 | 92,849 → 103,702(**+11.7%**) | 64,392 → 70,394(**+9.3%**) |
| ②地板厚度 med cell p90-p10 | 0.04844 → 0.04838 m(不变/微薄) | 0.011726 → 0.012159 m(+0.43mm,**纯成分效应,见下**) |
| ②厚度 p90 cell | 0.07754 → 0.07760 m | 0.04236 → 0.04342 m |
| ③正确覆盖 2cm 格 | 2,182 → 2,416(**+234 新格,+0.094m²**) | 4,363 → 4,567(**+204 新格,+0.082m²**) |
| ④墙钟(host 代理) | 提取 2.0s+走廊 0.4s+签名 0.9s+取色 3.6s | 1.4s+0.2s+0.6s+2.7s |

**厚度成分效应已构造性排除增厚**(逐格对账,`run_both.log` 后另行验证):既有被测格(cap50 379 格 / cap51 766 格)spread 变化 **全部 = 0.000000,一个点都没加进去**(G7 构造保证);med 位移完全来自 18–19 个**新出现的被测格**(新覆盖地板区,2-view refit 散布 med 2.7–4.0cm,厚于存量 BA 地板但它们是原本的洞)。分层看=既有地板零损,新区披露如实。

## 鬼层复查(逐项 before/after,注入不得新增)

| 指标 | cap50 | cap51 | 判 |
|---|---|---|---|
| 双地板带密度(fh∈[−0.06,−0.015)) | 3,917 → 3,917(+0) | 6,880 → 6,880(+0) | ✅ |
| 地板下点数(fh<−0.10) | 0 → 0 | 0 → 0 | ✅ |
| 拖尾签名点数(四签名并集,同一探测器跑两朵云) | 824 → **721(−103)** | 500 → **423(−77)** | ✅(注入点被标=0) |
| 椅子 ROI near-floor | 93 → 93 | n/a | ✅ |

**PASS(两 cap)**。签名语境细节(诚实):注入让 56/50 个既有 E3 点在组合云语境下**新被标记**(注入占据补全了证据——它们现在可证地"隔着新致密面被看到",位置与身份不变,是**未来刀的候选**不是新鬼),同时 166+ 个稀疏真几何点因去 wisp 化**脱标**,净 −103/−77。

## 注入点空间分布(填洞还是已密区?——诚实回答:大头是致密化)

| | cap50 | cap51 |
|---|---|---|
| 距最近生产点 | 98% 在 2–5cm | 87% 在 2–5cm,13% >5cm |
| 落在已密区(cnt10≥40) | **8,804(76.1%)** | **4,300(68.5%)** |
| 洞/半稀疏区(cnt10<40) | 2,766(23.9%) | 1,977(31.5%) |
| 分层 | 地板 1,940 / 低层物体 4,494 / 高层墙面 5,136 | 246 / 3,260 / 2,771 |
| 新增地板覆盖格 | +234(纯洞填,G7 构造保证) | +204 |

**如实报告**:约 3/4 注入点落在已密区 = **表面致密化**而非填洞(RS 纪律下过门即发布,它们是真实验证对,不是噪声;但如果用户的目标只是"填洞",这部分是可选项)。真填洞部分:cap50 694 洞点 + 234 新地板格,cap51 573 + 204。**若肉眼判致密化无益,可从 `rescue_provenance_<cap>.npz` 的 `injected_mask ∧ (cnt10<40)` 直接构造"仅填洞"子候选,无需重跑。**

## 注入点质量(refit 后)

cap50:θ p50=5.9°(p10=2.7°)、maxres p50=0.86px;cap51:θ p50=4.4°、maxres p50=1.15px——都远离 3px/2° 门边缘,不是擦线点。

## 肉眼并排(同 gauge 直出,禁 Sim3)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3 -m http.server 8123 &
# E3 候选(用户已批) vs v1.1(真彩,注入点已按认证配方取色)
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E3_birth_discipline/cap50/e3_candidate_cap50.ply&right=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply"
# 生产基线 vs v1.1
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=E6_rescue_inject/cap50/v1_1_candidate_cap50.ply"
# diff:蓝=注入点,灰=E3 存量
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E3_birth_discipline/cap50/e3_candidate_cap50.ply&right=E6_rescue_inject/cap50/diff_inject_cap50.ply"
# cap51 同法
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E3_birth_discipline/cap51/e3_candidate_cap51.ply&right=E6_rescue_inject/cap51/v1_1_candidate_cap51.ply"
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E3_birth_discipline/cap51/e3_candidate_cap51.ply&right=E6_rescue_inject/cap51/diff_inject_cap51.ply"
```

## 文件清单(SHA256SUMS.txt 为准)

- `e6_rescue_inject.py` — 全管线(python3.11,复跑同序;S1/E2-A/E3 常量逐字复用,SHA 断言上游同云)
- `cap50/`,`cap51/`:`v1_1_candidate_<cap>.ply`(v1.1 候选=E3 存量真彩+注入点认证取色)、`diff_inject_<cap>.ply`(蓝=注入,灰=存量)、`side_by_side_<cap>.png`(E3 vs v1.1 真彩,俯视+立面)、`inject_overlay_<cap>.png`(注入点蓝色高亮)、`spatial_dist_<cap>.png`(距离/密度/分层直方图)、`rescue_provenance_<cap>.npz`(全部 48,226/28,224 对的位姿证据+逐门掩码,可无重跑构造子候选)、`stats.json`(漏斗/四尺/鬼层/分布/SHA 全量)
- `stats_all.json`、`run_both.log`(含首跑教训)、`run_cap50.log`(G7 之前的首跑,保留作证据)

## 诚实边界

- 证据自 sfm_live.db 观测空间重建,**非生产 finalize 逐字节复刻**;注入位置=冻结精化位姿下的 structure-only DLT refit,生产若真收编这些 track 会再走三角化+BA,毫米级会动;
- **首跑教训(已披露不粉饰)**:无 G7 时 cap50 地板厚度 0.04844→0.05172(+3.3mm)——地板注入落在已覆盖格=增厚不填洞,是 2-view 深度噪声壳老病;G7 是对此的规则修正,修正后整跑重来(规则改在用户看产物**之前**,非之后);
- G5 短走廊(相机 <55cm)无 march 证据记干净票:cap50 614 点、cap51 0 点(已声明);G6 若干注入点因彼此 removal 连锁被标,3 轮迭代收敛;
- 904/444 点 NN 回退取色(缺照片帧),占注入 7.8%/7.1%——若肉眼见色斑先查这批(`rescue_provenance` 可定位);
- 约 3/4 注入 = 已密区表面致密化(见上),是否要这部分由用户裁决,"仅填洞"子候选一行掩码可得;
- 注入侧从严各门(G2/G3/G4/G5-双票/G6-零签名/G7)是本机器的取舍声明,**不是认证配置**;本目录一切不 ship,合入生产须签决;
- 墙钟是 host python 代理,非设备数。
