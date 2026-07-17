# U3 治理规格 — 生产「原 SfM 来源」的 ~12 条私有出点/评据通道收编

状态:**规格草案(specification only)**。本文只做一手源码审计的形式化,
**不改任何生产代码、不产候选、不声称已实现**。给 U3「接入原 SfM」的继任者补
真实 scope:让今天各自为政的 ~12 条通道,统一改成向一张 **CandidateEvidence /
SurfaceHypothesis 证据图** 发 support/opposition/occlusion 证据,由单一 arbiter
按 `AMBIGUOUS → VERIFIED → BORN` 生命周期裁决出生,而不是每条通道各带私有几何门
自行 `AddPoint3D` / `AddObservation` / `MergePoints3D` / `DeletePoint3D`。

本规格不产生任何 PLY、不跑任何管线、不做任何 A/B。它只是把「生产今天怎么出点」
写清楚,并逐条给出「该往证据图里发什么」。产候选与视觉裁决仍是后续步骤 + 用户签决。

## 词表(沿用 U4 `04_evidence_contract` / U3 `prototype_rs_surface_consensus`)

- **SurfaceHypothesis / candidate**:一个 source-neutral 的候选 3D 点(几何 +
  观测 + 显式缺失证据),`provenance.generator` 只是标签,不决定命运。
- **证据三类**:
  - **support**:独立相机对该候选的支持观测(独立 solve 支持帧 + held-out
    支持帧);越多独立视角 + 越大视差角越强。
  - **opposition**:反对证据(高 reproj 残差、θ_max 塌到歧义带、与已确证表面
    冲突、time-far 无第三视确认)。
  - **occlusion**:signed-visibility(自由空间看穿票 / 穿透 / 被表面遮挡)。
- **生命周期**:`AMBIGUOUS`(fail-closed 默认)→ `VERIFIED`(≥2 独立 solve 支持
  帧 + 独立 held-out 支持 + 无 opposition + 有限 metric 几何)→ `BORN`(可见;
  **只有 arbiter 能置 BORN,任何单通道都不许**)。

## 审计依据(只读核对,行号已逐条 grep 复核 2026-07-18)

- Native:`/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc`(6482 行)
- Dart:`/Users/kaidongwang/Developer/pocketworld/lib/capture/sfm_live_recon.dart`(2134 行)

> 结论(既有):生产所谓「原 SfM 来源」实为 ~12 条各带私有几何门的
> **建 / 改 / 删 / 评据** 通道,**0 条走统一证据图**。出生/死亡由私有阈值
> (2°/3px/4px/K 窗/frame-gap/thermal)单方面决定,provenance 压过 evidence。

## 通道角色三分(这是收编的骨架)

审计后 ~12 条通道天然落进三个角色,U3 证据图按角色收编:

| 角色 | 通道 | 今天做什么 | 证据图里应该做什么 |
|---|---|---|---|
| **A 评据产出(只写 TVG 对,不出点)** | enrich #9、rematch #10、repay #11 | 往 db 写「验证过的两视几何对」,下游私自三角化 | 纯 **support-observation** 采集器:把选中的对作为 `candidate.observations` 边喂给图,**永不做出生决定** |
| **B 出生/改写(单方 AddPoint3D/AddObservation/Merge)** | live create #1、live grow #2、live merge #3、temporal-detail create #6 / grow #7 / grow-refit #8、track-upgrade #12 | 私有门通过就直接建点/加观测/合并/挪位 | 每条改成 **发一个 SurfaceHypothesis + support 观测**,arbiter 判 `VERIFIED→BORN` |
| **C 死亡(单方 DeletePoint3D/DeleteObservation)** | live floater #4、finalize floater #5、Dart spatial_two_view_filter #13 | 私有阈值过不了就硬删点 | 改成对候选发 **opposition** 证据(高残差/低视差/time-far 无支持),arbiter 据此下调置信/不予出生,**不硬删** |

关键点:A 类今天其实已经把「出生决策」推给了下游 B 类 —— 它们只挑对、写对。
所以 A 类收编成本最低(只需把 db 副作用改成 `CandidateEvidence.observations`);
B/C 类是真正把私有裁决权收归 arbiter 的地方。

---

## 逐条规格(①现私有门 ②该发的证据 ③映进证据图 ④标注)

### 通道 #1 — live create(2 视新建)
- **源**:`aether_sfm_c.cc:5118-5158`(建点 `AddPoint3D` 在 5156-5157)。
- **① 现私有门**:TVG inlier 对 → `TriangulatePoint`(5126)→ cheirality
  两端 z>0(5132)→ `CalculateTriangulationAngle ≥ kMinTriAngleRad`(5136,
  live 创建门)→ 两端 reproj ≤ `kMaxCreateReprojPx`(5147-5148)。过则建 2 视点。
