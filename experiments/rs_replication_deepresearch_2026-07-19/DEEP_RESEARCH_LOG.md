# DEEP_RESEARCH_LOG — RS 复刻深度调研状态板(2026-07-18 汇总)

> 汇总 agent 生成。证据级标注:**VERIFIED**(一手多源交叉)/ **SUPPORTED**(单源或代理源)/ **INFERENCE**(推断)/ **UNRESOLVED**(未解)/ **UNTESTED**(未实测)。
> 铁律:本目录只写研究 worktree;不改 tracked 源码、不 git 操作、不动他人 dirty 文件;质量无损硬门;RS mobile 内部 = UNRESOLVED 红线。

---

## 用户 7 项清单状态板

### 1. DR1 — RS 桌面版参数核实 【完成】
- **Mac 版存在与否:VERIFIED 不存在。** RealityScan 桌面版历来 Windows-only(realityscan.com/download 一手 + dev.epicgames.com docs + KB DB58 + CG Channel 2.2 + Wikipedia 四方一致)。Linux 仅 CLI(Wine 打包)。"Mac 装 RS 抄面板" 前提不成立,诚实报废。
- **下载渠道:** 仅 Epic Games Launcher 分发,无免登录独立包 → downloads/ 留空,无 SHA 可报。
- **参数升级账(替代路径超额兑现):** 官方 Keys and Values 键值表(rshelp.capturingreality.com,一手,SHA256=1396…e455)含全部设置 Default 列。双源交叉(rshelp × dev.epicgames 代理)Alignment 段 100% 一致。**升 VERIFIED**:Max features/image=40,000(另有 KB DB58 三证)、per mpx=10,000、Preselector=10,000、Detector sensitivity=Medium、Max reprojection error=2.0px、Image overlap=Medium、Image downscale=1(社区"默认3"=混淆深度图降采样 Preview=4/Normal=2)、Feature detection quality=High、Force component rematch=false、Draft final BA=false、Distortion=Brown3、camera priors 全套、重建纹理段全表(101 行)。
- **残余非 VERIFIED:** "Merge components only"(结构性 SUPPORTED,显式动作非持久设置);键值表↔2.2 装机包逐位一致(SUPPORTED,唯一剩给实机);两官方源 2 个控制点先验字段漂移(2.0/4.0、0.10/0.001,与复刻无关,记录在案)。
- **用户最后一步(已降为可选):** Windows 10/11 x64 机(无需 NVIDIA)→ Epic Launcher → 装 RS → 截 Alignment Settings 面板对照;无实体机备选 VMware Fusion + Win11 ARM 24H2(Prism AVX2 仿真,UNTESTED)。清单在 DR1 README §5。
- 产物:`DR1_rs_desktop/README.md`、`defaults_table_full.md`、`evidence/`(16 件 + SHA256SUMS.txt)。
- 网络注记:dev.epicgames.com 被本网络 TLS/SNI 掐断,内容经 r.jina.ai 代理抓取并与一手表交叉核对;其余站直连正常。

### 2. RS mobile 内部 — 永久 watchlist 【红线 UNRESOLVED,只跟踪不猜】
- 状态:RS mobile 拍摄期内部算法 = **UNRESOLVED 红线不动**,禁止用推断当事实。
- **检查方式(每次触碰 RS 复刻课题时执行):**
  1. `https://dev.epicgames.com/documentation/en-us/reality-scan/` 官方文档树 diff(本网络需经 r.jina.ai 代理);
  2. RealityScan release notes / KB(rshelp.capturingreality.com + realityscan.com 新闻页)新版本条目;
  3. Epic 官方论坛 forums.unrealengine.com RealityScan 板块官方员工回帖;
  4. 仅官方一手材料可升级证据级;社区逆向/传闻只记不采信。

### 3. E1 Q8 【进行中,引用】
- E1 批(Q8)由并行 session 在跑,本板只挂状态,结论以 E1 自身产出为准(见其 session 产物目录/汇报)。⚠️ E1 并行占内存,重活串行铁律已在 DR5/DR6 执行中遵守。

### 4. 被裁幅度 / 真机墙钟 【拆分:host 出数 + 设备批】
- 被裁幅度 = E1 S1 出(引用,进行中)。
- 真机墙钟 → **设备批队列**(见下),host 墙钟 ±30% 单次不可信锚在 DR6 再坐实(同配置差 22%)。

