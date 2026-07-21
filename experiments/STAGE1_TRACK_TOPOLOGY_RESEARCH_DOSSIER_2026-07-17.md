# Stage-1 Track 拓扑(鬼层/feature-site alias)研究 Dossier — v2(合并版)
日期:2026-07-17(v2 合并;v1 同日)

> **v2 数据来源说明(替代 v1 的"输入数据缺失声明")**:本版由四路证据合并而成——
> ① **8 线索并行 sweep 原始数据**(colmap-official / camera-triplets / detector-free-track-topology / disambiguation-classics / production-track-building / community-social / recent-2025-2026 / license-audit),全部为一手联网核查(GitHub API、raw 源码逐行、论文 PDF 全文、zip 解包);
> ② **对抗核查裁决**:对高影响 claim 逐条独立复查,给出 CONFIRMED / PARTIALLY_TRUE verdict(本轮无 REFUTED);凡 PARTIALLY_TRUE 本文一律采用**修正版**表述;
> ③ **v1 单 agent 一手核查**(引用与 REFUTED 表可靠,全部保留);
> ④ **本地 grep 核实**(vendored COLMAP 树,2026-07-17)。
> 冲突消解规则:带 CONFIRMED verdict 的新数据 > sweep 高置信 > v1 > 推断;v1 与 v2 的冲突/改判全部记录在 §6.3。
> ⚠️ 已知残缺:license-audit 线索的数据在传输中截断(findings 到 Doppelgangers++ 条目为止,该线索的 verdict 段缺失);其结论凡有其它线索交叉印证的按印证置信采用,孤证按 sweep 原置信标注。

---

## 1. 执行摘要

- **证据最强的技术路线(v1 结论维持并强化)**:"保留多 orientation 匹配证据到几何验证之后、在 track/Point3D 出生之前做 site 级 alias 裁决"。官方 COLMAP **PR #3681(2025-11-04 merge,3.13.0 于 2025-11-07 发布,列为 Breaking Change)** 已把 correspondence graph 改为保留 one-to-many 匹配;**本地 grep 已证实(CONFIRMED)vendored 树内置该逻辑**(§2.3),stage-1 无需 patch 图层,定位就是补官方留白的**裁决层**。
- **v2 最重要的新增设计事实(源码级,CONFIRMED)**:COLMAP 4.1.0 的 IncrementalTriangulator **Merge/Complete 机器已经具备消费 alias 跨边的全部能力**(Merge 沿显式 correspondence 边、全轨迹 4px 重投影投票);鬼层无法自愈的**结构性原因是缺 alias 跨边而非缺合并机制**——图禁自匹配使同图 alias 永无直连边(§2.4)。stage-1 的最小形态可以收敛为"生产 alias 跨边证据 + 决定谁出生",合并执行复用原生机器。
- **v2 最重要的新增限定(CONFIRMED)**:PR #3681 只是让图"能收"one-to-many;COLMAP 内置 SIFT matcher 在 **cross_check=true(本项目铁律)下仍严格一对一**,one-to-many 只来自单向 NN 或外部导入。即该能力在现有管线中**处于休眠态**——alias 证据要 stage-1 自己注入,与互检铁律不冲突(alias 边走独立通道)(§2.2)。
- **生产系统横向扫描(v2 新增,源码级)**:OpenMVG / AliceVision / Theia / GLOMAP / hloc 五家对"同图多特征冲突"只有三种原始处理——整 track 销毁、顺序依赖任意丢一个、GLOMAP 独家在 10px 固定容差内保留双观测(CONFIRMED)。**无一家做几何证据驱动的自适应 alias 裁决**;stage-1 的裁决器没有现成完整实现可抄,但方向被 GLOMAP 容差聚合 + PR #3681 双重印证(§3.2)。
- **两处对 v1 的改判(§6.3)**:① camera triplets 官方代码 zip 内 .m 文件头带完整 **BSD-3-Clause**(v1 误判为无 license 不可商用)→ 可直接对照移植;② Dense-SfM 代码**已发布**(IceTea-CV/DenseSfM-Refine,v1 说未发布)但 **repo 无 LICENSE=全保留**,且论文核心的 GS track extension 未开源——净结论仍是"只能读论文 clean-room"。
- **文献空白定位(经对抗核查收窄后仍成立)**:DFSfM 的 match quantization 证明"出生前 per-site 聚合"并非全然空白(但它在**几何验证之前**、治 detector-free 匹配抖动);"**verified geometry 之后、track 出生之前、针对 SIFT 多 orientation alias 的逐站点裁决**"这一最窄窗口,8 线索独立检索均未命中公开工作——无撞车、无反例、也无现成实现。
- **商用可行性一句话**:核心路径零许可风险(vendored COLMAP BSD-3、camera-triplet 官方 demo BSD-3、Zach 式 cycle 统计自实现、GLOMAP/hloc/PixSfM 结构参考均 permissive);所有 learned 消歧/匹配路线在权重或训练数据层污染(Doppelgangers++ 与 MASt3R 双 NC 确证;LoFTR 权重无授权+SenseTime IP 声明;ScanNet ToU 一手全文=非商用死线);唯一查到"权重也标 permissive"的半稠密通道是 HF zju-community/efficientloftr(Apache-2.0,medium 置信)。

---

## 2. 官方风向:COLMAP PR/issue 谱系(全部经对抗核查)

