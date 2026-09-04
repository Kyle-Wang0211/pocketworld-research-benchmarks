# 终审:噪声壳的对症手段 + 按性价比排序的可实施清单

日期 2026-08-05。配套材料:`00_source_audit_and_measurements.md`(源码+实测)、
`01_community_and_official_evidence.md`(社区/官方证据)、三个可复跑脚本。

---

## 0. 一句话结论

**RC / Metashape / COLMAP 三家都会**生成低视差 2-view 点;差别只在于
**RC 和 Metashape 把它们逐点打上标志位、在"显示/导出层"剔除,而我们把原始
points3D 全量交付。** RealityScan 零浮点不是解算更强,是**出货口径不同**。
所以对症手段是:**在 finalize 之后、写 PLY 之前,加一道"交付层"过滤,
判据用 track length + 各向异性不确定度 —— 不动求解层。**

三家的判据是同一套东西的三种叫法:

| | 低视差判据 | 2-view 判据 |
|---|---|---|
| **RealityCapture / RealityScan** | flag `ill` = "apical angle is smaller than a minimal requirement" | flag `weak` = "unverified two-view point" |
| **Agisoft Metashape** | Reconstruction Uncertainty = `sqrt(k1/k3)`(协方差最大/最小特征值之比) | Image Count("points that are visible only on two photos are likely to be located with poor accuracy") |
| **COLMAP** | `filter_min_tri_angle`(1.5°) / `GetPointCov` 的 λmax/λmin | `ignore_two_view_tracks` / `FilterPoints3DWithShortTracks` / GUI 的 `min_track_len=3` |