### 5. DR5 — MVS free-space 定价 【完成】
- 核心数(cap50,139 帧,92,849 稀疏点,Mac 实测,双实现互证,热受控):
  - 纸面账:CasDiffMVS 补推理 139×709ms ≈ 98.6s 是唯一大项;若稠密段本就全帧出深度,free-space 反证边际成本 = 秒级 + <10MB 流式内存,近乎免费。
  - carve 核 2.17–2.21ms/视 → 139 视 0.30s;2M 稠密点 47.4ms/视 → 6.6s(线性);A16 保守 ×5 仍量级安全。内存**必须流式**(全驻留 510MB 违规,流式 3.67MB/图)。
  - 覆盖:139 视 λ≈37.6 观测/点,3× 聚集折扣后 P(≥3 观测)≈99.96% → 净票仲裁充分;5 视仅 42.3% 点 ≥2 观测(=过夜 #4 定量形态);margin 3%→6.4% 点被看穿、8%→2.0%(平滑旋钮)。
- **诚实边界:** 深度源是 L1 plane-sweep(384 档 ~1.1cm 量化)非 CasDiffMVS 输出(计时可迁移,票型统计偏保守);709ms/帧 vs 过夜"每视 80s"的 100× 矛盾已标注;A16 UNTESTED;杀伤百分比无 ground truth 不承诺,门限须 Mac 'o' 真值 + 肉眼对比签定。**spike 定价,非实现承诺。**
- **S2 判别力预检 = 稠密段课题注记:** free-space 票的判别力最终取决于稠密深度质量,须待稠密段(CasDiffMVS 输出)落地后用真实票型复测,勿以 plane-sweep 代理票型下强结论。
- 产物:`DR5_mvs_freespace_pricing/PRICING.md`(先行 agent 11:07 版,数字与独立复测一致)、`ADDENDUM_margin_dense_scaling.md`、双基准脚本、`bench_results.json`(⚠️11:24 被本实现覆盖,先行数字已完整摘录进 PRICING.md §1/§3 无丢失)、`margin_sensitivity.txt`。

### 6. DR6 — rounds 曲线 【完成】
- env 确认:exe=`sfm_replay_stored_pairs_exe`(§4.2 冻结,SHA 前缀 9583814f);源码级确认 honor `AETHER_STAGE1_ROUNDS_CAP`(Stage1RoundsCap() 读 env,上界 min(5,N),被砍轮次经 max(1,5−s1轮) 转入串行 stage2;aether_sfm_c_replay.cc:1117/4313/4362)。无需重编译。
- 曲线读数(base + cap1..5 + base_r2,7 跑):
  - 每轮 s1 成本 ~3–4s/轮(host:3.9/7.3/9.6/14.1/17.1s @1..5 轮);ftol 从未提前收敛停。
  - 🔴 **cap51 host 形态下砍 rounds 是负优化**:enrich(~32–41s)是临界路径,stage1 在其并行窗内免费;砍掉轮次转串行 stage2(cap1: s2=10.3s),finalize 42.5s 反超 base 35.1s。与 cap47 记忆锚一致。时间刀只在 stage1 自身成临界路径(93 帧热态 ~58s)形态生效。
  - 质量 1..5 轮全无损(点数带宽 0.05%、reproj 0.826–0.827、注册 105/105)——⚠️非"1 轮就够":s2 预算补偿保住总轮数;"砍总轮数"未测。
  - 厚度 proxy 5.10–7.24mm 单跑抽签(重跑差 0.28mm,须 ≥3 跑中位);墙钟同配置差 22%。
- **repay 上限 host 不可测 → 设备批**:结构性(replay 驱动器从不调 `aether_sfm_live_repay`,stored-pairs 绕过 matcher,无采集空闲窗语义)+ 实证(7 跑 repay_* 六字段全 0)。
- 注记:exe 冻结于 Jul 14–16;bench/aether_sfm_c.cc Jul 17 10:30 另有 stage1-alias 方向改动,曲线对应冻结版行为。
- 产物:`DR6_rounds_curve/README.md`(含 curve.md/curve.json/rounds_curve.png/sweep.log,runs/ 7 跑全量)。

### 7. E1 联网闭环 【进行中,引用】
- 由并行 session 在跑,结论以其产出为准,本板只挂状态。

---

## 设备批队列(凑一次装机全测)
| # | 待测项 | 来源 | 说明 |
|---|--------|------|------|
| 1 | 真机墙钟(cap51 形态 finalize 分段) | 清单 4 / DR6 | host 墙钟 ±30% 不可信;A16 幅度须实测 |
| 2 | repay 空闲还债上限 | DR6 | host replay 结构性不可测(repay_* 全 0) |
| 3 | A16 热态 rounds 形态复验 | DR6 | 时间刀仅在 stage1 成临界路径(93 帧热态 ~58s)时生效,须设备确认形态 |
| 4 | enrich 子计时拆解 | DR6 / 清单 6 | enrich 是 host 临界路径(32–41s),设备上占比待测 |
| 5 | A16 LAPACK 收尾幅度 | 清单 6 / 记忆锚 | Mac −65%,A16 幅度必须实测(运行时开关已在库,可暗 ship A/B) |
| 6 | phase-1 + colorize 并行 | 清单 6 / cap47 记忆锚 | colorize 并行设计 6.8→~2s,须设备验证 |
| 7 | free-space carve A16 计时 | DR5 | Mac 2.2ms/视,保守 ×5 估计 UNTESTED |
| 8 | host 鬼层 bimodality ≥3 跑中位规程 | cap47 记忆锚 | 设备云确定/host 抽签,涉厚度类指标装机批同测 |
| 9 |(可选)Windows 实机截 RS Alignment 面板 | DR1 | 已降为可选;键值表↔装机包逐位一致是唯一剩余价值 |

## 待 commit 文件清单(编排者统一提交,本目录全部 untracked)
- `DEEP_RESEARCH_LOG.md`(本文件)
- `DR1_rs_desktop/`:README.md、defaults_table_full.md、evidence/(16 件 + SHA256SUMS.txt)
- `DR5_mvs_freespace_pricing/`:PRICING.md、ADDENDUM_margin_dense_scaling.md、carve_bench.py、bench_freespace_carve.py、bench_results.json、margin_sensitivity.txt
- `DR6_rounds_curve/`:README.md、curve.md、curve.json、rounds_curve.png、sweep.log、runs/(7 跑:run.log、finalize_segments.json、cloud.ply、COLMAP bin)
- E1 相关产物由其 session 自行入列(引用)
