# E4 执行批日志(rs_replication_exec_2026-07-19)

- 日期:2026-07-18(E4-A host 回放自洽基线 + E4-B S1 四场景补齐)
- 范围:全部产物只写 `E4_cap4041_host_replay/`(研究 worktree,整体 untracked);**零 tracked
  源码改动、零 git 操作**(由编排者统一提交)。python3.11;vm_stat 门未触发(E3 批彼时未在跑,
  可回收内存 ~6GB)。
- 背景:cap40/41 pulled db 与设备交付 meta 位姿几何不一致(Sampson ~15px,根因=设备 finalize
  走全量重解非 live_reuse),S1 四场景验收被卡;用户指示 Mac host 回放重建自洽基线。

---

## E4-A:cap40/41 host 回放自洽基线(`E4_cap4041_host_replay/README.md`)

- **自洽验证双双 PASS**:cap40 Sampson p50 1.117px(原设备 meta 15.686)、cap41 0.937px
  (原 14.2);track 重投影中位 0.652 / 0.707px;cap51_control 对 DR6 冻结基线对齐
  (105=105 注册,reproj 0.830 vs 0.826)。
- 注册:cap40 86/89(缺 frame 79/80/81,匹配图连通性缺口);cap41 **102/102**(设备 95/102
  的 closure 缺口在 host 上消失=设备全量重解路径问题,非数据问题)。
- 🔴 指定 DR6 exe(sha 9583814f)被 cap51 硬编码钉死(要求恰 858 对),cap40/41 进门 rc=5;
  改用同管线未钉死 `sfm_replay_bench_exe`(sha 7648090b…)+ cap51 控制跑验证。
- 🔴 新证据:cap40/41 **设备交付云 gauge/尺度整体跑飞**(bbox >100m、floor_y −15.5/−25.6m),
  NN 对账在 gauge 断裂下无意义(如实报 7m/22m);cap51 对照 NN p50=4cm 证明口径没问题。
- env 面=生产装机臂 7 项(Q8 口径)逐项设置;输入 db 用副本,源 md5 跑后复核不变。

## E4-B:S1 统一规则重跑于 host-replay 基线(`E4_cap4041_host_replay/S1_rerun/`)

基线三元组构造(`run_s1_rerun.py`;`build_candidate.py` import 引用零改动):

- PLY = 回放 points3D.bin(与 replay_finalize.ply 逐点同序,差 2.4e-7)+ **host 取色**
  (生产配方 track 观测+全分双线性+均值+round;raw 像素坐标不做 EXIF 旋转——cap51_control
  对设备真彩裁决 raw median|ΔRGB|≈8 vs 旋转 ≈55)。cap40 取到 74,278/74,500(222 黑点=
  观测全在缺失 JPEG);cap41 62,161/62,161 全取到。
- meta = 回放 images.bin 位姿(refined=true);db = pulled db 副本 + cameras.params 补丁成
  回放精化 K(cap40 f 2412.83 vs db 2565.38;cap41 2362.33 vs 2566.40),源 db md5 不变。
- 同 gauge 由构造保证;refit_disp p50=0.0m 反证三元组自洽。

**S1 四场景总账**(完整表在 `S1_rerun/README.md`;cap50/51=设备基线,cap40/41=host-replay 基线):

| 尺子 | cap50 | cap51 | cap40(host-replay) | cap41(host-replay) |
|---|---|---|---|---|
| 点数 | −537(−0.58%) | −249(−0.39%) | 74,500→74,217(−0.38%) | 62,161→61,976(−0.30%) |
| 裁决构成 | 535θ+2r | 247θ+2r | 283θ+0r | 184θ+1r |
| 厚度 med cell(m) | 0.04843→0.04844 | 0.011802→0.011726 | 0.033379→0.033379 不变 | 0.027398→0.027318 微降 |
| 覆盖 2cm 格 | −0.14% | −0.14% | 7625→7607(−0.24%) | 3943→3930(−0.33%) |
| 墙钟(host 代理) | ≈1.0s | ≈0.4s | ≈0.9s | ≈0.9s |

**质量门自评:四场景全过**(厚度不劣化、覆盖近零损、裁掉的以 θ<2° 低视差浮点为主,
floorband 肉眼一致)。⚠️ 结构性差异如实:cap40/41 裁决覆盖率 ~99%(基线与证据同源的构造
效应;cap50/51 设备云 ~87-91% 点观测恢复不出,只能原样保留)——跨场景看四把尺子,不比覆盖率。
rescue 未注入照旧(cap40 725 / cap41 545)。

**下一步留用户/编排者**:①用户肉眼批准(compare_any.html 链接在 S1_rerun/README.md);
②设备 finalize gauge 跑飞是独立生产 bug(全量重解未锚 ARKit gauge),须单独立案修复后在
设备复核 S1;③设备端 refit 墙钟实测。

---

## 待 commit 清单(编排者统一提交;本批全部 untracked 落盘)

```
experiments/rs_replication_exec_2026-07-19/E4_cap4041_host_replay/
  README.md  SHA256SUMS.txt  consistency_summary.json  validate.log  validate_replay.py
  run_replay.sh  run_replay_v2.sh  replay_sweep_v2.log
  runs/{cap40,cap41,cap51_control}/…(52 文件,含 replay_finalize.ply / solved_poses.csv / bin 模型)
  runs_pinned_exe_failed/…(钉死 exe rc=5 证据)
  S1_rerun/
    README.md  SHA256SUMS.txt(34 文件)  run_s1_rerun.py  run_s1_rerun.log  stats_all_rerun.json
    inputs/{cap40,cap41}/{sfm_sparse.ply, sfm_sparse_meta.json, sfm_live.db(K补丁副本,~130MB,可标 LFS 或删除后由脚本重建), prepare_report.json}
    {cap40,cap41}/{s1_caseA_*.ply, diff_*.ply, rescue_candidates_*.ply, 4×PNG, stats.json, render_arrays.npz}
experiments/rs_replication_exec_2026-07-19/E4_EXEC_LOG.md(本文件)
```

注:`S1_rerun/inputs/*/sfm_live.db` 是唯一大文件(2×~130MB),内容=pulled db + 一行 K 补丁,
可由 `run_s1_rerun.py` 确定性重建 → 建议编排者裁决是否入库(不入库亦可复现)。
