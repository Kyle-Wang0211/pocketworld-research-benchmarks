# E19-B 终审:匹配图增稠(RS M-A 复刻)= 构造性空操作 —— "救回对"本来就在生产匹配图里,且 98% 已经以点的身份出生

日期 2026-07-19(执行 07-18 晚)。研究产物,不 commit,不 ship。
铁律执行:A worktree tracked 脏文件零改动;**零代码变量**(用 E12 目录未改基线 exe `2e03c66b…1c38`,SHA 已核);db 只动副本;-j2 无编译;每跑前 vm_stat ≥3GB 门(实测 5.3GB);与 E18 并行期间全程串行。

## 一句话结论

任务设想的"把 E6 已验证跨窗对写进 db 匹配图→track 变长→2-view 占比降→鬼带降"**在事实层面不成立,且不是差一点,而是前提全反**:
1. 这些对 **100% 已在 db 的 matches+two_view_geometries 里**(注入=逐字节 no-op,SHA 证明);
2. 它们**不是跨窗对**:100% 帧距 ≤12,中位帧距=1(相邻帧窗内对);
3. 回放基线里 **98.1-98.6% 的"救回对"已经出生成交付点**(其中 93-95% 正是 2-view 点)——它们不是待救的库存,它们就是 65-70% 2-view 人口本身;
4. 真正未出生的只剩 1.2-1.7%(596/487 对),而且**结构性无出生通道**(见 §五),继续喂匹配图救不了它们。

M-A(全局匹配→长 track)的真缺口不是"这些边不在图里",是**图里缺第三视桥接边**(把同一物理点的两个 2-view 碎片连起来的 K↔P 新边)——那是新匹配证据(detector-free 救援道/stage-1 merge-and-transfer 线的活),不是 npz 重灌能产生的。

## ① 注入台账(inject_ledger.json)

按任务口径实做(定位=npz 像素对 db keypoints 的 float32 精确相等;缺 keypoint 则 append;缺对应则补 matches+TVG inlier 行,保留原 config=已验证语义)。结果:

| cap | npz 对 | 已在库 | 新增 keypoint | 新增 match 行/对应 | 新增 TVG 行/inlier | 注入后 db SHA |
|---|---|---|---|---|---|---|
| cap50 | 48,226 | **48,226(100%)** | 0 | 0/0 | 0/0 | ==源(380b23d0…) |
| cap51 | 28,224 | **28,224(100%)** | 0 | 0/0 | 0/0 | ==源(484ab94d…) |

cap51 特别核过:E6 当时读的是 `device_full_pull_2026-07-17` db,回放配方用的是 `replay_database` db(两文件 SHA 不同)——**28,224 对在回放 db 里同样 100% 在库**(keypoint 精确命中+对应在 raw matches 与 TVG inlier 双表,f1_presence.json)。
根因:E6 的"救回对"提取自 **db 自己的 two_view_geometries 2-节点 union-find 分量**(e6_rescue_inject.py L364/L418),出生地就是匹配图——"喂回匹配图"在集合论上是恒等映射。db 副本(170M+129M)因逐字节等于源已删,凭 ledger SHA+`inject_pairs.py` 可一键重造。

## ② 对照回放(runs/,基线 exe 2e03c66b,E9 配方逐字,生产 env face,--k=12)

密稠 db(=SHA 恒等副本)各一跑,rc=0,零断言红线,n_reg 不掉(139/105):

| | n_points | 2-view 占比 | ghost_2045 | band_below | 厚度 med | cover | below_floor | 墙钟 total |
|---|---|---|---|---|---|---|---|---|
| cap50 off×3 | 93,268-93,274 | 70.08% | 725-738 | 1,953-2,025 | 0.02659-0.02677 | 3,619-3,635 | 372-444 | 44.1-44.5s |
| **cap50 densified** | 93,274 | 70.08% | 734 | 2,005 | 0.02668 | 3,618¹ | 427 | **43.7s** |
| cap51 off×3 | 65,927-65,929 | 67.63% | 6,574-6,711 | 8,686-8,726 | 0.01115-0.01133 | 3,645-3,651 | 120 | 29.3-29.5s |
| **cap51 densified** | 65,929 | 67.64% | 6,586 | 8,690 | 0.01116 | 3,649 | 120 | **29.0s** |