> RC 官方逐字(A,https://rshelp.capturingreality.com/en-US/appbasics/reports_fav_points.htm):
> ```
> $ExportPointsEx( flags, minTrack, maxTrack, anyText )
>   flags:  active   - active in reconstruction
>           ill      - apical angle is smaller than a minimal requirement
>           outlier  - invalid projection
>           weak     - unverified two-view point
>           ...
>   minTrack - a minimal number of images where the point has been tracked
>   maxTrack - a maximal number of images where the point has been tracked
> ```
> **注意:`ill`/`weak` 是 per-point flag,还有 `GetPointCount(flags, minTrack, maxTrack)`
> 可以按 flag 计数 ⇒ 这些点在 RC 内部是被生成并保留着的,只是被打了标记。
> 导出函数本身就带 `minTrack` 参数 —— track length 是 RC 的一等导出维度。**

---

## 1. 🔴 先纠正三条前提(否则会做错刀)

### 1.1 `ignore_two_view_tracks` 在我们代码里**默认是开的**,而且它管不到 86.6% 的云
`official_aether_sfm_c.cc:2030` 的 `TriIgnoreTwoViewTracks()` 默认返回 **true**
(只有 `OFFICIAL_AETHER_TRI_IGNORE_2VIEW=0` 才关)。
且同文件 `:1980` 注释记录:交付云 **86.6% 由自研 live 三角化器生成**,
该路径根本不查 correspondence graph 的 two-view 规则。
⇒ **翻这个开关最多影响官方三角化器那 ~13% 的产出,不可能是主刀。**
(⚠️ 需核实真机 env 是否设了 0;注意 Dart 的 `Platform.environment` 读不到 setenv。)

### 1.2 `ignore_two_view_tracks` ≠ `min_track_len >= 3`(A,源码)
`correspondence_graph.cc:353` 的判据是「该特征在整张已验证匹配图里**只有 1 条对应**,
且对方也只有 1 条」。我从我们自己出货的 DB 数出来:
**115,124 个特征(20.65%)满足,即最多 57,562 个候选点**。
而 61.3% 的 2-view track ≈ 82k 点 > 57.5k ⇒ **至少 ~25k 个 2-view track
这个开关抓不到,只有 track-length 过滤能抓。**

### 1.3 收紧 `filter_max_reproj_error` 对这类点**在原理上失明**
COLMAP 作者 ahojnnes 逐字(A,issue #416):
> "They were probably triangulated from cameras with very similar projection
> center ... **The reprojection error should be very small for those points**"

我们自己的数据佐证:交付云 `reproj_px = 1.2989`,已经远低于 4.0 阈值。

---

## 2. 🔴 实测:纯几何后处理的天花板(在真实交付云上跑出来的)

数据:`cap_1785934283657550`,134,227 点 / 201 帧。
壳带(1.3 ≤ r ≤ 2.0 m)= **12,694 点 = 9.46%**(不是 41 个,不是 0.03%)。

| 手段 | 参数 | 壳覆盖率 | 核心误伤 | 判决 |
|---|---|---|---|---|
| SOR(Open3D 教程值) | k=20, std_ratio=2.0 | **5.2%** | 0.34% | ❌ 无效 |
| SOR(极端) | k=20, std_ratio=0.5 | 26.8% | 4.89% | ❌ 不划算 |
| 半径离群点 | r=0.05, nb=16 | 21.6% | 3.33% | ❌ 不划算 |
| 半径离群点 | r=0.02, nb=16 | 66.2% | **27.0%** | ❌ 灾难 |
| 局部形状(linearity + 视线夹角) | L≥0.5, \|cos\|≥0.8 | 5.7% | 6.7% | ❌ 误伤>覆盖,纯随机 |
| **粗尺度密度(ball count R=0.40m,删最低 10%)** | 百分位自适应 | **68.4%** | **3.7%** | ⚠️ 唯一可用的几何法 |
| **粗尺度密度(voxel 0.20m 3×3×3,删最低 10%)** | O(N),可上端 | **63.2%** | **4.4%** | ⚠️ 同上,实现更便宜 |

两条关键机理:
- **kNN(20) 尺度上壳只比核心稀 1.9×(AUC 0.758)** —— 12,694 个壳点足够互相支撑一个
  k=20 邻域,所以 SOR 看不出异常。**这就是 SOR 失效的根因。**
- **0.20–0.40 m 粗尺度上壳比核心稀 ~10×(AUC 0.937 / 0.950)** —— 拉开尺度才看得见。

**学术背书(B)**:PLOS ONE 2018(pone.0201280)
> "When there are sparse outlier and isolated outlier, both methods could obtain
> reasonably good removal results. **When the non-isolated outliers exist,
> however, the quality of results decreases significantly.**"

**局部形状假说被判死**:壳在 xyz 里**不是**沿视线排列的 streak。
linearity AUC 0.514、\|cos(e1,ray)\| AUC 0.475(随机水平)。
⇒ **判别信息不在 xyz 里,在被丢掉的摄影测量元数据里。**

---

## 3. 按性价比排序的可实施清单

### 🥇 #1 交付层加 COLMAP 官方"展示口径":`track.Length() >= 3 && point3D.error <= 2.0`

- **类型**:新增后处理(在 finalize 之后、写 PLY 之前),**不改任何求解参数**
- **证据**:**A 级,已在我们自己的 vendored 树逐字复核**
  `ui/render_options.h:44-48` → `int min_track_len = 3; double max_error = 2;`
  `ui/model_viewer_widget.cc:1165` → `if (point3D.error <= ... && point3D.track.Length() >= min_track_len)`
  维护者 tsattler 在 issue #3441 明说:"The viewer only shows 3D points with a
  certain minimal track length. By default ... at least 3";作者 ahojnnes 结案:
  "sparse point cloud visualization difference due to track length filtering."
  **那条 issue 的标题就是我们的现象**:GUI 干净 / 导出的 ply 全是浮点。
- **成本**:**零额外计算**。`point3D.error` 已由 `UpdatePoint3DErrors()` 填好
  (`official_aether_sfm_c.cc:8911` 已调用),track length 天然可读。
  官方函数 `ObservationManager::FilterPoints3DWithShortTracks(3)` 现成可用
  (`observation_manager.cc:395`)—— **我们全树零调用**。
- **是否影响真实点**:会删掉全部 2-view 点。按 61.3% 估算,交付点数会从 134k
  降到 ~50k 量级。这是**最大的一个未知数**,必须先量(见 §4 必做实验)。
  参照物:AliceVision 官方对同一动作的实测(A,Meshroom `StructureFromMotion.py`):
  > "Setting it to 3 (or more) **reduces drastically the noise in the point cloud**,
  > but the number of final poses is a little bit reduced (from 1.5% to 11% on
  > the tested datasets)."
  Metashape 官方(A,手册 Image Count 判据):
  > "points that are visible only on two photos are likely to be located with
  > poor accuracy. Image count filtering enables to remove such unreliable points"
- **符合既有裁决**:属于「显示层 ≠ 求解层」,不动 BA;删的是全场景一致的判据,
  不产生局部密度不均。

### 🥈 #2 各向异性不确定度 U = √(λmax/λmin),即 Metashape 的 Reconstruction Uncertainty

- **类型**:新增后处理(每次全局 BA 后算一次),不改求解
- **这是唯一一条"专门针对深度歧义椭球"的成熟判据**,而且**COLMAP 已经能算,我们从没用过**。
- **Metashape 官方定义逐字**(A,Metashape Pro 2.2 手册 p.145):
  > **Reconstruction uncertainty** — "Ratio of the largest semi-axis to the
  > smallest semi-axis of the error ellipse of the triangulated 3D point
  > coordinates. The error ellipse corresponds to the uncertainty of the point
  > triangulation alone without taking into account propagation of uncertainties
  > from interior and exterior orientation parameters."
  > `sqrt(k1 / k3)`  (k1 = largest eigenvalue, k3 = smallest eigenvalue of the
  > tie-point covariance matrix)
  > "**High reconstruction uncertainty is typical for points, reconstructed from
  > nearby photos with small baseline. Such points can noticeably deviate from
  > the object surface, introducing noise in the point cloud. While removal of
  > such points should not affect the accuracy of optimization, it may be useful
  > to remove them ... for better visual appearance of the point cloud.**"

  > ⇒ **官方原话把它的定性完全说死了:这就是我们的现象(小基线 → 偏离物体表面 →
  > 点云噪声),而且删它不伤解算、纯为观感。跟我们的用途逐字吻合。**

- **COLMAP 侧的等价实现**(A,已读 vendored `estimators/covariance.h/.cc`):
  `BACovarianceOptions::Params::POINTS` + `BACovariance::GetPointCov(id)`。
  头文件注释:"Covariance for 3D points, **conditioned on all other variables set
  constant**" —— **与 Metashape "without taking into account propagation of
  uncertainties from interior and exterior orientation parameters" 是同一个口径。**
- **成本**:`covariance.cc:105-135` 只做 per-point 3×3 Hessian 块求逆;
  `covariance.cc:349` 在只要 POINTS 时**提前 return,完全跳过 Schur 补与稠密 L_inv**
  (那才是贵的)。⇒ 一次 Jacobian 求值 + N 个 3×3 求逆,**O(N),端上可承受**。
  finalize 已经建好 ceres::Problem,可直接复用。
- **阈值**:
  - 绝对起点 **U = 10**(A,USGS Open-File Report 2021-1039,
    "Set level: 10 (if >50% points are selected, increase until <50% points are selected)")
  - 或 **RC 式分位数自适应**(A,rshelp inspection.htm):
    > "Reference uncertainty region percentile ... The default value is 70, which
    > means that 70% of all tie points are considered stable and of good quality.
    > These points are colored blue and are used as a reference ... Color palette
    > radius is a multiplier that defines a range of points' uncertainty."

    ⇒ 取全体 U 的 70 分位为基准 × 倍率作为切线。**尺度无关、场景自适应**,
    对我们(无绝对尺度)更友好。
- **学术源头**(A):Beder & Steffen, DAGM 2006, "roundness" `R = sqrt(λ3/λ1)`
  —— Metashape 的 RU 正是它的倒数。
  > "The roundness of the confidence ellipsoid is directly related to the
  > condition number of the 3d reconstruction of the point."
- **风险**:U 的分布尾极重,必须用分位数而非固定阈值;damping=1e-8 是官方为
  "poorly conditioned 3D points" 加的,别去掉。

### 🥉 #3 把 `filter_min_tri_angle` 从 1.5° 抬到 2.0–3.0°

- **类型**:改 COLMAP 现有参数(求解层,会影响 BA)
- **证据**:同行默认值 —— OpenMVG `RemoveOutliers_AngleError(sfm_data_, 2.0)` 硬编码 2.0°(A);
  AliceVision `minAngleForTriangulation = 3.0`,`minAngleForLandmark = 2.0`(A)。
  我们创建门已经是 2.0°,但 **`filter_min_tri_angle` 还停在 1.5°**
  (`official_aether_sfm_c.cc:5633` 注释已自承认这个缺口)。
- **⚠️ 但它对我们的壳只能是配角**:注意
  `FilterPoints3DWithSmallTriangulationAngle` 是 **max over 所有成对组合**
  (`observation_manager.cc:455` 注释:"Only delete point if **none** of the
  combinations has a sufficient triangulation angle"),长轨迹只要有一对够开就活。
  且我们的壳已经通过了 1.5° 这道门。
- **❌ 诚实 gap**:**全网找不到一条"调大 min_tri_angle 减少浮点"的实测报告**。
  官方参数文档只有"往下调"的指导语,没有"往上调"的。这是空白区。

### #4 粗尺度密度过滤(几何兜底,仅当 #1/#2 不可行时)

- **类型**:新增后处理,纯 xyz
- **实测**(本机,B):voxel 0.20m 的 3×3×3 邻域计数,删密度最低 10%
  → 壳覆盖 **63.2%**,核心误伤 **4.4%**,AUC 0.937。O(N),端上便宜。
- **代价**:会误伤真实的稀疏区(远墙、地板边缘);阈值是场景相对的百分位,
  跨场景不稳。**是症状级手段,不是根治。**

### ❌ #5 SOR / 半径离群点移除 —— 判死,不要做

实测覆盖率 5.2%(Open3D 教程参数)。文献(PLOS ONE / GauSSmart / Clean-GS)
一致指出它对 non-isolated outlier 无效;Clean-GS 定量显示邻域法只贡献 2 个百分点。
社区之所以到处推荐它,是因为 2018 年 issue #416 的语境是**远处孤立飞点**,
和我们的壳是两码事。

### ❌ #6 半径 / bounding box 裁剪 —— 判死
`colmap model_cropper` 是轴对齐盒。壳与真点半径完全重叠(p90=1.29 / p99=1.64),
按半径切必然大面积误伤。实测超过 3×p50 的只有 41 点。

---

## 4. 🔴 必做的下一个实验(唯一该做的一件事)

**在写 PLY 前把每点的摄影测量元数据 dump 成 sidecar**,然后把覆盖/误伤表原样跑一遍:

```
per point: track_len, max_pairwise_tri_angle, point3D.error,
           U = sqrt(λmax/λmin) of GetPointCov(id)
```

要回答的三个数(现在全是未知):
1. `track_len >= 3` 对壳的覆盖率 / 对核心的误伤率,以及交付点数从 134k 掉到多少
2. `error <= 2.0` 单独的效果(叠加后的边际)
3. U 的分布,以及 U > p70×k 与壳的重合度

**为什么必须做**:交付 PLY 只有 xyz+rgb,我在本机**无法**量出 #1/#2 的真实代价 ——
这是本次调研最大的空缺,也是唯一挡在"直接装机"前面的东西。
脚本骨架(壳/核心分带 + 覆盖率/误伤表 + AUC)已在 `analyze_shell.py` 里现成,
把 `knn_mean` 换成新的判据列即可。

---

## 5. 诚实标注的 gap

1. **社区对"清理稀疏点云"没有共识配方。** COLMAP 官方 FAQ 只有"如何增加点数",
   **没有对应的"如何减少坏点"章节**。唯一的官方立场是 GUI 的隐式显示口径,
   埋在 `render_options.h` 里,直到 2025 年 issue #3441 才被维护者说破。
2. **找不到"关掉 ignore_two_view_tracks 导致点云变脏"的公开报告**(带数字的一条都没有)。
3. **找不到"调大 min_tri_angle 减少浮点"的公开实测**(一条都没有)。
4. **找不到高质量的 "COLMAP vs RC/Metashape 谁的稀疏云更脏" 社区对比帖。**
   只能从"导出口径 ≠ 展示口径"结构性反推。
5. **RC/RS 默认稀疏云导出模板到底调 `$ExportPoints` 还是 `$ExportPointsEx("active",…)` —— 未闭合。**
   官方只说 "exports all tie points in the scene **no matter the point selection**"
   (没说 no matter the flag)。模板 xml 在 Windows 安装目录
   `C:\Program Files\Epic Games\RealityScan` 下,官方确认可编辑
   ("To customize these exports, you will need to edit the corresponding files in
   the installation directory")。**在装了 RC/RS 的机器上打开那个 xml 看一眼,
   一分钟就能给"RS 零浮点"归因钉死最后一块拼图。**
6. **RC 的 `ill` 判据里那个 "minimal requirement" 阈值本身没有公开**,
   官方 CLI 键值表(sfmMaxFeaturesPerMpx / sfmMaxFeatureReprojectionError=2.0 等)
   里**没有任何 min-angle / min-track 键**。
7. **Reddit 全域屏蔽本次工具的 UA**,r/photogrammetry 一手帖零证据。
8. **149,440 → 134,227 的交付期策展逻辑不在 `aether_cpp` 里**,本次未定位到。
   实施 #1 前要先找到它,避免加出第二处平行过滤(参照既有"平行同名实现三处"的教训)。
