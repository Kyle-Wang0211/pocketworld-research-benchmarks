# E12-B 终审判决书 — stage-2 精刀(merge-and-transfer 出生裁决)矩阵验证

日期 2026-07-18。执行者:E12-B 验证线。上游 E12-A(实现+编译+smoke)全绿交接。
铁律执行:A worktree tracked 脏集零改动(结束态 `git diff --stat` = 13 files +3603/−1411 逐字同;
`bench/aether_sfm_c.cc` SHA 仍 `ad478da3…ca23`);E12 全部产物 untracked;零 commit;串行跑,内存门
5.6-6.0 GB > 3 GB;基线 off×3 复用 E9 在库 runs(未重跑,遵编排指令)。

## 总判决(先说结论)

🔴 **FAIL —— 精刀在其设计主测床 cap51 上不是无效,而是反向行刑:真地板被摧毁(生产框架地板峰
−91.2%),鬼层高度的合并厚层反而变肥(+59%),外加 16× below-floor 垃圾与 p90 119mm 位姿翘曲。**
四回归门 cap51 三门 FAIL(覆盖/位姿/below-floor),仅注册数门 PASS。cap50 无灾难但也无收益,
位姿门边缘超标。机制归因见 §5:这是 E11 早已预言的"gate 通过率 1% 物理 = 出生前 union 也救不了
跨层"的最终坐实,叠加一个新病理:**出生序=时间序 ⇒ 首出生=最低视差=最深偏置假设,
incumbent-always-wins 把最坏的假设永久钉死在 site 上**。

---

## 1. 运行与红线(全绿)

| 项 | cap51_stage2 | cap50_stage2 |
|---|---|---|
| rc / n_reg | 0 / **105(不掉帧)** | 0 / **139(不掉帧)** |
| n_points / reproj | 65,365 / 0.8670 | 92,371 / 0.9766 |
| 断言红线(`duplicate matches`/`THROW_CHECK`) | **0 命中** | **0 命中** |
| 遥测(臂生效证明) | union_births=22,559 transfers=331 rej_reproj=1,907 rej_angle=0 alias_claimed=42,972 **competing=0** | union_births=29,734 transfers=356 rej_reproj≈1,850 rej_angle=0 alias_claimed=56,117 **competing=0** |

- exe = `sfm_replay_bench_e12_exe`(SHA `ecb1c160…4755`,manifest 逐跑记 binary/input SHA)。
- 配方 = run_e9.sh 逐字(生产 env face + `--k=12 --keep-session-db=0`,db 拷贝隔离),见 `run_e12.sh`。
- 确定性:cap51 与 smoke 逐点级一致(65,364→65,365,±1 点);off×3 带内互差 <0.5% —— 非抽签。
- ⚠️ **competing=0 两 cap 皆然:case D(双 owner 支持比裁决)在两个数据集上都未行权**。
  实际被数据检验的规则是"在位者恒胜"(挑战者恒 support=2),真"支持比"从未上场。

## 2. 框架法医:v2 重锚尺在 cap51 stage2 云上失效,须回退生产原框读数

e9_shell_metrics_fixed_v2 口径(固定生产法向 + shift-only 重锚主地板簇)对 stage2 cap51 给出
锚移 **−25.2mm**——但该臂位姿翘曲中位仅 9.8mm(场景没漂 25mm)。法医结论:**重锚簇吸附在了
合并后的鬼高度厚层上**(真地板峰已不存在,"主地板簇"就是病灶本身),因此 v2 重锚帧下的
band_below −79.3%、覆盖 +25.3%、true_floor +29.2% **全部是伪影,不可引用**。
本判决以**生产原框**(不重锚)读数为准——对 stage2 合法,因其位姿翘曲中位仅 ~10mm
(对 E9 conflict_mv 原框读数不合法,其场景整体漂 66mm,故下表该列仅作方向参考)。

**生产原框直尺(analysis/raw_frame_forensics.json;地板峰=[−7.5,+12.5)mm,鬼带=[−45,−20)mm)**

