# E12-A BUILD — stage-2 精刀(merge-and-transfer 出生裁决)实现+编译+smoke

日期 2026-07-18(exec 目录沿用 07-19 批次)。执行者:E12-A 实现线。
铁律执行情况:**A worktree 全部 tracked 脏文件零改动**(结束时 `git diff --stat` 与继承基线逐字相同:13 files, +3603/−1411;`bench/aether_sfm_c.cc` SHA-256 仍为 `ad478da3…ca23`)。全部修改只发生在新建 untracked build 目录的源码副本上;零 git commit;编译 -j2;运行前内存核验(6.2-6.5 GB 空闲 > 3 GB 门)。

---

## 1. 语义(实现的是什么刀)

**AETHER_STAGE2_MERGE_TRANSFER=1**(全新 env 臂,默认 OFF=生产/回放行为不变)。在 live 出生闸(与 conflict_mv defer 完全相同的挂点,"neither assigned" 分支)把 CONFLICT_MULTIVIEW_BIRTH 的"冲突 site 一律 defer"替换为:

1. **不 defer 不杀**:冲突 site(bit-identical 像素上 ≥2 个 DSP-SIFT 变体)的匹配不再被整体推迟;
2. **首出生照常**:该 site 家族**尚无已建立 owner** 时,走与普通路径**逐字节相同**的 2-view 出生 gate(CamFromImg → TriangulatePoint → cheirality → tri-angle → reproj ≤ kMaxCreateReprojPx=10px)出生**一个点**,随后把两端 site 的全部未指派变体 alias 到出生观测(union 路由,复用 `ClaimExactSiteOwnerV2Aliases`);
3. **后到竞争假设 = 输家观测,逐个过 gate 转移进同一 track**:site 已有 owner 时,支持度(track 长度,`FindExactSiteOwnerV2Feature` 的"最长 track+确定性平局"规则)定赢家;当前两端观测各自过 **S5 gate 链:同帧查重 → 正深度 → 赢家三角化位 reproj ≤4px(env `AETHER_STAGE2_TRANSFER_REPROJ_PX`)→ 视角锥 <60°(env `AETHER_STAGE2_TRANSFER_MAX_ANGLE_DEG`,cos=0.5)**;过门 AddObservation 进赢家 track,不过门**弃**——**绝不出生第二个点**;
4. **alias 路由的晚到输家观测**(raw≠resolved 经 grow 路径进入已建立 track)同样收紧到上述 4px+60° gate(而非 14px grow 门),跨层 σ_depth 证据被拒收而不是被吸收成有偏中间层(SYNTHESIS 判不适用 WLOP 的教训);
5. **真地板普通 2-view 出生(无冲突 site)完全不动**:单变体 site 永不进精刀分支,普通出生代码文本零改动——这是与 conflict_mv 连坐(cap51 真地板 −42%、覆盖 −30.3% FAIL)的本质区别;
6. 已建立的败者点**不删**(live merge 机器仍是其裁判)——"支持比只定胜负、不定生死"(SYNTHESIS 总裁决)。

## 2. 产物与 SHA

| 物件 | 路径 | SHA-256 |
|---|---|---|
| 源码副本(已改) | `…/glomap_vendor/build-host-e12-stage2/aether_sfm_c_e12.cc` | `97846ba1…a515` |
| 继承基线(未动) | `…/glomap_vendor/bench/aether_sfm_c.cc` | `ad478da3…ca23`(与 E9 RECON 记录逐字一致) |
| 副本 diff | 本目录 `e12_vs_inherited_baseline.diff`(433 行,+341/−4,净 +337) | — |
| **E12 exe** | `…/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_e12_exe` | `ecb1c160…4755` |
| 基线 exe(同树同 flags 新编) | `…/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_exe` | `2e03c66b…1c38` |
| E12 库 | 同目录 `libglomap_core_e12.a`(= libglomap_core.a 换掉 aether_sfm_c.cc.o 成员) | — |

(`…` = `/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor`)

副本内另存 `incremental_triangulator.{h,cc}.refcopy` 为**未修改参考副本**:精刀不经过 IncrementalTriangulator(不用 ≥3-view 支路),triangulator 的继承脏态经 CMake 从 tracked 源正常编入 libglomap_core.a,无需也未做任何改动。

