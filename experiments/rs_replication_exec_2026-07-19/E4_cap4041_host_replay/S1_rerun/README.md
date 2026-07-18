# E4-B · S1 统一 2-view 生命周期规则 — cap40/41 host-replay 基线重跑(2026-07-18)

前情:cap40/41 设备交付 meta/PLY 与 pulled db 几何不一致(Sampson ~15px、交付 bbox >100m,
根因=设备 finalize 走全量重解未锚 gauge),S1 四场景验收被卡。E4-A 在 host 重建自洽基线
(Sampson p50 1.117/0.937px,PASS,见 `../README.md`)。本目录 = 用该基线重跑 **同一把
S1 统一规则**(`../../S1_twoview_lifecycle/build_candidate.py`,import 引用,零改动)。

## 基线三元组(inputs/<cap>/,构造脚本 `run_s1_rerun.py`)

- **PLY** = 回放 points3D.bin 坐标(与 `replay_finalize.ply` 逐点同序,最大差 2.4e-7)
  + **host 取色**(生产配方:track 观测 + 全分辨率双线性 + 均值 + round;**raw 像素坐标
  不做 EXIF 旋转** — 在 cap51_control 上对着设备真彩 PLY 裁决:raw 取色 median|ΔRGB|≈8,
  EXIF 旋转取色 ≈55,raw 胜)。cap40:74,278/74,500 取到色,222 点观测全落在缺失/未喂帧
  → rgb=0 如实保留;cap41:62,161/62,161 全取到。
- **meta** = 回放 images.bin 位姿合成(refined=true;frame_id=image_id−1 断言全过)。
- **db** = pulled 设备 db **副本**(wal checkpoint 后)把 cameras.params 补丁成回放精化 K
  (cap40 焦距 2412.83 vs db 2565.38;cap41 2362.33 vs 2566.40 — 回放精化了内参,
  评判必须用同一 K)。源 db 跑后 md5 复核不变(stats `source_db_md5_unchanged: true`)。

同 gauge 由构造保证(位姿+云同出一跑),零 Sim3、零对齐;refit_disp p50=0.0 m 反证
(规则重三角化精确落回基线位置=位姿/云/K 三者自洽)。

## S1 四场景总账表(尺子同一把;基线来源如实分列)

| | cap50 | cap51 | cap40 | cap41 |
|---|---|---|---|---|
| 基线来源 | **设备交付**(live_reuse,自洽) | **设备交付**(自洽) | **host 回放**(设备交付不自洽,弃) | **host 回放**(同左) |
| 注册 | 105/105 | 105/105 | 86/89(回放;设备 meta 84/89) | 102/102(回放;设备 95/102) |
| ①点数 基线→候选 | 92,849→92,312(−0.58%) | 64,392→64,143(−0.39%) | 74,500→74,217(−0.38%) | 62,161→61,976(−0.30%) |
| 裁决构成 | 535 θ<2° + 2 reproj | 247 θ + 2 reproj | 283 θ + 0 reproj | 184 θ + 1 reproj |
| ②地板厚 med cell p90-p10(m) | 0.04843→0.04844 | 0.011802→0.011726 | 0.033379→0.033379(不变) | 0.027398→0.027318(微降) |
| ②厚度 p90 cell(m) | 0.07748→0.07754 | 0.04336→0.04236 | 0.05848→0.05830 | 0.06595→0.06578 |
| ③正确覆盖 2cm 格 | 2185→2182(−0.14%) | 4369→4363(−0.14%) | 7625→7607(−0.24%) | 3943→3930(−0.33%) |
| ④墙钟(host 代理) | 0.9+0.1s | 0.4+0.0s | 0.6+0.3s | 0.6+0.3s |
| 2-view 候选(过/裁) | 2,294(1,759/537) | 1,438(1,189/249) | 15,160(11,972/283)† | 12,688(10,399/185)† |
| 未可裁决保留(<2 obs / 不传递) | 80,573 / 5,389 | 58,781 / 2,497 | **779 / 2,905** | **881 / 2,104** |
| rescue 通过未注入 | 15,694 | 8,538 | 725 | 545 |

