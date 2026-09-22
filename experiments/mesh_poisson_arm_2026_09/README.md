# 稠密 → 成网:Poisson 臂(arm C)= 当前最优解

2026-09-22。用户肉眼判决:**「Poisson超级好！！！」**,四窗页里 ③(本臂)胜过官方
Delaunay+graph-cut 的两条臂。本目录钉死这条臂的可复现配方,以及同日被判死的三条臂。

判决页(四窗,相机同步):`/root/page_adc`(箱上),窗口 = ① 官方 Delaunay / ② 关弱支撑面 /
③ **本臂 Poisson** / ④ Poisson 吃 2016 反投影云(负结果,见下)。

---

## 1. 最优臂的配方(arm C)

输入是 **CasDiffMVS ep0 在 768×576 的官方融合点云**,不是深度图:

```
/root/arm_full_ep0/pc_t3.ply     36,232,793 点,thres=3,带颜色
```

三步,常数全部来自 `poisson_ep0.py` 的默认值:

| 步 | 工具 | 参数 |
|---|---|---|
| 1 法线 | Open3D `estimate_normals` | `KDTreeSearchParamHybrid(radius=0.02, max_nn=30)` |
| 2 定向 | 最近相机中心翻法线 | 实测 59.5% 翻转 |
| 3 成网 | Open3D `create_from_point_cloud_poisson` | `depth=11`, `linear_fit=False` |
| 4 裁剪 | 按 Poisson 自出的 density | 裁掉最低 **2%** |
| 5 收尾 | `aliceVision_meshFiltering` | 与 ①②④ 同参(官方节点默认值) |

产物:**3,532,836 顶点 / 7,032,802 三角**,非流形边 **4,542**
(对照:官方 Delaunay 115,我们的 TSDF 56,640)。

🔑 **洞是第 4 步给的,不是 Poisson 给的。** Poisson 本身和 Delaunay 一样会把一切封死;
真正「没证据就留空」的是按密度裁剪这一刀。这正是用户要的行为。

## 2. 为什么它没有「瓷砖」(结构性原因,不依赖任何一次实验)

- **Delaunay+graph-cut 的网格顶点就是输入点本身**。已自证:把 `filt/` 深度反投影成云后,
  A 臂网格顶点到该云的最近距离 **p50 1.2 mm**(坐标系摆错时是 1716 mm)。
  ⇒ 没有点的地方只能由最近的几个点张成一个面,那几个点离多远,三角形就多大。
- **Poisson 的网格顶点是八叉树格点**,与输入点无关 ⇒ **结构上长不出跨越几百毫米的三角。**

同一把尺子(`scripts/tri_stats.py`):

| | ① Delaunay(2016 深度) | ③ **Poisson(本臂)** |
|---|---:|---:|
| 顶点 / 三角 | 913,460 / 1,816,547 | 3,532,836 / 7,032,802 |
| 最长边 p50 / p99 | 3.3 / 28.7 mm | 2.7 / 6.1 mm |
| **最长边 max** | **341 mm** | **17 mm** |
| 盖掉一半面积所需三角占比 | **1.63%** | 30.66% |

⚠️ **总面积不可横比**:①② 被 `estimateSpaceFromSfM` 裁到小体积(展示帧 r=1.47),
③ 没裁(r=2.24)。26.66 vs 17.63 m² 不是同一块地方的面积。

## 3. 🔴 本臂的已知缺陷:贴不了图

官方 `aliceVision_texturing` 在它上面 **7,032,566 个 chart 只能并成 5,373,809 个**
(对照臂 A:1,816,547 → 50,152)。UV 展不开,与 TSDF 同病。
判决页里 ③ 用的是**顶点色不是贴图**。**这是它上产线前的硬阻塞。**

## 4. 🔴 坐标系:本臂原来是错配下贴的图(已修)

`armC.sh` 用 `av_ep0_off/scene_dense.sfm`(官方全分辨率 SfM 帧)给一个建在**旧 768 COLMAP 帧**
的网格贴图,尺度差 3.75×。症状是 7,033,148 个三角产生 7,032,780 个 chart(**一三角一 chart**)。
`texC`/`texC2` 作废。

修法 `scripts/align_C.py`:用两套 sfm **共有的 132 个相机中心**求 Umeyama Sim3。
尺度 **0.2664**,残差中位 **6.73 mm** / p95 16.07 / max 25.10。

## 5. ⚰️ 同日判死的三条臂(负结果,别重试)