尺子=E9-C v2 认证口径(固定生产平面 ghost_mask.json 法向+shift-only 锚,常量逐字节;自检:off_r1 全指标与在库 analysis/shell_metrics_fixed.json **逐位相同**)。双峰:cap51 主峰 −2.5mm/鬼侧峰 −37.5mm、峰比 0.348(off 0.348-0.353)——鬼峰位=认证 −32.5~−37.5 带,对账通过。
¹ cap50 cover 3,618 比 off 带下沿低 1 格:输入逐字节相同,纯 run-to-run 噪声(off 带自身跨 16 格)。
**墙钟/30s 账:匹配图没有变大(0 新边),finalize 0 增量**——off 带内(cap50 31.5s vs 31.4-31.8;cap51 20.8 vs 20.6-20.8)。反事实:若这些对真是新边,是 TVG 对应数的 +19.1%/+13.7%(f2 counterfactual_graph),但本 npz 提供不了新边。

## ③ 机制核心证据:2-view 占比 65%→? 的答案 = 65%→65%(结构性不可动),且"救回对"就是 2-view 人口

track 长度分布 before-after 全同(f2_attribution.json hist:cap50 2-view 65,362-65,370 恒 70.08%;cap51 44,589-44,595 恒 67.63-67.64%)。方案书的"65%(57,820/89,594)"是 S1 在设备云上的口径;回放云同现象(70.1%/67.6%)。

**"跨窗对连的是谁"(对 off_r1 逐对归因,pair_membership_off_r1):**

| cap | 同一 track(已出生) | ↳其中恰 2-view | 连两个不同 track | 单边在 track | 完全未出生 |
|---|---|---|---|---|---|
| cap50 | **47,563(98.6%)** | 44,974 | 6 | 61 | 596(1.2%) |
| cap51 | **27,688(98.1%)** | 26,197 | 5 | 44 | 487(1.7%) |

- "救回对"≈**回放云里已交付的 2-view 点本身**(E6 对设备云的"absent>2cm"=15,694/8,538,是设备执行态欠账——热致匹配失败/背压饿死的出生,host 存图回放已经自己收复了绝大部分;npz dist_prod p50=14.9/13.9mm 同向印证);
- 能当"桥"把两个碎片 track 连起来的对**全库只有 5-6 条**(例:两 track 3D 距 3-105mm)——M-A 需要的桥接边在这套证据里近似为零;
- 鬼带里的"救回对"(refit 落 [-45,-20)mm):cap50 616(1.3%)/cap51 2,608(9.2%),其中 610/2,601 已经是交付点——**鬼带点大都"有对可依",不是缺对**。

**鬼带×track 长度横切(同尺,off_r1;新数据,十三战没量过):**
- cap50:鬼带 734 点中 2-view 占 **86.0%**(云整体 70.1%→超代表,+16pp);
- cap51(认证鬼峰 cap):鬼带 6,574 点中 2-view 占 **62.9%**(云整体 67.6%→**不超代表,反而低 4.7pp**);2,437 个鬼带点已是 ≥3-view。
诚实解读:即使 track 真被拉长,cap51 的鬼带也**不是**纯 2-view 抽签现象——37% 的带内点多视+BA 也没被钉回真面。这与在库终审(🏆鬼层:事后清算天花板,根治在 stage-1 出生前 merge-and-transfer)同向,**削弱本方案"2-view 占比降⇒鬼带随之降"的预设链条**。

## ④ 同 gauge 真彩并排 + 横截面(禁 Sim3,直出)

