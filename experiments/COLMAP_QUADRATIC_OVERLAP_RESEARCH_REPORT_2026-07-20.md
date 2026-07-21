# COLMAP `quadratic_overlap` 设计、track 传递性与 PocketWorld 适用性研究报告

> 检索截止：2026-07-20（Asia/Shanghai）  
> 输入文件：`COLMAP_QUADRATIC_OVERLAP_RESEARCH_PROMPT.md`  
> 输入 SHA-256：`28ce0183c64a806f52d5dabab22bb27a772317c2a11c66e903e3ea7b047d2fd9`  
> COLMAP 主源码冻结：`2ced1975bb6251feaab70fd48ec063246b636646`（2026-07-20T08:44:05Z）  
> 本地产品代码：PocketWorld `cb72962ff8cbc45dcaf44cf88df6b39f8f9ec90f`；Aether3D-cross `ea77244a8fd54153544cddaf95b56c0010d575ca`  
> 性质：公开资料、固定源码和本地只读审计；不是一次新的重建实验

## 1. 结论先行

| 问题 | 判定 | 最短答案 |
|---|---|---|
| Q1：COLMAP 有没有解释为什么用幂次间隔？ | **有，但只是有限的经验性解释** | Johannes Schönberger 说这是刻意设计，并观察到它对“小基线视频”匹配更好；2021 年又说意图是兼顾近、远匹配。没有正式理论、固定预算消融，也没有解释为什么必须是底数 2、为什么叫 `quadratic`。 |
| Q1：当前为什么漏掉 gap 3、5、6…？ | **历史上有意恢复，优越性未被证明** | 2017 年最初确实是纯幂次；2017–2024 年默认却是“连续 ∪ 幂次”；2024 年 PR #2711 才恢复成“连续或幂次二选一”。维护者只说是恢复原始实现和文档语义，没有给出排除 gap 3 的新证据。 |
| Q2：A–B、B–C 能否在没有 A–C 匹配时形成 A–B–C track？ | **可以，但不是无条件的全图闭包** | 两条边必须引用 B 中完全相同的 `point2D_idx`，都通过两视图几何验证；随后经 `Create`、注册、`Continue` 或 `Complete` 把 C 加入已有点。默认初查是一跳，completion 默认最多五层。 |
| Q2：A–C 直接边独有的价值？ | **断链冗余和 pair-level 几何，而非完整链下额外制造 A–C 角度** | 它能跨过 B 的漏检/错配，提供独立 A–C two-view geometry、初始化候选、pair 统计、重三角化和 track merge 机会。一旦 A、B、C 已在同一 track，三角化本来就能使用 A–C 两条视线的跨度。 |
| Q3：指数间隔是否理论上/实证上优于连续窗口？ | **只确立了索引跨度优势，没有确立 SfM 净收益** | 当序列尺度足够大时，同样名义偏移数下幂次图能直达更远索引并缩短部分长程 hop；它并非对所有 `n,m` 都支配连续图，更不等于匹配成功、独立信息或更小 BA 误差。未找到 COLMAP 的连续 vs 幂次控制变量消融。 |
| Q3：gap 3 相对 gap 2 几乎冗余吗？ | **未确立** | 未找到维护者、正式文档或论文作出这一比较。对非均匀的离散快门拍摄，图像编号差尤其不是基线或重叠的稳定代理。 |
| Q4：幂次 skip 是行业共识吗？ | **不是** | openMVG、AliceVision 的时序入口用连续窗口；Meshroom 用连续 + retrieval；hloc/Theia 用内容或共视检索；ORB-SLAM3 用数据驱动的共视/回环图；GLOMAP 直接消费外部匹配库。固定版本中均未发现原生 `2^k` temporal pairing。 |
| PocketWorld 应否直接把 K12 换成纯 quadratic？ | **现有证据不支持** | 这会删掉大量已有近邻边，并换入成功率未知的远边；视频经验不能直接迁移。更可防守的方向是保留短程连续边，再用几何/检索或少量多尺度边补长程，并做等成本、分阶段消融。 |

最准确的总判定是：

> **COLMAP 解释过“为什么想同时看近处和远处”，但没有充分解释或证明“为什么当前必须只看 1、2、4、8…而舍弃 gap 3”。**

这不是“毫无记载”，也不是“quadratic 显然最优”。它是一项有作者经验依据、强场景依赖、历史语义发生过变化、但缺少正式消融的工程启发式。

## 2. 边界、术语与证据标签

### 2.1 当前机制的精确核实

