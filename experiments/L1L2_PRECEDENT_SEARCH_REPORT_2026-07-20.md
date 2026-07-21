# L1 / L2 公开先例检索报告

> 检索截止：2026-07-20（Asia/Shanghai）  
> 输入文件：`L1L2_PRECEDENT_SEARCH_PROMPT.md`  
> 输入 SHA-256：`ee5ed061d45be9aa35ad123702c0c9aef001fa2e35e13a8e4fdd58ea1fa05f9d`  
> 结论性质：工程与公开资料检索，不是专利自由实施（FTO）或法律意见

## 1. 结论先行

| 层级 | 判定 | 结论摘要 |
|---|---|---|
| 1. 容器层 | **先例存在** | COLMAP、Metashape、RealityScan、CloudCompare、Potree 都证明：显示端可按点属性或阈值不画某些点，而不必修改源点集合。COLMAP 的普通 PLY 导出路径与 viewer render options 分离，是最强源码级证据。 |
| 2. 谓词几何层 | **先例存在** | CloudCompare 已有可复核的“拟合平面 → 计算逐点到平面距离 scalar field → 用显示区间隐藏阈值外点”组合；Open3D 和 Autodesk 专利补强“主/地面平面 + 距离阈值”几何原语。 |
| 3. 判据来源层 | **仅部分类比** | Loo（前轮已知）直接证明 learned depth 可裁决已有 sparse map points；本轮新增/强化的 Point-NeRF 用 learned MVS confidence 调制渲染，Lee 用学习模型、估计平面和逐点判据检测 ghost，缺少对照点时跳过判定。但没有一项同时是“外部 MVS 网络离线裁决现有 SfM 稀疏点 → 持久化 rescue bit → 只供显示使用”。 |
| 4. 完整组合 | **未找到先例** | 在本报告记录的学术、正式会刊、专利、商业产品与社区工具检索强度下，未找到同时覆盖四帧 learned MVS、主导地板带、三态 fail-open、持久 per-point rescue bit、`band ∧ ¬rescued`、默认不可调的 render-only 门和全量交付的公开实现。 |

最重要的变化不是“完整组合被找到了”，而是前一轮对第 3 层的描述过于悲观。公开资料已经覆盖了它的若干关键原语，尤其是：

1. learned depth 反向裁决现有 sparse map point；
2. learned multi-view MVS 输出 per-point confidence 并直接影响 rendering；
3. learned + plane-conditioned + pointwise ghost detection + evidence-missing skip/no-decision；
4. pointwise visibility/rescue-like value 在专利中被保留或降低。

因此，“学习判据与逐点可见性完全没有公开先例”应当撤回；但这些证据仍不足以把 L1/L2 的**完整耦合机制**判成已有先例。

### 对模块去留规则的直接含义

- 若项目铁律要求“同一机制、同一意图”的公开先例，**L1 的完整机制仍未通过**：现有公开工作分别缺少 multi-view MVS、floor band、持久 rescue bit、render-only 和 full export 中的一项或多项。
- L2 的两个基础构件——render-only/full-export 容器与 plane-distance visibility predicate——均有明确先例；但带上 L1 的 `rescued` 位后，完整公式仍只有局部类比。
- 这是一项工程证据结论，不替代产品价值、性能、用户测试或专利法律分析。若内部规则把“公开原语可组合”也视为足够，L2 基础架构可以保留；若只接受完整机制先例，则 L1 以及 L1/L2 耦合仍触发该规则。

## 2. 判定对象与边界

本报告严格按输入提示冻结下列对象，不用更宽松的“看起来像”替代。

### L1：学习深度对稀疏点的逐点仲裁

冻结特征：4 张参考帧；CasDiffMVS/CoreML/fp32；主导地板平面；仅处理地板附近可疑带内的现有 SfM sparse points；输出 hidden/rescued/abstain 三态；abstain 时 fail-open；rescue 写入交付点序对应的 `ghost_view_mask.bin` bit5；不删除点。

### L2：只影响渲染的可见性门

```text
hidden(p) = band15(p) ∧ ¬rescued(p)
```

其中 `band15` 由点到主导平面 slab 的 1.5 cm 阈值定义；hidden 只控制屏幕绘制；PLY、上传与交付始终使用完整点集；开关为默认开启、用户不可调的编译期常量。

### 严格排除

下列命中只作为排除项或反向证据，不计入同机制先例：

- SOR、radius filter 等通用离群点剔除；
- reprojection error、track length、triangulation angle 等重建内蕴质量过滤；
- dense MVS depth-map fusion 的一致性检查；
- sparse SfM points 反过来训练、补全或校正 depth network；
- LOD、octree、point budget、`appMaxPointsToDisplay` 等性能降采样；
- 单纯以新子云/新模型物化筛选结果，而没有 render-only/full-export 分离。

## 3. 方法、来源与校准

### 3.1 来源路由

- 正式论文：Crossref、arXiv、CVF Open Access、IEEE/作者公开稿、期刊官网及 DOI 元数据；对决策关键论文阅读正文而不只看摘要。
- 论文状态：对关键 DOI 检查 Crossref correction/update/retraction relationships；截至截止日均未发现更新关系。这不是对所有出版伦理状态的穷尽证明。
- 专利：Google Patents、可跳转的 USPTO/Espacenet family metadata、claims 和 description；只用于技术先例检索。
- 商业产品：优先官方帮助、官方 API/支持答复、厂商专利；营销页只作弱证据。
- 社区工具：官方文档、固定 tag/commit 源码、维护者 issue/discussion；不把博客二手转述当关键证据。

### 3.2 检索校准

本次检索有意优先证伪“没找到”：使用 `map point culling`、`point validation`、`visibility value`、`render mask`、`soft deletion`、`reinstate`、`rescue`、`whitelist override`、`non-destructive filtering`、`learned depth sparse point`、`plane-conditioned ghost removal` 等术语族，并沿关键论文的参考文献和引用链追溯。

负面结论统一写成“在本报告强度下未找到”，不写成“技术不存在”。

### 3.3 覆盖限制

- OpenAlex 与 Semantic Scholar 的研究证据接口各做 4 次探测，均返回 `api_key_not_configured`，有效结构化覆盖为 0；以 Crossref、arXiv、正式 venue 页面和引用链补位。Scopus、Web of Science 未系统检索。
- Google Scholar 没有稳定的可审计 API，本次未把个性化网页排序或 hit count 当可复核证据。
- 闭源 App 的未公开实现无法由帮助文档证明；产品无公开说明不等于内部没有相似代码。
- 部分专利库的 “legal status” 是聚合站推测，本报告不采用它作法律结论。
- 付费墙或不可读全文的候选被列入“未确立”，没有强行分类。

## 4. 四层逐项判定

## 4.1 容器层

> 层级：容器层  
> 判定：**先例存在**  
> 核心证据：COLMAP fixed-source viewer/export split；Metashape、RealityScan、CloudCompare 官方文档；Potree per-point attribute shader mask。  
> 与我们的差异：这些先例没有由 L1 rescue bit 驱动，默认值、用户可调性和 full-delivery 保证也不完全相同。  
> 检索强度：46 次定向核验 + 11 个社区仓库 issue/discussion 查询 + 固定源码深读；明细见本节末。

### 最强证据 A：COLMAP viewer 与 PLY export 的源码分离

固定版本：COLMAP `8cad79a597f423d392c91391cb28bebf9113d002`。

