# Q8 · 生产 env 开关面只读核查(2026-07-18 执行)

只读来源:
- 生产臂 Swift:`/Users/kaidongwang/Developer/pocketworld/ios/Runner/AetherARKitPlugin.swift`(register(),L78-118)
- C++ unset 默认:`/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc`
- E worktree 对照:`/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/shutter-v2-thermal-p0-20260714/ios/Runner/AetherARKitPlugin.swift`(L2242-2278)

Mac 自检:vm_stat 页 16KB,free≈18k 页(~0.28GB free,active+inactive 各 ~40 万页)— 本任务纯只读,无内存压力风险。

## 开关面总表(Swift 设置 vs C++ unset 默认)

| env | Swift 生产设 | C++ unset 默认 | 生效状态 | 备注/签决对账 |
|---|---|---|---|---|
| AETHER_STREAM_TEMPORAL_ONLY | `"1"`(L82) | OFF(e[0]=='1' 才开,L684) | 强制纯时间 K12 候选,spatial-first 关死 | 与记忆一致(spatial-first 二次判死,验证通过前默认关死) |
| AETHER_LIVE_CAND_K_HOT | `"6"`(L90) | 0=OFF(L4807,07-11 A/B 判 ship DISABLED、opt-in 待签) | 热态(thermal≥2)live 候选 12→6 | Swift 注释称 host A/B 全门绿后 opt-in;⚠️与 spatial-first kill switch 绑定 |
| AETHER_LIVE_CAND_K | 未设 | 0=用 options.k_neighbors | shipped K12 | — |
| AETHER_TD_GROW_REFIT | **注释掉**(L102) | OFF(L1017) | **OFF** | 07-11 cap47 法医定罪关停(从犯)✅一致 |
| AETHER_TRACK_UPGRADE | `"1"`(L103) | OFF(L1026) | ON | cap47 消融无罪且正收益,保留 ✅ |
| AETHER_ENRICH_TARGETED | `"1"`(L104) | OFF(L1035) | ON | 同上 ✅ |
| AETHER_ENRICH_PAIR_CAP | `"300"`(L105) | 无 override(max(默认,N) 语义,L1001) | cap=300 且是 floor | 与 joint sweep 定案"cap 语义=max(默认,N)"一致 ✅ |
| AETHER_FRAG_MERGE | **注释掉**(L106) | OFF(L1063) | **OFF** | 🔴见下"矛盾①" |
| AETHER_FRAG_MERGE_REPROJ_PX | 注释掉(L107) | 0.0→回落 3px 门(L1075) | n/a(随 FRAG_MERGE 关停) | — |
| AETHER_FRAG_MERGE_MIN_THETA_DEG | 未设 | 0.0=不启用 θ 门(L1089) | n/a | cap47 重开条件=θ≥5° 门重定价,尚未启用 |
| AETHER_TD_GROW_REFIT_MIN_THETA_DEG | 未设 | 0.0(L1099) | n/a | 同上 |
| AETHER_STAGE1_ROUNDS_CAP | `"4"`(L113) | 0=shipped 不设帽(L1119) | stage-1 loop=min(ba_global_max_refinements,4) | 与 cap47 记忆"只 CAP=4 中性"一致 ✅;rounds3+ftol 记忆锚不迁移 |
| AETHER_STAGE1_FTOL | 未设 | 0.0=shipped 1e-6(L1128) | shipped | ✅未擅自迁移 'o' 的 ftol |
| AETHER_GHOST_MASK | `"1"`(L118) | OFF(L4007) | ON:finalize 尾段写 ghost_mask.bin sidecar+L1 推理遥测 | 纯采集不 gate 交付;与"L1 暗舱标定"记忆一致 ✅ |
| AETHER_INCREMENTAL_GLOBAL_BA | 未设 | **OFF**(L1143) | OFF | (+EVERY_N=25/WINDOW=40/FINALIZE_ROUNDS=2 皆默认,未触发)✅ |
| AETHER_GUIDED_TEMPORAL | 未设 | OFF(L1052,unset=bit-identical) | OFF | 弱纹理 live 引导重匹配未开 |
| AETHER_GPU_MATCH_RETRY | 未设 | 2(rc=7 退避重试,L850-858) | 默认重试 2 次 | Swift 注释"rc=7 退避重试是 C++ 默认开"✅ |
| AETHER_ENRICH_TIME_BUDGET_MS | 未设 | unset=**AUTO** 模式(floor 30s,L1205-1216) | enrich AUTO 时间闸 ON | Swift 注释"enrich AUTO 时间闸 C++ 默认开"✅ |
| AETHER_LIVE_TRI_MIN_ANGLE | 未设 | 2.0°(T20 shipped 字面量,L949) | shipped T20 | 与 joint sweep"保守 T20"ship 一致 ✅ |
| AETHER_GROW_REPROJ_PX | 未设 | 14.0(L955) | shipped | — |
| AETHER_TD_TRI_ANGLE / AETHER_TD_REPROJ_PX | 未设 | 2.0° / 3.0px(L2060 shipped) | shipped | — |
| AETHER_BA_MIXED | 未设 | OFF | OFF | mixed 两度判死 ✅ |
| AETHER_BA_THREADS | 未设 | min(6,hw-2)(A16=4) | shipped | ✅ |
| AETHER_TRI_MIN_ANGLE / _P2 | 未设 | shipped 默认 | shipped | — |
| AETHER_INCREMENTAL_FINALIZE_ROUNDS 等三附属 | 未设 | 25/40/2 | 休眠(主开关 OFF) | — |

