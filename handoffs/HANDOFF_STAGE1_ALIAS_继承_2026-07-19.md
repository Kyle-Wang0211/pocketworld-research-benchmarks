# HANDOFF:stage1-alias arm 家族继承声明(2026-07-19)

> 按 CLAUDE.md"共享脏工作树交接以 HANDOFF_*.md 为准"立此存照。
> 本文件同时存于:`~/Documents/progecttwo/`(本份)与研究仓 `pocketworld-research-benchmarks` 分支 `codex/pocketworld-repro-contract-20260714` 的 `handoffs/`。

## 1. 继承声明
**E 系列线**(RS 复刻执行线,E1-E11,研究仓 `experiments/rs_replication_exec_2026-07-19/`,commit `0a19316`→`2b1e9f9`)自本日起**继承 stage1-alias 线的 arm 家族**,用于 stage-2 精刀(出生前 merge-and-transfer 裁决器)的研发与验证。用户 2026-07-19 口头授权:"按规矩写一份 HANDOFF……声明 E 系列线继承其 arm 家族做 stage-2 精刀,然后开工"。

## 2. 休眠证据(继承依据)
- 被继承线最后动作:**2026-07-17 10:30**(`incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc` mtime),此后树零漂移(E9 RECON 交叉证实);
- 无任何 `HANDOFF_*.md` 声明该线仍活跃;
- 其设计图纸公开在案:`~/Documents/progecttwo/STAGE1_TRACK_TOPOLOGY_RESEARCH_DOSSIER_2026-07-17.md`;
- 其树状态已于 07-17 被冻结存证:研究仓 `experiments/worktree_freeze_2026-07-17/aether_incremental_ba`。

## 3. 继承范围
A worktree(`~/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714`)中该线的未提交改动:
- `bench/aether_sfm_c.cc`(+2855 行):`PrepareSiteOwnershipFrame`/`CanonicalizeSiteOwnerMatches`(one-to-many 自注入)、`AETHER_CONFLICT_MULTIVIEW_BIRTH`、`enforce_exact_site_owner`(0.012m 出生闸)、`AETHER_EXACT_SITE_GEOMETRIC_WINNER`、`AETHER_REPLAY_FIXED_PRODUCTION_POSES`;
- colmap-src triangulator(+138 行,出生闸挂点);
- 其余 11 M / 16 ?? / 1 D / 1 T 未提交项。

## 4. 施工规则(构造性防撞车)
1. **绝不编辑该线的任何脏 tracked 文件**;不 reset/clean/checkout/stash 它的任何改动;
2. E 系列的全部修改只发生在**新建 untracked build 目录内的源码副本**上(先例:`build-host-incremental-ba-ab/aether_sfm_c_replay.cc`),副本以该线当前脏态为基线(即继承其 +2855 行);
3. 全部实验产物/报告/判决 bank 进研究仓 `experiments/rs_replication_exec_2026-07-19/E12_*`;
4. exe/build 产物留在 A worktree untracked build 目录,不入库。

## 5. stage-2 精刀目标与回归门
- **目标**:把 E11 验证过的 merge-and-transfer 机制五件套(逐观测转移/双守护重三角化/小步收敛/构造覆盖守护/照片级误杀审计)移植到**出生前**(产跨边后同一实体 union 成一条 track 再三角化),替换 conflict_mv 的连坐语义;
- **回归门**(E9-C/E11 教训固化):固定生产平面+shift-only 框架量壳;覆盖零损硬门;位姿翘曲门 dC 中位 ≤5mm / p90 ≤20mm;误杀审计=0(照片级);cap50 宽地板拍法不得回归(E9 五臂在 cap50 全翻车是前车之鉴);gate 数值 ship 前按 'o' 口径重标;
- **验证基建**:E9 矩阵协议(`E9_birth_alias/run_e9.sh`,off×3 基线已在库)+ `e9_shell_metrics_fixed_v2.py` + 横截面口径。

## 6. 复活条款
若 stage1-alias 原会话恢复活动:以本文件为协调点;E 系列工作全部在副本内,原树未动一字,双方 diff 副本 vs 原树即可对账;后续归属由用户仲裁。

—— E 系列线,2026-07-19,锚点 commit `2b1e9f9`