## 3. 编译配方(可复现)

1. `cmake -S glomap_vendor -B build-host-e12-stage2 -DCMAKE_BUILD_TYPE=Release -DAETHER_HOST_GLOMAP_BENCH=ON -DBUILD_BENCH=OFF -DCMAKE_CXX_FLAGS="-I/opt/homebrew/include/eigen3 -I/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/include"`(与 build-host-incremental-ba-ab cache 逐字同参)
2. `make -j2 sfm_replay_bench_exe` → 基线 exe + libglomap_core.a(140 TU,tracked 脏树原样)
3. 副本 TU 用 `CMakeFiles/glomap_core.dir/flags.make` 的逐字 flags 编译,仅追加 `-I$GV/bench`(副本在 bench/ 外,3 个 bench 本地 quote-include 需要);`e12_compile.log` 零警告零错误
4. `ar d` 换成员 + `ranlib`,用 `link.txt` 逐字链接线换库名 → `sfm_replay_bench_e12_exe`
5. 验证:E12 exe 含 3 个新 env 串 + 遥测串;基线 exe 含 0 个(swap 有效性对照)

## 4. 副本 diff 说明(vs 继承基线 ad478da3,函数级)

| # | 位置/函数 | 改动 | 行数 |
|---|---|---|---|
| 1 | env gate 区(ExactSiteOwnerMinDepthGapM 后) | 新增 `Stage2MergeTransferEnabled` / `Stage2TransferMaxReprojPx`(默认 4.0)/ `Stage2TransferMinCosAngle`(默认 60°) | +37 |
| 2 | `struct aether_sfm_session` | 新增 9 个 `stat_stage2_*` 遥测计数器 | +14 |
| 3 | `PrepareSiteOwnershipFrame` | 两处启用门加入 stage2(建 exact_site_grid/site_alias) | +2 |
| 4 | `IsExactSiteConflict` | 启用门 `!conflict_mv` → `(!conflict_mv && !stage2)` | ±1 |
| 5 | `FindExactSiteOwnerV2Feature` | 启用门放宽至 stage2(支持比选主复用;"最长 track+确定性平局"即 S4) | +5/−1 |
| 6 | `ClaimExactSiteOwnerV2Aliases` | 启用门放宽至 stage2(union 路由复用) | +6/−1 |
| 7 | 新函数 `EvaluateStage2Transfer` + `Stage2TransferVerdict` | S5 gate 链单一真相源(查重/正深度/≤4px/<60°),出生分支与 grow 路径共用 | +60 |
| 8 | live pair-loop 出生路径("neither assigned",conflict_mv defer 之前) | **精刀主分支**:owner 探测 → case B 首出生(逐字复刻普通 gate)+认领 / case C 单 owner 转移 / case D 双 owner 支持比定赢家(track 长度,平局取小 pid)→ 逐观测转移+认领;全路径 `continue`,绝不落到第二点出生 | +160 |
| 9 | grow 路径(reproj 门后、AddObservation 前) | alias 路由边(raw≠resolved)加 stage-2 gate 链;grow-accept 后加 stage2 认领 hook(新入 track 的观测把其 site 的变体收编) | +48 |
| 10 | 每帧遥测 | `stage2-merge-transfer` LOG(WARNING),20 帧节律,与 conflict_mv 同款 | +21 |

conflict_mv defer 块本体**原样保留**(其 env 不开即死代码;两 env 同开时精刀分支在前=精刀优先,已注释声明)。

## 5. Smoke(cap51,E9/E4 配方逐字:生产 env face + --k=12 --keep-session-db=0,db 拷贝隔离)

