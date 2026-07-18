# R2 — COLMAP 社区 + SLAM fusion 谱系深挖(鬼层/双层面壳)

日期:2026-07-18(执行)/ 归档于 rs_replication_exec_2026-07-19
范围铁律:只写本目录;不改生产;不 commit。
证据分级:【强】=论文/源码/官方文档逐字;【中】=官方论坛/维护者评论/一手转述;【弱】=二手转述/推断。
许可标注:✅=商用安全;🔴=GPL/NC 等 ship 阻断(判据数值可萃取,代码不可 vendor);⚪=专有(仅机制参考)。

去重边界(本轮**不**重复调查,只引用):COLMAP Merge/Complete/Retriangulate 机制(E2 审计)、GLOMAP track_establishment、PR#3681 谱系、DSO immature、ORB-SLAM found-ratio(仅作上下文)、PMVS/PixSfM/DFSfM/3DGS/Merrell/BundleFusion、Doppelgangers。

---

## 1. COLMAP 社区:issues / PR 考古(除 #3681 外)

### 1.1 issue #80 「Redundant 3D points with different IDs」(2017)【中】
- 病症与我们完全同构:points3D.txt 里坐标完全相同(0.46874, 4.27221, 6.06381)但 ID 不同、track 不同的冗余 3D 点。
- 维护者 ahojnnes 原话:**"You are right with your observations. This is intended and shouldn't be a problem in practice."** 直接关闭。
- 结论:同一物理点多条 track 共存是 COLMAP **设计意图**,上游从未把它当病。我们把它当病(双层面壳)是因为下游是点云交付而非位姿交付——用途分歧,不是我们理解错。
- https://github.com/colmap/colmap/issues/80

### 1.2 issue #3097 「track split 疑问」(2025)【中】——社区诉求与我们的 stage-1 一字不差
- 提问者怀疑:**"a single 3D point appearing as multiple reconstructed points in close proximity could result from views being categorized into separate groups, each forming distinct tracks"**——即我们的碎 track 重复出生病理,社区独立观测到。
- 提问者向上游明确请求:**"provide an option to force one group of matched 2d points only generate one single track"**——即 site 级"一物理点一 track"约束,和我们 stage-1 最小形态(产跨边+定出生)同方向。**该请求未被实现,issue 于 2026-02 被 ahojnnes 关闭。**
- 第三方 Richard-coder 评论:**"CompleteAndMergeTracks can partially address this issue, but it cannot fully resolve it... Currently, there is no perfect solution to completely resolve this issue."**
- 结论:上游明确不打算做出生前裁决;CompleteAndMergeTracks 只是部分补救(与 E2 审计结论一致)。**社区无现成补丁可抄,stage-1 自研的必要性再次坐实。**
- https://github.com/colmap/colmap/issues/3097

### 1.3 PR #2145 「Incremental Model Refiner」(tsattler,open)【中】——社区最接近的补救模式
- 作者 tsattler(Sattler 本人):**"For a given number of iterations, it, in each iteration, runs bundle adjustment and then completes and merges tracks."**
- 即:**迭代 {BA → CompleteAndMergeTracks} 循环**直至收敛,而不是单次 merge。适用场景 = 初始位姿不准的 refinement。ahojnnes 已 approve(2025-04),建议改名 model_refiner,尚未 merge。
- 可萃取:merge 是位姿依赖的——位姿每变好一轮,原本超过合并阈值的碎 track 会重新可合并。单次 merge 失败 ≠ merge 路线失败。若二阶段裁决器走"合并"臂,应设计成与 BA 交替迭代。
- https://github.com/colmap/colmap/pull/2145