| cap51 | off×3 中位 | stage2 | Δ | 设备生产云 |
|---|---|---|---|---|
| 地板峰 | 11,499 | **1,012** | **−91.2%** 🔴 | 12,118 |
| 鬼带 | 7,034 | **11,174** | **+58.9%** 🔴 | 5,568 |
| 肥层 [−45,−10) | 7,802 | **15,327** | **+96.4%** 🔴 | 7,614 |
| 上方新垃圾 [60,95) | 431 | 2,018 | +368% 🔴 | 351 |
| below-floor (<−100mm) | 104 | **1,665** | **16×** 🔴 | 25 |
| 覆盖 2cm 格(\|fh\|≤30mm) | 4,089 | 3,723 | **−8.9%** 🔴 | 5,525 |

直方图形态(analysis/raw_frame_forensics.log):off = 教科书双峰(+0mm 主峰 6,954/bin,
−35~−30mm 鬼峰 2,399/bin);stage2 = **+0mm 峰塌到 229/bin(−97%),全部质量堆进
−40~−15mm 宽厚层(峰 3,403/bin)**——双层没有合并成真地板,而是合并成了鬼高度的糊层。

**NN 真彩对账独立佐证**:stage2 cap51 云对设备生产云 NN 取色,>10cm 红标点占 **10.66%**
(6,965 点;NN 中位 23.8mm/p90 105.6mm);cap50 仅 0.32%。红标即"生产云中不存在的几何"。

## 3. 四回归门逐项判(E9-C 门)

| 门 | cap51(主测床) | cap50(泛化) | 判 |
|---|---|---|---|
| ① 塌带幅度(双层→单层且留真地板) | 重锚 −79.3% 为伪影;原框:鬼带 +59%、地板峰 −91% = **病理反转** | band_below −8.9%(帧可比,锚 11.2 vs off 10.5mm)| **FAIL** |
| ② 覆盖零损 | 原框 −8.9%(重锚 +25.3% 伪影) | +3.7% | **FAIL** |
| ③ 位姿翘曲(中位 ≤5mm,p90 ≤20mm) | 中位 9.8mm / **p90 119.0mm** | 中位 5.7mm / p90 23.5mm(双边缘超) | **FAIL** |
| ④ 注册数不掉 | 105=105 | 139=139 | PASS |
| (附)below-floor | 1,665(off 104) | 687(off 中位 441) | FAIL |
| (附)cap50 宽地板不回归 | — | 无回归(地板峰 +19%,肉眼同构) | PASS |

## 4. 误杀视角(E9 钝刀 −42% 是反面基准,本刀目标 ≈0)

- E9 conflict_mv:真地板 −42%(固定框架修正口径)。
- **E12 stage2:生产框架地板峰 −91.2% —— 比钝刀杀得更狠**。钝刀是"冲突 site 全不生"
  (双层一起饿死),精刀是"冲突 site 只生第一个假设"——而回放时间序里第一个假设恰是
  最低视差、深度偏置最大的那个(47 号病理的出生端),于是**系统性保鬼杀真**。
- 横截面肉眼(analysis/xsec_e12_cap51.png):OFF 两条密层清晰;stage2 两条层皆无,
  代之以跨越地板线的倾斜糊带 + 红标散点——不是塌缩,是结构摧毁。cap50
  (xsec_e12_cap50.png)stage2 与 OFF 肉眼同构,无灾难。

## 5. 机制归因(为什么精刀反向行刑)

1. **出生序 = 时间序 = 视差升序**:k=12 时间窗回放里,一个 site 家族最先凑齐 2-view 的
   pair 几乎总是最早、基线最短、视差最低的那对——即 bas-relief 深度偏置最大的假设。
   case B"首出生 + union 认领全部变体"把这个最坏假设立为 owner。
2. **支持比在出生粒度恒等于"在位者胜"**(E12-A 已如实预警):挑战者恒 support=2,
   case C 永远判在位者赢;case D(competing>0)在两 cap 上均未发生。裁决器从未裁决,
   只是执行了"先到先得"。
3. **4px 转移门物理上挡死跨层证据**(E11 1% 物理逐字复刻):真地板观测投到鬼位 owner 的
   三角化点上,reproj 远超 4px → 弃。cap51 transfers=331 vs rej_reproj=1,907,外加
   case B gate 拒(反推 ≈7.3k);而 off 的地板峰有 ~11.5k 点需要这些证据出生。
   **门是对的(它正确拒绝了跨层污染),错的是"拒了就弃、绝不出生第二点"**——证据无处安放。