**ON 臂** `smoke/cap51_stage2_smoke/`(manifest 含 binary/input SHA):
- **rc=0;n_reg=105(不掉帧);零断言红线**(`must not contain duplicate matches` / `THROW_CHECK` 两 log 均 0 命中)
- RESULT:n_points=65,364 / track3plus=21,109 / n_obs=172,068 / mean_reproj=0.8671 / stream 4.8s / finalize 11.5s
- 机制咬合遥测(frames=100):**union_events=31,010 / union_births=22,559 / transfers=331 / dedup=23 / rej_reproj=1,907 / rej_depth=0 / rej_angle=0 / alias_claimed=42,972 / competing=0**
- 解读:①冲突 site 家族**真的在出生**(22,559 次首出生 = 反连坐核心生效,对照 conflict_mv 同数据 deferred=69,829 全数不生);②转移 gate 拒:收 ≈5.8:1,方向与 E11 跨层 4px 物理一致(竞争证据大头投不进赢家 4px);③rej_angle=0 与 E11"同向壳视角门几乎不触发"预判一致;④competing=0 = case D 在 cap51 未触发(eager 认领使双 owner 相遇变稀有)——该路径经编译但未被数据行权,E12-B 换 cap 留意。
- 产物:`cloud.ply` + COLMAP bin model(points3D/images/cameras/frames/rigs.bin)+ ghost_mask.bin,壳尺可直接上。

**env-off 对照(同一 E12 exe)** `smoke/cap51_e12exe_envoff/`:
- rc=0;n_reg=105;n_points=65,928 / reproj 0.8623 —— 落在 E9 off 基线噪声带(65,658 / 0.8625);**stage2 遥测串 0 出现 = env 不开精刀完全休眠**。
- 注意:单跑对单跑,65,364 vs 65,928(−0.86%)**不构成壳结论**;正式 A/B(off×3 中位 + 固定框架壳尺 + E9-C 回归门)是 E12-B 的活。

## 6. 设计偏差与诚实边界(如实记录)

1. **"相对支持比"在出生粒度退化为绝对 track 长度**:挑战者恒为 2-view(support=2),已建立 owner 恒 ≥2 → 在位者恒胜(平局含在内);真正的比值裁决只在 case D(双 owner)出现,cap51 smoke 未行权。dossier §5.1 的归一化形态属 finalize 存量清算器,不属出生闸——此为粒度适配,非语义偏离。
2. **union 时机维持在出生闸**(任务预设),未上移匹配层:匹配层收编会改 TVG/db 证据流(E9 RECON 已判该面被 V2 rewrite 占据);出生闸版本零证据破坏。无挂点不适配发现。
3. **只挂 live 环**:enrich/finalize 侧其他出生路径未挂刀——与 conflict_mv 同覆盖面(E9 用同覆盖面拿到 −96%,证明 live 环是壳源主干);若 E12-B 显示残壳,再议扩挂。
4. **gate 数值 4px/60° 为 E8/E11 连续性锚**,env 可重定价;ship 前必须按 'o' 认证口径重标(E11 已声明的纪律:按 χ²5.99≈2.45px 口径 93% 转移会被拒)。
5. case B 的出生 reject 与普通路径**共用** `stat_create_reject_*` 账本(gate 逐字一致故同账),精刀专属账本只记 union/transfer 侧;E12-B 拆账时用 union_events−union_births−(transfers+dedup+rejects)/2 反推 case B gate 拒量(cap51 smoke ≈7.3k)。
6. 观测射线用 FrameRecord 的 ARKit 位姿、mean-dir 用 recon 位姿——与现行 grow/create gate 的混用惯例逐字一致,非新引入。
7. host 单跑计时不可信(±30% 纪律);本文全部墙钟仅作量级参考。

## 7. E12-B 交接(验证矩阵建议)

- `run_e9.sh` 改 EXE 指向 `sfm_replay_bench_e12_exe`、臂 env 换 `AETHER_STAGE2_MERGE_TRANSFER=1` 即可复用(off×3 + ON,cap51 主测床 + cap50 泛化);壳尺用 `e9_shell_metrics_fixed_v2.py`(固定生产平面+shift-only)。
- 回归门:E9-C 全套(覆盖零损 / dC 中位 ≤5mm p90 ≤20mm / n_reg 不掉 / cap50 宽地板不回归 / below-floor=0)+ 遥测 union_events>0(臂生效证明)+ 双红线断言 grep。
- 肉眼:`compare_any.html?left=<off cloud.ply>&right=<stage2 cloud.ply>` 同 gauge 直出禁 Sim3。
