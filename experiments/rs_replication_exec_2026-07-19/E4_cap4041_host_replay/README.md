# E4 · cap40/cap41 host 回放自洽基线(2026-07-18)

背景:S1 四场景验收发现 cap40/41 的 pulled db 匹配与设备交付 meta 精化位姿几何不一致
(per-pair median Sampson p50 = 15.7px / 14.2px,根因=设备 finalize 走了全量重解而非
live_reuse;诊断见 `../S1_twoview_lifecycle/cap4{0,1}/db_meta_consistency.json`)。
本实验按用户指示在 Mac 上用 host 回放 harness 重建自洽基线。

## 结论(TL;DR)

| | cap51_control | cap40 | cap41 |
|---|---|---|---|
| rc | 0 | 0 | 0 |
| 注册 | 105/105 | **86/89**(设备 meta:84/89) | **102/102**(设备:95/102,closure 缺口在 host 上消失) |
| n_points(finalize 模型) | 66,003 | 74,500 | 62,161 |
| RESULT mean_reproj_px | 0.830 | 0.989 | 1.042 |
| **自洽验证 Sampson p50(px)** | 1.051 | **1.117**(原设备 meta:15.686) | **0.937**(原:14.2) |
| frac pairs <3px | 0.93 | 0.93 | 0.95 |
| **track 重投影中位(px)** | 0.497 | 0.652 | 0.707 |
| 自洽裁决 | **PASS** | **PASS** | **PASS** |

**cap40/41 host 回放位姿回到 ~1px 量级(cap50/51 口径),自洽基线成立。**

## 对账:回放 vs 设备交付 PLY(同 gauge 直出,禁 Sim3)

| | cap51_control | cap40 | cap41 |
|---|---|---|---|
| 回放点数 vs 设备交付 | 66,003 vs 64,392(+2.5%) | 74,500 vs 62,691 | 62,161 vs 51,000 |
| NN p50(回放→设备) | **0.041 m** | 7.06 m(无意义,见下) | 22.1 m(无意义) |
| 回放 bbox(m) | 8.1×4.0×3.7 | 4.9×10.6×5.6 | 5.2×4.4×6.6 |
| 设备交付 bbox(m) | 7.9×11.2×12.4 | **111.6×45.2×85.2** | **115.7×54.4×146.8** |
| 回放地板厚 proxy(cell p90-p10 中位) | 15.7 mm(设备 11.8 mm) | 33.4 mm | 27.4 mm |
| 设备地板厚 proxy | 11.8 mm | 不可算(floor_y=-15.5m,检测崩) | 不可算(floor_y=-25.6m) |

- 🔴 **新证据:cap40/41 设备交付云不只位姿不一致,gauge/尺度本身跑飞**——房间级场景交付
  bbox >100m、centroid 偏出 -30m/-25m。与"全量重解未锚 ARKit gauge"根因一致。NN 对账在
  此 gauge 断裂下无意义,如实报出不粉饰。cap51 对照(live_reuse 交付)NN p50=4cm,
  证明对账口径本身没问题。
- **host-replay 基线 ≠ 设备逐字节**(cap51 先例:65,658 vs 64,392;本控制跑 66,003 vs
  64,392)。点数差含 host/device 浮点与 harness 版本差,不是回归信号。
- 厚度 proxy 单跑是抽签(cap47 记忆锚:host 须 ≥3 跑取中位),本表数字只作量级参考。

## 方法

- **exe(与 DR6 不同,原因见"诚实注记①")**:`sfm_replay_bench_exe`
  SHA-256 `7648090b9a93f2c7b856a45fe37c066ceeca309e82736f5f8b1123f66cbdb22b`
  (build-host-incremental-ba-ab/,链接于 Jul 16 21:11,源 `bench/sfm_replay_bench.cc`
  mtime Jul 16 19:30;早于 Jul 17 10:30 的 aether_sfm_c.cc stage1-alias 方向改动)。
  同一条 stored-pairs live-reuse 管线:`AETHER_REPLAY_MATCH_DB` 喂设备存好的
  matches+TVG,零 matcher 调用(run.err 证据:`finalize enrichment skipped
  (matcher_calls=0)`),finalize `live_reuse=1`。