†**裁决覆盖率结构性不同,不可跨列直读**:cap40/41 基线云=回放直接从 db stored matches
构造,故 ~99% 点的观测可恢复(cap50/51 设备云 ~87-91% 点恢复不出 2 个已验证观测,只能
原样保留)。这是"基线与证据同源"的构造效应,不是规则变了;四把尺子口径未变。
rescue 数同理:回放云已吸收几乎全部通过对(725/545 漏网),设备云漏 8-15k。

**质量门自评(cap40/41):过。** 厚度不变/微降、覆盖 −0.24%/−0.33%(裁掉的以 θ<2° 低视差
浮点为主,floorband 图肉眼一致)、墙钟近零、无 ROI 冻结对象。

## 产物

- `inputs/<cap>/`:`sfm_sparse.ply`(host-replay 真彩基线)、`sfm_sparse_meta.json`、
  `sfm_live.db`(K 补丁副本,可删可重建)、`prepare_report.json`
- `cap4{0,1}/`:`s1_caseA_<cap>.ply`(候选)、`diff_<cap>.ply`、`rescue_candidates_<cap>.ply`、
  `compare_truecolor_<cap>.png`(真彩并排,格式对齐 cap50/51)、`diff_verdict_<cap>.png`、
  `rescue_overlay_<cap>.png`、`floorband_culls_<cap>.png`、`stats.json`、`render_arrays.npz`
- `stats_all_rerun.json`、`run_s1_rerun.log`、`SHA256SUMS.txt`

## 网页肉眼并排(同 gauge 直出,禁 Sim3;相对 exec 目录起本地静态服务)

- cap40:`compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap40/sfm_sparse.ply&right=E4_cap4041_host_replay/S1_rerun/cap40/s1_caseA_cap40.ply&llabel=cap40%20host-replay%20baseline&rlabel=cap40%20S1%20caseA`
- cap41:`compare_any.html?left=E4_cap4041_host_replay/S1_rerun/inputs/cap41/sfm_sparse.ply&right=E4_cap4041_host_replay/S1_rerun/cap41/s1_caseA_cap41.ply&llabel=cap41%20host-replay%20baseline&rlabel=cap41%20S1%20caseA`
- diff 着色云:`right=E4_cap4041_host_replay/S1_rerun/cap40/diff_cap40.ply`(绿=2-view 留、红=裁、灰=其余)同 cap41。

## 诚实边界

1. cap40/41 基线是 **host 回放**,不是设备交付(设备交付 gauge 已坏,不可当尺);
   host-replay ≠ 设备逐字节(cap51 先例 66,003 vs 64,392)。S1 结论对设备落地前须
   在修好 gauge 的设备 finalize 上复核。
2. 颜色是 **host 取色**非设备 colorize(配方同,口径经 cap51_control 裁决,median|ΔRGB|≈8
   含 NN 身份噪声上界);cap40 有 222 个黑点(观测全在缺失的 frame 79/80/81 JPEG)。
3. 裁决覆盖率结构性升高(见†),跨场景比较看四把尺子,不看覆盖率本身。
4. 回放 gauge 非严格重力对齐(cap41 立面图地板略斜);floor proxy 同一把尺子内比较有效,
   跨 cap 绝对值不可比。厚度单跑是抽签(cap47 锚:host ≥3 跑取中位),本表厚度只作
   基线→候选的**差分**读数(同跑同尺,差分可信)。
5. K 补丁只改 db 副本 cameras.params 一行;源 db md5 前后一致;零 tracked 源码改动、
   零 git 操作。
6. 墙钟 = host python 代理,非设备数;单次墙钟 ±30% 不可信照旧。