- [`render_options.h:44-48`](https://github.com/colmap/colmap/blob/8cad79a597f423d392c91391cb28bebf9113d002/src/colmap/ui/render_options.h#L44-L48) 为 `min_track_len` 和 `max_error` 写明：**“for a point to be rendered.”**
- [`model_viewer_widget.cc:1152-1218`](https://github.com/colmap/colmap/blob/8cad79a597f423d392c91391cb28bebf9113d002/src/colmap/ui/model_viewer_widget.cc#L1152-L1218) 只把通过 render options 的点装入渲染缓冲。
- [`main_window.cc:1226-1260`](https://github.com/colmap/colmap/blob/8cad79a597f423d392c91391cb28bebf9113d002/src/colmap/ui/main_window.cc#L1226-L1260) 的 PLY export 不接收这些 render options；[`reconstruction_io.cc:417-424`](https://github.com/colmap/colmap/blob/8cad79a597f423d392c91391cb28bebf9113d002/src/colmap/scene/reconstruction_io.cc#L417-L424) 调用 `ConvertToPLY()`；[`reconstruction.cc:1052-1067`](https://github.com/colmap/colmap/blob/8cad79a597f423d392c91391cb28bebf9113d002/src/colmap/scene/reconstruction.cc#L1052-L1067) 遍历全部 `points3D_`。
- [Issue #3441](https://github.com/colmap/colmap/issues/3441) 的维护者把显示差异归因于 track-length filtering，并建议另行执行 `point_filtering` 才让模型数据与显示相同。

这构成“viewer 过滤集合 ≠ 普通导出集合”的源码级先例。它与 L2 的差异在**判据来源**：COLMAP 使用重建自带的 track/error，不是 L1 rescue bit。`UploadPointData` 是 GPU/render upload，不是网络上传。

### 证据 B：Metashape、RealityScan、CloudCompare

- Metashape 官方帮助 [Point cloud editing with Confidence filter tool](https://agisoft.freshdesk.com/support/solutions/articles/31000162209-point-cloud-editing-with-confidence-filter-tool) 明示 confidence filter **“only hides the points in the Model view”**，且不会自动移除。要得到过滤后的导出，官方支持流程要求另行选择并删除低置信点。限制：闭源，结论带版本/格式边界；该功能也不是默认自动开启。
- RealityScan [Alignment inspection](https://rshelp.capturingreality.com/en-US/tools/inspection.htm) 写道：**“Changing to Yes hides all correctly aligned points.”** [Point selection](https://rshelp.capturingreality.com/en-US/appbasics/pointsselection.htm) 又说明 tie-point export 无视 point selection。两页合并强力支持“显示隐藏不改 tie-point 导出集合”，但不是同一页逐字保证 inspection-hidden points 的 export 行为。
- CloudCompare 的 [Entity properties](https://www.cloudcompare.org/doc/wiki/index.php?title=Entity_properties&oldid=47395) 允许用 scalar-field display range **“hide points with values outside a given interval.”** 固定源码 `c7d5bb7...` 中 display range 与数据值分离；普通 [`PlyFilter.cpp:452-487`](https://github.com/CloudCompare/CloudCompare/blob/c7d5bb7eb9187203c17fb557bc7bf372638a31d4/libs/qCC_io/src/PlyFilter.cpp#L452-L487) 和 [`AsciiFilter.cpp:318-386`](https://github.com/CloudCompare/CloudCompare/blob/c7d5bb7eb9187203c17fb557bc7bf372638a31d4/libs/qCC_io/src/AsciiFilter.cpp#L318-L386) 遍历原实体 `size()`。若用户另行执行 `Filter by Value`，则创建一个新子云；它不是对原云的原地破坏性删除。该源码证据只直接覆盖 PLY/ASCII，不外推到全部格式。

网页证据均采集于 2026-07-20：Metashape help HTML SHA-256 `58f9146b...cab46`；RealityScan inspection `736f5f79...370ea`；RealityScan point selection `3ddedd7f...0f2c4`。短哈希用于识别本次抓取内容，不代表网站发布方签名。

### 证据 C：Potree 的逐点属性渲染门

Potree 1.8.2 [`pointcloud.vs:442-447`](https://github.com/potree/potree/blob/1.8.2/src/materials/shaders/pointcloud.vs#L442-L447) 用逐点 `classification` 查询 RGBA LUT；[`pointcloud.vs:747-767`](https://github.com/potree/potree/blob/1.8.2/src/materials/shaders/pointcloud.vs#L747-L767) 在 classification alpha 为零时把点移出裁剪空间并返回。它证明 per-point byte-like attribute 可直接控制 shader 可见性，而不在 shader 内删除输入点。

限制是 Potree viewer 自己不能保证任意下游 export/full-delivery；此外，Potree [issue #1012](https://github.com/potree/potree/issues/1012) 指出转换成 octree 后原 LAS 点序未必保持，按点序外挂 sidecar 有错位风险。对本项目而言，`ghost_view_mask.bin` 需要稳定 point ID、显式索引映射或强约束的不可变排序契约，不能只凭数组位置假定。

### 与 L2 的差异

- 先例中的显示条件是 track/error、confidence、selection、scalar field 或 classification，不是 `band15 ∧ ¬rescued`。
- 多数工具由用户选择 filter；L2 是默认开启、编译期、终端用户不可见。
- “不删除”与“所有 export/upload/delivery 永远全量”是两级保证。COLMAP 普通 PLY 路径有源码证据；闭源产品只能给到文档强支持；Potree 不能证明整个交付链。

### 检索强度

- 46 次定向官方文档/源码/issue 核验，覆盖 COLMAP、Metashape、RealityScan、CloudCompare、Open3D。
- 11 个社区仓库执行 `rescue | reinstate | soft delete` 的 issue/discussion 组合检索；原始相关词命中 4，人工判定与 L1/L2 相关为 0；另用 external byte array/original order 找到 Potree #1012。
- 深读 Potree、PDAL、Entwine/EPT、Nerfstudio、gsplat、SuperSplat、Viser 的固定版本源码或官方文档。

## 4.2 谓词几何层

> 层级：谓词几何层  
> 判定：**先例存在**  
> 核心证据：CloudCompare 官方/源码完整覆盖 fit plane → per-point distance scalar field → display threshold；Open3D、ERASOR、Autodesk 专利补强。  
> 与我们的差异：没有相同的自动 dominant-floor 选择、固定 1.5 cm slab、rescue override 或不可调默认开关。  
> 检索强度：社区固定源码、正式 RA-L 论文、官方 API 与专利 claims/description 定向核验；明细见本节末。

### 最强可组合先例：CloudCompare

固定版本：CloudCompare `c7d5bb7eb9187203c17fb557bc7bf372638a31d4`。

1. [Fit Plane](https://www.cloudcompare.org/doc/wiki/index.php?title=Fit_Plane&oldid=46710)：**“For each cloud CloudCompare will fit a plane primitive.”** 源码 [`ccPlane.cpp:112-186`](https://github.com/CloudCompare/CloudCompare/blob/c7d5bb7eb9187203c17fb557bc7bf372638a31d4/libs/qCC_db/src/ccPlane.cpp#L112-L186) 实现最小二乘拟合。
2. [Cloud-to-Primitive Distance](https://www.cloudcompare.org/doc/wiki/index.php?title=Cloud-to-Primitive_Distance&oldid=47411)：**“Computes the mathematically correct distance between a cloud and a primitive entity.”** [`mainwindow.cpp:9692-9950`](https://github.com/CloudCompare/CloudCompare/blob/c7d5bb7eb9187203c17fb557bc7bf372638a31d4/qCC/mainwindow.cpp#L9692-L9950) 生成逐点 distance scalar field。
3. Entity Properties 的 display range 用阈值隐藏范围外点，而不修改 scalar-field 数据。

这已经覆盖“平面拟合 → point-plane distance → threshold visibility”的机制。它不自动选择 dominant floor，也没有固定 1.5 cm 阈值、rescue override 或默认隐藏。

### 补强证据

- Open3D 0.19.0 [`segment_plane`](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html) 用 RANSAC 和 `distance_threshold` 返回最大支持平面及 inlier indices；示例随后创建 inlier/outlier 子云，所以它只补强几何原语，不是 render-only 容器先例。
- Autodesk 专利 [US9396545B2](https://patents.google.com/patent/US9396545B2/en) 描述地面点云处理中拟合/更新近似平面、计算 residual，并按阈值降低或排除点的参与。它是“地面平面 + point-plane distance + threshold”的专利级邻近项，但意图是 ground segmentation，且会改变下游参与集合。
- ERASOR（RA-L 2021，DOI [10.1109/LRA.2021.3061363](https://doi.org/10.1109/LRA.2021.3061363)）使用 ground-plane fitting 识别候选动态区域，并把被误删的静态点恢复到地图；它补强 plane-conditioned remove/revert 语义，但没有 learned depth 或 render-only/full-export。

### 与 L2 的差异

- CloudCompare 是交互式可组合工作流，不是一个内建、不可调、默认开启的业务 predicate。
- dominant floor 的鲁棒选择方法、slab 方向和 `>1.5 cm` 的具体定义没有找到相同常量先例。
- 这些几何工具没有消费 L1 的 persistent rescue bit，也没有 hidden/rescued/abstain 三态。

### 检索强度

- 覆盖 CloudCompare 固定源码与三页官方工作流、Open3D 固定版本教程/API、ERASOR 正式论文与 Autodesk ground-segmentation 专利。
- 术语族包括 `fit dominant plane point-to-plane threshold visibility`、`ground plane distance filter point cloud`、`plane conditioned ghost removal`、`revert ground plane map`；普通 RANSAC 平面分割只作为召回入口，不把其输出子云误计为 render-only。

## 4.3 判据来源层

> 层级：判据来源层  
> 判定：**仅部分类比**  
> 核心证据：Loo learned-depth/sparse-point culling；Point-NeRF learned-MVS/confidence/render；Lee learned/plane/point-ghost/no-evidence skip；LiON point-wise abstention/file output；Bentley per-point visibility value。  
> 与我们的差异：没有单项同时实现 external MVS → existing sparse SfM points → durable rescue bit → renderer-only/full export。  
> 检索强度：61 个 query families、122 次 Crossref/arXiv 核心调用、正式 venue/引用链/固定仓库/DOI 状态复核；明细见本节末与附录。

该层的完整定义是：“一个外部 learned model 离线产生持久 per-point bit，并由 visibility/rendering 消费。”公开证据覆盖了这句话的不同子串，但尚未找到一项覆盖整句。

### A. Loo 等：learned depth 直接裁决已有 sparse map points

Loo et al., *Online Mutual Adaptation of Deep Depth Prediction and Visual SLAM*, arXiv:2111.04096v3，DOI [10.48550/arXiv.2111.04096](https://doi.org/10.48550/arXiv.2111.04096)。

正文 §III-C 明示：**“with the learned depth information, we introduce a map point culling step”**；Eq. (10) 对 host keyframe 中的 map-point depth `d_mp` 和 CNN depth `d_CNN` 做逐点判断：

```text
keep = |d_mp - d_CNN| < γ d_CNN  OR  d_CNN > d_max
```

后一个分支用于避免超出 CNN 有效深度范围的远点被过早剔除，是窄义的 operational fail-open。正文又明确 online-adapted depth 用于移除潜在 noisy map points。

**同一原语：** learned depth → existing sparse map point validity。  
**差异：** 单目/在线适配，不是 4-view MVS；没有 floor band；结果是 culling/删除而不是 persistent rescue bit；没有显式三态或 render-only/full-export。

### B. Point-NeRF：learned multi-view MVS → per-point confidence → rendering

Xu et al., *Point-NeRF: Point-Based Neural Radiance Fields*, CVPR 2022，DOI [10.1109/CVPR52688.2022.00536](https://doi.org/10.1109/CVPR52688.2022.00536)，[CVF 正式公开稿](https://openaccess.thecvf.com/content/CVPR2022/papers/Xu_Point-NeRF_Point-Based_Neural_Radiance_Fields_CVPR_2022_paper.pdf)。

- 论文把 `γ_i∈[0,1]` 定义为 point 位于真实表面附近的 likelihood，并在 Eq. (4) 直接乘入特征聚合/渲染贡献。
- §4.1 用 MVSNet-like cost-volume 3D CNN 从多视图回归 depth probability volume，反投影生成 points，再采样该 volume 得到每点 `γ_i`；多数情况使用两个邻视图加 reference view。
- 低置信点在优化中每 10k iterations 被 prune，因此最终管线并非“不删点”。

**同一原语：** learned multi-view MVS、per-point surface confidence、直接影响 rendering。  
**关键差异：** MVS 网络创建的是自己的 dense/neural points，不是用 MVS 反查既有 sparse SfM points；confidence 是连续标量而不是 durable rescue bit；无 floor band/abstain；会 prune；论文没有 full-export 保证。论文也支持从 COLMAP 点云初始化，但该分支排除 MVS generation network，不能把两个分支拼成输入文件定义的同一机制。

### C. Lee、Joo、Sim：learned + plane-conditioned + pointwise ghost arbitration + no-evidence skip

Lee et al., *Learning-Based Reflection-Aware Virtual Point Removal for Large-Scale 3D Point Clouds*, IEEE RA-L 8(12), 2023，DOI [10.1109/LRA.2023.3329365](https://doi.org/10.1109/LRA.2023.3329365)，[UNIST 机构论文页（含作者稿下载）](https://aigs.unist.ac.kr/eng/learning-based-reflection-aware-virtual-point-removal-for-large-scale-3d-point-clouds-ieee-robot-autom-lett-prof-jae-young-sim/)。

工作先由 ResNet32 估计玻璃概率并用 RANSAC 拟合 glass plane，只对平面背后的 `Ω_back` 点做逐点虚点判定；用 3D learned feature 比较平面对称几何；当对称 `P_pos` 为空时，正文说 **“we do not consider P_anc in virtual point detection”**。原文直接证明的是 skip/no-decision；论文段落没有把这条分支一路追到最终标签/输出，故这里只把它视为 fail-open-like 类比，不写成已确认“放行并保留”。输出分类本身仍是二元，不是显式 abstain 状态。

**同一原语：** learned model、estimated plane、restricted candidate region、pointwise ghost arbitration、evidence-missing skip/no-decision。  
**差异：** 多回波 LiDAR/玻璃反射，不是 learned MVS depth/SfM sparse points/floor band；最终目标是 remove 并只保留 real points；没有 persistent bit、render-only 或 full export。

### D. Bentley visibility-value 专利：逐点降低/保持的 rescue-like 语义

[US20240153207A1](https://patents.google.com/patent/US20240153207A1/en) / US12299815B2（Bentley Systems，优先权 2022-11-08）Claim 1 为每点设置 visibility value；当另一点云没有阈值距离内的 corroborating point 时降低该值，有 corroboration 时 **“maintain the visibility value ... at a current value”**。该值参与模型生成。

**同一原语：** per-point visibility value；缺少证据时降低，有相邻支持时保持，语义上接近 rescue/whitelist。  
**差异：** 非 learned model、非 depth/plane、非 sidecar bit；消费者是模型生成/FSSR，不是只影响临时屏幕；不保证完整点云交付。

### E. LiON：learned point-wise abstention 与逐点文件输出

Xu et al., *LiON: Learning Point-Wise Abstaining Penalty for LiDAR Outlier DetectioN Using Diverse Synthetic Data*, AAAI 2025 39(9):8951–8959，DOI [10.1609/aaai.v39i9.32968](https://doi.org/10.1609/aaai.v39i9.32968)，[AAAI 正式页面](https://ojs.aaai.org/index.php/AAAI/article/view/32968)。论文定义逐点 `ABSTAIN iff g(x)=0` 并学习 point-wise abstaining penalty。固定仓库 revision `c63ef3ab...` 的[评估代码](https://github.com/Daniellli/LiON/blob/c63ef3ab48a08a7ebff6a27dae1a7a6f0769f57f/anomaly_semantic_kitti/val_cylinder_asym_ood2.py#L184-L210) 为每个输入点写出 uncertainty score 与 semantic prediction 二进制文件。

**同一原语：** learned point-wise abstention；一点一值的离线输出。  
**差异：** LiDAR semantic/outlier detection，不是 MVS/SfM/floor；文件内容是 float score 与 `int32` prediction，不是 1-byte rescue/visibility bit；没有 renderer 或 full-export 语义。论文和仓库正式名称是 LiON，不能称作 P²AD。

### F. 其他较弱邻近项

- Mirror-3DGS（IEEE VCIP 2024，DOI [10.1109/VCIP63160.2024.10849936](https://doi.org/10.1109/VCIP63160.2024.10849936)）为每个 Gaussian 学习连续 mirror probability 并渲染 soft mirror mask；外部 pretrained depth 只提供训练监督。论文没有规定 persistent bit/sidecar、primitive 不删或 full export，故前轮“逐 Gaussian 标志位 + 渲染期掩码 + 基元不删”的描述过强。
- Zhang et al., *A Front-End for Dense Monocular SLAM using a Learned Outlier Mask Prior*（ICRA 2021，DOI [10.1109/ICRA48506.2021.9561392](https://doi.org/10.1109/ICRA48506.2021.9561392)）把 learned per-pixel outlier mask 保存为 keyframe 属性并用于 dense SLAM 权重/融合；不是 sparse per-point bit，也不是 render-only。
- D-VINS（Remote Sensing 2023，DOI [10.3390/rs15153881](https://doi.org/10.3390/rs15153881)）给 feature points 语义标签并跨帧 Bayesian 更新；标签持续于跟踪过程，不等于 durable disk sidecar，消费者是 tracking/BA。
- SOLO-SLAM（Sensors 2022，DOI [10.3390/s22186977](https://doi.org/10.3390/s22186977)）将 learned instance segmentation、map-point dynamic probability 与 RGB-D depth 复判组合，服务于 tracking/pose；不是 MVS/floor/render-only。
- SLAMANTIC（ICCV Workshops 2019，DOI [10.1109/ICCVW.2019.00468](https://doi.org/10.1109/ICCVW.2019.00468)）为 3D map points 维护 static、static-dynamic、dynamic 三组且状态可逆；这是三组/恢复形态先例，但没有 depth、plane、sidecar 或 display consumer。
- Neural Point Cloud Rendering（CVPR 2020，DOI [10.1109/CVPR42600.2020.00785](https://doi.org/10.1109/CVPR42600.2020.00785)）学习 3D point visibility 并服务于 rendering；但 visibility 是多平面输出的 learned blending，不是显式持久 source-point bit，也没有 floor/full-export。
- Pomerleau et al.（ICRA 2014，DOI [10.1109/ICRA.2014.6907397](https://doi.org/10.1109/ICRA.2014.6907397)）长期维护逐点动态概率，评估前不因类别删除点；这是“点状态 + 暂不破坏源地图”的强先例，但没有 learned depth、plane 或 render gate。
- SemanticFusion（ICRA 2017，DOI [10.1109/ICRA.2017.7989538](https://doi.org/10.1109/ICRA.2017.7989538)）把外部 CNN 语义概率长期融合到每个 surfel 并随 loop closure 携带；它削弱“学习状态附着于空间元素”这一单组件的新颖性，但状态不是 rescue bit，也不控制 full-export viewer。
- ASPRS LAS 1.4 R16 的 Key-Point flag 是持久、逐点、保护性 bit：规范要求这类点通常不应在 thinning 中 withheld。它证明“点级保护位”的文件格式形态，但不是 learned rescue、三态或 display-only；不同 Point Data Record Format 的 bit 位置也不同，不能类推为项目 bit5。

### 检索强度

- 学术主检索累计 **61 个 distinct query families、122 次 Crossref/arXiv 单-provider 调用**，每次 `limit=20`，并人工复核前列结果；另查 CVPR/ICCV/ECCV/3DV、IROS/ICRA/RA-L、ISPRS、Remote Sensing、Sensors 等正式入口及关键引用链。
- 关键 DOI 均做身份解析；对 Point-NeRF、Lee、Zhang、D-VINS、Wolff、Removert、ERASOR、Mirror-3DGS 等检查 Crossref update relationships，均返回 `no_update_relationships_found`。
- 最强直接 sparse-point 命中仍是 Loo；最强 multi-view learned confidence/render 命中是 Point-NeRF；最强 plane-conditioned learned ghost/no-evidence-skip 命中是 Lee。三者不能拼接为一项“同一机制”先例。

## 4.4 完整组合

> 层级：完整组合  
> 判定：**在本报告记录的检索强度下未找到先例**  
> 核心证据：所有高相关命中都至少缺少 frozen definition 中的一项关键连接；最接近项逐项列于下文及 Top 5。  
> 与我们的差异：没有单一公开来源同时披露八项冻结特征。  
> 检索强度：学术、专利、8 组商业产品与 11 个社区仓库联合检索；明细见本节末、§6、§7 和附录。

未找到任何单一官方实现、正式论文、影响力开源实现或专利同时公开：

1. 对既有增量 SfM sparse points 进行后验裁决；
2. 裁决深度来自少量参考帧的 learned multi-view MVS；
3. 候选集合由 dominant floor plane 的近地 slab 条件化；
4. 明确 hidden/rescued/abstain 三态，abstain fail-open；
5. 结果按稳定 point identity 持久化为 per-point rescue bit；
6. `band15 ∧ ¬rescued` 只控制渲染；
7. 默认开启、用户不可调；
8. PLY、上传与交付路径始终消费完整点集。

相邻工作最多覆盖其中三到五项：Lee 覆盖 learned/plane/candidate/pointwise/no-evidence-skip，但破坏性且是 LiDAR；Point-NeRF 覆盖 learned MVS/per-point/render，但网络创建 points 且会 prune；Loo 覆盖 learned depth/existing sparse point/range fail-open，但破坏性且没有 plane；COLMAP/CloudCompare/Potree 覆盖 display container，却没有 learned producer。

### 检索强度

- 学术：Crossref、arXiv、正式 venue、作者公开稿、引用链；61 组查询族、122 次核心调用。
- 专利：Google Patents 及家族/claims 检查，重点覆盖 Autodesk、Bentley、ETH/Disney、Motional 及 photogrammetry/point-cloud/depth/visibility/ghost/remove-rescue 组合词。
- 商业：RealityCapture/RealityScan、Metashape、Autodesk ReCap、Bentley ContextCapture/iTwin、Polycam、Scaniverse、KIRI、Matterport 的公开帮助、官方论坛/API/专利线索。
- 社区：COLMAP、CloudCompare、Potree、Open3D、PDAL、Entwine/EPT、Nerfstudio、3DGS/gsplat、SuperSplat、Viser。

“未找到完整组合”只约束上述公开资料与截止日期；不覆盖闭源未公开代码、未公开申请、非英语小众资料或无法访问的付费全文。

## 5. 最接近的公开工作 Top 5

接近度按“命中冻结特征的数量与语义重要性”排序，不按引用数或法律相关性排序。

### 1. Lee, Joo & Sim，RA-L 2023

最接近 L1 的结构：学习模型 → 平面 → 限定区域 → 逐点 ghost 判断 → 缺证据时跳过该判定。差在传感器、判据、破坏性输出、持久性与显示/交付分离。它推翻“learned + plane-conditioned + pointwise ghost detection 没有先例”的宽泛说法；是否最终保留该 skipped point 未由引用段落直接建立。

### 2. Loo et al.，arXiv:2111.04096v3

最接近“learned depth 回头判断已有 sparse map points”，且公式内有有效深度范围外的 fail-open。差在单目在线适配、全图候选、二元 culling、无持久 rescue/render-only。

### 3. Point-NeRF，CVPR 2022

最接近“learned multi-view MVS → per-point confidence → rendering”。差在 MVS 同时生成自己的 neural points；COLMAP 输入分支不使用 MVS generation；continuous confidence 最终也用于 pruning；无 plane/fail-open/full-export。

### 4. Geomagical Labs US20210142497A1 / US11727587B2

最接近“多类构件在同一专利家族中分别被披露”：photogrammetry/SfM/MVS sparse data、neural depth、floor-plane fitting、point confidence、8-bit inverse-floor probability 与 render-time occlusion assets 分布于 claims 和多个可选说明书变体。不能据此说它们形成同一连续 producer→consumer 链。差在输出/权利要求围绕 dense per-pixel depth、segmentation 和 AR occlusion；没有 existing sparse-point rescue bit、1.5 cm slab、三态、delivery-order sidecar 或 full-export split。

### 5. CloudCompare scalar-field display workflow

最接近 L2 基础架构：plane → point distance SF → threshold display hide，并可保持原实体与普通原实体导出。差在完全交互式、没有外部 learned producer、rescue override、固定 1.5 cm、默认不可调开关。

Mirror-3DGS 没有进入 Top 5：它的 per-Gaussian mirror probability 与 soft rendering mask 确实邻近，但 learned depth 只作监督，论文没有 persistent/full-export/non-deletion 契约；前轮对其接近程度估计过高。

Bentley US20240153207A1/US12299815B2 排在其后：它是最强的 per-point visibility/rescue-like value 先例，但缺少 learned depth 与 plane，且 visibility value 用于生成过滤模型而不是只控制屏幕。

## 6. 专利检索结果

本节只报告公开技术文字。专利是否有效、权利要求如何解释、是否侵权、能否自由实施都不在本报告结论范围内；Google Patents 的 status/assignee 字段也带聚合误差警告。

| 家族/公开文本 | 申请人/优先权 | 命中机制 | 与 L1/L2 的关键差异 |
|---|---|---|---|
| [US20210142497A1](https://patents.google.com/patent/US20210142497A1/en), US11727587B2, [WO2021097126A1](https://patents.google.com/patent/WO2021097126A1/en) | 公开 metadata 列 Geomagical Labs；2019-11-12 | 同一 family 的不同 claims/可选变体分别披露 SfM/MVS sparse data、neural dense depth、floor plane/confidence、occlusion assets 与 8-bit inverse-floor probability | 未证明这些构件属于同一 claim/embodiment 或连续链；输出是 dense/per-pixel；无 sparse rescue bit、1.5 cm slab、三态或 full-export split |
| [US20240153207A1](https://patents.google.com/patent/US20240153207A1/en), US12299815B2, WO2024102308A1 | Bentley Systems；2022-11-08 | 每点 visibility value；跨点云 visibility rays；无 corroboration 时降低，有邻点时保持；value 参与 model generation | 无 ML/depth/plane；是模型过滤而非 render-only；无 full export |
| [WO2023070113A1](https://patents.google.com/patent/WO2023070113A1/en) | Argo AI；2021-10-22 | 外部 LiDAR depth map 比较 sparse SfM keypoint depth，按阈值标 outlier；可删除或标 low-confidence/review | dense-to-sparse validation 很接近，但深度不是 learned；无 floor band、persistent rescue/render-only |
| [US20240137646A1](https://patents.google.com/patent/US20240137646A1/en), US12568305B2, WO2024076027 | Samsung；2022-10-07 | 电子设备以 AI model 识别 point-cloud outlier；dependent claims 涉及 multi-view 与 heatmap/confidence，并可引导补拍 | 无明确 learned depth/plane/bit；目标是补拍及生成第二点云，不是屏幕隐藏/全量交付 |
| [US11468585B2](https://patents.google.com/patent/US11468585B2/en), US20210065391A1 | NEC；2019-08-27 | CNN depth → pseudo RGB-D/3D map；在 common tracked keypoints 上比较 network depth 与 SLAM depth | learned depth 与 SfM keypoint 强耦合，但方向是自改进 depth/map generation；无 post-capture 三态/plane/display bit |
| [US10074160B2](https://patents.google.com/patent/US10074160B2/en), US20180096463A1 | ETH Zürich / Disney；2016-09-30 | image-based 3D reconstruction 中，以其他视图 depth-map surface 检查每点并移除不一致点 | 非 learned；面向 per-view/dense MVS cloud；破坏性；无 rescue/display split |
| [US9396545B2](https://patents.google.com/patent/US9396545B2/en), US20130218472A1, WO2013123404A1 | Autodesk；2010-06-10 | ground plane/surface 拟合、逐点 residual/distance、阈值过滤或降权 | 几何层强先例；LiDAR ground segmentation；无 ML/rescue/render-only |
| [US11158120B1](https://patents.google.com/patent/US11158120B1/en), US20220157015A1 | Motional；公开文本所列家族 | 利用 LiDAR intensity/range-image 区域识别并过滤 ghost points | 非 SfM/MVS/floor；破坏性；无持久 display bit |
| [EP3251090B1](https://patents.google.com/patent/EP3251090B1/en) | 见公开 family metadata | 投影 map points、构造 depth map、按 keyframe patch/occlusion 判断 visibility | 非 learned；visibility 用于 mapping/occlusion，不是 full-export viewer gate |
| [US20240203052A1](https://patents.google.com/patent/US20240203052A1/en) | NVIDIA；见公开 metadata | surfel confidence；render 时只 rasterize 高于阈值的 surfels，并可按覆盖放宽阈值 | 公开分支不要求 ML；无 floor/sidecar/full-export |
| [US12175699B2](https://patents.google.com/patent/US12175699B2/en) | NEC；见公开 metadata | 学习模型给实际 LiDAR points 逐点 likelihood，形成带 confidence 的点云 | 无 visibility-bit/render consumer、plane/SfM/MVS/full-export |
| [US20220351518A1](https://patents.google.com/patent/US20220351518A1/en) | Niantic；2021-04-30 | trained repeatability model 为每个 interest point 打分，再选 summary-map subset | learned per-point criterion，但非 depth/ghost/floor；物化 subset，不是 display-only |

### Geomagical 家族的证据层级拆分

- **Claims：** Claim 1 组合 segmentation mask、geometric surface information 与逐像素 dense depth map；Claims 3/5 用 depth 做虚拟对象遮挡；Claim 8 按同一 planar surface 的其他 pixels 调整 pixel depth。Claims 本身没有 sparse-point rescue bit 或 full export。
- **Description / S460：** 说明书的可选变体描述 photogrammetry point cloud 与 neural depth map 的融合、outlier filtering/averaging，以及 MVS depth 与 neural depth 的局部修正；结果指向 fused dense depth。
- **Description / S470、S530、S600：** 其他变体分别出现 floor-plane fitting、point confidence、8-bit inverse-floor probability，以及把 depth/occlusion assets 交给 interactive renderer。
- **证据边界：** 上述构件位于同一 family，但跨不同可选阶段和变体。本文只把它判为“家族级构件聚集的强邻近项”，不把它称作一个已经公开的 L1→L2 连续实施例。

### 专利层面的最重要发现

Geomagical 是构件覆盖最广的专利近例：neural depth、SfM/MVS、floor plane、confidence 与 8-bit pixel representation 在同一家族的不同 claims/说明书变体中出现，但未形成已证明的单一连续机制。Bentley 把“每点 visibility value + corroboration 时保持”写入 claims；WO2023070113 又给出外部 depth map 校验 sparse SfM keypoints。Autodesk 与 ETH/Disney 分别补齐 ground-plane geometry 和多视 depth consistency。这些家族不能相互或跨变体拼接成单一完整先例。

## 7. 商业产品与社区工具

### 商业产品

| 产品 | 可确认公开行为 | 不能确认的部分 |
|---|---|---|
| RealityScan/RealityCapture | inspection 可隐藏正确对齐点；tie-point export 声明导出 scene 中全部 tie points | detector 内部实现、默认值、是否有 learned rescue bit |
| Agisoft Metashape | confidence filter 只隐藏 Model view 中的点；另行 delete 才得到过滤后数据 | 所有版本/格式的闭源导出实现；外部 model bit |
| Autodesk ReCap | [Clipping](https://help.autodesk.com/cloudhelp/ENU/Reality-Capture/files/Edit_Point_Clouds/clip_delete_points.html) 可隐藏而不永久移除；[structured E57](https://help.autodesk.com/view/RECAP/ENU/?contextId=supported_file_formats) 的完整导出明确不应用 deletions/clips | 最强商业 container 先例，但对象是 scan cloud；无 L1 learned-MVS producer |
| Bentley ContextCapture/iTwin | [Terrain/Ghost detectors](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0012038) 是 learned ground/ghost segmentation；专利公开 per-point visibility score | 分类/清理输出；商业版本是否实施专利不可由文档确认；无 render-only/full-export 保证 |
| Polycam | [Gaussian splat crop](https://learn.poly.cam/hc/en-us/articles/29647360522516-How-to-Crop-a-Capture-in-Polycam) 后 export 显示 original uncropped version | 非破坏/原始导出邻近项；手工 crop、splat 对象、无 learned predicate |
| Scaniverse/Niantic | release notes 把 crop 描述为 non-destructive，但后续 export 可包含 crop；Niantic 专利有 learned interest-point score | 产品 crop 不满足 full export；专利生成 summary subset |
| KIRI | [PromptDA](https://www.kiriengine.app/blog/kiri-engine-3.14-release) 使用 LiDAR prompt 的 depth foundation model并可导出 depth/confidence maps；Plane 工具手工移除 floors/walls | per-pixel/depth refinement，非 sparse rescue bit；编辑结果影响导出 |
| Matterport | Dollhouse Trim 可隐藏 mesh 而不从 model 删除；另有 neural-depth 与 plane-recognition 专利 | full-export 句仅能从首方索引弱支持；各层分散、无耦合 |

### 社区工具的边界表

| 工具 | 容器层 | 几何层 | 持久 byte/属性 | 违反或缺失项 |
|---|---|---|---|---|
| Potree | 强：classification alpha 在 shader 隐藏 | clip volumes，非 floor distance | 支持 classification/extra attributes | viewer 不保证所有 export；sidecar 点序不稳 |
| CloudCompare | 强：SF display range | 强：fit plane + distance SF | scalar field 存在于实体 | 无 learned producer/rescue；交互式 |
| Open3D | 弱：通常物化 index subset | 强：RANSAC plane | 可自定义 tensor 属性 | 无内建 per-point render mask/full export policy |
| PDAL | 无 renderer | 表达式与局部 PlaneFit，不是完整 L2 | 强：LAS Extra Bytes `uint8`、PointId | filters 创建新 PointView，是数据过滤 |
| Entwine/EPT | lossless octree container | 无 | 任意 `uint8` dimension | LOD 是性能机制；无 predicate/renderer producer |
| Nerfstudio | crop 可只传子集给 rasterizer | box crop | 模型参数持久 | crop 也可影响 export，违反始终全量 |
| gsplat/3DGS | raster visibility | 无 L2 floor predicate | Gaussian attributes | 训练会 split/prune；不是业务 rescue bit |
| SuperSplat | 编辑有 undo/reset | 手工选择 | 内部 selection/state | hidden splats 不进入 splat export，直接违反 full export |

这些组件说明“工程上能拼出来”不等于“已有单一同机制先例”。尤其是 PDAL/LAS `uint8` + stable PointId、EPT lossless container、Potree classification shader 可以组成相似数据通路，但这是组合设计，不是检索到的既有 L1/L2 实现。

商业检索按产品记录的人工检查规模为：RealityScan 约 8 个首方页、Polycam 约 6 个、Scaniverse/Niantic 约 4 个产品页和 4 个近邻专利、KIRI 约 5 个、Matterport 约 5 个和 2 个专利、Metashape 3 个核心来源、ReCap 约 6 个首方文档和 1 个强相关专利、Bentley 约 7 个首方页和 1 个强相关专利。搜索引擎未给稳定总 hit count，这些数字是人工打开的首方来源数，不是搜索全集。

## 8. 推翻与修正清单

1. **修正前轮“判据来源层整体未找到先例”的含义。** Loo 的 learned depth→existing sparse point 原语是前轮已知；本轮新增/强化 Point-NeRF 的 learned MVS→per-point confidence→render，以及 Lee 的 learned+plane+pointwise ghost+no-evidence skip。层级结论应改为“仅部分类比”。
2. **推翻对 Mirror-3DGS 的过强概括。** 它是连续 mirror probability 和 soft image mask；外部 depth 是监督；正文没有持久 sidecar、基元不删、full export 契约。
3. **修正 CloudCompare “原地破坏性删除”措辞。** `Filter by Value` 创建新子云并禁用原对象显示，不会原地删除源对象；应称“物化/实体化子集路径”。
4. **修正 COLMAP 旧行号。** 截止日固定 commit 的相关位置是 `render_options.h:44-48`、`model_viewer_widget.cc:1152-1218`、`main_window.cc:1226-1260` 等；旧提示行号因版本漂移不再精确。
5. **限制 RealityScan 和 Metashape 的 export 结论。** RealityScan 是两页官方文档合并得到的强推论；Metashape 是带版本/格式边界的闭源行为，不应写成所有当前版本的源码级保证。
6. **新增 Bentley 专利反例。** 前轮未覆盖专利，遗漏了 per-point visibility value 与 corroboration-based maintain/rescue-like 语义。
7. **保留“完整组合未找到”，但降低措辞强度。** 只能说在本报告覆盖范围和截止日期下未找到，不能说公开世界中不存在。

## 9. 严格假阳性与反向管线

| 候选 | 为什么不计入 |
|---|---|
| Wolff et al., 3DV 2016，DOI [10.1109/3DV.2016.20](https://doi.org/10.1109/3DV.2016.20) | 以多视 depth-map consistency 清理 image-based dense/per-view point cloud；对非常 sparse input 反而是失效域；破坏性 |
| Shan et al., CVPR 2014，DOI [10.1109/CVPR.2014.511](https://doi.org/10.1109/CVPR.2014.511) | 用 contours/depth cull PMVS points；非 learned、非既有 sparse SfM rescue、破坏性 |
| MP-SfM, CVPR 2025，DOI [10.1109/CVPR52734.2025.02039](https://doi.org/10.1109/CVPR52734.2025.02039) | monocular surface priors 支持 occlusion/free-space 推理，但冲突时 de-register image 并 discard structure；粒度与容器都不同 |
| Removert, IROS 2020，DOI [10.1109/IROS45743.2020.9340856](https://doi.org/10.1109/IROS45743.2020.9340856) | remove-then-revert 语义邻近，但非 learned depth/plane-render gate |
| YDD-SLAM, Sensors 2023，DOI [10.3390/s23239592](https://doi.org/10.3390/s23239592) | YOLOv5 + physical depth 筛 feature points，失败时框内全剔除；fail-closed，服务于 SLAM tracking |
| [Ghost-FWL, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/html/Ikeda_Ghost-FWL_A_Large-Scale_Full-Waveform_LiDAR_Dataset_for_Ghost_Detection_and_CVPR_2026_paper.html)，arXiv [2603.28224](https://arxiv.org/abs/2603.28224) | 学习模型按 full-waveform LiDAR peak 判别 Ghost/Glass/Object/Noise，并**移除**预测为 Ghost 的对应 3D 点；虽是稀疏移动 LiDAR 的强邻近项，但不是 MVS/SfM、无主导地板带、persistent rescue bit、abstain 或 render-only/full-export split |
| Dense Reconstruction from Monocular SLAM / CNN-SLAM / SimpleMapping | sparse SfM points 用来训练、补全或校正 dense/neural depth；方向与 L1 相反 |
| Potree/EPT LOD、RealityScan max-points display | 性能点预算，不根据 ghost suspicion 或 rescue 决策 |
| Open3D `hidden_point_removal` | 计算特定相机视点的遮挡可见性并返回 index subset，不是业务 ghost predicate |
| graphdeco/gsplat visibility-aware rendering | 指视锥、遮挡和 rasterization 可见性；训练还会 prune，非持久 rescue bit |

## 10. 证据台账

状态含义：`confirmed` 为原文/源码直接支持；`supported` 为多条一手证据合并的强支持；`unresolved` 为候选但无法完成关键核验。

| 主张 | 一手来源身份 | 版本/日期 | 直接支持 | 限制 | 状态 |
|---|---|---|---|---|---|
| COLMAP viewer filter 与 PLY export 分离 | COLMAP source + issue #3441 | commit `8cad79a...`; 2026-07-20 核验 | render options 只进入 viewer buffer；PLY 遍历 `points3D_` | 普通 PLY 路径；不代表所有插件导出 | confirmed |
| Metashape confidence filter 只隐藏 | Agisoft 官方 help/support | help 修改 2026-03-05 | 明示只隐藏、不会自动移除 | 闭源；版本/格式限定 | supported |
| RealityScan inspection hide 与 tie-point all export | Epic/RealityScan help 两页 | 2026-07-20 采集 | hide + all tie points irrespective selection | 跨页面推论；默认值未明 | supported |
| CloudCompare plane-distance display workflow | 官方 wiki + fixed source | `c7d5bb7...` | fit plane、distance SF、display range | 用户驱动，无 auto dominant floor | confirmed |
| learned depth 裁决 sparse map point | Loo et al. | arXiv v3, 2022-02-01 | Eq.10 和 map-point culling 正文 | 单目、破坏性 | confirmed |
| learned MVS per-point confidence 调制 rendering | Point-NeRF | CVPR 2022 | MVS cost volume→confidence；Eq.4 用于 render | MVS-created neural points；会 prune | confirmed |
| learned+plane+point ghost+no-evidence skip | Lee et al. | RA-L 2023 | 仅 `Ω_back`；无对照点时不参与虚点判定 | 未直接证明最终保留；LiDAR/glass、破坏性、二元 | supported |
| Mirror-3DGS per-Gaussian learned mirror probability | Mirror-3DGS | VCIP 2024/arXiv 2404.01168 | Eq.4 soft mask；GT mask supervision | 无 persistent/full-export/non-delete 保证 | confirmed |
| Bentley per-point visibility maintain/lower | US20240153207A1 claim 1 | priority 2022-11-08 | 每点 value；threshold corroboration 时 maintain | 无 ML/plane；model generation | confirmed |
| Potree attribute shader mask | Potree source | 1.8.2 | classification alpha=0 移出 clip space | 无 full-export contract | confirmed |
| `ghost_view_mask.bin` 位置 sidecar 可能错位 | Potree issue #1012 | 截止日可访问 | converter 后点序可能变化 | 是生态风险，不证明本项目实际错位 | supported |
| 覆盖范围内是否找到完整 L1/L2 组合 | 学术+专利+产品+社区联合检索 | 截止 2026-07-20 | 未获单一同机制命中 | 闭源、付费墙、未公开申请未覆盖 | unresolved |

## 11. 查询族与命中记录

### 学术查询族

核心组合包括：

```text
"map point culling" learned depth
"depth map" validates sparse 3D points
neural depth sparse map point validation
learned outlier mask map point SLAM
multi-view stereo per-point confidence rendering
MVS network point confidence prune render
plane-conditioned ghost point removal learning
reflection-aware virtual point removal plane deep
persistent per-point visibility flag learned model
soft deletion point cloud rendering export
rescue OR reinstate OR revert map point
non-destructive point cloud display filter confidence
```

累计执行 **61 个 distinct query families**；每个 family 分别调用 Crossref 和 arXiv，共 **122 次核心 provider 调用**，`limit=20`。Broad Crossref query 常返回 20/20，表示 top-k 截断且含宽松 token 匹配，不是 20 个 exact matches；arXiv exact-title 常为 0–3。对标题/摘要初筛后，深读并进入本报告的直接或重要邻近项约 20 项。原始 hit 有大量重复，不能当独立论文数。

用于审计召回方向的 61 个 query family 完整列于附录 A。另有 24 个 venue-specific Crossref query（12 个核心术语、12 个 venue 定向）均以 `limit=20` 返回 top-k，并在 ScienceDirect/ISPRS、Copernicus、Wiley、MDPI、IEEE Xplore、CVF、ECVA、3DV 正式入口人工筛选；0 项满足完整组合，8 项进入正式会刊决策账本。

**可复现性边界。** 本轮保留了附录 A 的 61 条精确 query、provider、limit、下表 exact-title 返回量及进入报告的证据身份；但没有持久化 122 次 broad call 的逐条原始响应。因此，第三、四层的负面结论应读作“**广覆盖但部分可复现的检索下未找到**”，而不是可由现有附件逐命中重放的系统综述或穷尽性检索。若要达到 litigation-grade 的逐条审计标准，必须用相同 query 重跑并保存 provider 响应、时间戳、结果顺序和逐项 disposition。

以下是运行时单独记录的 exact-title 审计样本；数字为 `Crossref/arXiv` 原始返回量，Crossref 的 `20` 是宽松 top-k，不代表 20 个标题精确命中：

| exact-title query（标题缩写） | Crossref / arXiv | 审阅结论 |
|---|---:|---|
| *Real-Time Dense Monocular SLAM With Online Adapted Depth Prediction Network*（Loo） | 20 / 1 | 进入核心证据 |
| *Pseudo RGB-D for Self-Improving Monocular SLAM and Depth Prediction* | 20 / 1 | 反向管线 |
| *Dense Reconstruction from Monocular SLAM using CNN-Inferred Depth* | 20 / 0 | 反向管线 |
| *A Front-End for Dense Monocular SLAM using a Learned Outlier Mask Prior* | 20 / 1 | 邻近项 |
| *Mirror-3DGS* | 20 / 1 | 邻近项，纠正过强概括 |
| *Removert* | 20 / 0 | 邻近项 |
| *ERASOR* | 15 / 3 | 几何/恢复语义邻近项 |
| *DeepC-MVS* | 20 / 1 | dense MVS fusion，严格排除 |
| *Updating Points Detection by Estimating Depth Map to Update Map* | 20 / 0 | 全文不足，unresolved |
| *DDM-VSLAM* | 20 / 0 | 全文不足，unresolved |

正式 venue 的人工 disposition 汇总为：ISPRS/ISPRS Archives/Photogrammetric Record 4 项，Remote Sensing/Sensors 4 项，ICRA/IROS/RA-L 4 项，CVPR/ICCV/ECCV 至少 6 项，3DV 未增加新的 exact 机制命中；其中 8 项进入本报告的正式会刊决策账本，0 项满足完整组合。这里的数量是被人工提升到候选审阅层的记录，不是各 venue 的数据库总量。

### 专利查询族

```text
point cloud learned depth visibility point patent
photogrammetry sparse point depth map culling patent
per-point visibility value rescue maintain point cloud patent
ghost point filtering plane learning patent
ground plane distance threshold point cloud patent
render only point cloud filter export all patent
MVS point confidence bit mask patent
```

专利通道完成 42 次官方数据库查询（PATENTSCOPE 11、Espacenet/EPO 9、USPTO 11、EPO 受让人 11），另做 8 次 Google Patents 补充查询；去重后实际审阅 25 个 family，其中 13 个读到 claims/description，12 个完成摘要、metadata 与 family 排查。本文保留 12 个相关、邻近或方向相反的 family。Geomagical、Bentley、Argo、NEC、Samsung、Autodesk、ETH/Disney 对四层判定最有实质价值。

代表性原始 query 与数据库返回量如下；宽查询的数百项只做结果层筛选，不等于逐件全文审阅：

| 数据库 | 精确 query（缩写保持数据库语法） | 原始返回 |
|---|---|---:|
| PATENTSCOPE | `FP:("sparse point cloud" AND "neural network" AND depth)` | 7 |
| PATENTSCOPE | `FP:(("visibility flag" OR "display flag" OR "render mask") AND "point cloud")` | 0 |
| PATENTSCOPE | `FP:("point cloud" AND ("non-destructive" OR "soft delete") AND (display OR render))` | 2 |
| PATENTSCOPE | `FP:(("floor plane" OR "ground plane") AND "point cloud" AND outlier)` | 0 |
| Espacenet | `ctxt="sparse point cloud" AND ctxt="neural network" AND ctxt=depth` | 272 publications / 192 families |
| Espacenet | visibility/display/render mask + point cloud | 6 / 3 |
| Espacenet | plane + point cloud + visibility + depth/photogrammetry | 142 / 99 |
| USPTO | `"photogrammetry point cloud" AND "neural depth map"` | 5 documents / 1 family |
| USPTO | map/tie point + learned depth + floor/ground plane + visibility/rescue/hide | 0 |
| USPTO | per-point/point flag/rescue bit + visibility/display flag | 2 / 2，均为误报 |
| USPTO | `"visibility value" AND "each point" AND "point cloud" AND ("plurality of cameras" OR photogrammetry)` | 45 / 12 |

EPO 受让人条件 `pa=<name> AND (photogrammetry OR point cloud OR depth map)` 中，Epic Games、Capturing Reality、Scaniverse、Polycam、KIRI、Agisoft 为 0；Niantic 174/23、Matterport 10/6、Autodesk 83/35、Bentley 55/29。零结果仅限本次法人名与字段条件，不证明厂商没有相关资产。Google Patents 后段出现 503，未绕过。

### 商业与社区查询

对 RealityCapture/RealityScan、Metashape、ReCap、ContextCapture/iTwin、Polycam、Scaniverse、KIRI、Matterport 分别组合 `hide/filter/clip/ghost/confidence/tie point/export/depth/AI`；对 11 个开源仓库执行 rescue/reinstate/soft-delete issue/discussion 查询。社区精确词原始命中 4、相关 0；语义检索另找到 Potree #1012、CloudCompare display range、Nerfstudio crop 和 SuperSplat export 反例。

### 分层检索账本（负面结论的覆盖边界）

| 层 | provider / 通道 | 可复核 query 或来源记录 | 原始量 / 实际提升审阅量 | 本层 disposition |
|---|---|---|---:|---|
| 容器 | 官方帮助、固定 GitHub 源码、issue/discussion | §4.1 的 COLMAP/Metashape/RealityScan/CloudCompare/Potree 链；11 仓库 exact-term 检索 | 46 次定向核验；社区 4 raw / 0 relevant | 5 个系统给出显示/数据分离证据，**先例存在** |
| 谓词几何 | CloudCompare/Open3D 官方与源码、RA-L、Google Patents | `fit plane`、`cloud-to-primitive distance`、scalar-field display range；ERASOR；US9396545B2 | 1 条完整交互链 + 3 类补强来源 | plane→逐点距离→阈值显示链直接命中，**先例存在** |
| 判据来源 | Crossref、arXiv、正式 venue、引用链、论文原文 | 附录 A 61 条 × 2 providers；上表 exact-title 样本 | 122 个 top-k call；约 20 项深读 | learned depth / learned MVS confidence / learned plane-ghost 各有部分链，**仅部分类比** |
| 完整组合 | 上述学术 + 42 次官方专利查询 + 8 次 Google Patents + 8 组商业产品 + 11 个社区仓库 | 附录 A/B、§6 专利 query、§7 产品表 | 专利 25 family 审阅；商业首方页按 §7 计；社区 4 raw / 0 relevant | 0 个单一公开来源覆盖全部冻结要素；在该强度下**未找到先例** |

## 12. 未确立与后续可查

1. **Nakashima & Tasaki, ICAM 2021**：*Updating Points Detection by Estimating Depth Map to Update Map*，DOI [10.1299/jsmeicam.2021.7.GS1-1](https://doi.org/10.1299/jsmeicam.2021.7.GS1-1)。J-STAGE 只露出 GAN/depth/map-update 关键词，全文受限；可能涉及 learned depth 判断更新点，但无法核对 sparse-point、plane、持久 bit 或 consumer，故保持 unresolved。
2. **DDM-VSLAM, SSRN 2022**：DOI [10.2139/ssrn.4195239](https://doi.org/10.2139/ssrn.4195239)。摘要显示 CNN/ORB feature extraction 与 depth-map filtering，但全文请求 403，无法判断是前端 feature filtering 还是 post-map sparse-point adjudication。
3. **闭源移动 App**：Polycam、Scaniverse、KIRI、Matterport 的公开说明不足以核实内部重建后处理；需要厂商答复、反编译授权范围内的实测或已公开专利族扩展检索。
4. **非英语专利全文与未公开申请**：本报告主要依赖英语关键词和公开 family；同义翻译、尚未公开的申请无法覆盖。
5. **代码全文索引**：grep.app 的 20 组实现术语检索均遇到 HTTP 429；Point-NeRF、LiON 等改为审核已知官方仓库固定 revision，但未知仓库召回仍是盲点。
6. **格式级 full-export 证明**：Metashape、RealityScan、ReCap 的不同版本和导出格式可能不同；若产品决策依赖“永远全量”，应做版本锁定的黑盒回归测试，而不是仅靠帮助文档。
7. **sidecar identity 契约**：本报告没有检查项目代码是否在排序、过滤、LOD、序列化之间保持交付点序。Potree 先例显示位置绑定很脆弱；应另做本地数据流审计。
8. **逐命中审计附件缺失**：122 次学术 broad call 的逐条响应没有持久化；现有文档可复核 query、provider、limit、exact-title 样本和最终入选项，但不能不重跑就还原每个 broad query 的所有返回与排除理由。这降低负面结论的可复现等级，不改变已由原文/源码直接支持的正面命中。

## 13. 最终裁决

在 2026-07-20 截止的公开资料检索下：

- **容器层：先例存在。**
- **谓词几何层：先例存在。**
- **判据来源层：仅部分类比。** 前轮的宽泛“未找到”应被修正，但仍没有命中冻结定义的完整 producer→persistent bit→renderer 链。
- **完整组合：未找到先例。** 这是有明确覆盖边界的负面检索结果，不是“证明不存在”。

最接近的三个公开技术分别来自不同领域：Loo 的 sparse map-point culling、Point-NeRF 的 learned MVS confidence/rendering、Lee 的 learned plane-conditioned ghost removal/no-evidence skip。它们证明 L1/L2 不是由完全陌生的原语构成；同时，它们也清楚显示，本项目把这些原语组合成“持久 rescue bit + render-only/full-delivery gate”的方式，仍未在本次覆盖的单一公开先例中出现。

## 附录 A：61 个学术 query family

以下每项分别送入 Crossref 与 arXiv，单次 `limit=20`：

```text
F01 "map point culling" depth CNN SLAM
F02 "sparse map point" "learned depth" validation
F03 "sparse point cloud" "depth prediction" filtering
F04 "multi-view stereo" "sparse point" validation
F05 "MVS depth" "map point" culling
F06 "deep depth" "map point" pruning
F07 "depth consistency" "sparse map points" SLAM
F08 "dominant plane" point filtering photogrammetry
F09 "ground plane" "map point" outlier rescue
F10 "revert" "map point" removal SLAM
F11 "abstain" depth "map point" validation
F12 "fail-open" depth "map point"
F13 "visibility flag" "sparse point cloud" rendering
F14 "non-destructive filtering" "point cloud" display
F15 "persistent" "per-point" confidence mask MVS
F16 "plane-conditioned" outlier detection point cloud depth
F17 "depth-guided" "sparse point" filtering SLAM
F18 "learned depth" "map point culling"
F19 "MVS network" sparse point cloud outlier
F20 "point rescue" point cloud depth
F21 "whitelist" "map points" SLAM
F22 "Pseudo RGB-D for Self-Improving Monocular SLAM and Depth Prediction"
F23 "CNN-SVO" "single-image depth prediction"
F24 "Deep Virtual Stereo Odometry" "depth prediction"
F25 "Dense Reconstruction from Monocular SLAM" "CNN-Inferred Depth"
F26 "Real-Time Dense Monocular SLAM With Online Adapted Depth Prediction Network"
F27 "map point" "CNN depth" noisy
F28 "potential noisy map points" depth
F29 "map quality" "learned depth" SLAM
F30 "filter sparse map points" depth map
F31 "validate sparse map points" depth map
F32 "reject map points" "predicted depth"
F33 "map point" "depth map consistency" culling
F34 "MVS" "SfM points" filtering
F35 "multi-view depth" "sparse reconstruction" outlier
F36 "MVS validation" "sparse point cloud"
F37 "depth prior" "point culling" SfM
F38 "learned multi-view depth" sparse points
F39 "depth network" "point validation" SLAM
F40 "depth prediction" "outlier map points"
F41 "depth maps" "map point culling"
F42 "sparse reconstruction" "learned depth" filtering
F43 "depth discrepancy" "map point" SLAM
F44 "A Front-End for Dense Monocular SLAM using a Learned Outlier Mask Prior"
F45 "learned outlier mask prior" SLAM
F46 "Depth Completion with Multiple Balanced Bases and Confidence" SLAM
F47 "outlier mask" "map points" SLAM depth
F48 "learned outlier mask" "sparse" SLAM
F49 "depth confidence" "map point" culling
F50 "landmark culling" depth CNN SLAM
F51 "landmark validation" "learned depth"
F52 "visual landmarks" "depth prediction" outlier
F53 "triangulated points" "predicted depth" reject
F54 "3D landmarks" "depth map" validation SLAM
F55 "MVS" validate triangulation points
F56 "sparse landmarks" "deep stereo" SLAM
F57 "learned stereo depth" "map points"
F58 "multi-view depth" landmark rejection
F59 "neural depth map" landmark validation
F60 "scene points" "CNN depth" culling
F61 "structure points" "depth prior" rejection SfM
```

Exact-title 审计示例：Loo、Pseudo RGB-D、Zhang–Leonard、Mirror-3DGS、DeepC-MVS 在 arXiv 各命中 1；ERASOR 命中 3；Removert、Nakashima、DDM-VSLAM 的 arXiv exact-title 为 0。Crossref 的对应查询大多返回 20 条宽松 top-k，ERASOR 返回 15，不能把该数字解释为 exact-title 数量。

## 附录 B：正式 venue 定向 query

以下 24 项均为 Crossref `limit=20` top-k；另在各 venue 官方入口人工复核：

```text
"dense depth" "map point culling"
"depth prediction" "map point culling"
"predicted depth" "map point" outlier
"depth consistency" "map points" SLAM
"multi-view stereo" "sparse point cloud" filtering
"MVS depth" "sparse points" validation
"depth map" "tie point" filtering photogrammetry
"depth maps" "sparse reconstruction" outlier
"learned depth" "map point" pruning
"neural depth" "map point" culling
"depth network" "sparse map" filtering
"multi-view depth" "map points" rejection
ISPRS JPRS sparse point learned depth filtering
ISPRS Archives sparse cloud learned filtering
Photogrammetric Record point cloud depth filtering
Remote Sensing VSLAM map point learned filtering
Sensors map point confidence filtering
IROS map point culling learned depth
ICRA learned outlier mask map point depth
RA-L map point dynamic filtering
3DV point cloud visibility mask filtering
CVPR learned depth sparse map points
ICCV learned depth sparse map points
ECCV learned depth sparse map points
```