- **命令行**(抄 DR6 sweep.log 格式):`exe <sfm_live.db副本> <sfm_fed_frames.jsonl> <outdir> --k=12 --keep-session-db=0`
- **env 面 = 生产装机臂**(Q8_env_audit.md 逐项):`AETHER_STREAM_TEMPORAL_ONLY=1
  AETHER_LIVE_CAND_K_HOT=6 AETHER_TRACK_UPGRADE=1 AETHER_ENRICH_TARGETED=1
  AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4 AETHER_GHOST_MASK=1`,其余 unset。
  控制跑(cap51_control)故意用 DR6 面(全 unset)以便与 DR6 冻结基线可比。
- **输入**:cap40 `device_full_pull_2026-07-17`、cap41 `device_db_pull_2026-07-17` 的
  `sfm_live.db(+wal/shm 副本)` 与 `sfm_fed_frames.jsonl`;每跑用副本,跑后源 db md5 复核
  不变(cap40 `9f6585d8…`、cap41 `a8997f27…`、cap51 `cd66e0df…`)。串行,每跑前
  vm_stat 门(<3GiB 等待;实测 5.5-6.7GB 未触发)。
- **自洽验证**(`validate_replay.py`):与 S1 `db_meta_consistency.json` 同口径的
  per-pair median Sampson(db two_view_geometries 内点 × 回放位姿)+ points3D.bin 全
  track 重投影;门=两者中位 <3px 判 PASS(实际全部 ≤1.1px)。

## 产物(runs/<cap>/)

`run.log`、`run.err`、`solved_poses.csv`(回放位姿)、`cameras/images/points3D/frames/rigs.bin`
(COLMAP bin 模型)、`replay_finalize.ply`(**finalize 模型导出,与 RESULT n_points 一致,
供 compare.html 肉眼对账**)、`cloud.ply`(见注记③)、`finalize_segments.json`、
`ghost_mask.bin/json`、`consistency.json`;汇总 `consistency_summary.json`、
`validate.log`、逐跑流水 `replay_sweep_v2.log`。SHA 见 `SHA256SUMS.txt`。

## 诚实注记

1. **🔴 指定的 DR6 exe(sfm_replay_stored_pairs_exe,sha 9583814f…)跑不了 cap40/41——
   它被 cap51 硬编码钉死**。反汇编其 "stored replay input is incomplete" 分支:要求
   stored_matches 字节数 == 0x6b40(=858×32,即恰 858 对)且 nonempty_matches == 0x35a
   (=858)——cap51 的精确对数。cap40(1067 对)/cap41(928 对)进门即 rc=5(证据:
   `runs_pinned_exe_failed/`)。改用未钉死的同管线 `sfm_replay_bench_exe` 并加 cap51
   控制跑验证,不算硬凑。
2. **harness 版本差(Jul-14 冻结 vs Jul-16)**:控制跑 vs DR6 base——注册 105=105、
   reproj 0.8297 vs 0.8259、点数 66,003 vs 65,653(+0.53%,略超 DR6 run-to-run 31 点带,
   判 harness 版本差非噪声);finalize 段结构也变了(本 build stage1_rounds=0、精化全在
   stage2,DR6 冻结版 s1 跑满;finalize_ms 13.3s vs 35.1s,墙钟单次 ±30% 不可信照旧)。
   质量端点(注册/reproj/点数量级)带内,自洽结论不受影响。
3. **cloud.ply ≠ finalize 云(本 build)**:aether_sfm_get_points 在此版本只导出
   ~12-20k live/preview 子集(DR6 冻结版写的是全量 65,653)。finalize 云=points3D.bin
   (与 RESULT n_points 逐一致),已导出为 `replay_finalize.ply`。
4. **回放 PLY 无颜色**(rgb 全 0):回放不读 JPEG,不走设备 colorize。肉眼对账看几何;
   如需真彩须另跑 colorize(cap40/41 photos_highres 在 pull 目录里,cap40 缺 3 张)。
5. **cap40 缺口如实带过**:回放注册 86/89,未注册=frame 79/80/81(连续三帧,与"cap40
   缺 3 张 JPEG"缺口对齐;stored-pairs 回放不需要 JPEG,故是匹配图连通性缺口非文件缺口)。
   另 cap40 stage2 有 6 次 dense Cholesky LM step 失败告警(LM 重试自恢复,已知 dense
   dpotrf 病理,非崩溃),终态质量门全过。cap41 的 95/102 closure 缺口在 host 回放上
   **不存在**(102/102 全注册)——缺口属设备全量重解路径,非数据本身。
6. 本批未改任何 tracked 源码、未 git commit、未动共享 worktree 脏改动;产物全部只写本目录。