| 臂 | 变量 | 结果 |
|---|---|---|
| **D** | `--voteFilteringForWeaklySupportedSurfaces` 1→0 | 三角分布逐档差 **<0.1pp**、实心四面体 6,316,656 vs 6,314,771(差 **0.03%**)⇒ **这个开关不是瓷砖的成因**,我的假设被证伪 |
| **A2** | 容量旗标全开(`maxInputPoints` 1e9 / `maxPoints` 50M / `minStep` 1) | 融合点 397 万→601 万,>20 mm 长边三角占可见面积仅 52.3%→48.5%,最大边长 341→**349** mm。用户肉眼:**「1和2的效果几乎完全一样」** |
| **E** | Poisson 吃 ①② 那份 2016 反投影云,点数对齐 36,232,793 | 用户肉眼:**「4是最烂的」** |

### 🔴 臂 E 是一个**无效对照**,它的教训比结果重要

我称它「公平对照」,实际**只对齐了点数,三个变量全没控,而且全是我自己引入的**:

1. **制备不同**:③ 的云走过 CasDiffMVS 自己的 `filter.py` 几何一致性融合;
   ④ 是 DepthMapFilter 存活像素**逐视图全取**,同一表面被不同相机重复记录、从未合并。实测:

   | | ③ 768 融合云 | ④ 2016 反投影云 |
   |---|---:|---:|
   | 最近邻距离 p50 | 1.897 mm | **0.839 mm** |
   | 有邻居在 0.5 mm 内 | 2.4% | **15.6%** |

   同点数下 ④ 挤密 2.3×、15.6% 是近重复点 ⇒ **有效独立采样远少于 36.2M**。
2. **随机抽稀**:223.5M 随机抽 16%,噪声幅度原样保留、覆盖被打散。
3. **包围盒**:大 2.4× ⇒ `depth=11` 的八叉树格子粗 2.4×(边长 p50 5.1 vs ③ 2.7 mm)。

**⇒ 「Poisson 赢在算法不在输入」这个结论作废。** 臂 E 对算法问题一个字都没回答。

**尺子也瞎了**:`tri_stats.py` 只测「瓷砖」一种失效模式。④ 最大边 32 mm、完全没有瓷砖,
却是整页最烂的。**「没有瓷砖」不等于「好」。**

## 6. 🔴 `aliceVision_depthMapFiltering` 的静默失败(已建闸)

找不到邻居相机时它毫秒内返回,**静默删掉约九成深度值,退出码和日志全正常**。
09-17 有一份产物就是这么来的(2.885 秒,只剩 **8.0%** 深度值,成网仅 250,229 顶点;
正确重跑是 **96.7%**)。闸门 `scripts/filt_gate.py` 比对 EXR 头里的
`AliceVision:nbDepthValues`,低于 30% 即 FAIL。**跑这个节点必须过闸。**

## 7. 脚本

| 文件 | 用途 |
|---|---|
| `scripts/poisson_ep0.py` | **本臂核心**:法线估计 + 朝相机定向 + Poisson + 密度裁剪 |
| `scripts/armC.sh` | 本臂后段:ply→obj → 官方 meshFiltering → 官方 Texturing |
| `scripts/align_C.py` | 相机中心 Umeyama Sim3,把旧帧网格搬进官方 SfM 帧 |
| `scripts/arms.sh` | 臂 A(官方 Delaunay)完整调用,所有参数取 Meshroom v2023.3.0 节点默认值 |
| `scripts/armD.sh` | 臂 D:唯一变量 = 弱支撑面开关(负结果) |
| `scripts/armE.sh` | 臂 E:无效对照(负结果,教训见 §5) |
| `scripts/texC3.sh` | 搬正后重贴图(仍失败,chart 并不动) |
| `scripts/unproject_filt.py` | 深度图→点云,坐标系用 EXR 头里的 `iCamArr`/`CArr`,不猜约定 |
| `scripts/tri_stats.py` | 三角尺寸分布尺子(**只测瓷砖一种失效模式**,见 §5 警告) |
| `scripts/obj2meshbins.py` | OBJ+PLY→判决页顶点色 bins(单段索引写 `<tag>.idx` 不加 `.0`) |
| `scripts/filt_gate.py` | DepthMapFilter 静默失败闸 |
| `scripts/fuse_px.py` | CasDiffMVS 融合参数化版(产 §1 的输入云) |

## 8. 环境

箱:vast.ai `107.209.104.125:45434`(= `ssh5.vast.ai:35833`),RTX 5090。
AliceVision `Meshroom-2023.3.0`(MPL-2.0),跑前必须 `export ALICEVISION_ROOT`。
Open3D 0.20.0(`pip install open3d`,箱上曾被清掉需重装)。
许可:AliceVision MPL-2.0 文件级 copyleft、Geogram BSD-3;六个 mesh 二进制对
**CGAL/GMP/MPFR 链接数全为 0**(已 `ldd` 核过)⇒ CGAL 那颗 GPL 雷不在链上。