4. alias_claimed=42,972:eager 认领把后续所有触及该 site 的匹配都路由进 owner track,
   真地板从此在该 site 上永无出生机会。BA 只能在"全是鬼向观测"的 track 内优化,
   合并层因混入少量过门的杂观测而变肥(肥层 +96%)、抖出 16× below-floor 与 +368% 上方垃圾。
5. cap50 为何无灾难:宽多层"拍法地板"本就没有干净的双假设竞争,首出生假设与质量中心
   相距不远,故只有轻度重塑(地板峰 +19%、below-floor +246)。

**最终物理定数(回答任务书的预设问题)**:是的——gate 通过率复刻了 E11 的 1% 物理,
**出生前 union 也救不了跨层**。且本实验补充了更强的一条:在时间序回放里,任何
"首出生假设永久占有 site"的机制都会**系统性选中深度偏置最大的假设**。出生闸粒度的
单点裁决(无论 defer 还是 union)已两度证伪;要保住"双层→单真层",裁决必须允许
两个假设都出生、在**证据积累后**(finalize 存量清算,dossier §5.1 归一化支持比形态)
再定生死——这正是 SYNTHESIS"支持比只定胜负"的原义,出生粒度适配丢掉了它的前提。

## 6. 肉眼并排(同 gauge 直出,禁 Sim3)

- cap51:`experiments/rs_replication_exec_2026-07-19/compare_any.html?left=E9_birth_alias/runs/cap51_off_r2/replay_finalize.ply&right=E12_stage2_fine_knife/runs/cap51_stage2/replay_finalize.ply`
- cap50:`…compare_any.html?left=E9_birth_alias/runs/cap50_off_r1/replay_finalize.ply&right=E12_stage2_fine_knife/runs/cap50_stage2/replay_finalize.ply`
- stage2 云已带 NN 真彩(生产云取色,>10cm 纯红标);OFF 回放云无色(灰渲染),几何对账为准。

## 7. 诚实边界

1. ON 臂单跑(off×3 中位为基线):cap51 回放近确定性(与 smoke ±1 点、off×3 互差 <0.5%),
   −91% 量级远超任何噪声带,结论稳;但 below-floor/上方垃圾的精确倍数属单跑读数。
2. 原框直尺对 stage2 含 ~10mm 位姿翘曲混入(其中位 dC),对 −91%/+59% 的主结论无影响;
   对 E9 conflict_mv 原框列不公平(66mm 场景漂),故其正式数字仍以 E9-C 固定框架版为准。
3. case D(真支持比)未被任何数据行权——**本判决证伪的是"出生闸 + 在位者恒胜 + 禁二次出生"
   的组合,不是"支持比"本身**;支持比的 finalize 存量清算形态未被测试。
4. 4px/60° 未重定价即判死:病理是"证据被弃无处出生",放宽 gate 只会把跨层污染吸进 owner
   (E11 已证吸收=有偏中间层),不构成救刀路径;故未跑 gate 扫描,省下的算力如实申报。
5. v2 重锚尺失效是**本臂云形态导致**(主簇=病灶),尺子本身对 off/E9 臂仍有效;
   `analysis/e12_shell_metrics.json` 保留了重锚读数并全部标注伪影,防后人误引。

## 8. 产物清单(全部本目录,untracked)

- `run_e12.sh` + `run_e12_matrix.log`;`runs/cap5{0,1}_stage2/`(run.log/err/manifest/
  solved_poses.csv/COLMAP bin/cloud.ply/**replay_finalize.ply(NN 真彩)**)
- `e12_analysis.py`(壳尺 v2 口径复刻已对 E9 在库数字逐位验证:conflict_mv band −96.26%/
  cover −30.3% 复现);`analysis/e12_shell_metrics.json`(重锚版,伪影已标)、
  `analysis/raw_frame_forensics.{json,log}`(判决主尺)、`analysis/xsec_e12_cap5{0,1}.png`
- 上游:`BUILD.md`(E12-A)、`e12_vs_inherited_baseline.diff`、`smoke/`