### 2.1 PR #3681 准确现状(核心锚点,verdict=CONFIRMED)
- 标题:**"Update the logic of duplicate correspondence to support one-to-many matches"**;作者 B1ueber2y(Shaohui Liu,README 列名的四位 core maintainers 之一)。
- 时间线:2025-11-03T05:00:29Z 开,**2025-11-04T16:59:24Z squash merge**(merge commit `3cdb5bf9`,含 Co-authored-by: Johannes Schönberger)。仅改 2 文件:`correspondence_graph.cc`(+8/−11)与其测试(+3/−3)。
- 逻辑变更:旧 = `duplicate1 || duplicate2`,两侧 lambda **只比 image_id**——任一端点与对方图像已存在任何 correspondence 即整条拒绝(贪心、输入顺序依赖;作者最小反例:matches [0,0],[1,1],[0,1] 依顺序得 1 或 2 条);新 = 单侧检查 `corr.image_id == image_id2 && corr.point2D_idx == match.point2D_idx2`,**仅完全重复对判重**(边双向插入故单侧检查充分,注释原文在源码中),one-to-many 全保留。测试期望 3→4。
- 作者动机(评论原文,CONFIRMED;注意引语在 PR 首评而非正文——PR body 为空):one-to-many "can potentially help two-view geometry to find better models, and can easily come from one-way nearest neighbor matching";主张 "keep the one-to-many matches and only filter out the completely duplicate ones",质量控制 "can be handled from the matching side outside CorrespondenceGraph"——**证据保留、裁决上移出图层**,与 stage-1 哲学同向。
- 维护者轨迹(verdict=PARTIALLY_TRUE,采修正版):ahojnnes 初始顾虑 NBV 可见点计数假设 → 查 observation manager 后确认无阻碍 → 曾短暂 CHANGES_REQUESTED(误建议 `duplicate1 && duplicate2`)→ 经作者解释后自承 "Didn't see we are adding the correspondences bi-directionally, which makes this correct" → 要求补注释后 16:09 APPROVED。至 2026-07-17 **无 revert**;其后触碰该文件的提交共 **7 个**(#3975/#3981/#3985/#4146/#4279/#4510/#4511,v1 sweep 曾漏两个)均为正交重构,one-to-many 语义不变。
- 发布载体(CONFIRMED):3.13.0(2025-11-07T15:43:45Z),changelog 列为 **Breaking Changes**:"Allow one-to-many matches in correspondence graph. Previously, only one-to-one matches were added to the correspondence graph and therefore other matches were not used during reconstruction." compare API 证明 merge commit 是 3.13.0 祖先(behind_by=14/ahead_by=0);4.0.4 与 4.1.0 两 tag 源码逐行核实含同一逻辑。

### 2.2 关键限定:内置 matcher 仍产出一对一(CONFIRMED,v2 新增)
4.1.0 `sift.cc` L826-952 逐行核对:**cross_check=true(默认)下 FindBestMatches 取双向最近邻交集,严格一对一**;one-to-many 只在 cross_check=false 的单向 NN 或外部导入自定义匹配时出现。PocketWorld 铁律要求 GPU matcher cross_check=true → **该能力在现有管线中休眠**。含义:上游只开了门,alias 证据要 stage-1 自己送进去;保留互检与利用 one-to-many 不矛盾——alias 边可作为额外通道单独注入。
⚠️ 对抗核查同时指出(PARTIALLY_TRUE 修正):"管道已经把多 orientation 副本证据送进 graph"是**未经验证的推断**——图层不再阻挡 ≠ 证据真的流入。且"副本匹到不同目标点(A1↔B1、A2↔B2)"在旧逻辑下本来也放行,非 #3681 贡献。**Phase-0 必须实测当前 DB 中 alias 证据的真实流量。**

### 2.3 vendored 树现状(v1 推断 → v2 CONFIRMED,本地一手)
**本地 grep 核实(2026-07-17)**:vendored COLMAP(`~/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/colmap-src/colmap/scene/correspondence_graph.cc`,及 A3X-colmap41 工作树同路径)第 ~144-153 行的 duplicate 判定**已是 image_id + point2D_idx 双条件**,并含 "checking from only one side is sufficient" 注释 = **PR #3681 one-to-many 保留逻辑已在本地树**。该树 `version.cc` COLMAP_VERSION="4.1.0"(注:CMakeLists 内版本串残留 "3.14.0.dev0",系迁移未改写的字符串,不影响行为)。v1 §2.3 的"待本地验证"警示就此关闭;stage-1 **不需要移植任何上游 patch**。

### 2.4 4.1.0 triangulator / 数据模型语义(v2 新增,源码逐行,load-bearing)
| 机制 | 源码事实(4.1.0 tag) | 对 stage-1 的含义 |
|---|---|---|
| **Merge()**(L583-677) | 仅当两 Point3D 的 track 元素间存在**显式 correspondence 边**才尝试合并;合并位置=按 track 长度加权平均;**两 track 全部观测**对合并点重投影都 ≤ merge_max_reproj_error(默认 4px)才接受,任一 outlier 整体放弃;成功后递归续并 | "local track support 全员投票"的生产级最近亲;stage-1 注入 alias 跨边后它就是现成裁决执行器,自带误杀保护 |
| **图禁自匹配**(correspondence_graph.cc L106-110) | image_id1==image_id2 直接拒 → **同图两个 alias keypoint 永远不可能有直连边** | 鬼层无法自愈的结构性原因:缺的是跨边,不是合并机制 |
| **Continue()**(L537-581) | 未三角化观测挂到角误差最小且 ≤2° 的**唯一**既有 3D 点——先到先得,无多假设仲裁 | alias 分裂身份的锁死点之一;裁决层要在此之前生效 |
| **Complete()**(L679-765) | 5 层传递 BFS + 4px 重投影门 | 可复用为被裁定 alias 观测的收编通道 |
| **Retriangulate()**(L360-401) | 明确拒绝合并两个既有 3D 点(注释:retriangulated correspondences "very likely bogus") | 不能指望 retriangulation 救鬼层 |
| **数据模型**(reconstruction.cc L553-590 / track.h) | AddObservation 唯一约束 `!point2D.HasPoint3D()`;Track::AddElement 无同图查重;MergePoints3D 无条件拼接 | **"一个 Point3D 身份 + 同图多个 alias 观测"是原生合法状态**;stage-1 聚合产物零数据结构手术 |
| **#3975(4.0.0)** | verified TwoViewGeometry(含配置/内点)常驻 correspondence graph | 聚合层可直接从图取证,不必回读 DB |

### 2.5 簿记断言与 one-to-many 的下游风险面(CONFIRMED,v2 新增)
- `ObservationManager::SetObservationAsTriangulated` 仍保留 `THROW_CHECK_LE(num_tri_corrs, num_total_corrs)`(失败信息即 "must not contain duplicate matches");image.num_correspondences 与 NBV 可见点计分**按边计数**,alias 边会被多重计入(PR 作者自己点名 NBV 计数责任在匹配侧)。
- 实证案例:issue **#4435**(2026-05-31)standalone GLOMAP(旧 3.12.6)开 loop detection 后触发同款断言 abort(26 vs 25),以"升级再看"关闭、无根因修复。
- **验收清单硬项**:stage-1 注入 alias 边后必须回归——该断言不触发;NBV/初始对计分未被 alias 边显著扭曲(或证明扭曲无害)。

### 2.6 issue 谱系与官方立场演变链(v1 保留 + v2 扩充)
| issue | 日期 | 要点 | 类别 |
|---|---|---|---|
| **#293** | 2018-01-31 | 用户报同坐标不同 scale/orientation 的"重复 keypoints";ahojnnes 唯一答复:"COLMAP detects multiple orientations per keypoint by default… please set SiftExtraction.max_num_orientations to 1."——**官方给的唯一旋钮正是本项目已判死项**;官方从未提供出生前聚合替代 | 第1类(alias) |
| **#832** | 2020-03-29 | ahojnnes 定性根因 = 多 orientation / scale-space 抑制不足;"apart from potential slight performance gains, this doesn't make a significant difference in the accuracy of the results"(⚠️ 不利证据,见 §6.4;其语境是重投影精度,非产品点云可见双层壳)。issue 至今 open,官方立场=良性忽视 | 第1类 |
| **#847** | 2020-04-18 | jatentaki 的自定义 matcher 产生 one-to-many(尺度差一对多)撞 duplicate WARNING;tsattler 让读源码,无语义承诺;2024-05 社区补代码位置。**需求早官方五年**;#3681 保留的正是该场景 | 第1类 |
| **#1437** | 2022-02-24 | Sattler 明示:"Colmap does not implement mechanisms to handle ambiguous matches",指路 cvg/sfm-disambiguation-colmap 并转述其结论"no universal method to handle ambiguities";Snavely 2024-03 补荐 Doppelgangers。至今 open | 第2类(repeated-texture) |
| **#4454** | 2026-06-16 | 珊瑚礁 7800 图 multiplanar/结构复制,仍 open;用户自查归因 sequential_matcher 召回不足,换 vocab_tree 后基本消失。2026 年活案例印证:先分类定性再选刀 | 第2/3类 |
| sift.h 默认 | main | `max_num_orientations = 2`(官方默认就生产 orientation alias);`estimate_affine_shape=false` | — |

**立场演变链**:#293(2018,给关闭旋钮)→ #832/#847(2020,良性忽视)→ #1437(2022,承认无机制)→ **#3681(2025,保留证据、去重上移)**。"证据保留、裁决后置"是官方 2025 起的既定方向;stage-1 是它在站点身份层的自然延伸——且官方**至今无任何 birth-time alias 聚合**,该层留白正是 stage-1 要填的位置。

### 2.7 3.12→4.1 changelog 相关变更(CONFIRMED)
3.12.0:transitive completion 修复(#3094)、三角化改在 camera rays 上(#3184)。3.13.0:one-to-many(#3681, Breaking)、静止点过滤(#3521)、random_seed 全确定性。4.0.0:**two-view geometries 存进 correspondence graph(#3975,聚合层取证挂点)**、track establishment 重构进 GlobalMapper(#3965/#3972)、EXIF upright 提取(#4122,从源头减多 orientation 的正交官方杠杆,依赖 EXIF 且改特征语义)。4.1.0:triangulator 提速、图/ObservationManager 增量构建(#4279)——对 finalize 时延预算是利好。全程无 birth-time alias 聚合类变更,one-to-many 立场无反复。

---

## 3. 候选方法对照

### 3.1 学术/官方方法对照表(v1 更新 + v2 扩充)

| 方法 | 机制 | 出生前/后 | 对四类来源 | 端上成本 | 许可(代码/权重/数据) | clean-room 可行度 |
|---|---|---|---|---|---|---|
| **A. COLMAP one-to-many(PR #3681)** | 图只去完全重复,保留一对多证据 | 出生前(graph 层) | 第1类的**必要基础设施**而非裁决器 | ≈0(**本地已内置,CONFIRMED**) | BSD-3 / 无权重 / 无数据 | 无需 |
| **B. Camera triplets(Manam & Govindu, CVPR 2024 + IJCV 2026)** | 边分 q^t_ij = n_ij / max(triplet 三边 inliers),跨 triplet 平均;Theorem 1 证明阈值化=全局选边最优;自适应阈值 τ=m(1−d_max/\|V\|)+d_max/\|V\|,唯一超参 m;IJCV 版加 weak triples(虚拟零 inlier 第三边)覆盖任意拓扑 | 出生前(viewgraph 边级预处理) | 主治**第2类**假边;**粒度是 image-pair 边非 feature site**,对第1类非现成解,范式可下沉 | 低:纯图统计,<1-2% 重建时间,~160 行 MATLAB | **代码=BSD-3-Clause(v2 改判:zip 内 .m 文件头逐字条款,两线索独立解包核实)** / 无权重 / 无数据 | 高;⚠️ 但见 §6.4 over-split 风险与 m 跨域 0.1-0.9 |
| **C. cvg/sfm-disambiguation-colmap(Yan'17/Cui'15/Kataria'20)** | Yan/Cui=重建前 match 过滤;**Kataria=修改增量重建内部 resectioning(修正:非 match 过滤)** | 出生前/重建中 | 第2类 | 中 | 代码:**无 LICENSE(API 404 + 全树递归零命中,CONFIRMED)= 禁抄** / 无权重 | 中;README 教训:"No method consistently works well over all datasets with a single set of hyperparameters" |
| **D. Doppelgangers(ICCV 2023)** | learned pair 二分类,低分对删 DB | 出生前(pair 级) | 第2类 | 高 | 代码 MIT / **权重无声明(不能由 MIT 推断)** / Wikimedia 逐图许可 + MegaDepth 子集 | 低-中:须自训;室内非其分布 |
| **E. Doppelgangers++(CVPR 2025)** | 冻结 MASt3R backbone + Transformer 头;τ=0.8 跨场景固定 | 出生前(pair 级) | 第2类 | 高(ViT-Large 级,A16 不现实) | **代码 CC BY-NC-SA 4.0(raw LICENSE 实查)+ 依赖 MASt3R(代码+权重均 CC BY-NC-SA)= 双重商用阻断(CONFIRMED)**;训练数据 VisymScenes 许可未明示 | 判死于 ship;三重阻断(license/体积/算力) |
| **F. Detector-Free SfM(ZJU, CVPR 2024)** | 匹配端点网格量化 ⌊x/r⌉·r(r=8 coarse)+ 每图按量化像素 groupby 统一 keypoint 身份 + 索引重写;refinement=transformer 精化→`incremental_model_refiner`(=BA+CompleteAndMergeTracks+FilterPoints 循环+gauge 固定,fork 无新几何算法);同图 duplicate:set 去重+均值+**精化坐标统一写回全部副本索引(坐标坍缩,不删除)**;coarse 期 tri_ignore_two_view_tracks=1 | 出生前(量化在**验证前**)+出生后(迭代拓扑调整) | 第1类构造性根治(换前端)+ 弱纹理 | 很高(既有定案:finalize 救援支路;O(对数) 是瓶颈) | 代码 Apache-2.0;⚠️ **third_party/aspantransformer=Apple 非商用许可(vendoring 陷阱)**;权重 Drive 无声明;LoFTR 权重无授权+SenseTime IP 声明;indoor=ScanNet 非商用 | 纯几何件全部可 clean-room(见 §5.5 菜单) |
| **G. Dense-SfM(CVPR 2025)** | 双向一致性验证(εp=3px)免量化;GS 可见性 + 3D→2D 投影做 track extension,**每图至多一个新观测(one-to-one 由构造保证)**;2 轮精化 εf=3px | track 层(与 stage-1 目标最接近) | track 一致性(间接 1/4 类) | 高 | **v2 改判:代码已发布(IceTea-CV/DenseSfM-Refine,pushed 2026-06-01)但 license=null=全保留、GS track extension 未开源、权重无声明** → 代码严禁复制 | 只能读论文取思想;纯几何部分(双向验证/投影收编)本有公开先例 |
| **G2. Pixel-Perfect SfM(ICCV 2021)** | ComputeTrackLabels:按描述子相似度**降序 union-find 最大生成森林 + 同图 image-set 不相交硬约束**;KA 位移 ≤8px;拓扑在 BA 期冻结 | 出生前(track 形成期 greedy) | 第1类的**已判死同族**(一次性全局 greedy forest) | 中 | 代码 Apache-2.0;S2DNet 权重无独立许可 | 仅局部借"同图不相交测试 + 按置信度排序处理边";整体方案不得再端上来 |
| **H. 本项目 stage-1(alias 聚合裁决)** | verified geometry 之后、track 出生之前:聚合同 site alias 证据,triplet/cycle + local track support 自适应裁决唯一 3D 身份;ambiguous 留 DB 不出生 | **出生前(裁决层)——最窄窗口文献空白位(经对抗核查收窄后仍成立)** | 专治第1类 | 图统计级 | 自研 + 上游 BSD 基础设施,零许可风险 | — |

### 3.2 生产系统 track 冲突处理谱系(v2 新增,全部源码逐行,补 v1 空白)

| 系统 | 同图冲突处理 | 源码事实 | license |
|---|---|---|---|
| **OpenMVG** | **整条 track 销毁**(连正确跨图观测陪葬) | tracks.hpp Filter():同 image id 出现多次 → 整 track 标 invalid,ExportToSTL 整条剔除;注释 "a track cannot list many times the same image index" | MPL-2.0 |
| **AliceVision / Meshroom** | 双模式(⚠️ verdict 修正:两层默认值相反):**引擎默认 filterTrackForks=true=整条删**;Meshroom 生产节点默认 False → exportToSTL 用 `std::map::operator[]` **静默 last-wins 覆盖,零日志,顺序依赖** | TracksBuilder.cpp `clearForks && myset.size() != cpt` → erase;Track.hpp featPerView=std::map(每视图单值);ReconstructionEngine_sequentialSfM.hpp 默认 true,StructureFromMotion.py 节点 value=False | MPL-2.0 |
| **Theia** | **first-wins 任意丢观测**(unordered_set 哈希序,顺序依赖),保 track,仅汇总计数 | track_builder.cc `InsertIfNotPresent` 失败即 continue | BSD-3 |
| **GLOMAP** | **唯一保留双观测者(CONFIRMED)**:同图第二特征与已有特征像素距离 ≤ thres_inconsistency(默认 10.0px)→ 照样 emplace_back 进同一 track(一图多观测进下游全局优化);超阈值 → **整条 track clear** 并计 discarded_counter | track_establishment.cc/h 逐字核实;min_num_view_per_track=3 / max=100;repo 2026-03-09 归档,**已全量迁入 COLMAP 主仓(global mapper)** | BSD-3(ETH 2024) |
| **hloc** | 无自建 track 层(直通 pycolmap);但 **match_dense.py 是"先聚合后出生"的成熟工程范式**:cell_size=8 量化格(max 1 kp/patch)→ 跨 pair 身份字典 → bin 票决定稿每图唯一 keypoint | match_dense.py to_cpts/aggregate_matches/most_common(1) | Apache-2.0 |
| **LightGlue** | 匹配层构造性一对一(mutual argmax);跨 pair track fork 仍可能 | filter_matches 双向 mutual 交集 | 代码+**权重均 Apache-2.0(README 明文,少见的权重明示)**;训练数据 MegaDepth 尾巴另计 |
| Meshroom 出生门 | minNumberOfObservationsForTriangulation 默认 2;官方原文:设 3+ "reduces drastically the noise in the point cloud, but the number of final poses is a little bit reduced (from 1.5% to 11%)" | StructureFromMotion.py | MPL-2.0 |

**横向结论(load-bearing,归纳限于已查五家)**:同图 alias 在生产生态里是被**销毁或任意二选一**,不是被裁决;GLOMAP 是唯一容差聚合先例——但用的是**单一固定像素阈值(本项目已判死机制)**且超阈整条陪葬,恰是 stage-1 要改进的那一格。SIFT 多 orientation 副本像素距离为 0,天然落进 GLOMAP 聚合分支 → **证明下游全局优化能消化一图多观测 track**。

### 3.3 feed-forward / 学习匹配家族(v2 新增,速查)
- **VGGSfM**:CC BY-NC 4.0(代码即非商用);机制上"身份=query 站点、track 是身份的延伸"正是 stage-1 想要的语义,可作概念佐证,不可参考实现。
- **MASt3R-SfM**:代码+权重 CC BY-NC-SA;reciprocal 强一对一 = "几何验证前丢证据"的另一形态(反例记录,不可借鉴)。
- **Fast3R** FAIR NC;**Light3R** 无代码;**FlowMap** MIT 但 per-pixel 无离散 track 身份;**VGGT** 代码 2025-07 起可商用(禁军事),仅 VGGT-1B-Commercial 权重可商用(申请制,medium 置信)。
- 净结论:feed-forward 家族没有 track 概念就没有 alias 裁决可抄;许可上除 FlowMap/VGGT 特例外普遍 NC。
- **RCM(ECCV 2024)**:显式 many-to-one 匹配策略,GT matches +260%——"早去重掉召回"的匹配层独立学术证据,与 #3681 动机互证。
- **MV-RoMa(CVPR 2026)**:顶会背书 "pairwise 链式传递产生 fragmented and geometrically inconsistent tracks" 的问题陈述,可作动机引用;改匹配器路线,与 stage-1 不同层。

---

## 4. 社区与从业者实况(谁说了什么;v1 保留 + v2 大幅扩充)

1. **ahojnnes(COLMAP 作者)**,#832,2020-03-29:同址多 keypoint 根因=多 orientation/scale-space 抑制不足;"doesn't make a significant difference in the accuracy of the results"(语境=通用重投影精度,非室内近距平面可见壳;如实记录于 §6.4)。#293,2018:唯一处方 max_num_orientations=1(本项目判死项)。
2. **B1ueber2y(core maintainer)**,PR #3681 首评,2025-11-03:旧贪心顺序依赖;one-to-many "can potentially help two-view geometry to find better models";去重责任在 "the matching side outside CorrespondenceGraph"。
3. **tsattler**,#1437,2022:"Colmap does not implement mechanisms to handle ambiguous matches";转述 cvg 复现结论 "no universal method";**snavely** 2024-03 同帖补荐 Doppelgangers。
4. **cvg/sfm-disambiguation-colmap README**(ETH CVG,verdict=CONFIRMED 引语逐字):"**No method consistently works well over all datasets with a single set of hyperparameters.** Tuning the parameters for large scenes is difficult and time-consuming for all three methods." + "Even Kataria's method … was still insufficient to disambiguate some datasets."——单一固定阈值判死的独立旁证。
5. **IISc CV Lab(camtripsfm)**:官方 claim "removes false edges, thereby avoiding incorrect superimposed reconstructions"(其 "ghosting" 指第2类叠影,引用勿混淆);**社区讨论度≈0**:OpenAlex 仅 4 条引用(含自引),无任何博客/Reddit/X 测评,仅两个 0-star 第三方 repo(均无 license);**PoliMi 学生复现:<400 图小集上推荐 m=0.7 过激,降到 m=0.1(作者从未用过的值)才可用**。
6. **Agisoft(Metashape)官方支持 Alexey Pasumansky**(论坛 topic 9759,~2018-10):"双层/两级"归因对齐设置(Low accuracy + Reference preselection),修法全在对齐/参考系层——业界把双层归为"对齐问题"是常态(类别:pose 类)。
7. **Epic/RealityScan**(官方论坛,2025-08/09):单 component 重复结构=弱环路约束("banana effect");员工 JakubVanko 处方=控制点+删 component 重初始化("RS is always initializing from the existing components")(类别:repeated-texture/pose drift)。
8. **MrNeRF(Janusch Patas,3DGS 头部影响者)**2024-2025 全押 SfM 提速与 C++ 工程化(赞 GLOMAP、移植 ALIKED+LightGlue、转发 FastMap);**对 ghost/duplicate geometry、track 质量零发声**——从业者注意力在速度,track-alias 卫生无人抢占。
9. **IMC 2024 社区方案综述**(arXiv 2407.03172):赛场"去重"=进 COLMAP 前粗暴合并 keypoints(变体的 max_num_orientations=1,已判死);track 精化(VGGSfM/PixSfM)全在出生后;repeated structures 虽是赛题类别但无前排方案专门消歧。
10. **负结果(检索受限,低置信)**:8+ 组措辞检索 Reddit/中文社区(知乎/CSDN),未命中任何把室内双层地板归因于同像素多 orientation 特征分裂的讨论;命中的归因全落 pose/反光/重复纹理/采集手法四类。**feature-site alias 类双层在从业者话语体系里没有名字**——四类鬼层分类学本身是差异化认知资产;验收叙事需自定义指标,无社区话语可对标。
11. **DetectorFreeSfM 算力实测**(issue #39,2024-06):100 张 640×480 单 3090 仅 coarse matching >1h(COLMAP 同任务 ~10min)——与既有定案一致:O(对数) 是瓶颈。

---

## 5. 对 stage-1 设计的具体启示(v1 保留 + v2 源码级扩充)

### 5.1 裁决评分函数候选形式(从已核实文献移植)
- **相对比值式(camera triplets,CONFIRMED 机制)**:降维到 site 级——alias 分 = 该 alias track 的支持(verified correspondence 数 / 通过 cycle 的三元组数)÷ 同 site 所有 alias 中的最大支持,跨 triplet 平均。相对量免疫场景绝对纹理密度差;这正是"简单 thresholding 可证最优"(Theorem 1)成立的原因。
- **作者的反面论证值得抄**:Manam & Govindu 显式拒绝"三视图共同 inlier"打分——共同 inlier 依赖 keypoint 跨图 repeatability,而 **SIFT 多 orientation alias 恰是 repeatability 病理** → 聚合 alias 证据应偏向"相对支持度"型统计,回避"绝对共同观测数"型统计。
- **weak-triple 技巧(IJCV 2026)**:两视图证据当"缺失第三边=0 支持"的退化三元组统一打分——2-view 点的 alias 裁决可用同款"虚拟零支持"语义纳入同一评分体系,不必单列规则。
- **独占观测率(Yan CVPR'17 思想)** + **cycle consistency 票决(Zach 2010 谱系,CONFIRMED)**:Zach 的机器可整体移植——环链乘变换偏离恒等、穷举三角环+生成树环基(环长≤6)、概率化裁决(内点指数分布/污染均匀分布)、且自报"参数在合理范围内不敏感";把"边=图像对"换成"边=候选 alias 关联"即可。Merrell 票决式避 Disney 专利(呼应鬼层方案书)。
- **track 长度作为类别判别器(Kataria 3DV'20)**:repeated-texture 的病 track 偏长,feature-site alias 的平行 track 偏短——免费信号,可用于把第1/2类鬼层在裁决前分流。
- **组合建议(v1 维持)**:相对支持比 × 独占观测率作主分,cycle 票决作硬门;全部在 verified geometry 之后计算,不用原始描述子距离。

### 5.2 自适应阈值如何导出(v1 维持 + v2 警示)
- 阈值定在**相对分布**上(site 内归一化 [0,1]),全局阈值只切"是否显著劣于 site 内冠军",从全图 alias 分数分布(双峰谷底/分位数)导出——兼容已判死项。
- triplet 覆盖数决定该 site 裁决**置信度**;覆盖不足直接进 ambiguous 不强裁——自动排除低视差/弱连接区,避免误伤第4类。
- **v2 硬警示(CONFIRMED)**:camtripsfm 的"自适应"公式只自适应图连通性,**不自适应数据域**——m 实际跨域取 0.1-0.9(论文 0.3-0.9,PoliMi 小图 0.1)。室内域的 m 等价物必须用 Mac 'o' 认证真值自行标定(误杀=0 红线),不能信论文默认值。
- 呼应 47 号定案:host 鬼层指标是抽签(5 跑 3.6-12.3%),bimodality 判据须 ≥3 跑中位;stage-1 阈值标定沿用该纪律。

### 5.3 ambiguous observation 语义与裁决落点(v1 维持 + v2 源码级具体化)
- 官方语义已是"graph 层全保留、track 层再说";stage-1 严格平行:alias 证据全留 DB,裁决只在 track/Point3D **出生闸口**;被裁并的 alias 观测挂到获胜 track(合并非删除);不确定 site 不发用户可见点——与 L2"数据不动、渲染门构造性不可见"哲学同构。
- **v2 关键具体化:合并执行不必自研**。stage-1 裁决层的最小职责=①生产 alias 跨边证据(注入 correspondence graph,one-to-many 已放行)②决定谁出生;合并由原生 **Merge()(全员 4px 投票)/Complete()** 自动消费。同时给反例意识:平行鬼层间距若超阈值×深度比,全员投票会正确拒并——**Merge 治"同点碎裂",不治第4类低视差噪声壳,类别要分清**。
- **锁死点**:Continue() 是先到先得的身份指派,裁决须在其前生效;DFSfM 的 `tri_ignore_two_view_tracks=1`(coarse 期 2-view track 一律不出生、后续补)是"低置信观测先不出生"的同构先例(注意它是全局开关,我们要的是自适应裁决)。
- **可借的同图收敛范式**:DFSfM 同图 duplicate 三件套(set 去重/均值/精化坐标统一写回全部副本索引)——**坐标坍缩而非删除**,再交 merge/filter 收尾;Dense-SfM 的投影式收编(唯一 3D 身份定了之后,按 3D→2D 投影+几何验证补观测,不需匹配边存在;可见性可用纯几何深度缓冲替代 GS)。
- **同图一对一局部测试**:PixSfM 的 image-set 不相交检查(set_intersection==0)是教科书实现,可在"验证后聚合"阶段复用为局部约束——但整体 greedy forest 已判死,不得作主方案。
- **工程形态**:hloc match_dense.py 的"量化格→身份字典→逐 pair 增量聚合→票决定稿"(Apache)可整体移植到裁决层;DFSfM 的"索引重写"(alias 聚合后重写 match 索引再进 triangulator)是 DB 侧落地样板。

### 5.4 计算成本定位(v1 维持 + v2 数据点)
- triplet/cycle 图统计是预处理级:camtripsfm <1-2% 重建时间(CPU);Zach 2010 在 126 视图上推断仅 0.6s;site 级版本规模更小(只在 multi-orientation site 上算,默认 max_num_orientations=2 封顶 alias 数)。远轻于 BA,与热账本兼容。
- 手机室内环扫的 viewgraph 是稀疏近链状——恰落在 loop-constraint 方法的**有利域**(Wilson 实测 Zach 法在稠密互联网图上不可用,稀疏图反而合适)。
- DFSfM/Dense-SfM 均只迭代 **2 轮**"精化→BA→过滤"即收敛——浅迭代够用,端上预算可承受。

### 5.5 纯几何 clean-room 菜单 + 回归验收清单(v2 新增)
**可直接 clean-room(许可干净)**:① DFSfM 匹配端点量化+每图身份统一+索引重写(≈60 行逻辑);② "独立全局精化命令"=BA+CompleteAndMergeTracks+FilterPoints 循环+阈值逐轮收紧+gauge 固定(机器全在 vendored 4.1.0,一天可等价复刻,不碰 hxy-123 fork);③ 同图坐标坍缩三件套;④ 双向一致性验证(εp=3px;等价于已有 cross_check 方向);⑤ 投影式观测收编(每图至多一观测+几何验证把关);⑥ PixSfM 同图不相交测试(仅局部);⑦ 中位尺度参考观测选择(scale=f/depth 取中位当锚,室内近远混合视角稳)。
**不可白嫖**:各家 multi-view 精化 transformer 及权重、Dense-SfM GS 可见性、S2DNet featuremetric(权重均无干净商用依据)。
**回归验收清单(硬项)**:SetObservationAsTriangulated 断言不触发;NBV/初始对计分不被 alias 边扭曲;改 tri_merge 阈值/轮次须按认证配置铁律走九门+签决;"stage-1 有效"结论须 ≥3 跑中位 + 设备端确认;Phase-0 先实测当前 DB 的 alias 证据流量(§2.2 休眠态问题)。

---

## 6. 风险与反例(诚实记录)

### 6.1 v1 REFUTED/修正表(全部保留,附 v2 注记)
| 原 claim | v1 裁决 | 修正版 | v2 注记 |
|---|---|---|---|
| "COLMAP 3.13.0 发布于 2024-11-07 / 2023-11-07" | **REFUTED** | GitHub API:3.13.0 = **2025-11-07**;4.0.4 = 2026-04-27;4.1.0 = 2026-06-26 | v2 sweep 再证:published_at=2025-11-07T15:43:45Z(CONFIRMED) |
| "COLMAP FAQ 建议 max_num_orientations=1" | **REFUTED(来源错误)** | FAQ 全文无此文字 | v2 补:该处方**真实存在但出处是 issue #293**(ahojnnes 2018 答复),非 FAQ;实质(官方唯一旋钮=判死项)成立,引用出处须改 |
| "Camera triplets 有官方 GitHub repo 和 license" | **REFUTED** | 无 GitHub repo(属实);**项目页**未声明 license(属实) | **v2 改判(重要)**:两线索独立解包 zip,camtripsfm_demo.m/unify_sfm_demo.m 文件头为逐字 BSD-3-Clause(IISc CV Lab 2024/2026)→ **代码可商用**;v1 "商用唯一路径=clean-room" 失效。详见 §6.3 |
| "Doppelgangers 权重可商用(repo MIT)" | **PARTIALLY_TRUE→修正** | 代码 MIT 属实;权重/数据条款未明示,不能由 repo license 推断 | v2 维持;并升级:Doppelgangers++ 的 LICENSE 经 raw 实查=**CC BY-NC-SA 4.0**(v1 "类型未逐字核验"落定),MASt3R 代码+权重亦 CC BY-NC-SA → 双重阻断 CONFIRMED |
| "one-to-many 保留必然减少鬼层" | **未证明(禁当事实)** | 净效应未知,需 A/B 实测 | v2 强化:cross_check=true 下内置 matcher 根本不产 one-to-many(§2.2),该问题部分悬空——先测 alias 证据现有流量,再谈净效应 |

### 6.2 v2 对抗核查修正表(PARTIALLY_TRUE 条目,本文一律用修正版)
| 原 sweep claim | 修正要点 |
|---|---|
| Wilson & Snavely "四个数据集只成功 Desk" | Roberts et al. 实有**六个**数据集(BLDG/DESK/BOOKS/OATS/BOXES/CUP,21-76 张);"四"疑与其自己的 4 个 Internet 集混淆;引文应为 "**but** we were only successful";oversegmentation 是有意保守设计(Ncomp 偏大) |
| camtripsfm over-split:"SAF/SPC/MDW/TRN 均 ETH3D;IDR 标 ✓*" | SAF/SPC 出自 Howard et al. 2022(IMC PhotoTourism),仅 MDW/TRN 属 ETH3D;IDR(152→42 相机/73k→9k 点)数字属实但**论文标 ✓ 非 ✓***(over-split 定性系引申) |
| "经典 disambiguation 文献全治 over-merge,出生前 per-site 聚合无任何先例" | **被 DFSfM 部分推翻**:match quantization 就是出生前 per-site 聚合(但在**验证前**、治 detector-free 抖动非 SIFT alias);最窄窗口(验证后+出生前+SIFT alias)仍未命中公开工作 |
| cvg repo "三法全部是重建前 match 过滤" | 仅 Yan/Cui 是;**Kataria=修改增量重建内部 resectioning**(track length 调 next-view 选择+reliable 点做注册),非 match 过滤 |
| DFSfM "round_matches_ratio 默认 4" | 真实默认 **None**(L45 的 4 是被入口参数覆盖的死配置);仅 texturepoor coarse_fine 配置传 4;另存在 ratio==1 时的 merge 分支("绝对无 NMS"不成立) |
| DFSfM "阈值 [3,2,1.5]px、窗 15→11→7" | 属代码配置;**默认 2 轮实际只消费 3→2px 与 15→11**;paper 自述固定 ε=3px |
| "AliceVision 默认 last-wins 静默覆盖" | **引擎/CLI 默认 filterTrackForks=true(整条删)**;False 是 Meshroom 生产节点层覆盖出来的——两层默认值相反 |
| "管道已把多 orientation 副本证据送进 graph" | 未经验证推断:图不再阻挡 ≠ 证据已流入;cross_check=true 休眠态;须 Phase-0 实测 |
| ahojnnes review 轨迹 "后续 5 个提交" | 实为 **7 个**(漏 #3981/#3985),经查均正交,结论(无 revert、语义不变)不变 |
| construct_matching_data.py 路径 | 在 src/post_optimization/data_construct/ 非 src/dataset/(勘误级) |

### 6.3 v1→v2 冲突与改判记录(按规则:CONFIRMED/双线索一手证据为准)
1. **Camera triplets 代码许可:无 license(v1)→ BSD-3-Clause(v2)**。v1 只查了项目页(页面确实无声明);v2 两条线索独立下载 zip 并逐行读 .m 文件头,均为完整 BSD-3-Clause 条款(camera-triplets 线索的 CONFIRMED verdict 证据中亦复核了 zip 取回与逐行内容)。影响:B 路线从"仅 clean-room"升级为"可直接对照移植";残留注意:zip 无独立 LICENSE 文件,按 .m 头部条款执行;unifysfm demo 有一处变量名 bug(L159),demo 级质量。
2. **Dense-SfM 代码:未发布(v1)→ 已发布但无 LICENSE(v2)**。IceTea-CV/DenseSfM-Refine 存在(GitHub API license=null,pushed 2026-06-01),README 明示 GS track extension 未包含。净结论与 v1 一致(无物可抄),但表述必须更正,且新增"repo 代码严禁复制"的合规红线。
3. **Doppelgangers++ license:未逐字核验(v1)→ CC BY-NC-SA 4.0 确证(v2)**,叠加 MASt3R(代码+权重 CC BY-NC-SA)与 ViT-Large 体积,三重 ship 阻断。
4. **vendored 树含 one-to-many:推断(v1 §2.3)→ CONFIRMED(v2 §2.3 本地 grep)**。v1 的"⚠️ 建议本地 grep"行动项已执行并关闭。
5. **Kataria 归类**:v1 表 C 行把三法统称"出生前过滤"→ 修正为 Yan/Cui 出生前、Kataria 重建中。

### 6.4 对已定方向不利的证据(如实呈报;v1 保留 + v2 扩充)
1. **维护者对病理严重性的历史定性偏轻**(v1 保留):ahojnnes 2020 称同址多 keypoint 对精度"无显著影响"。我们的反驳(室内近距平面+低视差下 alias 分 track 三角化成 2-3.5cm 平行壳,47 号法医)是项目内实测,非文献共识;对外引用须区分"官方认为无害(通用重投影精度)"与"我们实测有害(特定几何+用户可见性)"——**房间级平行鬼层的可见性论证必须用自己的数据,不能引官方背书**。
2. **camtripsfm 的 over-split 反例(v2 新增,load-bearing)**:方法依赖边冗余度;作者自认低冗余顺序采集小集会 over-split——IJCV 版 Yan 小集全部 ✓*,Heinly Indoor 从 152 相机/73k 点砍到 42/9k(论文仍标 ✓);PSM 相似纹理所有方法全灭;第三方小图复现被迫 m 0.7→0.1。**手机室内环扫正是"顺序+低冗余"形态**——抄它的打分范式可以,抄"删边"动作要极其克制(与判死"greedy forest 削覆盖"同病);这也支持"ambiguous 留 DB 不删数据、只控点出生"的既定取舍。
3. **文献空白是双刃剑**(v1 保留,v2 收窄):最窄窗口无先例=无反例也无背书;且 DFSfM 已占据"出生前聚合"的验证前变体——方案书须精确表述窗口边界,正确性论证只能靠九门+多跑中位纪律。
4. **camera triplets 零第三方测评/复现旁证(v2 新增,load-bearing)**:OpenAlex 4 引用、无 COLMAP/GLOMAP 主线采用、无社区讨论——论文数字不可默认可复现,采纳前必须在自有 fixture 上小 spike 实证(项目验证文化)。
5. **GLOMAP 的先例是双刃的**:它证明一图多观测 track 可行,但其机制(固定 10px 阈值+超阈整条销毁)恰含两个已判死元素——引用它时只引"下游可消化",不引其裁决方式。
6. **PR #3681 是 Breaking Change**(v1 保留):官方自标破坏性;§2.5 的断言/NBV 统计面是注入 alias 边后必须回归的确切位置(#4435 有 abort 实证)。
7. **47 号纪律**(v1 保留):host 鬼层指标 5 跑 3.6-12.3% 抽签;一切有效性结论须 ≥3 跑中位+设备端确认。
8. **学习型消歧整条判死于 ship(v2 确证)**:精度最高、唯一 τ 固定的 DG++ = NC+重 backbone;stage-1 选纯几何不是妥协而是唯一可行路径。其"元数据自动标注正负 pair"思想可借给未来用 ARKit pose 自动造室内 alias 验证集。

### 6.5 流程风险
- license-audit 线索数据截断(findings 部分缺失、verdict 段全缺):其孤证条目(如 ScanNet ToU 逐字、DFSfM aspantransformer Apple 条款)未过对抗核查轮,但均为一手文件级证据(ToS PDF 全文/raw LICENSE),按 high 置信采用;若后续找回完整数据应 diff 合并。
- 对抗核查覆盖是抽样式(每线索 2-4 条高影响 claim),非全量;未被抽中的 sweep 条目维持其自报置信度。
- v1 的"无独立对抗核查轮"风险已由本轮部分解除;剩余高影响待验项集中在 §2.2 Phase-0 实测(alias 证据流量)与 §5.2 室内域 m 标定。

---

## 7. 完整引用列表(全部于 2026-07-17 前后访问;标注★=经对抗核查 CONFIRMED/修正)

### 官方 COLMAP
| # | 来源 | URL |
|---|---|---|
| 1★ | COLMAP PR #3681(one-to-many;merge commit 3cdb5bf9,2025-11-04) | https://github.com/colmap/colmap/pull/3681 |
| 2★ | COLMAP 3.13.0 release notes(Breaking Change 条目;2025-11-07T15:43:45Z) | https://github.com/colmap/colmap/releases/tag/3.13.0 |
| 3 | COLMAP releases API(版本日期权威源) | https://api.github.com/repos/colmap/colmap/releases |
| 4 | COLMAP CHANGELOG.rst(3.12→4.1 变更核对) | https://github.com/colmap/colmap/blob/main/CHANGELOG.rst |
| 5★ | correspondence_graph.cc(4.1.0/main;duplicate 双条件+双向注释) | https://github.com/colmap/colmap/blob/4.1.0/src/colmap/scene/correspondence_graph.cc |
| 6 | sift.cc(4.1.0;cross_check 一对一边界) | https://github.com/colmap/colmap/blob/4.1.0/src/colmap/feature/sift.cc |
| 7 | incremental_triangulator.cc(4.1.0;Merge/Complete/Continue/Retriangulate) | https://github.com/colmap/colmap/blob/4.1.0/src/colmap/sfm/incremental_triangulator.cc |
| 8 | reconstruction.cc / track.h(AddObservation/MergePoints3D 语义) | https://github.com/colmap/colmap/blob/4.1.0/src/colmap/scene/reconstruction.cc |
| 9 | observation_manager.cc(num_tri_corrs 断言) + issue #4435 | https://github.com/colmap/colmap/issues/4435 |
| 10 | issue #293(2018,max_num_orientations=1 处方) | https://github.com/colmap/colmap/issues/293 |
| 11 | issue #832(2020,良性忽视定性) | https://github.com/colmap/colmap/issues/832 |
| 12 | issue #847(2020,one-to-many 需求) | https://github.com/colmap/colmap/issues/847 |
| 13 | issue #1437(2022,"no mechanisms for ambiguous matches") | https://github.com/colmap/colmap/issues/1437 |
| 14 | issue #4454(2026,duplicate-structure 活案例) | https://github.com/colmap/colmap/issues/4454 |
| 15 | sift.h(max_num_orientations=2 默认) | https://github.com/colmap/colmap/blob/main/src/colmap/feature/sift.h |
| 16 | **本地一手**:vendored correspondence_graph.cc(Aether3D-cross glomap_vendor/colmap-src,L~144-153 双条件判定,2026-07-17 grep)★ | 本地路径:~/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/colmap-src/colmap/scene/correspondence_graph.cc |
| 17 | COLMAP FAQ(用于 v1 REFUTED 条目) | https://colmap.github.io/faq.html |

### Camera triplets / 消歧经典
| # | 来源 | URL |
|---|---|---|
| 18★ | Manam & Govindu, CVPR 2024(论文 PDF;打分/Theorem 1/阈值公式 CONFIRMED) | https://ee.iisc.ac.in/cvlab/research/camtripsfm/cam_triplets_sfm.pdf |
| 19★ | IJCV 2026 扩展版(weak triples;over-split 自认) | https://link.springer.com/article/10.1007/s11263-025-02681-3 |
| 20★ | camtripsfm 项目页 + camtripsfm.zip/unifysfm.zip(.m 头 BSD-3-Clause,两线索解包核实) | https://ee.iisc.ac.in/cvlab/research/camtripsfm/ |
| 21 | Dawars/camera_triplets(第三方,license=None) | https://github.com/Dawars/camera_triplets |
| 22 | SAFUANlip/IACV_project(PoliMi 复现,m=0.1) | https://github.com/SAFUANlip/IACV_project |
| 23★ | Wilson & Snavely, ICCV 2013(blcc;小场景失效自报) | https://www.cs.cornell.edu/projects/disambig/files/disambig_iccv2013.pdf |
| 24★ | Zach et al., CVPR 2010(loop constraints,机制全 CONFIRMED) | https://people.inf.ethz.ch/pomarc/pubs/ZachCVPR10.pdf |
| 25 | Roberts et al., CVPR 2011(六数据集出处,Wayback) | http://web.archive.org/web/20160319162424/http://research.microsoft.com/pubs/147401/Roberts-CVPR11.pdf |
| 26 | Heinly et al., ECCV 2014(重建后修正;repo 无 LICENSE) | https://github.com/jheinly/sfm_duplicate_structure_correction |
| 27★ | cvg/sfm-disambiguation-colmap(license=null,全树递归核实;README 超参教训) | https://github.com/cvg/sfm-disambiguation-colmap |
| 28 | Kataria et al., 3DV 2020(reliable resectioning) | https://josephdegol.com/docs/ReliableResectioning_3DV20_Paper.pdf |
| 29 | TC-SfM(track-community,低置信未精读) | https://arxiv.org/abs/2206.05866 |

### Detector-free / Dense / PixSfM
| # | 来源 | URL |
|---|---|---|
| 30★ | zju3dv/DetectorFreeSfM(Apache-2.0;量化/refinement/同图坍缩,多条 CONFIRMED) | https://github.com/zju3dv/DetectorFreeSfM |
| 31★ | hxy-123/colmap DFSfM_modify(incremental_model_refiner=既有机器拼装,CONFIRMED) | https://github.com/hxy-123/colmap/blob/DFSfM_modify/src/exe/sfm.cc |
| 32 | DFSfM paper(ar5iv 2306.15669;quantization 原文) | https://arxiv.org/abs/2306.15669 |
| 33★ | IceTea-CV/DenseSfM-Refine(license=null;GS extension 未开源)【v2 改判 v1】 | https://github.com/IceTea-CV/DenseSfM-Refine |
| 34 | Dense-SfM paper(arXiv 2501.14277 / CVPR 2025) | https://arxiv.org/abs/2501.14277 |
| 35 | cvg/pixel-perfect-sfm(Apache-2.0;greedy forest 参考=判死同族) | https://github.com/cvg/pixel-perfect-sfm |
| 36 | zju3dv/LoFTR(代码 Apache;权重无授权+SenseTime IP 声明) | https://github.com/zju3dv/LoFTR |

### 生产系统源码
| # | 来源 | URL |
|---|---|---|
| 37 | OpenMVG tracks.hpp(整 track 销毁;MPL-2.0) | https://github.com/openMVG/openMVG/blob/develop/src/openMVG/tracks/tracks.hpp |
| 38★ | AliceVision TracksBuilder/Track.hpp + Meshroom 节点(两层默认值相反,verdict 修正) | https://github.com/alicevision/AliceVision |
| 39 | TheiaSfM track_builder.cc(first-wins;BSD-3) | https://github.com/sweeneychris/TheiaSfM/blob/master/src/theia/sfm/track_builder.cc |
| 40★ | GLOMAP track_establishment.cc/h(10px 容差保双观测,CONFIRMED;BSD-3;已归档并入 COLMAP) | https://github.com/colmap/glomap/blob/main/glomap/controllers/track_establishment.cc |
| 41 | hloc match_dense.py(聚合票决范式;Apache-2.0) | https://github.com/cvg/Hierarchical-Localization/blob/master/hloc/match_dense.py |
| 42 | cvg/LightGlue(代码+权重 Apache-2.0 明示) | https://github.com/cvg/LightGlue |
| 43 | Meshroom StructureFromMotion.py(min obs 出生门量化代价) | https://github.com/alicevision/AliceVision/blob/develop/meshroom/aliceVision/StructureFromMotion.py |

### 学习法 / 许可审计
| # | 来源 | URL |
|---|---|---|
| 44 | RuojinCai/doppelgangers(MIT 代码;权重无声明;Wikimedia attributions.json) | https://github.com/RuojinCai/doppelgangers |
| 45★ | doppelgangers25/doppelgangers-plusplus(LICENSE=CC BY-NC-SA 4.0,raw 实查) | https://github.com/doppelgangers25/doppelgangers-plusplus |
| 46 | naver/mast3r LICENSE + CHECKPOINTS_NOTICE(CC BY-NC-SA;训练集条款叠加) | https://raw.githubusercontent.com/naver/mast3r/main/LICENSE |
| 47 | ScanNet ToU PDF(一手全文:non-commercial only) | https://kaldir.vc.in.tum.de/scannet/ScanNet_TOS.pdf |
| 48 | MegaDepth 官网(衍生物 CC-BY 4.0;原图各自许可) | https://www.cs.cornell.edu/projects/megadepth/ |
| 49 | HF zju-community/efficientloftr(权重标 Apache-2.0,medium) | https://huggingface.co/zju-community/efficientloftr |
| 50 | facebookresearch/vggsfm(CC BY-NC 4.0) | https://github.com/facebookresearch/vggsfm/blob/main/LICENSE.txt |
| 51 | facebookresearch/fast3r(FAIR NC)/ dcharatan/flowmap(MIT)/ facebookresearch/vggt(商用 checkpoint 申请制) | https://github.com/facebookresearch/vggt |
| 52 | apple/ml-aspanformer(非商用;DFSfM vendoring 陷阱对照) | https://github.com/apple/ml-aspanformer |

### 社区 / 新作
| # | 来源 | URL |
|---|---|---|
| 53 | Agisoft 论坛 topic 9759(双层归因 pose/参考系) | https://www.agisoft.com/forum/index.php?topic=9759.0 |
| 54 | Epic 论坛(RealityScan banana effect,2025) | https://forums.unrealengine.com/t/misaligned-geometry-and-duplicate-structures-in-single-realityscan-component/2631008 |
| 55 | MrNeRF/Janusch Patas X 时间线(GLOMAP 赞誉等三条) | https://x.com/janusch_patas/status/1817984899967762715 |
| 56 | IMC 2024 Methods Review(arXiv 2407.03172) | https://arxiv.org/abs/2407.03172 |
| 57 | RCM, ECCV 2024(many-to-one +260%) | https://arxiv.org/abs/2407.07789 |
| 58 | MV-RoMa, CVPR 2026(fragmented tracks 问题陈述) | https://arxiv.org/abs/2603.27542 |
| 59 | Learning to Filter Outlier Edges, CVPR 2025 | https://openaccess.thecvf.com/content/CVPR2025/html/Damblon_Learning_to_Filter_Outlier_Edges_in_Global_SfM_CVPR_2025_paper.html |
| 60 | GLOMAP paper(ECCV 2024;track=验证后串接) | https://arxiv.org/abs/2407.20219 |
| 61 | ArchSym(2026;对称显式建模前瞻) | https://arxiv.org/abs/2604.22202 |
| 62 | IUI 2025 User-Guided Correction(人在环重建后修正) | https://dl.acm.org/doi/10.1145/3708359.3712141 |
| 63 | SfM taxonomy 综述(2025;歧义自动处理列为 open problem) | https://arxiv.org/abs/2505.15814 |
| 64 | DetectorFreeSfM issue #39(算力实测) | https://github.com/zju3dv/DetectorFreeSfM/issues/39 |