- `xsec_cap50_off_vs_densified.png` / `xsec_cap51_off_vs_densified.png`(认证渲染器同款;肉眼:两面板逐点重合,cap51 双层地板两边同样在)。
- 网页并排(repro-contract 根起 `python3 -m http.server 8123`):
  `compare_any.html?left=E9_birth_alias/runs/cap50_off_r1/replay_finalize.ply&right=E19_no_birth/B_match_enrichment/runs/cap50_densified/replay_finalize.ply`(cap51 同法)。densified 侧 replay_finalize.ply 由 points3D.bin 直出(与 E9 同格式)。

## ⑤ 终审裁决 + 集成规格

**M-A 复刻(以 npz 重灌形态)= NO-GO,构造性空操作。**"把救回对喂进生产匹配图"没有可集成物:生产匹配图已含全部 76,450 对,时间账=0 成本 0 收益。判据链:①SHA 恒等;②对照回放四把尺全落 off×3 噪声带;③2-view 占比不动(70.08/67.64 恒等)。

**证据指向的真杠杆(交编排者,均需签决,不在本任务擅动):**
1. **桥接边才是 M-A 缺口**:同一物理点的碎片间新匹配(K↔P 边)。全库现存桥仅 5-6 条。产生它的机制=定向新匹配(detector-free 救援道,in-bank 已界定)或 stage-1 merge-and-transfer/alias(Jul17 dossier+E12 精刀已 smoke),不是 db 重写。
2. **残余未出生对(596/487)结构性死因**(源码坐实,incremental_triangulator.cc):CompleteTracks 只从**已有 3D 点**外延(无种子不可达);Retriangulate 只碰 tri_ratio<re_min_ratio=0.2 的欠重建对——救回对的父对 tri_ratio p50=0.67/0.71,651 对里只有 17/3 对低于门(f2 parent_pair_tri_ratio_est);track-upgrade 只加长已有 track。**"验证过却从未出生的 2-view 分量,BA 后无人再试"**=E19-A 通道改革(方案§三案1/2)的适用地,收益上限=E6 漏斗(风险门后 11,570/6,277 点,且大头是致密化非填洞)。
3. **设备-回放出生差**:设备云欠 15,694/8,538 对的出生,host 干净回放自己收复到只欠 596/487——先修设备执行态(热/背压致匹配-出生饿死,cap41 device-exact 基线线),比改算法便宜。

## 诚实边界

- 本实验**没有**跑出"增稠后"的独立世界:输入逐字节相同,"densified" 跑=第 4 个 off 复跑(仍照单跑完,作 placebo 对照入库);
- 归因参照系=off_r1 单跑(off×3 间 track 计数漂移 ≤8 点,不影响 98% 量级);tri_ratio 是离线估计(同 3D 点内点对应/内点总数),非 colmap 运行时计数;
- 鬼带×track 横切是**成分观察**,不是干预实验——"多视也在鬼带"说明相关非因果链断言;
- "设备欠账已被回放收复"用 dist_prod+G1 做代理,未做设备云↔回放云逐点身份映射;
- host 单跑墙钟 ±30% 纪律照适用(本处只用来证"0 增量",带内即可);
- E19-A(temporal_detail 通道归因)是并行线的活,本目录未涉;若两线合并结论,须协调 Jul17 stage-1 alias 线防撞车。

## 文件清单

`inject_ledger.json`(①台账+SHA)/ `f1_presence.json`(在库性法证)/ `f2_attribution.json`(track 分布+逐对归因+反事实图规模)/ `f3_rulers.json`(认证四尺+双峰)/ `runs/cap5{0,1}_densified/`(manifest 含 exe+输入 SHA,run.log,points3D.bin,replay_finalize.ply)/ `xsec_*.png` / 脚本 5 件(f1_presence.py, inject_pairs.py, run_e19b.sh, f2_attribution.py, f3_rulers_render.py)/ `SHA256SUMS.txt`。