冻结源码的 [`SequentialPairingOptions`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/controllers/pairing.h#L86-L95) 给出：

```cpp
int overlap = 10;
bool quadratic_overlap = true;
```

[`SequentialPairGenerator::Next`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/controllers/pairing.cc#L518-L538) 是排他的 `if/else`：

- `quadratic_overlap=true`：前向生成 `i→i+1, i+2, i+4, i+8, ...`；
- `quadratic_overlap=false`：前向生成 `i→i+1, ..., i+overlap`；
- 越过序列末尾即停止；
- 数据库中的 image pair 是无序/对称关系，所以内部节点在候选图上可概念化为 `i±d`，但生成器本身只发出一次前向 pair；
- `loop_detection=false` 是另一条默认关闭的内容检索路径，不能把固定幂次边叫作回环检测。

还有一个 rig 边界：`expand_rig_images=true` 默认开启；[`MaybeExpandRigImages`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/controllers/pairing.cc#L489-L515) 会把 anchor pair 扩展到相关 rig frames 的其他相机。因此“只存在幂次 gap、永远没有 gap 3”精确适用于单相机/无 rig expansion、且 loop detection 关闭的序列；多相机 rig 可能因 frame expansion 产生额外 image-ID pairs。PocketWorld 当前手机主路径属于单相机语境。

因此提示文件对“当前默认会漏掉非 2 的幂 gap”的核心理解正确；需要补上的只是“生成器前向、候选图无向”的表述边界。

### 2.2 证据标签

- **[确认]**：固定源码、提交 diff、维护者原话或原论文直接支持。
- **[支持]**：多个强来源一致，但仍含实现/场景外推。
- **[争议]**：来源之间、历史语义或本地记录之间存在冲突。
- **[推导]**：本报告的数学或工程推论，不冒充 COLMAP 官方理由。
- **[未确立]**：按本报告检索强度未找到足够证据；不等于绝对不存在。

## 3. Q1——设计理由、文档、提交史和维护者发言

### 3.1 正式文档和 CLI：描述用途与开关，不解释设计选择

当前官方 [`tutorial.rst`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/doc/tutorial.rst#L319-L340) 只说明：序列/视频的连续帧通常有视觉重叠，因此无需 exhaustive；它还把 vocabulary-tree loop detection 作为独立功能。文档没有解释：

- 为什么偏移必须是 `2^k`；
- 为什么 overlap 默认 10、布尔值默认 true；
- 为什么 gap 3 相对 gap 2 或 4 可被舍弃；
- 为什么指数增长被命名为 `quadratic`。

历史 [3.2 changelog](https://github.com/colmap/colmap/blob/3.2/CHANGELOG.txt#L6) 把它定位为面向 high-frame-rate image sequences 的新 sequential mode。这是“小基线/高帧率视频”场景的官方旁证，但仍没有解释精确的幂次调度。

源码声明只写“match images against their quadratic neighbors”；当前 PyCOLMAP [参数页](https://colmap.github.io/pycolmap/pycolmap.html#pycolmap.SequentialPairingOptions.quadratic_overlap) 也只有同义参数说明。本地 COLMAP 3.13.0 的帮助仅显示默认值：

```text
--SequentialMatching.overlap arg (=10)
--SequentialMatching.quadratic_overlap arg (=1)
```

头文件 [`feature_matching.h`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/controllers/feature_matching.h#L78-L95) 写出线性和 `2^o` 两条公式，但仍只是机制描述。它在当前排他实现下也容易被误读为并集，不能当作性能论证。

判定：**正式文档说明了“是什么”和大类使用场景，没有说明“为什么这个精确拓扑更好”。**

### 3.2 Git 考古：三种核心语义，而不是一个始终不变的默认

| 时期 | 核心实现 | 关键提交 | 记录强度 |
|---|---|---|---|
| 2017-04-19 至 2017-07-17 | 纯幂次，线性窗口被替换 | [`8e3f59d0275c66e41a2955fc32b2f41a43ac3846`](https://github.com/colmap/colmap/commit/8e3f59d0275c66e41a2955fc32b2f41a43ac3846) | [确认] |
| 2017-07-17 至 2024-08-14 | 默认有效 distinct-image gap 为 `{1…overlap−1} ∪ {1,2,4,…}`；原始线性循环沿用了从 `i=0` 起的 self-inclusive 索引约定 | [`d6d2c210c5c692d26328886430cd4207f20526ec`](https://github.com/colmap/colmap/commit/d6d2c210c5c692d26328886430cd4207f20526ec) | [确认] |
| 2024-08-14 至 2024-08-16 | 仍为并集，但 linear overlap 修成包含精确的 gap `1…overlap` | [`96891d9cfcc4b3c2783f199810e4c7d206856387`](https://github.com/colmap/colmap/commit/96891d9cfcc4b3c2783f199810e4c7d206856387) / [PR #2701](https://github.com/colmap/colmap/pull/2701) | [确认] |
| 2024-08-16 至冻结版本 | `linear XOR quadratic` 二选一；开启时纯幂次 | [`1b55b9a92f444c35d80bbc0c6ef84bff3318b217`](https://github.com/colmap/colmap/commit/1b55b9a92f444c35d80bbc0c6ef84bff3318b217) / [PR #2711](https://github.com/colmap/colmap/pull/2711) | [确认] |

#### A. 首次把连续窗口改成纯幂次

提交：`8e3f59d0275c66e41a2955fc32b2f41a43ac3846`，Johannes Schönberger，2017-04-19。

完整 commit message：

```text
Change sequential matching strategy
```

diff 把连续上界循环替换为 `image_idx1 + (1 << i)`，代码注释也同步为 `2^o`。提交本身没有正文、PR 或理论解释。

#### B. `quadratic_overlap` 选项的引入和默认值

提交：`d6d2c210c5c692d26328886430cd4207f20526ec`，2017-07-17。

完整 commit message：

```text
Add option to enable/disable quadratic sequential matching
```

结论：

- `quadratic_overlap` 在这里首次出现；
- 它出生时默认就是 `true`，没有找到“后来从 false 改为 true”的提交；
- 当时开启后不是纯幂次，而是线性邻居与幂次邻居的并集；
- 最初 union 的 [raw 生成循环](https://github.com/colmap/colmap/blob/d6d2c210c5c692d26328886430cd4207f20526ec/src/base/feature_matching.cc#L1142-L1158) 用 `image_idx1+i, i=0…overlap−1`，继承了旧 self-inclusive 范围；下游会[跳过 self-pair 并去重](https://github.com/colmap/colmap/blob/d6d2c210c5c692d26328886430cd4207f20526ec/src/base/feature_matching.cc#L901-L914)，所以当时有效 distinct-image 线性 gap 是 `1…overlap−1`，再与幂次 gap 取并集；不能把整个 2017–2024 阶段都简写成精确 gap `1…overlap`；
- Johannes 当天明确写道默认同时启用 “old and new behavior”。[Issue #180 后续评论](https://github.com/colmap/colmap/issues/180#issuecomment-315679438)

2018 年提交 [`e338111b170d957a15fd324aaa5bb57afb169193`](https://github.com/colmap/colmap/commit/e338111b170d957a15fd324aaa5bb57afb169193) 的完整 message 为：

```text
Increase number of images to be matched in sequential matching
```

它把数值 `overlap` 从 5 增为 10，并把 loop retrieval 数从 30 增为 50；没有改变布尔默认值，也没有给出实验数据。

2024 年 pair generator 重构提交 [`022e42fa4cdb2c91252414bfbacd6260bb4f54ef`](https://github.com/colmap/colmap/commit/022e42fa4cdb2c91252414bfbacd6260bb4f54ef) 仍保留 additive 语义。随后 [`96891d9cfcc4b3c2783f199810e4c7d206856387`](https://github.com/colmap/colmap/commit/96891d9cfcc4b3c2783f199810e4c7d206856387) 才把 linear index 从 `image_idx+i` 改为 `image_idx+i+1`。其完整 commit message 是：

```text
Fix: sequential matcher overlap number should be inclusive (#2701)

Co-authored-by: Johannes Schönberger <joschonb@microsoft.com>
```

这项修复只让 linear 分支精确覆盖 gap `1…overlap`；两天后的 #2711 才把 union 改成 exclusive。

#### C. 2024 年恢复互斥语义

提交：`1b55b9a92f444c35d80bbc0c6ef84bff3318b217`，2024-08-16。

完整 commit message：

```text
Tests for pairing library in feature matching (#2711)

* WIP
* t
* d
* spatial
* imported
* descs
* vocab tree
* d
* d
* d
* d
```

它把 `linear + quadratic` 改成 `linear XOR quadratic`，并用单测固定 `overlap=3` 时的幂次结果为 gap 1、2、4。维护者的 PR 行内解释是：

> “This restores the original implementation … one either matches linearly or quadratically.”

[PR #2711 原评论](https://github.com/colmap/colmap/pull/2711#discussion_r1718173220)

这证明当前排他行为不是偶然重构错误；但该 PR 没有 benchmark，也没有回答为何恢复旧行为比保留并集更好。

### 3.3 维护者的直接动机：有原话，但范围有限

#### 2017：小基线视频的经验观察

Issue [#180](https://github.com/colmap/colmap/issues/180) 的提问者注意到 gap 3 被跳过，并问是否是 bug。Johannes 对性能的逐字解释是：

> “I noticed that the matching produces better results in this case. Especially, when the input is a video with small baseline.”

[原评论](https://github.com/colmap/colmap/issues/180#issuecomment-315676790)

同一评论还说他观察到这种情况下匹配结果更好，同时承认其他场景可能变差。它是对**最初纯幂次实现**最强的作者理由；但性质是未附数据的经验观察。

同帖用户报告自己的视频有大量重复结构，只有真实连续邻帧反而更好；Johannes 接受该反例并建议关闭选项。[用户报告](https://github.com/colmap/colmap/issues/180#issuecomment-315688691)、[维护者回复](https://github.com/colmap/colmap/issues/180#issuecomment-315689391)

#### 2021：近邻 + 远邻、直接匹配和帧率

Issue [#636](https://github.com/colmap/colmap/issues/636) 中，Johannes 写道：

> “The intent is to get both nearby and further away matches.”

同一评论还逐字写道：

> “colmap will only attempt to triangulate points from direct and not from transitive matches”

他还说三角化会尝试 direct 而不是 transitive matches，收益取决于帧率。[原评论](https://github.com/colmap/colmap/issues/636#issuecomment-932697039)

必须加两层版本限定：

1. 2021 年的实现是“连续 ∪ 幂次”，所以 “both nearby and further away” 不能单独证明 2024 年后排除 gap 3 的纯幂次拓扑；
2. 当前源码的初始 `Find` 默认确实只看一跳，但已有 track 可经后续注册、`Continue` 和 `Complete` 跨链扩展。维护者这句不能扩张成“没有 A–C 直接边就永远不能形成 A–B–C track”。

#### Q1 最终判定

| 子问题 | 结论 |
|---|---|
| 是否有作者解释？ | **有**：小基线视频经验更好；意图是取得近、远直接匹配；收益依帧率。 |
| 是否有官方正式设计文档？ | **没有找到**。教程、CLI、参数页和注释只描述用途/机制。 |
| 是否有精确底数 2 的理论或消融？ | **没有找到**。 |
| 是否解释了 gap 3 为什么应被舍弃？ | **没有**。2024 年只记录“恢复原始二选一语义”。 |
| 是否解释了名称 `quadratic`？ | **没有找到**；从序列间隔看实际是 exponential/geometric spacing。 |
| 默认何时变 true？ | 选项在 `d6d2c210...` 首次出现时已经是 true。 |

## 4. Q2——feature track 的传递性与直接边的真实价值

### 4.1 数据结构：节点是精确 keypoint，不是抽象“物理特征”

COLMAP 把 feature observation 表示为 `(image_id, point2D_idx)`。冻结源码中：

- [`AddTwoViewGeometry`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/scene/correspondence_graph.cc#L100-L200) 只把通过几何验证的 two-view inlier 加入双向 correspondence graph；
- [`ExtractTransitiveCorrespondences`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/scene/correspondence_graph.cc#L230-L290) 可以从一个精确节点做有限深度 BFS；
- 默认初始 `max_transitivity=1`，track completion 默认最大 5 层，[`incremental_triangulator.h`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.h#L45-L85)。

这不是每次都把整张 correspondence graph 求无条件 connected components。它是一个受注册状态、深度和几何门限约束的增量过程。

### 4.2 A–B–C 无 A–C 的形成路径

假设 verified correspondences 是：

```text
A:a  ↔  B:b  ↔  C:c
```

且两条边中的 `B:b` 是**完全相同的 point2D 索引**。可发生以下路径：

1. `TriangulateImage` 从 A 或 B 出发，经一跳直接对应取得 A、B；
2. [`Create`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.cc#L481-L539) 在至少两个合格观测上 robust triangulate，建立 `P={A:a,B:b}`；
3. C 注册时，C:c 的直接邻居 B:b 已有 `point3D_id=P`，mapper 可[构造 C 的 2D–3D correspondence](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_mapper.cc#L262-L323)；通过 absolute-pose RANSAC 后，[注册流程把合格 observation 加入 P](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_mapper.cc#L418-L474)；
4. 若注册时没加入，[`Continue`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.cc#L542-L585) 可按角度重投影误差把 C 续入已有点；
5. [`Complete`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.cc#L684-L769) 还能从 track 全体元素出发，默认最多五层补全符合 pose、相机和重投影条件的观察。

因此答案是：**A–C 不直接匹配也可以形成 A–B–C track。**

COLMAP 2016 论文 §4.3 也明确写道：

> “Leveraging transitivity establishes correspondences between images with larger baselines …”

[CVPR 2016 原文](https://openaccess.thecvf.com/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html)，DOI [`10.1109/CVPR.2016.445`](https://doi.org/10.1109/CVPR.2016.445)。

### 4.3 失效条件

| 失效条件 | 为什么断链 | 状态 |
|---|---|---|
| B 中该物理点未被检测 | AB 或 BC 没有共同图节点 | [确认] |
| AB 命中 `B:b1`、BC 命中 `B:b2` | 图按精确 point2D index 建边，不按像素邻近自动合并 | [确认] |
| ratio/distance/cross-check 杀掉一环 | 对应边未建立 | [确认] |
| raw match 未成为 E/F/H RANSAC inlier，或 pair 未过最小内点数 | pair 不进入 correspondence graph | [确认] |
| C 未注册、无 pose 或相机参数异常 | `Find`、`Continue`、`Complete` 会跳过 | [确认] |
| triangulation angle、cheirality、角误差或重投影误差不合格 | `Create`/`Continue`/`Complete` 拒绝该观察 | [确认] |
| point2D 已属于另一个 3D 点 | 不能直接重复绑定；可能依赖后续 `Merge` | [确认] |
| 两个分裂 track 没有任何直接 correspondence 桥 | `Merge` 无候选桥边 | [确认] |
| 超出配置的传递深度 | 默认初查一跳、completion 最多五层，不是无限闭包 | [确认] |
| 后续 BA/过滤判为大误差、小角或负深度 | 观察或整个两视图点会被移除 | [确认] |
| PocketWorld 自研流式 fork 没有在相同时序调用补全 | 上游“最终可传递”不能自动迁移 | [支持，需集成测试] |

默认 `ignore_two_view_tracks=true` 也不等于 A–B–C 链一定被当作孤立 two-view：[`IsTwoViewObservation`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/scene/correspondence_graph.cc#L354-L362) 要求两端度数都恰为 1；B 同时连接 A、C 时不满足这个条件。

### 4.4 A–C 直接边真正买到什么

#### 源码支持的独有价值

1. **断链冗余。** B 漏检、遮挡、重复纹理选择不同 B keypoint，或 AB/BC 一环验证失败时，AC 可独立连接 A、C。
2. **立即一跳可达。** 默认初始 `max_transitivity=1`；AC 可让当前调用直接看到远观察，不必等待 B 先成点、C 后注册或后续 completion。
3. **独立 two-view geometry。** AC 可单独估计 E/F/H、相对 pose 和 pair 内点；链式可达不会凭空创建一个 AC pair。
4. **初始图像对候选。** 初始化逻辑依赖两张图之间的直接 correspondences，[`incremental_mapper_impl.cc`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_mapper_impl.cc#L147-L186)。
5. **pair 统计和重三角化机会。** [`Retriangulate`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.cc#L307-L405) 遍历真实存在的 image pairs；没有 AC 边就没有 AC 专属 pair ratio/重三角化入口。
6. **桥接已分裂 tracks。** `Merge` 从 track 元素的直接 correspondences 寻找另一个点；AC 可成为额外桥边。
7. **structure-less registration 的直接约束。** 相应 fallback 也只枚举当前图像的直接邻边。

#### 需要推翻或限定的三个候选答案

**① 中间环节断裂时的冗余：成立。** 这是直接 AC 最清楚的独有价值。

**② 更大基线必然只有直接 AC 才能提供：不成立。** 一旦 A、B、C 已进入同一候选/3D track，triangulator 会检查所有观测射线组合，包括从未直接匹配的 A–C 视线，[`triangulation.cc`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/estimators/triangulation.cc#L117-L128)。小角过滤也遍历 track 内 image-pair combinations，[`observation_manager.cc`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/observation_manager.cc#L453-L480)。AC 的大基线价值只在它使原本缺失/延迟的观察进入 track，或提供更好的初始 pair 时是独有的。

**③ AC 自动阻止误匹配沿链传播：未成立。** 正确 AC 可提供替代路径和额外几何核验机会；但 traced path 没有因为形成 A–B–C 三角形就自动执行严格 cycle-consistency certificate。错误 AC 也会扩大 false-positive surface。源码甚至警告 bogus correspondence 可能破坏两个既有 3D points，[`incremental_triangulator.cc`](https://github.com/colmap/colmap/blob/2ced1975bb6251feaab70fd48ec063246b636646/src/colmap/sfm/incremental_triangulator.cc#L365-L401)。

### 4.5 文献中的 match/view graph 边界

- Wilson & Snavely, ICCV 2013，[DOI `10.1109/ICCV.2013.69`](https://doi.org/10.1109/ICCV.2013.69)：feature tracks 常由 pairwise matches 的传递闭包/连通结构形成，但重复结构会造成歧义。
- Shah et al., WACV 2015，[DOI `10.1109/WACV.2015.44`](https://doi.org/10.1109/WACV.2015.44)：tracks 可看作 feature graph 的 connected components；triplet verification 需要三角结构。
- Zhou et al., ICCV 2015，[DOI `10.1109/ICCV.2015.459`](https://doi.org/10.1109/ICCV.2015.459)：cycle consistency 是需要显式建模的约束，不能由“边多”自动得到。
- Shen et al., ECCV 2016，[DOI `10.1007/978-3-319-46487-9_9`](https://doi.org/10.1007/978-3-319-46487-9_9)：先构造相似度图，再用三角结构扩展；树结构脆弱，环路有验证价值，但仍不是固定时间幂次规则。
- Shah et al., ECCV 2018，[原文](https://openaccess.thecvf.com/content_ECCV_2018/html/Rajvi_Shah_View-graph_Selection_Framework_ECCV_2018_paper.html)：view-graph 选边更直接依赖 inliers、coverage、相机几何和三角角，而不是图像编号 gap。

这些文献支持“连通性、冗余、环和可靠长基线有价值”，不支持“gap 3 应被固定删除”。

## 5. Q3——指数间隔的长程价值：事实、理论与推断

### 5.1 已经确立的部分

1. **维护者经验。** 2017 年作者观察到幂次间隔在小基线视频上更好；同时明确承认其他场景可能更差。
2. **多尺度意图。** 2021 年作者用“nearby and further away”概括设计意图。
3. **真实较大基线可能改善三角条件。** 前提是视场仍重叠、匹配正确、相机运动含平移且视差没有退化。
4. **非连续直接匹配可以跨越 detector/matcher dropout。** ENFT 明确讨论连续跟踪失败会断开子序列，并用自适应的非连续匹配延长 tracks、缓解长序列漂移。[TIP 2016，DOI `10.1109/TIP.2016.2607425`](https://doi.org/10.1109/TIP.2016.2607425)
5. **对数间隔在长时 correspondence tracking 中有实证价值。** 这不是 COLMAP ablation，但提供了最接近的控制证据。

#### MFT / MFTIQ：最接近的 powers-of-two 实证，但不是 SfM 证明

MFT 使用 `D={∞,1,2,4,8,16,32}`，在多条光流链中按不确定度和遮挡选择路径；其摘要明确说使用 logarithmically spaced intervals。[WACV 2024 原文](https://openaccess.thecvf.com/content/WACV2024/html/Neoral_MFT_Long-Term_Tracking_of_Every_Pixel_WACV_2024_paper.html)，DOI [`10.1109/WACV57701.2024.00669`](https://doi.org/10.1109/WACV57701.2024.00669)。报告的 TAP-Vid DAVIS first-mode AJ：完整多尺度 `47.3`，仅连续 `Δ=1` 为 `38.3`。

MFTIQ 延续 `{1,2,4,8,16,32,t−1}`；补充材料 Table 7 报告 default base-2 AJ `65.67`、base-4 `{1,4,16,t−1}` 为 `65.50`、直接单边 `57.46`、仅连续链 `54.67`。[WACV 2025 原文](https://openaccess.thecvf.com/content/WACV2025/html/Serych_MFTIQ_Multi-Flow_Tracker_with_Independent_Matching_Quality_Estimation_WACV_2025_paper.html)、[补充材料](https://openaccess.thecvf.com/content/WACV2025/supplemental/Serych_MFTIQ_Multi-Flow_Tracker_WACV_2025_supplemental.pdf)，DOI [`10.1109/WACV61041.2025.00784`](https://doi.org/10.1109/WACV61041.2025.00784)。

限制：它们是逐像素 long-term tracking，且有显式质量选择；没有在同样成功边数/同样计算成本下比较 `{1,2,4,8}` 与 `{1,2,3,4}`。它们证明“多尺度直接路径可跨遮挡、模糊和漂移”，不能证明 COLMAP 的静态候选图最优。

### 5.2 最小图论分析——本报告推导，不是官方理由

设长度为 `n≥2` 的序列，每个内部图像名义上配置整数 `m≥1` 个向前偏移：

- 连续图 `C_m`：有效 `D={1,...,min(m,n−1)}`；
- 幂次图 `P_m`：有效 `D={1,2,4,...}`，只保留 `<n` 的前 `m` 项。

令 `m_eff=min(m,floor(log2(n−1))+1)`，`L_eff=2^(m_eff−1)`。假设每条候选边都能成功且视为等权无向边：

- 当 `m<n` 时，`C_m` 的最大直接 gap 是 `m`，直径为 `ceil((n−1)/m)`；当 `m≥n−1` 时直径为 1；
- `P_m` 在该有限序列上的最大有效直接 gap 是 `L_eff`；任意距离 `d=qL_eff+r` 可先走 `q` 条 `L_eff` 边，再按 r 的二进制展开，所以

```text
ceil((n−1)/L_eff) ≤ diam(P_m) ≤ floor((n−1)/L_eff) + m_eff − 1
```

当 `m≥floor(log2(n−1))+1` 时，所有序列内需要的幂次边均存在，任意距离可以直接二进制分解，最短路 hop 不超过 `popcount(d)`，即 `O(log n)`。靠近尾部时每图实际 pair 数更少；名义配置 `m` 绝不等于每图都产生 `m` 条有效边。

这只证明**索引候选图的覆盖/跳数**，不证明 SfM 误差更小：

- 远图像可能没有共同视野，候选边不会变成 verified edge；
- 一条 landmark 未必能沿整条索引路径被同一 keypoint 链连接；
- 图 hop 数不是 BA Fisher information、协方差或三角化角；
- 远边的 outlier 风险、计算成本和验证失败率未被计入；
- 若远边只是已有测量的代数组合而非独立图像观测，它没有新增信息。

反例：`n=4,m=3` 时，连续图包含 gap 3、直径 1；幂次的有效偏移只有 1、2、直径 2。指数策略并非对所有短序列和局部距离都支配连续策略。

### 5.3 与 pose-graph 漂移的关系：有条件类比，不是直接证明

《Reliable Graphs for SLAM》把 odometry 子图视作 path，并给出新增边的 D-optimal 边际与边权和 effective resistance 相关。[IJRR 2019，DOI `10.1177/0278364918823086`](https://doi.org/10.1177/0278364918823086)

**[推导]** 在单位权 path 上，端点更远的候选边 effective resistance 更大；若候选测量同样可靠且独立，首条远边可能比又一条局部边带来更大图信息增益。但：

- 真实远图像 pair 的成功概率和信息权重通常不是常数；
- 若误差方差随 gap 增长，优势会缩小甚至反转；
- COLMAP match edge 最终形成 shared feature/reprojection constraints，不等于经典独立 Gaussian pose edge；
- 固定 2 的幂也不保证命中真实回访位置，例如回访发生在 gap 37 时，32 或 64 未必有重叠。

所以 powers-of-two 更像廉价的**多尺度探针**，不是 loop detector。真正回环仍依赖 appearance/place retrieval、共视关系和几何验证。

### 5.4 “视频相邻帧冗余”到底写到什么程度

官方教程只说连续帧有视觉重叠，因此不必 exhaustive。2017 维护者只说小基线视频上观察到更好。ENFT 认为逐帧处理往往冗余，并实际每 3–5 帧采样，再用共享特征阈值自适应找较远帧。

没有找到任何来源明确推出：

```text
gap 3 相对 gap 2 几乎不增加信息，因此可固定删除 gap 3。
```

它依赖近似匀速、帧率高、运动平滑、相邻 baseline 很小、时间 gap 与空间 baseline 单调、各尺度仍有足够重叠等前提。违反任一条件，图像编号差就可能成为很差的几何代理。

## 6. Q4——社区实践与其他系统

### 6.1 COLMAP 用户经验

| 来源 | 报告 | 证据强度 |
|---|---|---|
| [Issue #180](https://github.com/colmap/colmap/issues/180) | 重复结构视频中，用户报告真实连续邻居优于幂次远邻；维护者建议关闭 `quadratic_overlap` | 直接用户报告 + 维护者接受；无公开数据，**支持性反例** |
| [Issue #636](https://github.com/colmap/colmap/issues/636) | 维护者说要限制时间窗口就关闭 quadratic；较大时间跨度是预期行为 | 维护者直接配置建议，**确认** |
| [Issue #1831](https://github.com/colmap/colmap/issues/1831) | 用户称开启 quadratic 并同时改变 loop 参数后结果改善，但另一安装无法复现 | 多变量混杂、平台差异，**弱证据** |
| [COLMAP Google Groups](https://groups.google.com/g/colmap/c/nXRNGrQY8ZI/m/rZ4aGtgsBQAJ) | 维护者指出过高视频帧率可能使默认配置更差；降帧建议也未在该用户案例中解决问题 | 场景提示，**非保证/非消融** |
| [Rerun `pysfm`](https://github.com/rerun-io/examples-monorepo/blob/a18733d955c6eb39fe57288581b81f0c5a9484f4/packages/pysfm/pysfm/apis/pycolmap_vid_recon.py#L220-L235) | 固定代码显式设置 `quadratic_overlap=False`、overlap 5；工作流记录多个完整注册结果 | 真实工程实践，但没有 on/off 对照，**支持“有人会关闭”** |

没有找到公开的、固定数据集和同成本设置下的 COLMAP `linear vs quadratic` benchmark。社区经验的正确读法是“开关需要按序列验证”，不是形成单向共识。

hloc 维护者 `sarlinpe` 对 2569 帧车辆序列给出的公开建议也很有代表性：每图连接前 K 张连续图，并每 N 帧用 retrieval 增加稀疏 loop closures，保留较多 sequence constraints、较少回环边。[hloc issue #135](https://github.com/cvg/Hierarchical-Localization/issues/135#issuecomment-1004703788) 这是“连续局部核心 + 内容驱动长边”的维护者实践证据，不是 `2^k` 证明。

### 6.2 其他 SfM/SLAM 系统的实际拓扑

| 系统（冻结 revision） | 候选或优化图的实际做法 | 原生 `2^k` temporal skip？ |
|---|---|---|
| hloc `c13273bd0ecc2917a35910fd843712a1c6243193` | [retrieval](https://github.com/cvg/Hierarchical-Localization/blob/c13273bd0ecc2917a35910fd843712a1c6243193/hloc/pairs_from_retrieval.py#L50-L71) top-K、共享 3D 点的 [covisibility](https://github.com/cvg/Hierarchical-Localization/blob/c13273bd0ecc2917a35910fd843712a1c6243193/hloc/pairs_from_covisibility.py#L12-L47) top-K、pose 距离 top-K，另有 exhaustive；没有通用 temporal generator | **否** |
| openMVG `c76d87244fb3590fb8b9a752be34f07411057ae2` | [`CONTIGUOUS`](https://github.com/openMVG/openMVG/blob/c76d87244fb3590fb8b9a752be34f07411057ae2/src/openMVG/matching_image_collection/Pair_Builder.hpp#L24-L43) 精确枚举 gap 1…X；默认 PairGenerator 是 exhaustive | **否** |
| AliceVision `8fac66f838014022b5b9ea00af5b72e28a06d79e` | [`generateSequentialMatches`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/imageMatching/ImageMatching.cpp#L172-L190) 按 `(imagePath, viewId)` 排序后，对每图精确枚举后续 `nbMatches` 张；[CLI 默认](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_imageMatching.cpp#L53-L62) VocabularyTree，参与视图数严格 `<200` 时[整体改为 exhaustive](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/imageMatching/ImageMatching.cpp#L454-L504) | **否** |
| Meshroom `88d85f67bd7a88078e5b4a269f8c509bff0af869` + AliceVision `8fac66f...` | Meshroom 会从[外部 AliceVision 安装目录加载](https://github.com/alicevision/Meshroom/blob/88d85f67bd7a88078e5b4a269f8c509bff0af869/meshroom/__init__.py#L187-L210)节点；配套 [`ImageMatching.py`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/meshroom/aliceVision/ImageMatching.py#L55-L123) 默认 `SequentialAndVocabularyTree`，连续 5 与 retrieval 40 [写入同一 pair set](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_imageMatching.cpp#L247-L264)，而[默认工作流](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/meshroom/photogrammetry.mg#L93-L105) 未覆盖这些值；`<200` 时整体 exhaustive | **否** |
| Theia `d2112f15aa69a53dda68fe6c4bd4b0f1e2fe915b` | build app [默认开启](https://github.com/sweeneychris/TheiaSfM/blob/d2112f15aa69a53dda68fe6c4bd4b0f1e2fe915b/applications/build_reconstruction.cc#L94-L114) Fisher-vector global descriptor pairing，K=100；[候选生成](https://github.com/sweeneychris/TheiaSfM/blob/d2112f15aa69a53dda68fe6c4bd4b0f1e2fe915b/src/theia/sfm/feature_extractor_and_matcher.cc#L353-L439) 取 `min(N−1,100)` 的 top-K 并做一跳 query expansion。当参与 pairing 的 `N≤101` 时，top-K 已严格等于全连接 | **否** |
| GLOMAP `99806d0869f802fad218516a2e027793e7ca687d` | [`global_mapper`](https://github.com/colmap/glomap/blob/99806d0869f802fad218516a2e027793e7ca687d/glomap/exe/global_mapper.cc#L65-L88) 读取已有 COLMAP DB，不自行生成 pairs；论文实验使用 BoW retrieval | **不适用；只会继承上游** |
| ORB-SLAM3 `0df83dde1c85c7ab91a0d47de7a29685d046f637` | [共视图](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/0df83dde1c85c7ab91a0d47de7a29685d046f637/src/KeyFrame.cc#L379-L470)按共享 MapPoints 形成；[回环候选](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/0df83dde1c85c7ab91a0d47de7a29685d046f637/src/LoopClosing.cc#L483-L512)由 BoW/地点识别后做几何验证；显式[惯性时间链](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/0df83dde1c85c7ab91a0d47de7a29685d046f637/src/Tracking.cc#L3233-L3244)使用直接 `mPrevKF/mNextKF` | **否** |
| VINS-Mono `90dabb5ec79946ae42fd2e1e91d4e69aabe1e25d` | [pose graph](https://github.com/HKUST-Aerial-Robotics/VINS-Mono/blob/90dabb5ec79946ae42fd2e1e91d4e69aabe1e25d/pose_graph/src/pose_graph.cpp#L479-L512) 连接前 1、2、3、4 个同序列关键帧，并另加可选 loop edge | **否；是连续四邻** |

几个重要边界：

- ORB-SLAM3 的共视边是**完成特征关联之后**的数据驱动优化结构；COLMAP sequential pair 是**特征关联之前**的候选任务。二者只能类比“稀疏可靠图”，不能互相证明具体调度。
- ORB-SLAM3 论文强调时间上相隔很远的共视关键帧可提供 high-parallax observations，但边由共享 MapPoints 决定，而非时间 gap。
- Meshroom 这个 revision 本身没有锁定 AliceVision revision；上表数值只在把两个列出的 SHA 配对时可复现，单独一个 Meshroom SHA 不足以锁定节点默认值。
- GLOMAP 本身没有原生 pairing 默认；说“GLOMAP 用 quadratic”只有在上游明确运行 COLMAP sequential matcher 时才成立。
- 固定源码的负向检索只能证明这些入口没有该调度，不能证明整个行业从未有人私下实现。

### 6.3 是否有连续 vs skip-link 的直接消融

在指定的 COLMAP、hloc、openMVG、AliceVision、Theia、GLOMAP 和 ORB-SLAM3 渠道中，**未找到**连续窗口与 `2^k` 候选图的同预算直接消融。

最接近的证据分为三类：

1. COLMAP 作者无表格的经验观察；
2. MFT/MFTIQ 对长时像素 tracking 的多尺度间隔 ablation；
3. ENFT、view-graph selection 和 pose-graph 理论对自适应远边/可靠环路的支持。

这三类都不能替代 PocketWorld 自身的控制变量实验。

## 7. 对 PocketWorld / Aether3D 的适用性

### 7.1 视频论证不能直接迁移到离散快门

按提示文件给出的相邻运动范围：平移 `0.012–0.33 m`，旋转 `2–22°`。跨度分别约为 27.5 倍和 11 倍。即使这些值都是已冻结的同口径统计，也说明：

- 图像索引 gap 不是稳定的物理 baseline 代理；
- gap 3 可能跨过模糊、漏检、遮挡并恢复结构，也可能已经因转身失去重叠；
- gap 4 不保证比 gap 3 更好；停留、纯旋转、往返运动还会破坏时间 gap 与视差的单调性；
- 小基线高帧率视频里“少量多尺度采样”的直觉，不能推出离散拍摄中非幂次 gap 冗余。

因此：**gap 3 在该产品场景中可能携带真正独立信息，不能按编号先验判死；是否有净收益只能测量。**

### 7.2 K12、纯幂次和 exhaustive 不是同预算比较

唯一候选 pair 数可由 `sum(n-d)` 精确计算：

| 图像数 n | 纯幂次的有效 gap | 纯幂次 pairs | 连续 K12 | exhaustive |
|---:|---|---:|---:|---:|
| 15 | 1,2,4,8 | 45 | 102 | 105 |
| 140 | 1,2,4,8,16,32,64,128 | 865 | 1602 | 9730 |

所以把 K12 直接换成 COLMAP 默认纯幂次不是“相同计算量下换一种采样”：

- 15 张时会把 102 个近邻候选降到 45；
- 140 张时会从 1602 降到 865，同时把部分预算推到 gap 16–128；
- 成功验证的边数还会因真实重叠随 gap 下降而进一步变化。

比较策略时必须至少按**实际尝试 pair 数、实际 matcher 成本或成功 verified edges**之一归一化；不能把同名 `overlap=10` 当成同预算。

### 7.3 当前产品代码的真实路径：采集 K12，但 finalize 不保证 `>12=0`

本地只读审计发现：

1. App 启动会注册 Aether 插件，[`AppDelegate.swift`](/Users/kaidongwang/Developer/pocketworld/ios/Runner/AppDelegate.swift:25)。
2. 注册函数设置 `AETHER_STREAM_TEMPORAL_ONLY=1` 和热态 K6，[`AetherARKitPlugin.swift`](/Users/kaidongwang/Developer/pocketworld/ios/Runner/AetherARKitPlugin.swift:78)。
3. Dart live options 默认覆写为 K12，[`aether_sfm_ffi.dart`](/Users/kaidongwang/Developer/pocketworld/lib/aether_sfm_ffi.dart:823)；serious/critical thermal state 会降为 K6。
4. native capture-time temporal 分支按 `frame_id-1...` 向后取最近 K 个可用旧帧，[`aether_sfm_c.cc`](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc:680)。
5. 正常、有效的 [async](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc:4235)、[sync](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc:5429) 和 [resume](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc:5556) finalize 路径都会调用 `AddSpatialRevisitMatches`；[函数本身](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/bench/aether_sfm_c.cc:1937) 在 session/DB/相机无效或少于 3 帧时会早退。它先枚举 `gap>K` 的空间锚；只有没有确认到 multi-frame spatial revisit region 时，才使用 16/32/64…幂次安全网。
6. App 还启用 targeted enrichment 和 pair cap 300，[`AetherARKitPlugin.swift`](/Users/kaidongwang/Developer/pocketworld/ios/Runner/AetherARKitPlugin.swift:103)，native 路径会考虑 beyond-K pairs。

因此：

> “i 匹配 i−1…i−12”是非热态 capture-time 的名义候选路径；“实测 max gap=12、gap>12=0”只能是某个已冻结数据库、某个 pre/post-finalize 阶段的事实，不是当前交付管线的静态保证。

仓库内未跟踪的 [`cap47_live.db`](/Users/kaidongwang/Developer/Aether3D-cross/_lapackbench/Resources/cap47_live.db)（SHA-256 `f38963b9134308225e542db113e295c0c754c95bc67f4b2c3df44e6295947d5b`）有 121 images、1133 match/TVG rows，其中 33 个 gap>12、最大 gap 76；因它没有可靠 revision provenance，本报告只用它反驳“所有本地运行都绝对没有 >12”，不把它当提示文件目标实验的替代结果。

另一个集成边界：vendored COLMAP pairing 进入 host matcher target，但不在设备生产 archive 的 live pairing 路径中。产品要试 pure quadratic/hybrid，需要改或配置自研 capture/finalize candidate generator；并非简单打开上游 `SequentialMatching.quadratic_overlap`。

### 7.4 对提示文件实验数字的证据校准

本报告把用户给出的数字作为场景输入，但本地仓库没有形成同一 revision、同一 DB、同一阶段、同一口径的完整证据包：

| 提示中的声明 | 本地只读复核 |
|---|---|
| `track_len=2.4–2.8` | 旧分支 E20 的两组记录落在范围内，但当前工作树没有原始 DB；历史还有 4.4+ 的其他口径结果。**局部支持，不能泛化。** |
| `<8°=12–20%` | 找到一条 12.4% 的 commit message 记录，但缺独立 manifest；其他实验有更高值。**证据不足以重算。** |
| 20–36% extracted features 进入 triangulation、浪费中 87–96% 从未匹配 | 未找到同口径 artifact；现存 87% 记录指另一类 observation recovery。**未验证。** |
| exhaustive 比 K12 `+178 / 3–4%` 且墙厚不变 | 最接近的 E20 实际不是全配对，ledger 与 verdict 自身还有 151/51 vs 185/55 冲突。**未验证且存在冲突。** |

这不会推翻用户现场观察，但会限制推论强度。下一轮实验前应冻结目标 DB SHA、代码 revision/dirty diff、pre/post-finalize 阶段、环境变量、thermal history、pair table 和指标脚本。

### 7.5 当前最可防守的工程判断

#### 不支持的动作

现有证据不支持仅凭 COLMAP 默认值，把 capture-time K12 整体替换成 pure powers-of-two。理由是：

- 2017 作者经验面向 small-baseline video；当前是非均匀离散快门；
- 2024 的排他语义没有新的性能证据；
- 切换会真实删除 gap 3、5、6…等大量近邻候选；
- 当前产品 finalize 已有 spatial/targeted beyond-K 路径，长边是否真的“字面为零”必须先按阶段复核；
- 用户提供的 exhaustive 结果若成立，更直接说明“盲加全部远边”不是墙厚主因，但不能证明删 gap 3 无损。

#### 有证据支持的方向——仍标为工程假设

更合理的候选是：

```text
短程连续核心  ∪  少量经重叠/位姿/检索选择的长程边
```

而不是纯时间幂次。理由：

- 短程连续边保留离散拍摄下未知但可能有价值的 gap 3 等观察；
- 远边用 pose prior、视觉 retrieval、已知共视/匹配成功率或 spatial revisit 选择，比编号 `2^k` 更接近几何目标；
- powers-of-two 可以作为低成本 fallback 探针，但不应被当作 loop closure 或理论最优调度；
- 这与 Meshroom 的 continuous + retrieval、ORB-SLAM3 的共视 + loop、ENFT 的共享特征自适应选择更一致。

### 7.6 最小可证伪实验

固定同一组已提取 features、matcher、几何验证、mapper、随机种子和硬件，至少比较：

1. `C12`：连续 K12 基线；
2. `C12\{3}`：只删 gap 3，直接回答 gap 3 是否独立；
3. `P`：纯 `1,2,4,8,...`；
4. `P∪{3}`：判断 gap 3 对 pure powers 的边际值；
5. `H`：保留短程连续核心，加等预算的 spatial/retrieval 长边；
6. 可选 `C12 + long`：只加长边、不删近边，分离“长边增益”和“删近边损失”。

所有 variant 必须：

- 按实际尝试 pair 数或 matcher wall/GPU 时间做等成本版本；
- 分别保存 pre-finalize、post-spatial、post-targeted 的 pair manifests；
- 保留失败和无 inlier pairs，而不只看成功 rows；
- 预注册指标和停止规则。

最低指标集：

| 层级 | 指标 |
|---|---|
| 候选/匹配 | attempted pairs、verified pair ratio、inliers/pair、gap 分布、false geometry rate |
| observation/track | 新进入匹配的 extracted observations、track length 全分布、断裂/合并数、新增跨段 observations |
| 几何 | 三角化角分布、<8° 比例、reprojection error、注册图像率、components |
| 产品 | 墙厚与其他 surface/coverage 指标，不只单一平均值 |
| 成本 | wall time、GPU/CPU 时间、峰值内存、真机 thermal state、耗电 |

只有这个实验能区分：

- gap 3 本身有无独立价值；
- 长程边有无增益；
- pure powers 的收益来自覆盖更远，还是损失来自删掉近边；
- 当前 finalize 已有 long-pair enrichment 是否使新策略重复劳动。

## 8. 未确立事项

1. 没有找到“为什么底数必须是 2”的作者说明、数学证明或 COLMAP ablation。
2. 没有找到 `quadratic` 名称的官方解释；实现实际是指数间隔。
3. 没有找到 gap 3 相对 gap 2 几乎冗余的直接证据。
4. 没有找到 current pure-power 与 historical union 语义的性能比较。
5. 没有证据证明 fixed temporal skip 能替代 place recognition/loop detection。
6. 没有公开资料能量化 PocketWorld 数据上 pure powers 的成功边率、track 增量或墙厚变化。
7. 提示文件的若干实测数字缺少一个可重算的冻结 evidence bundle；尤其需要目标 DB SHA 和 pre/post-finalize 标识。
8. 当前 upstream 机制不能保证自研 iOS fork 以同样顺序调用 `Continue/Complete/Merge`；需运行态或专项源码追踪确认。
9. 公开检索不能覆盖私有邮件、已删除内容、内部 benchmark 或口头设计讨论；所有阴性结论均是“在本报告渠道和强度下未找到”。

## 9. 证据账本

| Claim | 关键来源 | 直接支持 | 限制 | 状态 |
|---|---|---|---|---|
| 当前默认是 pure powers | 冻结 `pairing.h/.cc`、单测 | true 分支只生成 `1<<i` | 只描述 upstream；设备产品路径不同 | confirmed |
| 纯幂次 2017 首次进入 | `8e3f59d...` diff | 线性循环被 `1<<i` 替换 | commit message 无动机 | confirmed |
| option 出生即 true | `d6d2c210...` | 声明和默认值同一提交加入 | 当时语义为 union | confirmed |
| 当前 exclusive 是有意恢复 | PR #2711 review、`1b55b9a...` | maintainer 明说恢复 either/or；有单测 | 无 benchmark | confirmed |
| small-baseline video 是作者动机 | Issue #180 maintainer comment | 直接经验陈述 | 无公开数据，且承认反例 | supported |
| 意图是近 + 远 | Issue #636 maintainer comment | 直接原话 | 发布时为 union 语义 | supported with version limit |
| ABC 无 AC 可成 track | correspondence graph + triangulator + mapper | 精确节点共享后可 Create/Continue/Complete | 非无限闭包；多重门限 | confirmed |
| AC 并非完整链下额外创造 baseline | triangulation/observation manager | track 内遍历所有 ray/image pair | AC 仍可能帮助建成 track | confirmed |
| AC 自动防错 | 未见显式 triangle certificate；源码有 bogus-edge 风险 | 只能提供冗余候选 | 错边也可伤害 | unsupported |
| powers 有理想图覆盖优势 | 本报告组合图推导 | 二进制分解/直径界 | 不等于成功 match graph 或 BA 信息 | supported mathematical inference |
| powers 对 COLMAP 固定预算更优 | 未找到直接 ablation | 无 | 邻近领域不能替代 | unresolved |
| MFT 多尺度边有实证价值 | WACV 2024/2025 原文和补充 | 有对应任务 ablation | 任务和质量选择机制不同 | supported analogy |
| 行业普遍使用 powers | 固定 hloc/openMVG/AliceVision/Theia/GLOMAP/ORB-SLAM3/VINS 源码 | 主要使用连续、检索或共视 | 不是全行业存在性证明 | disputed / not supported |
| PocketWorld 全流程 `>12=0` | 本地 capture/finalize 源码与 cap47 反例 | capture 名义 K12；finalize 可加 beyond-K | 目标实验 DB 未冻结 | disputed / stage-dependent |
| 直接改 pure powers 适合 PocketWorld | 作者视频动机 + 本地离散运动范围 | 无直接产品实证 | 会删大量近边 | unresolved; current recommendation is no |

## 10. 检索与复现审计

### 10.1 GitHub / COLMAP

GitHub Issues/PR 的主要精确查询及 raw totals：

```text
repo:colmap/colmap quadratic_overlap                 7
repo:colmap/colmap "quadratic overlap"              17
repo:colmap/colmap quadratic sequential matcher      8
repo:colmap/colmap sequential small baseline         1
repo:colmap/colmap transitive direct triangulate      1
repo:colmap/colmap sequential repeated structures     2
repo:colmap/colmap sequential gap                     4
```

`"quadratic overlap"` 的 17 个结果全部筛查；深读 #180、#636、#1831、#2359、#2701、#2711、#2900。查询之间有重叠，raw total 不等于唯一文档数。

在完整本地 mirror 上对 `-S quadratic_overlap` 的命中逐 diff 检查，并额外追溯首次 `1<<i` 的 `8e3f59d...`。不把会随新 remote refs 变动的 `--all` commit 总数当作复现标识；复现边界以报告头的冻结 SHA 为准。还核对：

- `022e42fa4cdb2c91252414bfbacd6260bb4f54ef`：pair generation / matching 拆分；
- `96891d9cfcc4b3c2783f199810e4c7d206856387`：linear overlap inclusive 修复；
- `1b55b9a92f444c35d80bbc0c6ef84bff3318b217`：恢复 exclusive 并加测试。

### 10.2 学术与网页

- Crossref 对 COLMAP、MFT、MFTIQ、ENFT、Reliable Graphs、ORB-SLAM 等做 DOI 解析；关键 DOI 的 correction/update relationship 检查均返回 `no_update_relationships_found`。这不是绝对“无撤稿/无勘误”证明。
- OpenAlex/Semantic Scholar 的部分关键词入口因 `api_key_not_configured` 无有效返回，不能把 0 结果当阴性证据；以 Crossref、CVF、IEEE/作者稿和固定源码补位。
- Q3 定向网页检索共 29 个唯一 query、224 个工具可见结果，标题/摘要筛查后完整阅读 8 个原始来源。
- Google Groups 精确查 `quadratic_overlap`、`quadratic overlap`、`power of two`、`sequential overlap`；相关 COLMAP 线程 2 个全文审阅。
- StackOverflow 的精确相关结果为 0；不据此声称“社区无人讨论”。
- 未调用 Zotero，因为请求没有要求读取用户本地 Zotero library。

代表性 query：

```text
"quadratic overlap" COLMAP powers of two sequential matching rationale
COLMAP quadratic overlap ablation
"powers of two" temporal matching structure from motion video frames
pose graph "powers of two" edges temporal
"gap 3" "gap 2" video frames redundant matching
video SfM matching redundant baseline consecutive frames
"Efficient Non-Consecutive Feature Tracking for Structure-from-Motion"
"Reliable Graphs for SLAM" effective resistance
ORB-SLAM essential graph covisibility loop closure drift
MFTIQ logarithmically spaced deltas powers supplemental
```

### 10.3 固定源码完整性

COLMAP revision：`2ced1975bb6251feaab70fd48ec063246b636646`。

关键 blob 的本次 SHA-256：

```text
pairing.h                    23e81a07e06dbac003e0b56f5e909f1859585e2932797caa4cebc2d2d6421f4c
pairing.cc                   371de89b1191f617b9985505b8a6abfd0bad26ee35c12fd0f0fb141b7483a8ed
feature_matching.h           4eb54402a99dcb48f3e30e71932336432691d9f4b8ca5620a6a45b82d2cbf054
correspondence_graph.cc       c54fe012da89ab10a2c6a54a7d626ebb7fa64585cbb4876ac73d5f28b46ee4bd
incremental_triangulator.cc   7699ada72dde810fcfb436feb828de43b3b6ec692196cde98d79327f2082a6e8
incremental_triangulator.h    ae14816a6a92c018ab1a40af87f4986ce5d684e8e36419817a1dde58471d974b
incremental_mapper.cc         c894804524f673434e048b2ff0bc25949cfb25993cee75f37647f26abac24b3c
observation_manager.cc        3a34e1ade0b5b09763634fa4e06fde2643c2c8c65ec0e9ae92b419a61979553e
triangulation.cc              0160b1fa3f136a1b3537547244b554e370276e2dca47b3c64dd7520f4b7f1c17
```

### 10.4 报告自检

- 重算 `n=15/140` 的 pure-power、C12 和 exhaustive pair 数，均与第 7.2 节一致。
- 直接构图穷举 `n=2…200、m=1…8`，第 5.2 节的连续图直径等式和幂次图上下界全部通过。这只核验组合图推导，不是 SfM 性能实验。
- 报告中 74 个唯一 HTTP(S) 目标均做了跟随重定向的可达性检查；73 个返回 2xx。SAGE 的 `10.1177/0278364918823086` 落地页对自动请求返回 403，但 Crossref 原始记录独立返回了同一 DOI、题名 *Reliable Graphs for SLAM*、journal-article 和 2019 年出版信息。链接可达不等于内容断言自动成立；关键断言仍按原文/源码逐项核对。
- 所有报告内的绝对本地链接均存在；Markdown 代码围栏成对，未留 `TODO/TBD/FIXME` 或内部检索占位符。
- 对 `cap47_live.db` 的 SQLite 查询以 read-only 模式重跑，重现 121 images、1133 matches、1133 two-view geometries、33 个 gap>12 和最大 gap 76。

本地仓库均为只读审计；没有 reset、clean、checkout、commit，也没有修改 PocketWorld 或 Aether3D-cross。Aether3D-cross 工作树原本高度 dirty，所有既有改动均保留。

## 11. 最终回答

如果把问题压缩成一句话：

> COLMAP 的 powers-of-two pairing 是 Johannes 基于小基线视频效果观察做出的多尺度工程启发式；它能以少量索引偏移探测很远帧，但没有公开证据证明当前 pure-power 版本应固定舍弃 gap 3，尤其不能把这一视频经验直接迁移到 PocketWorld 的非均匀离散快门采集。

对 PocketWorld，当前最稳妥的研究结论不是“照搬 COLMAP 默认”，也不是“永远保持 K12”，而是：先冻结真实 pair graph 和阶段，保留短程连续核心，用等成本的 adaptive/hybrid 长边做可证伪实验，再由新增 verified observations、track/角度分布和产品指标决定。
