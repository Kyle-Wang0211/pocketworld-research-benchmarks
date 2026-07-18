# E9-A 只读侦察报告(RECON)— 出生前产跨边 + 定出生

日期 2026-07-18。全程只读,零源码改动,零 commit。三件事结论 + 实施路线裁决 + E9-B 行动指令。

---

## ① Jul17 stage1-alias 未提交改动侦察(结论:**别人已把"产跨边+定出生"做到可跑可 A/B 的程度,且已在 cap51/cap56 回放上跑过**)

### 1.1 改动全景(worktree `/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714`,分支 codex/incremental-ba-ab-20260714,HEAD 0a8b8428)

未提交 tracked 改动(git diff --stat):
- `bench/aether_sfm_c.cc` **+2855 行**(mtime Jul 17 10:30,当前 SHA-256 `ad478da3…ca23`)— 全部 alias/出生裁决 arm 的宿主
- `colmap-src/colmap/sfm/incremental_triangulator.{h,cc}` +27/+111(Jul 15 10:50-52)— 出生闸口 hook
- `colmap-src/colmap/sfm/incremental_mapper.cc` +16、`controllers/incremental_pipeline.{cc,h}`、`estimators/bundle_adjustment_ceres.*`(Jul 15,配套)
- untracked:`bench/sfm_replay_bench.cc`(回放驱动)、`build-host-incremental-ba-ab/`(build 目录)、`bench_runs/`(证据)

### 1.2 已实现的机制(源码逐行核实)

**A. COLMAP triangulator 出生闸口(tracked colmap-src 改动,通用 hook)**:
`IncrementalTriangulator::Options` 新增:
- `min_track_length`(默认 2 = 上游原样;可提 3 → 2-view 假设不出生,等第三视图确认)
- `enforce_exact_site_owner` + `exact_site_owner_min_depth_gap`(默认 0.012m):**同一 bit-identical 图像坐标(exact site)只允许一个 Point3D 身份**——候选点出生/续挂/补全前,检查该 site 上已有 3D 点的相机系深度差 ≥ gap 即拒绝(= 双层壳的"第二层"在出生闸口被拒);同深度假设保留。Create()/Continue()/Complete()/CompleteImage() 四个入口全部挂闸。
- `point_birth_gate` / `observation_commit_gate` 两个 std::function 回调(caller 自定义出生/观测提交裁决;空 = 上游行为逐位不变)。

**B. aether_sfm_c.cc 的多条 arm(全部 env-gated,默认全 OFF = 生产行为不变)**:
| arm | env | 机制 |
|---|---|---|
| exact-site alias 身份(产跨边) | `AETHER_EXACT_SITE_IDENTITY` / `AETHER_EXACT_SITE_OWNER_V2`(+`_PERSIST`,`_PERSIST_ALL`) | `PrepareSiteOwnershipFrame` 按 bit-identical x/y 建 `exact_site_grid`,DSP-SIFT orientation/affine 变体互为 alias;`CanonicalizeSiteOwnerMatches` 把 raw match / TVG inlier 的 feature 索引**重写到 canonical owner**(DFSfM"索引重写"范式)→ 重写后同图多变体的边收敛到同一身份,天然形成 one-to-many,由 vendored PR#3681 图层收下 = **"自注入"已实现**。V2=动态所有权(第一个几何接受的观测占有该 site 身份),不删任何已验证对应 |
| 半径版 site owner | `AETHER_SITE_BIRTH_OWNER`(radius 12px / min_cos 0.75 / mean_cos 0.84 / min_views) | 近邻(非 exact)site 聚合,较激进 |
| conflict-only 多视出生(定出生,hybrid) | `AETHER_CONFLICT_MULTIVIEW_BIRTH` | 普通 site 照旧 2-view 出生;**有 exact-site 冲突的 site 的 2-view 出生被 defer**(`stat_conflict_multiview_deferred`),交给 COLMAP IncrementalTriangulator ≥3-view 出生(`ignore_two_view_tracks=true`,min_angle 2°、reproj 2px 可调),消费 `live_corr_graph`(AddTwoViewGeometry 喂入)|
| 冲突 site 的 commit 期 owner | `AETHER_CONFLICT_MULTIVIEW_SITE_OWNER`(+`AETHER_EXACT_SITE_OWNER_MIN_DEPTH_M`) | 打开 triangulator 的 `enforce_exact_site_owner` 深度差闸 |
| 全量多视出生 | `AETHER_MULTIVIEW_BIRTH` | 所有出生走 ≥3-view(all-or-nothing 版) |
| exact-site 几何冠军 | `AETHER_EXACT_SITE_GEOMETRIC_WINNER`(winner 参数族 `AETHER_EXACT_SITE_WINNER_*`:max_reproj 2px/min_angle 1°/depth 0.012-0.100m/reproj margin 0.2px) | 同 site 两条已建立 track 打擂(views/rms/max reproj/角度 strictly_better),败者 `site_birth_suppressed`(**Jul 17 10:30 最新增量**:suppression 跨 post-enrichment 持久化 + 冲突判官日志) |
| postgeom site 指派 | `AETHER_POSTGEOM_SITE_ASSIGN` | 几何验证后最大权一对一 site 指派 |
| publish 门 | `AETHER_PUBLISH_GATE`(+DEPTH_CONFLICT_OWNER / MIN_TRACK_LENGTH / MAX_MEAN_REPROJ 2px / MAX_REPROJ 3px / LOO 4px / MIN_TRI_ANGLE 5°) | 交付侧过滤(cap51 实测 on/off 点数全同 65,794 = 该门当时没咬到东西或语义为标注) |
| 设备位姿冻结控制臂 | `AETHER_REPLAY_FIXED_PRODUCTION_POSES`(**Jul 17 10:30 新增**) | host 回放锁定 95 帧生产位姿(fix_existing_frames + 全帧 SetConstantRigFromWorldPose,跳滚动位姿解算)= device-exact gauge 控制臂,正合 compare 同 gauge 铁律 |