## E worktree 对照(dirty 层,只读)

E worktree 同文件的 register() 开关块在 **L2242-2278**(文件被大幅重构/前移了 ManualCaptureV2 代码),但 **setenv 集合与生产臂逐行相同**:TEMPORAL_ONLY=1、K_HOT=6、TRACK_UPGRADE=1、ENRICH_TARGETED=1、PAIR_CAP=300、STAGE1_ROUNDS_CAP=4、GHOST_MASK=1;TD_GROW_REFIT/FRAG_MERGE/FRAG_MERGE_REPROJ_PX 同样注释掉。**无 env 面漂移**,差异仅在快门 v2 代码结构。

## 🔴 矛盾/张力红标

1. **🔴矛盾①:FRAG_MERGE 记忆锚打架**。记忆 `thinning_and_speed_pack`(07-11)称"碎片合并@4px+刀A组合**签决 ship**:cap45 达标 0.0059";记忆 `cap47_doublefloor_verdict` 称 FM 被法医定罪主犯、"主犯降级不可证但**判死维持**"。装机代码现状=**FRAG_MERGE 注释关停**(两 worktree 一致)。**结论:cap47 判死(后裁决)已覆盖 cap45 ship 签决,代码与 cap47 一致;引用记忆时须以 cap47 为准,勿按 07-11 ship 锚重开**。重开门槛已在代码注释写死:θ≥5° 门重定价+过九门。
2. **⚠️张力②:K_HOT=6 是"超带后补签"opt-in**。C++ L4785-4795 写明 07-11 A/B 因点数 +2.4% **超 ±2% 预审带**判 ship DISABLED、待用户对新带签决;Swift L86-87 注释称"host A/B 全门绿"后开启。两处口径不完全同源(Swift 引 cap45+1.26%/cap44+0.49% 在带内的那轮)。现状=生产 ON,视为已获签;但若复跑 A/B 应引用 Swift 注释那组数据口径。另 C++ 注释明示:**启用 spatial-first 前须先重跑热调速 A/B**(与 TEMPORAL_ONLY kill switch 绑定)。
3. **⚠️"A 判 OFF"(ABCDE 记忆锚)对账**:装机面上所有非 shipped 增强中,处于 OFF 的是 TD_GROW_REFIT、FRAG_MERGE、GUIDED_TEMPORAL、INCREMENTAL_GLOBAL_BA、spatial-first、BA_MIXED——与"手机已回滚 pre-ABCDE 原版 + A 判 OFF"不冲突;本审计**无法从代码单方面确认"A"具体指哪个开关**,不猜(UNRESOLVED 红线),由编排者按 ABCDE 权威文件对号。
4. 无张力项:INCREMENTAL_GLOBAL_BA 默认 OFF 未开、STAGE1_FTOL 未迁移、T20/14px/3px 全 shipped、mixed OFF、enrich AUTO 闸与 rc=7 重试为 C++ 默认——均与已知签决一致。