### 1.4 其他命中(低相关,记录避免重挖)
- #4435:GLOMAP retriangulation 在 duplicate correspondence check 上 abort(closed)——PR#3681 谱系的边界 bug,与 vendored 自注入 one-to-many 时须注意的断言同源。【中】
- #471:model_merger 后 BA 震荡发散——模型级合并病,非 track 级。【中】
- cvg/sfm-disambiguation-colmap:治的是**场景级重复结构**(对称/复制建筑导致错误关联),与我们的 site 级重复出生是不同病,勿混。✅(代码 Apache,未逐字核)【中】
- GitHub issue 搜索 "two surfaces / second surface / thick wall" 在 colmap repo **零命中**(仅误中 #482)——双层面壳作为病名在 COLMAP 社区不存在,进一步证明上游视角里这不是病。【中】

---

## 2. Track 构建冲突处理:五家 SfM 库源码级对比

同图多特征落进一条 track(我们的 site 冲突)时,各家怎么办:

| 库 | 机制 | 冲突处置 | 裁决依据 | 许可 |
|---|---|---|---|---|
| OpenSfM | UnionFind → `_good_track()` | **整条 track 丢弃**(`len(images) != len(set(images))` → False) | 无裁决,直接弃 | ✅ BSD-2(本轮逐字核实) |
| OpenMVG | UnionFind → `TracksBuilder::Filter()` | **整条 track 丢弃**(`insert(image_id).second==false` → problematic,置 max() 标记不导出) | 无裁决,直接弃 | ✅ MPL-2.0【中,惯例值未逐字核】 |
| Theia | ConnectedComponents → `TrackBuilder` | **逐观测丢弃**:`InsertIfNotPresent(&view_ids,...)` 失败的观测被 `continue` 跳过,track 保留 | **先到先得**(插入顺序,任意性,无支持度) | ✅ BSD-3【中】 |
| COLMAP | 增量三角化 + Merge/Complete | **允许同物理点多 track 共存**(#80 官方定性 intended);相容性拆分产新 track(E2 已审) | 事后部分补救 | ✅ BSD-3(vendored 在用) |
| hloc | 无自建层 | **全权委托 pycolmap**:`pycolmap.triangulate_points(...)`,仅在匹配层做 `verify_matches`(ransac max_num_trials=20000, min_inlier_ratio=0.1)与 min_match_score 过滤 | 同 COLMAP | ✅ Apache-2.0【中】 |

【强】OpenSfM/Theia/OpenMVG/hloc 均为本轮源码逐字提取(tracking.py / track_builder.cc / tracks.hpp / triangulation.py)。

**结构性洞见**:SfM 库谱系对 site 冲突只有两种策略——"整条丢"(OpenSfM/OpenMVG,丢真点)与"先到先得"(Theia,任意裁决)。**没有任何一家做基于支持度的裁决**。dossier §5.1 相对支持比裁决器在 SfM 库谱系无先例(与 07-17 记忆"site 级出生前裁决无先例"从另一谱系交叉确认)。有支持度裁决的先例在 SLAM 谱系(下节)。

---

## 3. SLAM map point fusion 深挖 —— "同病已验证解"的最成熟谱系

### 3.1 ORB-SLAM2:完整判据链(全部【强】,源码逐字)🔴 GPLv3

#### (a) 出生门 CreateNewMapPoints(LocalMapping.cc)
- 邻域:`nn=10`(stereo)/ `nn=20`(mono)个最佳共视 KF。
- **低视差出生禁令**:`ratioBaselineDepth = baseline/medianDepthKF2; if(<0.01) continue;`——基线/场景中位深比 <1% 直接不三角化。**这正是掐我们 σ_depth 毫米级深度噪声壳的第一道闸**(我们的病 = 低视差点出生后叠成第二层;ORB-SLAM 在出生前就按对拒绝)。
- 视差角:`cosParallaxRays = ray1·ray2/(|ray1||ray2|)`,须 `cosParallaxRays<cosParallaxStereo && >0`。
- 双侧正深度 + 双侧重投影卡方:mono `err² > 5.991·σ²` 拒,stereo `> 7.8·σ²` 拒。
- 尺度一致性:`ratioDist·ratioFactor<ratioOctave || ratioDist>ratioOctave·ratioFactor` 拒,`ratioFactor = 1.5×scaleFactor`。

#### (b) 出生后立即融合 SearchInNeighbors(LocalMapping.cc)——每个新 KF 都跑,不是回环才跑
- 目标 KF:一阶共视 nn 个(10/20)+ 每个一阶邻的 5 个二阶邻。
- **双向 Fuse**:当前 KF 的点投到邻 KF(forward)+ 邻 KF 的点投回当前 KF(backward)。
- th 未显式传,头文件默认 **th=3.0**(本轮逐字核:`int Fuse(KeyFrame* pKF, const vector<MapPoint*>& vpMapPoints, const float th=3.0);`)。
- 融合后:`ComputeDistinctiveDescriptors()` + `UpdateNormalAndDepth()` + `UpdateConnections()`。

#### (c) Fuse 判据全链(ORBmatcher.cc)——按序七道门
1. 相机系深度 >0;
2. 投影在图像内 `IsInImage(u,v)`;
3. 距离在尺度金字塔不变带内(GetMax/MinDistanceInvariance);
4. **视角 <60°**:`PO.dot(Pn) < 0.5·dist3D` 拒(0.5=cos60°);
5. **搜索半径 = th × mvScaleFactors[nPredictedLevel]**(尺度自适应:粗层半径大);
6. 描述子门:`bestDist ≤ TH_LOW = 50`(256-bit ORB 的 Hamming,≈20%);
7. 重投影卡方(σ² 加权):mono `e²·invSigma² > 5.99` 拒,stereo `> 7.8` 拒。

#### (d) 撞点裁决——**支持度定赢家,输家不删而是并**
```cpp
if(pMPinKF->Observations() > pMP->Observations())
    pMP->Replace(pMPinKF);
else
    pMPinKF->Replace(pMP);
```
- **赢家 = Observations() 多者**(绝对支持数对比;dossier §5.1 相对支持比的"绝对版"先例)。
- `MapPoint::Replace`(本轮逐字):输家的**全部观测转移**给赢家(`IsInKeyFrame` 查重后 `ReplaceMapPointMatch`+`AddObservation`),`nvisible/nfound` 计数合并(`IncreaseFound/IncreaseVisible`),重算最优描述子,再 `EraseMapPoint(this)`。
- **对 E9 连坐误杀的直接启示:该谱系从不"杀观测",只"并观测"。**我们 conflict_mv 臂 -42% 真地板 = 把输家整条处决;ORB-SLAM 的输家观测全数转入赢家 track,物理信息零损失。误杀=0 红线在该设计下是构造性满足的。

#### (e) 回环级融合 SearchAndFuse(LoopClosing.cc)
- `matcher.Fuse(pKF, cvScw, mvpLoopMapPoints, 4, vpReplacePoints)`——**th=4.0**,比局部 3.0 宽,因为 Sim3 校正后残余误差更大。
- 两阶段:先并行记录 vpReplacePoints,后在 `mMutexMapUpdate` 锁下批量 `Replace`。
- 萃取:**融合半径应随位姿不确定度分级**——位姿新鲜/准 → 窄半径;经过大校正/漂移场景 → 宽半径。我们二阶段裁决器若在 BA 前后各跑一次,阈值不应同值。

#### (f) 出生后试用期 MapPointCulling(上下文,found-ratio 已在既有审计)
- `GetFoundRatio()<0.25` 剔;出生 ≥2 KF 后观测数 ≤2(mono)/≤3(stereo)剔;3 KF 后转正。
- 完整生命周期:**严出生门 → 出生 → 立即邻域融合 → 2-3 KF 试用期 → 长期 found-ratio 监督**。融合不是一次事件,是每 KF 常态。

### 3.2 ORB-SLAM3(【强】源码)🔴 GPLv3
- Fuse 判据与 2 代同构;Atlas 跨地图合并 `MergeLocal`:welding window(惯性图 `numTemporalKFs=25`,纯视觉用共视邻),收集两图窗口点集后 `SearchAndFuse(vCorrectedSim3, vpCheckFuseMapPoint)`,同样 **th=4** + `Replace`(保留双图观测)。matcher 构造 `ORBmatcher matcher(0.8)`。
- 萃取:跨"地图"(≈我们的跨窗口)融合与局部融合共用同一 Fuse 原语,只换 th 和点集来源——机制可复用,参数按场景分级。

### 3.3 RTAB-Map(【强】OdometryF2M.cpp 源码)✅ BSD-3
- 局部特征图去重走**外观身份**:新点仅当 `mapWords.find(word_id)==end()` 时入图——即 BoW word-ID 唯一性 = **按外观身份的出生前裁决**(同 word 不重复出生),完全不做 3D 邻近融合。
- 修剪:超 `OdomF2M/MaxSize` 时两遍——先删非内点,再删最老,保 `regInfo.inliersIDs` 近期内点。
- **双墙是 RTAB-Map 已知病**(ROS Answers #250537【中】):社区修法全在**位姿/约束侧**(`Vis/MaxDepth=3.5` 限远特征、`Vis/MinInliers=30`、`RGBD/LoopClosureReextractFeatures true`、关 ICP refine),点层零融合。RTAB-Map 的"自愈"靠云挂在节点位姿上、图优化后重拼装——**位姿病能自愈,拓扑病不能**。与我们 07-17 定案"鬼层不自愈=缺 alias 跨边非缺合并机制"同构互证:我们的病在 track 拓扑层,位姿再准也不自愈。
- 新线索:II-NVM(arXiv 2504.08204,2025)用**法向量区分墙的正反面**治 double-sided mapping——若二阶段裁决器需要区分"真双面"vs"假双层",法向一致性是可借判据。【弱-中,仅摘要,许可未查】

### 3.4 VINS-Mono(【强】feature_manager.cpp 源码)🔴 GPLv3
- 特征以 tracker 分配的 `feature_id` 全局唯一(`find_if` 按 id 查,有则 append 观测,无则新建);每 id 一次 SVD 三角化、单一 `estimated_depth`;**零融合机制**。
- 结构性结论:**KLT 时序跟踪的身份连续性从源头杜绝同物理点重复出生**——重复只在跟踪断裂时发生。我们的窗口匹配(检测-匹配范式)天然缺身份连续性,这是碎 track 的第一性根源。stage-1 的"产跨边"本质是在补时序谱系免费拿到的东西。

---

## 4. 商业软件公开机制(⚪ 专有,仅机制参考)

### 4.1 Metashape(文档/官方帮助台,【中-强】)
- **点置信度 = 贡献 depth map 数**:每个稠密点记录参与的 combined depth maps 数量,1-255 存为 confidence;`Tools > Point Cloud > Filter by Confidence` 按区间过滤(须建云时勾 Calculate point confidence)。官方帮助台文档明载。——**"多少张深度图支持这个点" = 支持度裁决的稠密层版本**。
- **稀疏层 gradual selection 四刀**(USGS 有标准化 error-reduction workflow):
  1. **Reconstruction Uncertainty**——误差椭球长短轴之比,高值典型来自**小基线相邻照片**,正是我们低视差 σ_depth 壳的直接对应刀(社区常用阈值 ~10;本轮拿到实例 10.859)【中,手册原文本轮未逐字获取】;
  2. Projection Accuracy——大尺寸特征定位差的点;
  3. Reprojection Error——迭代式:每轮只删 10%,直到 RMS ≤0.3(默认);**删-优化交替**,与 PR#2145 的 {BA→merge} 迭代模式同构;
  4. Image Count——观测数门(支持度)。
- 萃取:业界唯一明文档的"低视差点专杀刀"(Reconstruction Uncertainty)+ 迭代小步删除范式(单轮大删会破坏 BA 平衡)。

### 4.2 Pix4D(官方 support 文档,【强】)
- 稠密化 **Minimum Number of Matches:2-6,默认 3**——每个 3D 点须在 ≥3 张图正确重投影才存在。**出生门=支持度**,且文档明说 2 会"more noise and artifacts",4-6 减噪但减点。
- Noise filter:删远离相机的点(地平线假点)。

### 4.3 RealityCapture / RealityScan(官方帮助,【强】)
- Max feature reprojection error:官方建议 **≤3px**;Detector sensitivity 文档自认高敏档"may include less reliable points from image noise"(与 07-12 弱纹理定案互证:RS 弱纹理出点=激进检测非鲁棒匹配)。
- **无任何 tie point 去重/融合的公开文档**——RS 预览无鬼层的解释仍应回到 07-19 定案(每点=真实匹配+BA+≤3px 裁剪),而非存在隐藏融合器。

---

## 5. 萃取:可移植判据表(供二阶段相对支持比裁决器定参)

| 判据 | 谱系值 | 出处 | 移植建议 |
|---|---|---|---|
| 低视差出生禁令 | baseline/medianDepth ≥ 0.01 | ORB-SLAM2 birth【强】 | 出生前按对检查,掐 σ_depth 壳源头 |
| 融合搜索半径 | 3.0×尺度因子(局部)/ 4.0×(大残差场景) | ORB-SLAM2/3【强】 | 半径随位姿不确定度分级;BA 前宽 BA 后窄 |
| 视角门 | <60°(cos=0.5) | Fuse【强】 | 防不同面误融(真双面 vs 假双层) |
| 外观门 | ORB Hamming ≤50/256bit(≈20%) | Fuse【强】 | 换算到 SIFT/DSP 描述子的等效分位 |
| 误差门 | chi2 5.99(2DoF)σ² 加权 | Fuse/birth【强】 | 与生产 reproj 门统一语义(禁双常量) |
| 赢家判据 | Observations() 多者 | Fuse【强】 | dossier §5.1 相对支持比 = 其连续化,谱系背书 |
| 输家处置 | **观测全转移,不删**(Replace) | MapPoint::Replace【强】 | E9 连坐误杀的解:并而非杀,误杀=0 构造性满足 |
| 试用期 | 出生 2-3 KF 内观测 ≤2/3 剔;foundRatio<0.25 剔 | MapPointCulling【强】 | "出生宽进+试用期严出"可作裁决器软化版 |
| 支持度出生门 | ≥3 图重投影(2-6 可调) | Pix4D【强】 | 稠密层已知等价物 |
| 低视差事后刀 | 误差椭球轴比(~10)迭代删 10%/轮 | Metashape【中】 | 若裁决器漏网,补刀在此;必须小步迭代+BA 交替 |
| 迭代模式 | {BA → complete+merge} 循环 | PR#2145【中】 | 单次 merge 不足 ≠ 路线死;位姿变好解锁新合并 |
| 时机 | 融合是每 KF 常态,非终局一次 | SearchInNeighbors【强】 | 若在 finalize 单点跑,须一次到位或迭代 |

**顺序萃取**(ORB-SLAM 验证过的完整序):几何门(深度→图内→尺度带→视角)→ 外观门 → 误差门 → 支持度裁决 → 观测转移 → 描述子/法向重算。裁决放最后、转移紧随其后——先裁后并,不裁不删。

---

## 6. 结论(对我们三条待决线的回答)

1. **COLMAP 社区无现成补丁**:同物理点多 track 是官方 intended(#80),"一物理点一 track"诉求被拒(#3097),最接近的社区补救是 tsattler 的迭代 {BA→merge}(PR#2145,未 merge)。stage-1 自研方向再次坐实,且应吸收"与 BA 交替迭代"模式。
2. **SfM 库谱系无支持度裁决先例**(整条丢/先到先得两极);**SLAM 谱系有**:ORB-SLAM Fuse 的"支持度定赢家+输家观测全转移"是与 dossier §5.1 最接近的已验证实现,并给出全套可移植数值(§5 表)。其"并而非杀"直接解 E9 连坐误杀。
3. **时序身份是第一性差距**:VINS/KLT 谱系构造性无此病;RTAB-Map 按外观身份去重;我们的窗口匹配缺身份连续性 → 碎 track。stage-1"产跨边"是在补这个,不是可选优化。
4. **低视差壳有双保险先例**:出生前(ORB-SLAM baseline/depth ≥1%)+ 事后刀(Metashape Reconstruction Uncertainty)。
5. 许可红线:ORB-SLAM2/3、VINS-Mono = GPLv3 🔴,**只抄判据数值与顺序,绝不 vendor 代码**;RTAB-Map(BSD-3)、OpenSfM(BSD-2,本轮逐字核)、OpenMVG(MPL2)、Theia(BSD-3)、hloc(Apache)、COLMAP(BSD-3)✅。

## 7. 未决/复核项
- Metashape Reconstruction Uncertainty 的手册原文定义(误差椭球轴比)本轮仅拿到多方一致转述【中】,手册 PDF(1.6/1.7)逐字待补。
- II-NVM 许可与细节未查(仅新线索登记)。
- OpenMVG/Theia/hloc 许可为惯例共识【中】,若真要 vendor 须按 license-audit-exhaustive 逐文件核。
- ORB-SLAM3 Fuse 常量(TH_LOW 等)按 2 代同构推定,3 代头文件未逐字核【中】。

## 8. 来源清单
- https://github.com/colmap/colmap/issues/80 · /issues/3097 · /pull/2145 · /issues/4435 · /issues/471
- ORB-SLAM2 源码(raulmur/ORB_SLAM2 master):ORBmatcher.cc/.h、LocalMapping.cc、LoopClosing.cc、MapPoint.cc
- ORB-SLAM3 源码(UZ-SLAMLab/ORB_SLAM3 master):LoopClosing.cc(MergeLocal/SearchAndFuse)
- RTAB-Map 源码(introlab/rtabmap master):corelib/src/odometry/OdometryF2M.cpp;ROS Answers #250537(double walls)
- VINS-Mono 源码(HKUST-Aerial-Robotics/VINS-Mono master):vins_estimator/src/feature_manager.cpp
- OpenSfM(mapillary/OpenSfM main):opensfm/tracking.py、LICENSE;OpenMVG(develop):src/openMVG/tracks/tracks.hpp;TheiaSfM(master):src/theia/sfm/track_builder.cc;hloc(cvg/Hierarchical-Localization master):hloc/triangulation.py
- Agisoft:helpdesk "Point cloud editing with confidence filter tool"、Manual 1.6/1.7、USGS "Metashape Automated Image Alignment and Error Reduction v2.0"
- Pix4D support:"Processing Options > Point Cloud"(Minimum Number of Matches)
- RealityScan Help:appbasics/alignsettings.htm
- II-NVM:arXiv 2504.08204