### 1.3 已有回放验证程度(bench_runs/,Jul 15,cap51+cap56)

- `cap51_conflict_multiview_off` vs `_hybrid`:n_points 65,658→64,846(−1.2%),track3plus 19,095→18,972,reproj 0.8259→0.8370,finalize 42.5→40.7s;cap56 同法 16,350→15,559(−4.8%)。manifest 带 input/binary/git_diff SHA,exit 0。
- `cap51_full_multiview_birth_on_v2`(全量多视出生):65,658→61,509(−6.3%),track3plus 19,097→**20,099(+5.2%)**,注册掉 1 帧(105→104)。
- exact_birth_owner on/control、publish_multiview_owner 6 臂等均有 log。
- **关键缺口:所有 run 只有 n_points/track3plus/reproj/时延,没有任何壳指标(双地板带/横截面),没导出 PLY 存档,且没跑过 cap50**。"这些 arm 是否真的塌壳"完全未验证——这正是 E9-B 的活。

### 1.4 可执行性

- 回放 exe:`build-host-incremental-ba-ab/sfm_replay_bench_exe`(Jul 16 21:11,SHA 7648090b,E4 已验证与 DR6 基线一致)。strings 证实该 exe 已含上表全部 arm 的 env 串,**但不含 Jul 17 10:30 的两处增量**(FIXED_PRODUCTION_POSES 控制臂、geometric-winner suppression 持久化)——`libglomap_core.a` 已在 Jul 17 10:30 重编但 exe 未重链。
- 对照冻结快照(研究仓 `experiments/worktree_freeze_2026-07-17/aether_incremental_ba/tracked_modified.patch`)diff:**冻结后仅新增 136 行** = 上述两处;其余 arm 与冻结时逐字一致 → Jul 17 10:30 的"别人改动"已被银行化,当前树未再漂移。
- 输出:exe 每臂落 `cloud.ply` + COLMAP bin model + RESULT 行 → 壳指标可直接在 PLY 上算。
- 调用配方(E4 逐字先例,`E4_cap4041_host_replay/run_replay_v2.sh`):`sfm_replay_bench_exe <sfm_live.db> <sfm_fed_frames.jsonl> <out_dir> --k=12 --keep-session-db=0` + 生产 env face(AETHER_STREAM_TEMPORAL_ONLY=1 AETHER_LIVE_CAND_K_HOT=6 AETHER_TRACK_UPGRADE=1 AETHER_ENRICH_TARGETED=1 AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4 AETHER_GHOST_MASK=1);db 先拷到临时目录防写回。
- 输入齐备:cap50 `data/pocketworld_captures/cap50/device_full_pull_2026-07-17/{sfm_live.db, sfm_fed_frames.jsonl}`;cap51 同层 + `replay_database/sfm_live.db`(DR6 输入在 `rs_replication_deepresearch_2026-07-19/DR6_rounds_curve/input`)。

---

## ② PR#3681 休眠机制定位(结论:vendored 已含、休眠原因坐实、注入面已被 ① 的 rewrite 路径占据)

