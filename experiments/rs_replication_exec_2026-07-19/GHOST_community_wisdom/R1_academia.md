# R1 学术界:track 碎片化 / 重复点 / 同site竞争裁决 — 社区智慧普查

- 日期:2026-07-18
- 范围:只覆盖任务书指定的**未查过角度**(①track fragmentation/merging 文献 ②低视差出生策略 ③duplicate 3D points/双面抑制 ④近两年新系统的 track 冲突处理 ⑤同site竞争裁决配方)。已查过项(COLMAP Merge/Complete/Retriangulate、GLOMAP track_establishment、DSO immature、ORB-SLAM found-ratio、PMVS/PixSfM/DFSfM/3DGS/Merrell/BundleFusion、PR#3681、Doppelgangers)不重复。
- 证据分级:**强**=论文原文/源码逐行;**中**=官方 README/检索摘要/二手引用;**弱**=博客/论坛转述。
- 许可红线:NC/AGPL/学术限制 = 🔴(思想可参考,代码不可 vendor)。

## TL;DR(对二阶段裁决器的三条主发现)

1. **⑤有比"相对支持比裁输家"更保数据的公开配方:ORB-SLAM2 的 Fuse + Replace(merge-and-transfer)** — 同 site 竞争时观测数多者胜,但输家的观测**转移给赢家**而非丢弃,且逐观测过几何 gate 后才转移(不连坐)。源码级配方,直接回应 E9 conflict_mv 连坐误杀(真地板 -42%)的病根。
2. **②"出生前裁决"有完整文献谱系背书**:SVO 深度滤波(收敛才出生)→ Civera inverse depth(低视差不删、换参数化 undelayed 出生)→ DSM(出生时先查 reobservation,复用已有点,构造性防重复出生)。DSM 是与我们"碎 track 重复出生"病理最对口的系统级先例。
3. **④2025-2026 学界共识正在转向"track 在多视图层面直接产,不走 pairwise 链"**(VGGSfM / Dense-SfM / MV-RoMa / TAP-for-SfM)。Dense-SfM 白纸黑字承认 dense matcher 的碎 track 通病(平均 track 长仅 2.11),解法是"用重建反哺 track 延长"而非裁决。可 ship 许可几乎全 🔴(NC),但思想与我们"产跨边"方向互为印证。

---

## ① Track fragmentation / merging / linking 文献

### 1.1 Moulon & Monasse "Unordered feature tracking made fast and easy"(CVMP 2012)+ OpenMVG tracks.hpp 【强:论文+源码】
- 机制:Union-Find 把两视图匹配传递闭包成多视图 track,O(n·α(n)) 准线性;2600 图 / 4100 万对匹配实测,比先前方法快至 4×。
- **冲突处理(源码逐行核实)**:`Filter()` 中 "a track cannot list many times the same image index" — 同一 track 出现同图两个 feature → `problematic_track_id.insert(track_id)` → **整条 track 作废**(UF 树 parent 置 max uint32_t)。
- 许可:OpenMVG = **MPL-2.0**(文件头核实),许可干净可抄。
- 对我们:这是"连坐杀整条"路线的祖师爷 — 证明我们 conflict_mv 的连坐不是孤例,但 OpenMVG 场景是无序图集(冲突≈误匹配污染),我们的场景是视频流碎 track(冲突≈同一物理点的两段真 track),**同一处方对不同病**。裁决器不应照抄这条。
- 出处:http://imagine.enpc.fr/~moulonp/publis/featureTracking_CVMP12.pdf ; https://github.com/openMVG/openMVG (src/openMVG/tracks/tracks.hpp)

### 1.2 Theia TrackBuilder 【强:源码】
- 机制(track_builder.cc 逐行核实):同样 Union-Find(ConnectedComponents),但冲突处理不同 — "Do not add the feature if the track already contains a feature from the same image":`InsertIfNotPresent` 失败 → **只丢弃后到的冲突 feature(FCFS 先到先得),track 其余部分保留**,计数进 `num_inconsistent_features` 日志。另有 `max_track_length` 把超长 track 拆分(文档:过长 track 极可能含 outlier)。
- 许可:TheiaSfM = New BSD(repo license.txt;LICENSE 文件路径 404,按 repo 惯称 BSD-3,**未逐字复核**)【中】。
- 对我们:比 OpenMVG 温和(不连坐),但**无裁决**——保谁全看插入顺序,是偶然性配方。价值在于证明"one-to-many 冲突可以逐观测处理而非逐 track 处理"这个粒度是工程主流之一。
- 出处:https://github.com/sweeneychris/TheiaSfM/blob/master/src/theia/sfm/track_builder.cc ; http://theia-sfm.org/sfm.html

### 1.3 Multi-way matching / cycle consistency 族(碎 track 的全局合并理论)【中:论文摘要层】
- 谱系:Permutation Synchronization(Pachauri et al., NIPS 2013,特征分配矩阵谱分解一次解出全局一致匹配)→ MatchALS(Zhou/Zhu/Daniilidis ICCV 2015,低秩交替最小化)→ QuickMatch(Tron et al. ICCV 2017,密度聚类,无需两两匹配全图)→ HiPPI(Bernard et al. ICCV 2019,高阶投影幂迭代,可扩展)→ 分布式 QuickMatch(IJRR 2020)。
- 核心思想:**cycle consistency(环路复合=恒等)是判定"两条 track 是否同一物理点"的全局判据** — 恰是我们窗口匹配缺失的"跨边"在数学上的名字。碎 track 合并=把观测按一致性聚类,天然产出跨边。
- 许可:算法=公开论文数学,自实现无许可问题;QuickMatch 参考实现许可未核【弱】。
- 对我们可抄性:**中高**。可做 finalize 离线后处理(在 BA 前对 track 集合跑一次一致性合并),与现有管线正交;谱方法成本在我们 ~10^5 特征量级可控。风险:合并错误=把两个不同物理点焊死,须配 3D 距离 + 重投影 gate(见 ⑤ ORB-SLAM gate 配方)。
- 出处:https://papers.nips.cc/paper/5128-solving-the-multi-way-matching-problem-by-permutation-synchronization ; https://arxiv.org/pdf/1505.04845 ; https://openaccess.thecvf.com/content_ICCV_2019/papers/Bernard_HiPPI_Higher-Order_Projected_Power_Iterations_for_Scalable_Multi-Matching_ICCV_2019_paper.pdf ; https://journals.sagepub.com/doi/full/10.1177/0278364920917465

---

## ② 低视差 / 退化三角化的出生策略(DSO 之外)

### 2.1 SVO 深度滤波(Forster et al.;滤波模型出自 Vogiatzis & Hernández, IVC 2011)【强:论文+官方源码】
- 机制:每个新特征起一个递归贝叶斯深度滤波器(Gaussian×Uniform 混合,显式建模 outlier 测量),初始化在平均场景深度、大不确定度;**只有滤波器收敛(`seed_convergence_sigma2_thresh` 方差阈值)才把 3D 点插入地图**,需要多次测量支持。
- 许可:rpg_svo = **GPL-3** 🔴(代码);滤波公式=论文公开,自实现干净。
- 对我们:这是"出生前裁决"的**概率化升级版** — 支持不是计数而是 inlier-ratio 后验;低视差点天然收敛慢=自动延迟出生,不需要显式视差角门。与 E9 的存在性结论(出生前裁决塌 -96%)同方向,提供了"裁决量应该是什么"的第二种答案(后验方差 vs 相对支持比)。
- 出处:https://rpg.ifi.uzh.ch/docs/TRO16_Forster-SVO.pdf ; https://github.com/uzh-rpg/rpg_svo/blob/master/svo/include/svo/depth_filter.h

### 2.2 DSM — Direct Sparse Mapping(Zubizarreta, Aguinaga, Tardós, Montiel;IEEE T-RO 2020)【强:论文】
- 机制:**与我们病理最对口的系统级先例**。指出既有光度 BA 系统(DSO 系)用临时地图+边缘化旧关键帧,重访同一区域时**无法识别 reobservation → 同一表面重复出生新点**;DSM 保留持久全局地图,重访时**检测 map point reobservation 并复用已有点**,构造性防止点重复,EuRoC 上直接法最高精度。
- 许可:https://github.com/jzubizarreta/dsm = **GPL-3** 🔴(代码);机制=论文公开。
- 对我们:文献级证实两件事:(a) "同一表面点重复出生"是有名有姓的已知病,病根=**出生时不查已有点**,与 dossier "缺 alias 跨边非缺合并机制"的定性完全一致;(b) 正解是把裁决提到出生时(reobservation query:新种子先投影到已有地图找归属),而不是出生后清理。stage-1 "产跨边+定出生"的最小形态与 DSM 的 pattern 同构。
- 出处:https://arxiv.org/abs/1904.06577 ; https://github.com/jzubizarreta/dsm

### 2.3 Civera/Davison/Montiel inverse depth + linearity index(IEEE T-RO 2008)【强:论文】
- 机制:低视差特征不删、不延迟,用 **inverse depth 参数化 undelayed 出生**(测量方程高度线性,大深度不确定度可安全表示);**linearity index** 自动判定何时收敛到可转 XYZ。低视差点可以长期停留在 inverse-depth 态而不污染地图。
- 许可:纯公式,无许可问题。
- 对我们:第三种出生哲学 — **不裁决、换表示**:让低视差点以"射线+粗深度"存在,不参与表面竞争,收敛后才有资格成为表面点。若裁决器要留"不确定区"(而非二选一杀/留),这是理论依据。
- 出处:https://www.doc.ic.ac.uk/~ajd/Publications/civera_etal_tro2008.pdf

### 2.4 ParallaxBA(Zhao, Huang et al., IJRR 2015)【中:论文摘要+官方 PDF】
- 机制:BA 内改用 parallax angle 参数化(anchor 两帧+视差角),证明 XYZ/inverse-depth 在低视差下导致法方程病态、梯度消失,视差角参数化收敛性/精度全面优于 SBA/sSBA/g2o。
- 许可:代码在 OpenSLAM(许可未核,OpenSLAM 多为 GPL/学术)【弱】;公式公开。
- 对我们:与 2.3 同路线的 BA 侧版本 — 低视差 track **无害化**而非删除,契合"质量无损"北极星。但改 BA 参数化是大手术,violates "参数全抄认证配置",只作理论储备,不建议动。
- 出处:https://journals.sagepub.com/doi/abs/10.1177/0278364914551583 ; https://opus.lib.uts.edu.au/bitstream/10453/35549/1/ParallaxAngleParametrization_IJRR_20140825.pdf

### 2.5 LDSO(本次确认无新增)【中】
- LDSO = DSO 点管理原样 + 闭环(特征化部分点做词袋);点出生策略与 DSO immature 无差异,**不必再挖**。

---

## ③ Duplicate 3D points / 点云 consolidation / 双面抑制

### 3.1 ORB-SLAM2 ORBmatcher::Fuse + MapPoint::Replace(重复地图点融合)【强:源码逐行】
- 注:已有记忆只覆盖 found-ratio 淘汰;**Fuse/Replace 是另一条机制,此前未审**。
- 机制(ORBmatcher.cc 核实):LocalMapping::SearchInNeighbors 把当前关键帧地图点投影到一二阶邻居帧,发现落点处已有别的 MapPoint(= 同 site 两个点竞争)时:
  ```cpp
  if(pMPinKF->Observations()>pMP->Observations())
      pMP->Replace(pMPinKF);
  else
      pMPinKF->Replace(pMP);
  ```
  **观测数多者胜;输家 Replace = 其全部观测/引用转移给赢家,数据不丢**。
- 融合前逐观测几何 gate(全部源码核实):深度为正 → 图像内 → 尺度距离带 `[minDistance,maxDistance]` → 视角 <60°(`PO.dot(Pn)<0.5*dist3D`)→ 描述子距离 `TH_LOW=50` → (双目)重投影 χ² `e2*invSigma2 ≤ 7.8`。
- 许可:ORB-SLAM2 = **GPL-3** 🔴(代码不可 vendor);机制/阈值结构可抄(自实现)。
- 对我们:**⑤的最强候选配方**,详见 ⑤ 汇总表。
- 出处:https://github.com/raulmur/ORB_SLAM2/blob/master/src/ORBmatcher.cc ; https://github.com/raulmur/ORB_SLAM2/blob/master/src/LocalMapping.cc

### 3.2 Keller et al. 2013 "Real-time 3D reconstruction in dynamic scenes using point-based fusion"【中:论文引用链】
- 机制:surfel = 位置+法线+半径+confidence+时间戳;新测量在投影 5×5 窗口内找**位置/法线相容**的已有 surfel → 相容则加权融合(confidence 累积),不相容才新生;confidence 超阈值(σ_conf≈5)才算 stable、才参与表面预测 — **"试用期"点不污染输出**。
- 许可:论文机制公开;各实现许可各异(ElasticFusion 继承此配方,Imperial College **非商用** 🔴【中,未逐字复核 license 文件】)。
- 对我们:合并式(加权平均)而非裁决式(选边)。**注意**:对我们 2-3.5cm 双壳,加权平均=把两层揉成中间层,均值有偏 — 不如裁决式;但 confidence 试用期思想(新点先隔离观察)可与出生前裁决组合。
- 出处:https://www.thomaswhelan.ie/Whelan16ijrr.pdf(§surfel fusion 描述);https://mewangcl.github.io/pubs/TOGHRBFFusion.pdf(引用链)

### 3.3 WLOP / CGAL point set consolidation【中】
- 机制:密度加权局部最优投影 + 排斥项,把噪声点云投影成均匀无外点分布(CGAL `wlop_simplify_and_regularize_point_set()`)。
- 许可:CGAL Point Set Processing = **GPL-3** 🔴(或商业双许可)。
- 对我们:**判不适用** — WLOP 是有损平滑+重采样:双壳会被均匀化成中间面而非选出真面,且输出不是原始观测点(违反"点云全量交付/质量无损")。记录在案防止后续绕路。
- 出处:https://doc.cgal.org/latest/Point_set_processing_3/index.html

### 3.4 Directional TSDF(Splietker & Behnke, IROS 2019)【中】
- 机制:TSDF 按表面朝向分 6 方向存储,反向表面分离,配改造 Marching Cubes — 解决**薄结构两侧互相抹除/伪面**。
- 许可:AIS-Bonn/DirectionalTSDF 基于 InfiniTAM v3,repo 标 "Other"(InfiniTAM v3 = Oxford 学术非商用)🔴。
- 对我们:**病理不同,防混淆记录** — 它治的是"一片薄墙的正反两面"(法线相反),我们的双层地板是"同一朝向的重复壳"(法线相同、深度差毫米级)。方向分离对我们无效;但反证:fusion 侧无法治我们的病,必须在 SfM/track 层治,支持出生前裁决路线。
- 出处:https://arxiv.org/abs/1908.05146 ; https://github.com/AIS-Bonn/DirectionalTSDF

---

## ④ 近两年新系统对 track 冲突的裁决

### 4.1 VGGSfM(Meta, CVPR 2024)【强:LICENSE 文件逐字核实】
- track 机制:query point + transformer tracker,**一次性跨全部帧直接预测 track(含逐点置信椭圆)**,不做 pairwise 链接 → 碎 track 问题被构造性绕开(不存在"两段链在窗口边界断开"的病)。query 特征可混 sp/sift/aliked。
- 许可:**CC BY-NC 4.0** 🔴(LICENSE.txt 逐字核实:"for NonCommercial purposes only")。VGGT 同属 Meta 谱系(许可同类,未逐字核)。
- 对我们:代码不可用;**思想=track 出生即多帧**,与 dossier "产跨边"同构 — 跨边不是修补出来的,是 track 生成机制原生的。
- 出处:https://github.com/facebookresearch/vggsfm ; https://arxiv.org/pdf/2312.04563

### 4.2 Dense-SfM(Lee et al., CVPR 2025)【强:论文原文】
- **白纸黑字承认碎 track 通病**:"semi-dense and dense matching often results in fragmentary feature tracks"(DKM/RoMa 原始匹配平均 track 长仅 **2.11**,几乎全是 2-view — 和我们"鬼层点多为 2-view 碎 track"同一张病历)。
- 解法:不裁决、不量化合并,而是 **track extension via Gaussian Splatting** — 用中间重建把 3D 点投影到其它帧,可见性得分 >εv 即把该帧收编进 track(2.11→4.97,量化法只有 3.23),再 kernelized 多视图 refine + BA。
- **无显式 merge/冲突裁决**(论文明说只有几何验证);低视差未特殊处理;code/license 未公布。
- 对我们:第三条治碎 track 的路 — "以重建反哺 track"(与 COLMAP retriangulate 的区别:按投影可见性收编观测,不是重新三角化)。我们的 plane-sweep 已认证平面恰好是最强可见性先验,此思路与已有 planesweep 战果可组合。
- 出处:https://arxiv.org/html/2501.14277v1 ; https://openaccess.thecvf.com/content/CVPR2025/papers/Lee_Dense-SfM_Structure_from_Motion_with_Dense_Consistent_Matching_CVPR_2025_paper.pdf

### 4.3 MV-RoMa(CVPR 2026)【中:摘要】
- 机制:multi-view encoder 拿 pairwise 匹配当几何先验,pixel-wise attention 直接输出**多视图一致对应**,后处理整合成高质量 track 进 SfM。
- code/license 未见(项目页 icetea-cv.github.io/mv-roma/)。
- 对我们:趋势佐证第二票 — 匹配器本身多视图化,pairwise→track 的"链接"步骤正在被学界取消。
- 出处:https://arxiv.org/abs/2603.27542

### 4.4 TAP-for-SfM 族:DATAP-SfM / CoTracker / TAPIR / LocoTrack【中】
- DATAP-SfM(arXiv 2411.13291):明说 "point trajectory construction based on pairwise optical flow matching will undoubtedly bring long-term cumulative errors",用 dynamic-aware TAP 长时点追踪直接产 track。
- 许可格局(co-tracker README 许可段,中证据):CoTracker = **CC BY-NC** 🔴;**TAPIR(TAP-Vid)与 LocoTrack = Apache-2.0** ✅ — 若未来想让"跨边"由 tracking 产生(视频流场景我们天然有序!),Apache 阵营是唯一许可干净的学习法候选。LocoTrack 自称比 SOTA 快 ~6×,移动端可行性未知须实测。
- FlowMap(3DV 2025)= **MIT** ✅(LICENSE 逐字核实);但它是"flow/track 监督下梯度下降求位姿+深度",无 track 裁决机制,对裁决器无直接可抄物。
- MASt3R-SfM(3DV 2025)= **CC BY-NC-SA 4.0** 🔴(checkpoints 还叠加训练集限制,mapfree 尤其严),只作思想参考。
- 出处:https://arxiv.org/html/2411.13291v1 ; https://github.com/facebookresearch/co-tracker ; https://cvlab-kaist.github.io/locotrack/ ; https://github.com/dcharatan/flowmap ; https://github.com/naver/mast3r

---

## ⑤ 同site竞争裁决:公开配方全谱对比(vs dossier§5.1 相对支持比)

| 配方 | 出处 | 裁决量 | 输家命运 | 粒度 | 对连坐误杀的免疫性 |
|---|---|---|---|---|---|
| 连坐杀整条 | OpenMVG Filter()【强】 | 冲突存在性 | 整条删 | track | 无(=我们 conflict_mv 的病)|
| FCFS 丢观测 | Theia TrackBuilder【强】 | 插入顺序 | 只删冲突观测 | 观测 | 高但无原则(偶然性)|
| 重投影兼容合并 | COLMAP Merge(E2 已审) | 合并后重投影 | 被合并 | track | 中 |
| **观测数胜者 + 转移** | **ORB-SLAM2 Fuse/Replace【强】** | **Observations() 计数** | **观测转移给赢家,不丢数据** | track,但 gate 逐观测 | **高:六重 gate 逐观测验证后才转移** |
| 出生前后验收敛 | SVO/Vogiatzis【强】 | inlier-ratio 后验方差 | 不出生(种子丢弃) | 种子 | 高(根本不产生竞争)|
| 出生时 reobservation 查询 | DSM【强】 | 光度重观测检测 | 不出生(复用已有点) | 种子 | 高(根治)|
| 相容加权融合 + 试用期 | Keller 2013【中】 | 位置/法线相容 | 融进均值 | surfel | 高,但均值有偏(双壳→中间层)|
| 支持数票决 | Merrell(已审)/MVS fusion | 一致视图数 | 删 | 像素/点 | 中 |
| 相对支持比(我们的) | dossier§5.1 | 同site支持比 | 裁输家整条 | track | 取决于是否逐观测 |

**裁决器可抄结论(按优先序)**:
1. **把 ORB-SLAM 的 "merge-and-transfer" 嫁接到相对支持比上**:支持比只用来**定胜负**,不用来**定生死** — 输家 track 的观测逐个过 gate(重投影 χ²、尺度带、描述子距离;阈值结构照抄 3.1,数值按我们 'o' 认证口径重标)后**转移给赢家再进 BA**。这比"裁输家删除"多保一层数据(质量无损契合),且构造性避免 E9 连坐误杀:gate 不过的观测才丢,过的归赢家。
2. **DSM pattern 背书出生时裁决**:新种子出生前先向同 site 已有 track 做归属查询(= 我们 stage-1 "定出生"),竞争根本不产生。文献证明这条路在直接法 SLAM 已走通并拿到 SOTA 精度。
3. **cycle consistency(1.3)是"同一物理点"的全局判据**,可作为支持比之外的第二裁决特征:两条候选 track 若经第三帧观测能环路闭合,是"同点碎片"的强证据(该合并);闭合失败则是"真两点"(都保留)。直接回应"鬼层不自愈=缺 alias 跨边"。
4. **不要抄**:OpenMVG 连坐(同病)、WLOP/surfel 均值融合(双壳会揉成有偏中间层)、方向分离 TSDF(病理不对口)。

---

## 许可速查表

| 系统/代码 | 许可 | 可用性 |
|---|---|---|
| OpenMVG | MPL-2.0【强:文件头】 | ✅ 可抄可 vendor |
| TheiaSfM | New BSD(repo license.txt,未逐字复核)【中】 | ✅(复核后) |
| FlowMap | MIT【强:LICENSE 逐字】 | ✅ |
| TAPIR / TAP-Vid / LocoTrack | Apache-2.0【中:co-tracker README 许可段】 | ✅(复核后) |
| ORB-SLAM / ORB-SLAM2 | GPL-3【中:repo 惯称】 | 🔴 代码;机制自实现 ✅ |
| rpg_svo | GPL-3【中】 | 🔴 代码;公式自实现 ✅ |
| DSM (jzubizarreta/dsm) | GPL-3【中】 | 🔴 代码;机制自实现 ✅ |
| CGAL Point Set Processing | GPL-3/商业双许可【中】 | 🔴 |
| VGGSfM | CC BY-NC 4.0【强:LICENSE 逐字】 | 🔴 |
| CoTracker | CC BY-NC【中:README】 | 🔴 |
| MASt3R / MASt3R-SfM | CC BY-NC-SA 4.0(+数据集叠加限制)【中】 | 🔴 |
| ElasticFusion | 非商用(Imperial)【中,未逐字复核】 | 🔴 |
| DirectionalTSDF(InfiniTAM v3 底座) | "Other"/学术【中】 | 🔴 |
| Dense-SfM / MV-RoMa | code 未公布 | 思想参考 |
| Civera inverse depth / ParallaxBA / multi-way matching 公式 | 论文公开数学 | ✅ 自实现 |

## 参考文献(全部一手 URL)

1. Moulon & Monasse, CVMP 2012 — http://imagine.enpc.fr/~moulonp/publis/featureTracking_CVMP12.pdf
2. OpenMVG tracks.hpp — https://github.com/openMVG/openMVG
3. TheiaSfM track_builder.cc — https://github.com/sweeneychris/TheiaSfM/blob/master/src/theia/sfm/track_builder.cc
4. Pachauri et al., Permutation Synchronization, NIPS 2013 — https://www.semanticscholar.org/paper/ab63735bb09ab96916830a8fb563049bc10c420d
5. Zhou et al., MatchALS, ICCV 2015 — https://arxiv.org/pdf/1505.04845
6. Bernard et al., HiPPI, ICCV 2019 — https://openaccess.thecvf.com/content_ICCV_2019/papers/Bernard_HiPPI_Higher-Order_Projected_Power_Iterations_for_Scalable_Multi-Matching_ICCV_2019_paper.pdf
7. Serlin et al., Distributed QuickMatch, IJRR 2020 — https://journals.sagepub.com/doi/full/10.1177/0278364920917465
8. Forster et al., SVO, T-RO 2016 — https://rpg.ifi.uzh.ch/docs/TRO16_Forster-SVO.pdf
9. rpg_svo depth_filter.h — https://github.com/uzh-rpg/rpg_svo/blob/master/svo/include/svo/depth_filter.h
10. Zubizarreta et al., Direct Sparse Mapping, T-RO 2020 — https://arxiv.org/abs/1904.06577 ; https://github.com/jzubizarreta/dsm
11. Civera et al., Inverse Depth Parametrization, T-RO 2008 — https://www.doc.ic.ac.uk/~ajd/Publications/civera_etal_tro2008.pdf
12. Zhao et al., ParallaxBA, IJRR 2015 — https://journals.sagepub.com/doi/abs/10.1177/0278364914551583
13. ORB_SLAM2 ORBmatcher.cc / LocalMapping.cc — https://github.com/raulmur/ORB_SLAM2
14. Whelan et al., ElasticFusion, IJRR 2016(surfel fusion 描述)— https://www.thomaswhelan.ie/Whelan16ijrr.pdf
15. CGAL Point Set Processing — https://doc.cgal.org/latest/Point_set_processing_3/index.html
16. Splietker & Behnke, Directional TSDF, IROS 2019 — https://arxiv.org/abs/1908.05146 ; https://github.com/AIS-Bonn/DirectionalTSDF
17. VGGSfM — https://github.com/facebookresearch/vggsfm ; https://arxiv.org/pdf/2312.04563
18. Lee et al., Dense-SfM, CVPR 2025 — https://arxiv.org/html/2501.14277v1
19. MV-RoMa, CVPR 2026 — https://arxiv.org/abs/2603.27542
20. DATAP-SfM — https://arxiv.org/html/2411.13291v1
21. CoTracker — https://github.com/facebookresearch/co-tracker ; LocoTrack — https://cvlab-kaist.github.io/locotrack/
22. FlowMap — https://github.com/dcharatan/flowmap
23. MASt3R / MASt3R-SfM — https://github.com/naver/mast3r ; https://arxiv.org/pdf/2409.19152