- **② 该发的证据**:一个 SurfaceHypothesis(candidate.xyz = 三角化位),
  support = {prev, cur} 两帧观测(带各自 reproj 残差、视差角);无 held-out、
  无第三视 → 显式标 `missing: independent_holdout`,故默认应停在 `AMBIGUOUS`。
- **③ 映进图**:`provenance.generator="live_create"`;观测入 candidate.observations;
  cheirality/reproj/θ 作为 support 质量字段,不作为出生开关。
- **④ 标注**:这是「捕获期低视差 2 视点」的主产源之一;与 #13 的删除口径相关
  (见文末自相残杀)。

### 通道 #2 — live grow(向已存在点加观测)
- **源**:`aether_sfm_c.cc:5091-5115`(`AddObservation` 在 5112)。
- **① 现私有门**:一端已赋点 → 新观测 cheirality z>0(5099)→ reproj ≤
  `kMaxGrowReprojPx`(inlier)或 `kMaxCreateReprojPx`(raw)(5105-5107)。
  注意:门是「在**当前**未精化点位」量 reproj —— 低视差噪声点位会把本能修它的
  宽基线观测挡在门外(与 #8 grow-refit 的动机同源)。
- **② 该发的证据**:对既有 candidate 追加一条 support 观测(帧 + reproj + 该
  观测引入的新视差角);若观测显著抬高 θ_max 应记为「升级证据」。
- **③ 映进图**:同一 candidate 上加 support 边;是否接受由 arbiter 综合
  union 残差判,而非 4px@当前点位硬门。
- **④ 标注**:「当前点位」门是 opposition/挪位逻辑本该合并的地方(见 #8）。

### 通道 #3 — live merge(合并两条碎裂 track)
- **源**:`aether_sfm_c.cc:5037-5075`(`CanMergeLivePoints` 5046,`MergePoints3D`
  5051,装 union refit 位 5057)。
- **① 现私有门**:两端赋不同点 & 仅 TVG-inlier 允许合(5041)→
  `CanMergeLivePoints`:disjoint-images(`kMergeRequireDisjointImages`)+ union
  refit reproj ≤ `kMaxMergeReprojPx`(5046-5048)→ 过则合并 + 装 refit 位。
- **② 该发的证据**:一条「两 candidate 指向同一 SurfaceHypothesis」的
  **support/equivalence** 断言(证据 = union refit 残差、共享/不共享图集);
  冲突时应是 opposition(disjoint 违反 = 同帧两观测 = 不可能同点)。
- **③ 映进图**:合并 = 图上把两候选节点归并为一,由 arbiter 依 union 证据裁,
  裁决前保留两节点,失败不静默丢。
- **④ 标注**:merge 装的是 union refit 位而非 `MergePoints3D` 的加权平均 ——
  这已是「按证据定位而非按通道」的正确雏形,U3 可直接复用其 refit 语义。

### 通道 #4 — live windowed floater cleanup(逐窗删浮点)
- **源**:`aether_sfm_c.cc:5210-5224`(BA cadence 后,over `touched`)。
- **① 现私有门**:`FilterObservationsWithNegativeDepth` + `FilterPoints3D
  WithLargeReprojectionError(max_error=4.0)` + `FilterPoints3DWithSmall
  TriangulationAngle(min_tri_angle_deg=2.0)`,直接 DeletePoint3D/Observation。
- **② 该发的证据**:对候选发 **opposition**:负深度观测(occlusion/cheirality
  违反)、reproj>4px(high-residual opposition)、θ_max<2°(low-parallax
  ambiguity opposition)。
- **③ 映进图**:不硬删;把三类信号作为 opposition 记入候选,arbiter 决定是否
  阻止/撤销出生。硬删只应在「有 opposition 且无任何 support 抵消」时由 arbiter 做。
- **④ 标注**:此通道与 #5 是同三把尺子的窗内 vs 全局两次施加。

### 通道 #5 — finalize global floater cleanup(全局删浮点)
- **源**:`aether_sfm_c.cc:5823-5831`(finalize structure-only BA 后 over `all_pts`)。
- **① 现私有门**:同 #4 三把尺子(neg-depth / reproj>4px / θ<2°),范围是全部点。
- **② 该发的证据**:同 #4,只是对全云每个候选评一遍 opposition。
- **③ 映进图**:同 #4,arbiter 全局裁决层。
- **④ 标注**:#4/#5 是「删」侧的两次;与「造」侧的 #6 温和地互相拉扯(#6 造 2°
  低视差点,#5 用 2° θ 门删低视差点 —— 只因 #6 在 BA **之后**造、逃过了 #5 之前
  的那趟窗内过滤;U3 须让同一 θ 判据只在证据层裁一次,别一造一删)。

### 通道 #6 — RestoreTemporalDetail:create(BA 后灌 2 视点)
- **源**:`aether_sfm_c.cc:2340-2371`(`AddPoint3D` 2369,计数 `stat_temporal_
  detail_created` 2371);函数 2056 起,由 finalize 在 3629/4378 调。
- **① 现私有门**:只吃**原始时序 K 邻**的 TVG inlier(gap≤K,大 gap 先做);
  两端未赋点 → `TriangulatePoint` → cheirality(2349)→
  `CalculateTriangulationAngle ≥ kMinTriAngleRad`(默认 2°/T20,2353-2356)→
  两端 reproj ≤ `kMaxReprojPx`(默认 3px,2360-2361)→ 建 2 视点。**位姿/内参
  冻结,建后不再 BA**(纯 DLT,永不精化)。这正是交付云厚度的 ~18k 低视差 2 视点。
- **② 该发的证据**:SurfaceHypothesis + {frame1, frame2} 两 support 观测(含
  θ_max、两端 reproj);无第三视/held-out → 显式 `missing: independent_holdout`
  + 低视差 opposition 风险标记 → 默认 `AMBIGUOUS`。
- **③ 映进图**:`provenance.generator="temporal_detail_create"`;这些点**不该**
  因为「是我造的」就免检 —— 与 A 类 enrich 写来的对合流后,由 arbiter 用同一
  support/opposition 判据决定出生。
- **④ 标注**:🔴 **自相残杀主角之一**,见文末。

### 通道 #7 — RestoreTemporalDetail:grow(legacy 加观测)
- **源**:`aether_sfm_c.cc:2310-2329`(`AddObservation` 2325,计数
  `stat_temporal_detail_grown` 2328)。
- **① 现私有门**:一端已赋点 → 无同图冲突(`has_image_in_track` 2180)→
  cheirality(2312)→ `reprojects_cleanly`「在**当前点位**≤3px」(2316)→
  `has_stable_baseline`(存在一对 ≥kMinTriAngleRad 的观测,2321)→ 加观测。
- **② 该发的证据**:对既有 candidate 追加 support 观测(帧 + 当前点位残差 +
  是否带来 stable baseline)。
- **③ 映进图**:support 边追加;接受由 union 证据裁,而非「当前噪声点位 3px」硬门。
- **④ 标注**:「当前点位」门与 #8 grow-refit 是同一伤口的两种处理,证据图里应统一
  成「union refit 后残差」判据。

### 通道 #8 — RestoreTemporalDetail:grow-refit(env-gated,默认 OFF)
- **源**:`aether_sfm_c.cc:2184-2308`(`AETHER_TD_GROW_REFIT`;union DLT
  `TriangulateMultiViewPoint` 2238 + `PolishPointGN` 2249;装 refit 位
  `Point3D(...).xyz = refit_xyz` 2296)。
- **① 现私有门**:union(track+候选)refit → GN polish → 每条 union 观测都
  `reprojects_cleanly`(2250-2263)→ 可选 θ_max ≥ `AETHER_TD_GROW_REFIT_MIN_
  THETA_DEG`(2274-2292)→ 装 refit 位 + 加观测(接受集是 legacy 门的严格超集)。
- **② 该发的证据**:support 观测 + **候选几何更新提案**(union refit 位 + union
  θ_max + 全 union 残差);θ 不足 = low-parallax opposition。
- **③ 映进图**:证据图的「候选位由 union 全观测证据定」正是此通道的语义 —— U3
  应把它提升为 default 的 support 聚合方式,而非 env 暗门。
- **④ 标注**:cap47 记录该 arm 会把 ghost 4.3%→5.5%(低视差点被 refit「救活」反而
  增鬼),故 θ_max 绝对下限必须留在证据层由 arbiter 把关,不能无门 refit。

### 通道 #9 — enrich / AddSpatialRevisitMatches(只写 TVG 对)
- **源**:`aether_sfm_c.cc:1937-2039`(anchor pass 1944-1949、quadratic 兜底
  1954-1958、enrich top-up cap 1972-2038;写对 `WriteVerifiedSpatialPair` 2035)。
- **① 现私有门**:pose-gated 空间 revisit anchor → `ProcessRevisitAnchors`
  需 2-of-3 region 确认才落库;无确认 region 才退化到 powers-of-two quadratic
  兜底;`AETHER_ENRICH_PAIR_CAP` 既是 cap 又是 floor 的 top-up(按相机中心距/
  或 `AETHER_ENRICH_TARGETED` 的升级潜力分排序)。**产的是验证过的两视几何对,
  不直接出点。**
- **② 该发的证据**:候选的 support **观测边**(每对 = 一组潜在跨帧支持);
  它是「支持证据的采集器」,不该有出生权。
- **③ 映进图**:A 类 —— 把 `WriteVerifiedSpatialPair` 的 db 副作用改成往证据图
  喂 `candidate.observations`;anchor/quadratic/top-up 只是「挑哪些对」的策略,
  收编后仍可保留为证据采集预算,但出生交 arbiter。
- **④ 标注**:与 #10/#11 三者是同一「补对」职能在 finalize/finalize/capture-idle
  三处的分身,证据图里应合成一个统一的 evidence-gathering 预算。

### 通道 #10 — FinalizeRematchStarvedFrames(只写缺失 TVG 对)
- **源**:`aether_sfm_c.cc:3197-...`(starved 判定 3229-3241,todo 收集
  3250-3266,写对在后段)。
- **① 现私有门**:GPU 要求但符号缺 → fail-closed 整趟跳过(3203);逐帧数 K 窗内
  `n_inliers ≥ kRematchValidInlierGate` 的有效对(3216-3226)→
  `win_valid < kRematchMinValidWindowPairs` 或 `fed_throttled`(热降 K)判 starved
  (3235-3237)→ 按 gap 升序补 gap≤kRematchNearGap(always)或 gap≤K(starved 侧)
  的缺失对,cap `kFinalizeRematchMaxPairs`。**产的是 TVG 对,不直接出点。**
- **② 该发的证据**:同 #9,补 support 观测边(尤其为热降频/稀疏帧补回 K 拓扑)。
- **③ 映进图**:A 类;starved/throttled 是「该多采证据」的触发器,不是出生判据。
- **④ 标注**:热降频帧「总被判 starved 强制重配」是 delivery-lossless 的关键,
  收编时这条触发语义要保留成「证据补齐优先级」。

### 通道 #11 — aether_sfm_live_repay(capture-idle 补对)
- **源**:`aether_sfm_c.cc:6182-...`(thermal gate 6185-6200,补对循环 6224-6301,
  写对 `WriteMatches`/`WriteTwoViewGeometry` 6287-6292)。
- **① 现私有门**:thermal≥3(critical)直接拒(6188);thermal==2 需
  `gpu_pairs_since_rc7 ≥ RepayThermal2CleanN()` 干净历史且 max_pairs 夹到
  `kRepayThermal2MaxPairs`(6192-6200);同 starved/gap 规则补缺失对,每对
  memoize 一次(成败都记,6271),中途 thermal 恶化即中止。
- **② 该发的证据**:同 #9/#10,capture 期空闲把 support 观测边提前补上。
- **③ 映进图**:A 类;thermal 门是「何时能采证据」的资源闸,不改证据语义。
- **④ 标注**:#9/#10/#11 三合一后,thermal 门应作为证据采集调度层的统一约束。

### 通道 #12 — TrackUpgrade(env `AETHER_TRACK_UPGRADE`,默认 OFF)
- **源**:`aether_sfm_c.cc:2426-...`(finalize 尾,跑在 RestoreTemporalDetail 之后)。
- **① 现私有门**:对 2 视/低视差(θ_max<3°)点,索引 db 里触及其 keypoint 的
  TVG inlier → 每点收集轨外自由 partner keypoint → trimmed union refit(DLT +
  GN polish)+ 每条 union 观测在前方且 reproj 合格 → 升级(加第三视 + 挪位)。
- **② 该发的证据**:对低视差 candidate 追加 support 观测 + union refit 位提案
  (等价于把第三视支持补进图,拉高 θ_max)。
- **③ 映进图**:B 类;与 #8 同属「用 union 全证据重定位 + 加支持」,U3 应与 #8
  合并成一条统一的「support 聚合 + 候选重定位」规则,而非两个 env 暗门。
- **④ 标注**:它专门救 #6 造出来的 2 视点 —— 造(#6)、救(#12/#8)、删(#4/#5/#13)
  三方对同一批低视差 2 视点各行其是,正是 U3 要收归一处裁决的核心乱象。

### 通道 #13 — Dart filterFinalSpatialTwoViewPoints(删 time-far 2 视点)
- **源**:`sfm_live_recon.dart:181-229`(判据 219-221,压缩 231-252;调用点
  1304-1315)。
- **① 现私有门**:仅删「恰好 2 观测 且 两帧 frame-id 差 `> temporalK`」的点
  (`end-start==2 && |frameIds[start]-frameIds[start+1]| > temporalK`,219-221)。
  即 finish-time loop 匹配产生的 time-far 2 视点;K12 内 2 视点与所有 3+ 视点全留。
- **② 该发的证据**:对该类候选发 **opposition**:「2 观测无第三视确认 + 两帧
  time-far → 可能是错对却低残差、深度极端(长射线)」。
- **③ 映进图**:C 类;不硬删 —— 把「time-far + 仅 2 视 + 无 held-out」记为
  opposition/`missing: independent_holdout`,arbiter 据此不予出生;若该点另有强
  support(大 θ_max、held-out 支持),则不该只因 frame-gap 就死。
- **④ 标注**:🔴 **自相残杀另一主角**,见文末。

---

## 🔴 温和标注:temporal_detail 造 vs spatial_two_view_filter 杀 —— 一造一杀

两条通道对「无第三视确认的 2 视点」下了**相反的、且只看 provenance/frame-gap
而非几何证据的**裁决:

- **#6 RestoreTemporalDetail:create** 在 stage-2 BA **之后**,专门从**时序 K 邻
  (gap≤K)**的对里,以 2°/3px **制造**低视差 2 视点(交付云厚度的 ~18k 点主源),
  且建后永不精化(纯 DLT)。→ **造「近时 + 低视差」2 视点**。
- **#13 filterFinalSpatialTwoViewPoints** 在交付前,**无条件删除**两帧
  **frame-gap > temporalK(远时/loop)**的 2 视点。→ **杀「远时」2 视点**。

两者作用在**不同子集**(近时 vs 远时),但判据都是「哪条通道 / 帧间隔多远」,
**不是这个点自己的几何证据(θ_max、独立视角数、held-out 支持、opposition)**。
后果是 provenance 压过 evidence 的双标:

- 一个 **远时但大视差、多帧 reproj 干净**的 2 视点(可能是真表面)→ 被 #13 秒杀;
- 一个 **近时但视差极小、深度噪声大**的 2 视点(歧义壳/鬼层原料)→ 被 #6 制造并保留。

这与「双墙 / 低视差深度噪声壳」记忆里的病理同根:2 视点该不该活,取决于它的
**视差角 + 独立支持 + 有无 opposition**,而非它出自哪条私有通道、两帧隔多远。

**U3 收编时必须裁决 2 视点归属**:把 #6 的「造」与 #13 的「杀」合并成证据图上
**同一条 2-view-point 生命周期规则** —— 每个 2 视候选统一发 support(θ_max、
观测数)+ opposition(低视差歧义、time-far 无 held-out)+ `missing: independent_
holdout`,由 arbiter 用**同一把尺子**判 `AMBIGUOUS/VERIFIED/BORN`。近时/远时只作为
证据强度的输入,不作为出生/死亡开关。这条裁决是 U3「接入原 SfM」真实 scope 的一部分,
本规格只提出,不实现,不预判裁决方向(留给继任者跑候选 + 用户签决)。

---

## 交给继任者的 scope 清单(U3「接入原 SfM」)

1. A 类(#9/#10/#11):把三条「写 TVG 对」的 db 副作用改成向证据图喂
   `candidate.observations`,合成统一的证据采集预算(保留 starved/thermal 触发语义)。
2. B 类(#1/#2/#3/#6/#7/#8/#12):每条改成「发 SurfaceHypothesis + support」,
   出生权收归 arbiter;#8/#12 合并为统一的「union 全证据重定位 + support 聚合」。
3. C 类(#4/#5/#13):三把删除尺子改成发 opposition 证据,硬删仅由 arbiter 在
   「有 opposition 且无 support 抵消」时执行;#4/#5 的同 θ 判据只在证据层裁一次。
4. **裁决 2 视点归属**(#6 造 × #13 杀 的自相残杀),见上节。
5. 全程沿用 U4 `CandidateEvidence` envelope + `provenance.generator` 标签 +
   `AMBIGUOUS→VERIFIED→BORN` 生命周期;fail-closed;冻结 device stock 仍是每个
   候选的 byte-for-byte 前缀。

**非目标(本规格明确不做)**:不改生产代码、不产 PLY/候选、不跑管线/A-B、
不声称任何通道已收编、不预判 2 视点裁决方向。这些都需后续步骤 + 用户签决。