- **已含(本地一手,与 dossier §2.3 一致)**:`colmap-src/colmap/scene/correspondence_graph.cc` L150 duplicate 判定 = `corr.image_id == image_id2 && corr.point2D_idx == match.point2D_idx2`(双条件,仅完全重复对判重,one-to-many 全保留;含 "checking from only one side is sufficient" 注释)。
- **休眠原因**:(a) `sift.cc` L826-952 `FindBestMatches` 在 cross_check=true(项目铁律,GPU matcher 互检)下取双向最近邻交集,**严格一对一**——管线自然产不出 one-to-many;(b) 图禁自匹配(correspondence_graph.cc L107 `image_id1 == image_id2` 直接拒)→ 同图 alias keypoint 永无直连边(鬼层不自愈的结构性原因,dossier §2.4)。
- **自注入最小改动面**:aether_sfm_c.cc 里 TVG 写入/喂图前的 match 数组——即 `CanonicalizeSiteOwnerMatches`(重写后写 `db->WriteTwoViewGeometry` / `live_corr_graph->AddTwoViewGeometry`)。**这一面已被 Jul17 改动占据并实现**(V2 arm)。不需要也不应该再去 patch correspondence graph 本体。
- 回归红线(dossier §2.5):注入 alias 边后 `SetObservationAsTriangulated` 的 `THROW_CHECK_LE(num_tri_corrs, num_total_corrs)` 断言不得触发(issue #4435 有 abort 实证);E9-B 跑 ON 臂时 run.err 里 grep 该断言。

---

## ③ Dossier 研读(`~/Documents/progecttwo/STAGE1_TRACK_TOPOLOGY_RESEARCH_DOSSIER_2026-07-17.md` v2,305 行;附 `POCKETWORLD_HANDOFF_ADDENDUM_2026-07-17.md`)

定案要点(与 E8/E9 直接相关的):
1. **最小形态 = 产跨边 + 定出生**:Merge/Complete 机器已具备消费 alias 跨边的全部能力(Merge 沿显式边、全轨迹 4px 投票);鬼层不自愈 = 缺 alias 跨边(图禁自匹配)非缺合并机制。E8 已用实测把"事后并"天花板钉死(带内 −4.2%),与此合流。
2. **裁决设计**:相对支持比(camtripsfm 范式,site 内归一化)× 独占观测率作主分,cycle 票决作硬门;**回避"绝对共同观测数"型统计**(SIFT alias 正是 repeatability 病理);triplet 覆盖不足 → ambiguous 不强裁不删数据;阈值定在相对分布上,室内域等价 m 须 Mac 'o' 真值自标定(camtripsfm m 跨域 0.1-0.9,论文默认不可信)。
3. **锁死点**:Continue() 先到先得,裁决须在其前生效(Jul17 改动正是在 Continue/Create/Complete 前挂闸——落点正确)。
4. **site 级出生前裁决无先例**:五家生产系统(OpenMVG 整 track 销毁/AliceVision 整删或 last-wins/Theia first-wins/GLOMAP 10px 固定容差聚合超阈整删/hloc 验证前量化)**无一家做几何证据驱动的自适应 alias 裁决**;官方立场链 #293(给关闭旋钮)→#832/#847(良性忽视)→#1437(承认无机制)→#3681(证据保留、裁决上移)但至今无 birth-time alias 聚合;最窄窗口(verified geometry 之后、track 出生之前、SIFT alias 逐站点)8 线索检索零命中——无撞车也无背书,正确性只能靠九门+多跑中位纪律。
5. **纪律**:host 鬼层指标是抽签(47 号:5 跑 3.6-12.3%)→ 有效性结论须 ≥3 跑中位;ambiguous 留 DB 不出生(与 L2 渲染门哲学同构);别抄 GLOMAP 的固定阈值+整条陪葬。

---

## 实施路线裁决:**用别人已有改动,经 replay 验证;不重复造**

理由:
1. Jul15-17 的改动**正是** "产跨边(exact-site alias 索引重写→one-to-many 进图)+ 定出生(conflict-deferred ≥3-view 出生 + exact-site owner 深度差闸 + 几何冠军 suppression)" 的完整实现,挂闸位置与 dossier 锁死点分析吻合,全部 env-gated 默认 OFF,零 ship 影响。
2. 回放基建现成(sfm_replay_bench_exe + E4 验证过的调用配方 + cap50/51 输入齐备),PLY 直出可上壳尺。
3. 它唯一没做的是**壳指标验证**(bench_runs 只有点数/reproj,且没跑 cap50)——补验证远小于重实现,也符合"E4 发现别人改动就直接用其成果"的编排指令。
4. 若各臂全部塌不动壳,再谈在 build 目录副本上做 dossier §5.1 的相对支持比裁决器(第二阶段,须新代码);现在不做。

---

## E9-B 确切行动指令

**铁律重申:不改任何 tracked 源码;bench/aether_sfm_c.cc、colmap-src/* 是别人的未提交改动,只读;如需改代码,只能复制进新建 untracked build 目录(先例:build-host-incremental-ba-ab/aether_sfm_c_replay.cc)。产物全落本目录;不 git commit;vm_stat <3GB 空闲串行等待;编译 -j2。**

1. **重链 exe(不改源)**:`cd .../glomap_vendor/build-host-incremental-ba-ab && make -j2 sfm_replay_bench_exe`(libglomap_core.a 已是 Jul 17 10:30 态,通常只需重链;build 目录 untracked,允许)。记录新 exe SHA-256。若重链失败,退回 7648090b 旧 exe(缺 Jul17 两增量,仍可测全部主力臂)并如实标注。
2. **A/B 矩阵(cap50 主 + cap51 验,E4 配方逐字,生产 env face 为底)**,每臂独立 out_dir,db 拷贝隔离,`--keep-session-db=0`:
   - `off`:纯生产 env(基线,壳指标自算锚)
   - `conflict_mv`:+`AETHER_CONFLICT_MULTIVIEW_BIRTH=1`
   - `conflict_mv_owner`:+`AETHER_CONFLICT_MULTIVIEW_BIRTH=1 AETHER_CONFLICT_MULTIVIEW_SITE_OWNER=1`
   - `exact_v2`:+`AETHER_EXACT_SITE_OWNER_V2=1`
   - `geom_winner`:+`AETHER_EXACT_SITE_GEOMETRIC_WINNER=1`(需新 exe)
   - (可选第二轮)`AETHER_MULTIVIEW_BIRTH=1`;组合臂 owner+winner;`AETHER_REPLAY_FIXED_PRODUCTION_POSES=1` 控制臂验证 gauge 敏感性
3. **壳指标(E8 口径)**:对每臂 `cloud.ply` 算双地板带(fh∈[−0.06,−0.015))点数、地板厚度 med cell p90-p10 / p90 cell、覆盖 2cm 格(硬门:不得掉)、below-floor(fh<−0.10 须 0);地板系自算(回放基线口径,勿用 v1.1 的 3,917 直比,那是另一条管线);渲染 `ghost_crosssection_floor/wall` 横截面图(E8_shell_collapse/e8_post_analysis.py 与 PNG 生成逻辑可复用)。**off 臂 ≥3 跑取中位**(47 号抽签纪律);ON 臂显著性以中位带对比。
4. **回归硬项**:run.err grep `must not contain duplicate matches` / `THROW_CHECK_LE` 断言(触发即 FAIL);n_reg 不得掉帧(multiview_birth_on_v2 曾 105→104,记为该臂风险);覆盖格硬门。
5. **肉眼并排(铁律)**:同 gauge 直出禁 Sim3,`compare_any.html?left=<off cloud.ply>&right=<arm cloud.ply>`,截图入库;每臂给 stat 行(`conflict-multiview frames= deferred= committed_observations=`、`exact_site_*`)佐证机制真的咬合(deferred=0 = 臂没生效,先查 env)。
6. **诚实汇报**:哪臂带内塌了多少、厚度/覆盖代价、掉帧与否;全塌不动 = 如实报"已有臂天花板不够,须二阶段裁决器",不粉饰。

关键路径速查:
- worktree:`/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/`
- exe:`build-host-incremental-ba-ab/sfm_replay_bench_exe`;E4 配方:`experiments/rs_replication_exec_2026-07-19/E4_cap4041_host_replay/run_replay_v2.sh`
- 输入:`data/pocketworld_captures/cap50/device_full_pull_2026-07-17/`、`cap51/replay_database/sfm_live.db`(或 DR6_rounds_curve/input)+ 各自 `private_manifests/sfm_fed_frames.jsonl`
- E8 壳工具:`experiments/rs_replication_exec_2026-07-19/E8_shell_collapse/{e8_shell_collapse.py,e8_post_analysis.py}`
- 冻结对账:`experiments/worktree_freeze_2026-07-17/aether_incremental_ba/tracked_modified.patch`
