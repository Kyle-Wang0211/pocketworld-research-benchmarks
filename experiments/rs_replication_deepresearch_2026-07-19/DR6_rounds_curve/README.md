# DR6 · stage1 rounds 成本曲线(cap51 host replay)

日期:2026-07-18(runs 11:13–11:26)。目标:为 S3 时间刀"rounds 砍"提供每轮成本曲线——**砍到几轮质量开始掉、每轮到底值多少墙钟**——纯 host 可测遥测,不动设备。

## 方法(单变量)

- **exe**:`.../worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-incremental-ba-ab/sfm_replay_stored_pairs_exe`(§4.2 冻结 harness,SHA-256 前缀 `9583814f7a095fcb`,mtime Jul 14 17:46)。stored-pairs replay:喂 cap51 db 的 keypoints/descriptors/ARKit 位姿,匹配全部原样导入设备存好的 pairs+TVG,**零 matcher 调用**;finalize 走 shipping 的 async live_reuse 路径。
- **env hook 已源码级确认**:`AETHER_STAGE1_ROUNDS_CAP=N (>0)` → stage1 循环上界 = `min(ba_global_max_refinements=5, N)`;unset/0 = shipped。读取点:`bench/aether_sfm_c.cc` `Stage1RoundsCap()`(build 快照 `aether_sfm_c_replay.cc:1117`);消费点:`:4313`(stage1 上界)与 `:4362`(**s2 预算补偿**:`stage2 rounds = max(1, 5 − s1轮)`——被砍掉的轮次会转进串行 stage2)。binary `strings` 亦含该 env。
- **输入**:cap51 `replay_database/sfm_live.db`(105 帧,858 pairs;本目录 `input/` 快照,md5 `cd66e0df…` 每跑后复核不变)+ ledger `private_manifests/sfm_fed_frames.jsonl`。
- **arms**:base(env unset)、base_r2(同配置重跑=噪声带)、cap1..cap5。串行,每跑前 vm_stat 门(可用<3GiB 即等,E1 并行批在跑)。`--k=12`(生产口径),`AETHER_INCREMENTAL_GLOBAL_BA` unset(A 判 OFF)。
- 产物:`runs/<arm>/{run.log,run.err,finalize_segments.json,cloud.ply,COLMAP bin}`;汇总 `curve.json` / `curve.md` / `rounds_curve.png`;逐跑流水 `sweep.log`。

## 结果

| arm | s1轮 | s1_ms | s2_ms | s2预算 | enrich_ms | finalize_ms | total_ms | 点数 | reproj_px | 厚度mm | 注册 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base    | 5 | 17074 | 1633  | 1 | 33368 | 35145 | 41851 | 65653 | 0.826 | 7.153 | 105 |
| base_r2 | 5 | 14603 | 2079  | 1 | 40647 | 42988 | 48720 | 65655 | 0.826 | 6.874 | 105 |
| cap1    | 1 | 3859  | 10256 | 4 | 32086 | 42460 | 49149 | 65662 | 0.827 | 5.642 | 105 |
| cap2    | 2 | 7280  | 7321  | 3 | 32823 | 40229 | 47023 | 65684 | 0.827 | 5.102 | 105 |
| cap3    | 3 | 9552  | 5148  | 2 | 33124 | 38386 | 45021 | 65672 | 0.827 | 6.010 | 105 |
| cap4    | 4 | 14063 | 3108  | 1 | 33506 | 36751 | 43472 | 65684 | 0.827 | 7.244 | 105 |
| cap5    | 5 | 17611 | 3586  | 1 | 33763 | 37596 | 44360 | 65657 | 0.826 | 7.179 | 105 |

(峰值 RSS 全部 ~0.97–1.01 GB;厚度 = 相机中心 umeyama 对齐 ledger 后地板带平面拟合 p84−p16,与冻结的 cap51 incremental-BA 评估器同公式。)

## 读数

1. **每轮边际成本(host,结构性可信)**:s1_ms 随轮数单调 3.9→7.3→9.6→14.1→17.1/17.6 s,即 **~3–4 s/轮(host M 系;A16 设备幅度须另测)**。ftol 收敛停在 cap51 上从未提前触发(base 跑满 5 轮)。
2. **🔴 本形态下砍 rounds 是负优化**:stage1 跑在 enrich 并行窗内(enrich ≈32–41 s 是临界路径),砍掉的轮次经 s2 预算补偿(`max(1,5−s1轮)`)转成**串行** stage2 时间——cap1 的 s2=10.3 s 全在临界路径上,finalize 42.5 s 反超 base 35.1 s。与 cap47 记忆锚"并行语境砍轮次=砍免费时间,只 CAP=4 中性"完全一致。**时间刀只在 stage1 本身成为临界路径的形态才生效**(如 cap47 93 帧热态 stage1≈58 s>enrich),彼时每砍 1 轮按本曲线口径省 ~3–4 s/轮(host)。
3. **质量:1..5 轮全部无损**——点数带宽 31 点(0.05%)、reproj 0.826–0.827、注册 105/105 全平,均在 base vs base_r2 的 run-to-run 噪声带内。⚠️ 但这**不是**"stage1 一轮就够"的证据:cap1 时 s2 预算自动补到 4 轮,总精化轮数被补偿机制保住了。"砍总轮数"(s1+s2 合计 <5)本 harness 没测,需另设 env 或设备批。
4. **厚度 proxy 单跑是抽签**:5.10–7.24 mm;同配置 base vs base_r2 差 0.28 mm,且记忆锚(cap47)判 host 鬼层/厚度类指标须 ≥3 跑取中位。cap1/cap2 的"更薄"**不可当真**。
5. **墙钟噪声再坐实**:同配置 finalize 35.1 vs 43.0 s(差 22%),enrich 33.4 vs 40.6 s——单次墙钟 ±30% 不可信锚成立。本曲线可信的是 s1_ms/s2_ms 随轮数/预算的**单调结构**,不是绝对秒数。

## repay 上限:host 不可测 → 设备批

- 结构性:repay 入口 `aether_sfm_live_repay` 由 App 采集 worker 在**队列有空闲**时调用;本 replay 驱动器(`bench/live_order_stored_match_replay.cc`)从不调它,且 stored-pairs replay 完全绕过 matcher,repay 的"空闲窗重匹配"语义在 host 上无对象。
- 实证:全部 7 跑 `finalize_segments.json` 的 `repay_calls/attempted/written/inliers/failed/skipped_thermal` 六字段全 0。
- 结论:repay 上限(含 thermal=2 清洁小额还的重议)**标设备批**。

## 诚实注记

- exe 为冻结二进制(bench TU 编译于 Jul 14–16);`bench/aether_sfm_c.cc` 源码在 Jul 17 10:30 又有改动(stage1-alias 方向),本曲线**对应冻结版行为**,非最新源码。未改任何 tracked 源码、未 reset/clean、未 git commit。
- 首轮 sweep(base+cap1..5)由前一 session 于 11:13–11:18 完成;其 base_r2 在 11:19 中途被杀,本 session 于 11:25 重跑补齐(sweep.log 已续写),输入 db md5 复核不变。
- host 曲线只回答"结构/每轮成本/质量是否掉";A16 设备幅度、热态形态(stage1 成临界路径)须设备批复验。
