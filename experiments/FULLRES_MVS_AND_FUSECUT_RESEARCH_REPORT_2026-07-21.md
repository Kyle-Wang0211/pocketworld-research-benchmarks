# PocketWorld：全分辨率 CasDiffMVS 与无 CUDA fuseCut 可行性研究

日期：2026-07-21（Asia/Shanghai）  
研究类型：源码、论文、构建配置、许可证与本地只读资产审计；本报告没有修改产品代码，也没有运行大模型、构建 AliceVision 或生成新网格。

## 结论先行

| 问题 | 判定 | 决策含义 |
|---|---|---|
| 4224×2376 且峰值与 896×512 持平 | **PARTIAL** | 对现有 CasDiffMVS 和现有 runner 是 **NO**；以固定 896×512 活动窗口进行算子级分块、按需取源视图特征、流式输出，理论上可把**模型工作集**压在同一量级，但“总进程峰值持平”和“质量无损”尚未实测成立。|
| 直接把整张图送入 CasDiffMVS | **NO** | 目标像素数是基线的 21.8772 倍；仅 stage-1 的三个同时存活大张量在 4224×2400 fp32 下就约 4.08 GiB，源码可见 eager 量估算超过 5.7 GiB，尚未计运行时工作区。|
| 简单裁成若干相同矩形后独立推理 | **NO，不能声称等价** | reference tile 的平面扫描可能访问 source image 任意区域；卷积边界、跨阶段上下文和随机扩散场也会改变结果。重叠只能缓解，不能自动证明等价。|
| 稀疏点收窄每块深度范围能否省 cost-volume 内存 | **NO（固定 D 时）** | `numdepth_initial=48`、后两阶各 4 个候选不变时，张量形状不变；收窄范围只提高逆深度采样密度，并带来漏包围真实深度的风险。|
| AliceVision fuseCut 是否必须 CUDA | **NO** | `meshing`、`meshFiltering`、`texturing` 无 CUDA/SYCL 闸门；fuseCut 是 Geogram `BDEL` + Boost Boykov–Kolmogorov。`depthMapEstimation` 和 stock `depthMapFiltering` 目标才受 CUDA/SYCL 闸门。|
| fuseCut 能否跳过 AliceVision 深度估计 | **YES，附条件** | 可把 CasDiffMVS 融合云编码成 AliceVision SfMData landmarks，但每点必须带真实相机 observations；裸 PLY/XYZ 不够。|
| COLMAP `delaunay_mesher` 是否同族 | **YES，广义同族；不是同实现** | 它是 Labatut 2009 的 CGAL Delaunay + 可见性 + Boost 图割；AliceVision 实现 Jancosek/Pajdla 弱支撑扩展及额外后处理。当前实现间没有找到同输入客观对照。|
| 现有 PocketWorld vendored COLMAP 是否“几乎白送” | **NO** | vendor 树里有源码，但产品 CMake 不编译 `colmap/mvs`，还显式排除 `graph_cut.cc`，也未定义 `COLMAP_CGAL_ENABLED`。接入不是打开一个开关。|
| 3.62M 点全局 fuseCut 直接上 iPhone | **LIKELY NO；当前输入精确峰值 UNVERIFIED** | 给定实际 tetra 数 `T` 的源码字段下界可算；采用公开 Poisson `T/n` 只能得到约 3.73 GiB 的**场景估计**，不是这份点云的地板。它与历史桌面实测共同构成强风险信号，但必须先量出实际 `T/n` 才能作设备硬判。|

推荐顺序：

1. **Mac 上先做共同输入 A/B**：现成 Homebrew COLMAP 只用于研究基线；同时准备 AliceVision `meshing` 的无 CUDA、无 Triangle 构建，喂同一份“点 + 每点可见相机”。
2. **产品 Mac 候选优先 AliceVision fuseCut**：它更接近目标弱支撑算法且避开 CGAL GPL，但必须显式关闭 Geogram Triangle，并完成精确产物许可证扫描。
3. **手机不移植全局实现**：先做 packed、分区的局部 Delaunay/局部 cut/边界假设合并原型；在完整 3.62M 输入通过内存和网格非劣门前，现有 TSDF 仍是生产基线。

这些路线排序依据可行性硬门、算法保真度和后文预注册指标，不使用主观评分。

## 研究契约、证据等级与冻结身份

### 证据标签

- **CONFIRMED**：固定 revision 的源码/CMake/LICENSE、官方文档或可复算本地事实直接支持。
- **SUPPORTED**：同行评审结果或相邻任务的定量证据支持，但不是 PocketWorld 当前实现的直接实测。
- **INFERENCE**：从已确认机制推导，必须通过指定实验验证。
- **UNVERIFIED**：本次没有足够原始证据或没有在目标设备执行。
- 许可证结论使用 `allow`、`conditional`、`conflict`、`block`、`insufficient-evidence`；它们是工程合规筛查，不是法律意见。

### 固定输入与版本

| 对象 | 固定身份 |
|---|---|
| 本研究提示词 | SHA-256 `567ac94bcd314398a49f09e3a23dd7b99f857e5d9627348edfbd3c195b46cd20` |
| DiffMVS/CasDiffMVS | [`cd10d5c282a9cabd45a2f64598cd2b990b408d35`](https://github.com/cvg/diffmvs/commit/cd10d5c282a9cabd45a2f64598cd2b990b408d35) |
| AliceVision | [`8fac66f838014022b5b9ea00af5b72e28a06d79e`](https://github.com/alicevision/AliceVision/commit/8fac66f838014022b5b9ea00af5b72e28a06d79e) |
| AliceVision 内建 Geogram | [`fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8`](https://github.com/BrunoLevy/geogram/tree/fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8)，1.9.6 |
| COLMAP | [`85350623e67c5a074dd36808de4aefadd4e805f2`](https://github.com/colmap/colmap/commit/85350623e67c5a074dd36808de4aefadd4e805f2) |
| Aether3D-cross 本地根 | HEAD `ea77244a8fd54153544cddaf95b56c0010d575ca`，已有未提交改动，未触碰 |
| Benchmark repo | HEAD `0a1931658ffff4d2e606b87b197656fe8a14025d` |
| 当前 runner | [`pw_diffmvs_run.py`](/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/pw_diffmvs_run.py:23)，SHA-256 `f627415c663b8181acd411129b287d6b67bb90d019e94213c95eff06b0a43c13` |
| vendor CMake | [`CMakeLists.txt`](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/CMakeLists.txt:17)，SHA-256 `aac12eac04e21ae516e930e1a3b4c4f99fae0f7ca5f49ad80b64ff92edf5b970` |

检索截止到 2026-07-21。论文身份通过 DOI/正式论文页核对；固定源码链接均包含 commit。没有使用个人 Zotero 数据。

### 本地素材的纠正

提示词写“436 张照片”，只读清点得到：

- `photos_highres/` 是 **414 个 JPEG + 22 个 JSON sidecar**；396 张为 4224×2376，18 张为 3840×2160。
- 有序图像字节聚合 SHA-256：`34043430523035910ce5c17cde7779d33d4ed65f13541e41b177819aa741b189`。
- capture 的 COLMAP sidecar 有 414 个 camera/pose，但 **0 个 3D 点、0 个 2D observation**；不能直接提供 tile-local sparse depth，也不是有效 sparse Delaunay 输入。
- 现存 `trio_model_lapa.npz` 有 413 个注册帧；`cell_92_slot_8.jpg` 缺失。
- 认证稠密云 [`mvs_ofull.ply`](/Users/kaidongwang/Desktop/tiled_414_viewer/mvs_ofull.ply) 有 3,620,875 点，SHA-256 `cdd2c899fd7b84ee033cb9b29230df185c5629ebbb800a94870cad882d0fa582`，但 PLY 没有每点 visibility provenance。
- `photos_depth/` 是 414 张 504×280 PNG；其 manifest 路径、尺寸、度量单位与解码契约互相矛盾，不能当真值。
- 当前剩余空间约 24 GiB；不应在此状态启动 AliceVision superbuild 或多变体全分辨率缓存。

# Q-A 全分辨率 MVS

## A1 分块推理：可行性、已发表先例与质量代价

### 直接和相邻先例

| 工作 | 已发表事实 | 定量信息 | 能证明什么 / 不能证明什么 |
|---|---|---|---|
| [DeepMVS, CVPR 2018](https://openaccess.thecvf.com/content_cvpr_2018/papers/Huang_DeepMVS_Learning_Multi-View_CVPR_2018_paper.pdf) | 训练 64×64 patch；测试用 128×128 输入，只保留中心 64×64，再拼成整图。VGG-19 特征仍对整图一次计算。 | 输入 patch 的 75% 面积被当作 context 丢弃；论文最终 completeness 100%、geometry error .036、photometric .224，但这些是组件结果。 | **CONFIRMED：learned MVS 可 patch-wise。** 不提供 tiled-vs-whole ablation，且全局 VGG 使它不能证明恒定总峰值。|
| [Gomez et al., WACV 2022](https://openaccess.thecvf.com/content/WACV2022/papers/Gomez_An_Experimental_Comparison_of_Multi-View_Stereo_Approaches_on_Satellite_Images_WACV_2022_paper.pdf) | 卫星多视图管线把 GANet 以 1872×480 重叠 tile 运行，按到边界距离加权合并；作者明确说边界更易出错。 | 未报告 overlap/stride、tile-vs-whole 质量差或峰值差。 | **SUPPORTED：重叠和边界加权有实际用途。** 任务是双目匹配子步骤，不是 CasDiffMVS。|
| [PatchFusion, CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/papers/Li_PatchFusion_An_End-to-End_Tile-Based_Framework_for_High-Resolution_Monocular_Metric_Depth_CVPR_2024_paper.pdf) | 在 3840×2160 上结合全局粗深度与 960×540 local patches，并训练一致性。 | UnrealStereo4K：fine-only REL .0627；P16 .0399；P49 .0392；一致性误差 fine-only .2546，完整 P49 .0464。 | **SUPPORTED：朴素局部块会损失全局一致性，粗全局上下文+overlap 可显著改善。** 这是单目，不证明跨视图 warping 可直接照搬。|

**本次没有找到** CasDiffMVS、CasMVSNet、UCS-Net、PatchMatchNet 或 MVSFormer++ 的受控“同一网络整图 vs 空间分块”质量和峰值对照。因此，不能给出 PocketWorld 所需的已发表质量损失百分比；这个关键数值是 **UNVERIFIED**，必须实测。

### 高分辨率 MVS 的标准路线并没有让空间内存恒定

| 方法 | 原论文可复算结果 | 结论 |
|---|---|---|
| [CasMVSNet, CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Gu_Cascade_Cost_Volume_for_High-Resolution_Multi-View_Stereo_and_Stereo_Matching_CVPR_2020_paper.pdf) | 1152×864：MVSNet 10823 MB、overall .551；CasMVSNet 5345 MB、overall .355。 | 级联把常数降约 50.6%，不使内存与像素数脱钩。|
| [UCS-Net, CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Cheng_Deep_Stereo_Using_Adaptive_Thin_Volume_Representation_With_Uncertainty_Awareness_CVPR_2020_paper.pdf) | 640×480：1/2/3 阶分别 1309/1607/1647 MB；两次细化体积的 GT coverage 为 94.72% 和 85.22%。 | 自适应窄体积省常数，但区间会漏真值；稀疏范围不是无损保证。|
| [CVP-MVSNet, CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Yang_Cost_Volume_Pyramid_Based_Depth_Inference_for_Multi-View_Stereo_CVPR_2020_paper.pdf) | 输入约 640/800/1600×1152 时内存 1416/2207/8795 MB，overall .403/.379/.351。 | 分辨率提高带来质量收益，也显著增内存。|
| [R-MVSNet, CVPR 2019](https://openaccess.thecvf.com/content_CVPR_2019/papers/Yao_Recurrent_MVSNet_for_High-Resolution_Multi-View_Stereo_Depth_Inference_CVPR_2019_paper.pdf) | 1600×1200、D=512 为 6.7 GB；论文在 11 GB 上最高到 3072×2048，不能处理 6000×4000 ETH3D。 | 沿 depth 轴 recurrent，把 3D volume 的 D 维降掉；空间内存仍增长。|
| [PatchMatchNet, CVPR 2021](https://openaccess.thecvf.com/content/CVPR2021/papers/Wang_PatchmatchNet_Learned_Multi-View_Patchmatch_Stereo_CVPR_2021_paper.pdf) | ETH3D 2688×1792、7 views：5529 MB，F1 训练/测试 64.21/73.12。 | “PatchMatch”是候选传播，不是图像 tile；仍不能满足同峰值目标。|
| [MVSFormer++, ICLR 2024](https://openreview.net/pdf?id=wXWfvSpYHh) | 864×1152 / 1152×1536 / 1088×1920：4873 / 5964 / 6613 MB。 | 增长可次线性，但不是常数。|
| [APD-MVS, CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023/papers/Wang_Adaptive_Patch_Deformation_for_Textureless-Resilient_Multi-View_Stereo_CVPR_2023_paper.pdf) | ETH3D 分辨率 8.04%/50%/100% 时 1.4/3.7/6.6 GB；IterMVS 对照为 2.5/11.2/22.0 GB。 | 是 CUDA PatchMatch/NCC 的 adaptive matching support，不是空间 tile；内存仍随面积增长。|
| [DVP-MVS, AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/download/33056/35211) | 原尺寸 ETH3D/Tanks & Temples；每隔一行一列评估，11×11 matching patch；ETH3D test F1 89.60。 | 是 learned monocular prior 加传统 PatchMatch，不是 tiled neural cost volume。|

DiffMVS 论文自己在 DTU 1600×1152、Tanks & Temples 1920×1056、ETH3D 1920×1280 上评测；没有 4224×2376 或 tile 路线。其 context ablation 也说明上下文不是可随意删除：去 image context 后 ETH3D F1 从 74.86 降到 72.08，去 depth context 或 cost volume 后降到 43.07/47.16。[DiffMVS 论文](https://arxiv.org/pdf/2509.15220)

### A1 判定

- **CONFIRMED**：固定大小的重叠块可把活动张量窗口上界与整幅像素数解耦。
- **SUPPORTED**：边界需要 halo、中心裁切或一致性融合；朴素拼接会产生可量化的一致性损失。
- **UNVERIFIED**：CasDiffMVS 在 PocketWorld 上的最小安全 halo、tile-vs-whole 深度误差、融合后洞/双层面代价，以及总进程峰值是否真的不超过基线。

## A2 CasDiffMVS/扩散级联能否分块：机制与失效条件

### 目标尺寸首先不是 stock 有效输入尺寸

CasDiffMVS 的 3D regularizer 有两次 stride/down-up skip。4224×2376 的 stage-1 高度是 297；下采样 297→149→75 后，第一次转置卷积回到 150，无法与 149 行 skip 相加。[3D regularizer](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/module.py#L422-L448)

- 官方 loader 向下取 32 的倍数，会变成 **4224×2368**，丢 8 行。[loader](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/datasets/mvs.py#L104-L124)
- 保留完整 FOV 的定义应为：按冻结规则 pad 到 **4224×2400**，推理后 crop 回 4224×2376。padding 类型和偏移必须进入实验契约。

像素数：

```text
896 × 512   =    458,752
4224 × 2376 = 10,036,224  = 21.8772 × baseline
4224 × 2400 = 10,137,600  = 22.0982 × baseline
```

### 源码级活动张量

CasDiffMVS feature pyramid 是 stage1 `48×H/8×W/8`、stage2 `32×H/4×W/4`、stage3 `16×H/2×W/2`。[FeatureNet](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/module.py#L357-L420) 初始 volume 的 D 是 **48**，不是 CLI `numdepth=384`；后者用于 refinement 的归一化间隔。[stage-1 depth samples](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/diffusion.py#L185-L202)

| 显式张量 | 元素量 | 896×512 fp32 | 4224×2400 fp32 |
|---|---:|---:|---:|
| 单张 RGB | `3P` | 5.250 MiB | 116.016 MiB |
| 单视图保留 pyramid | `6.75P` | 11.812 MiB | 261.035 MiB |
| reference contexts | `13.5P` | 23.625 MiB | 522.070 MiB |
| stage-1 `ref_volume` | `36P` | 63.000 MiB | 1,392.188 MiB |
| stage-1 `warped_src` | `36P` | 63.000 MiB | 1,392.188 MiB |
| stage-1 乘积临时量 | `36P` | 63.000 MiB | 1,392.188 MiB |
| stage-3 单个 ref/warp | `16P` | 28.000 MiB | 618.750 MiB |
| stage-3 upsample mask | `9P` | 15.750 MiB | 348.047 MiB |

表中的单张/单个张量不随 view count 改名；后续 “>5.7 GiB” eager 可见量估算按当前 runner 的 3 个总视图理解。5-view 不能直接沿用该总量，必须单列。

`ref_volume`、`warped_src` 与相乘临时量来自 [`homo_warping`](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/module.py#L503-L545)。在 padded full-res 下三者约 **4.08 GiB fp32**；加三视图输入/feature/context/depth samples 的源码可见 eager 量估算超过 **5.7 GiB**，还没有算 grid、卷积 workspace、模型权重和 allocator。理想 fp16 约减半，但遗漏项前仍接近 2.9 GiB。

CoreML 可能融合或消除 repeat，所以这些数是**源码级上界模型，不是 CoreML 实测峰值**。它足以推翻“整图只改常数就能保持现有峰值”。

### 为什么不能做相同矩形的朴素 crop

1. **源视图访问非局部。** reference tile 中每个像素、每个深度假设经相机投影后可落到 source image 的远处；`grid_sample` 越界为零。[warping](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/module.py#L181-L218) 对 reference tile `T`，所需 source 区域是：

   \[
   S=\bigcup_{p\in T,d_j\in D}\pi\left(K_s(RK_r^{-1}p\,d_j+t)\right)
   \]

   再加 source feature receptive field 和 bilinear halo。它不等于 source 里的同坐标矩形。

2. **内部边界会被当作图像边界。** FeatureNet、3D regularizer、2D U-Net/ConvGRU 都有卷积 padding。静态源码分析得到：仅 stage-1 到 convex upsampler 前已有至少 377 输入像素 span、约 188 像素半径；后两次 diffusion refinement 还会扩大。这个 188 是**下界**，因此 32/64 px overlap 没有源码依据。

3. **扩散随机场会变。** 两个 refinement stage 用 `torch.randn_like`；tile 调用的 shape/顺序改变 RNG 消耗。[recurrent inference](https://github.com/cvg/diffmvs/blob/cd10d5c282a9cabd45a2f64598cd2b990b408d35/models/update.py#L466-L521) 要比较等价性，必须生成全局坐标可索引的 canonical noise，再切片给 tile。

4. **每块不同深度范围会改变算法。** normalized inverse depth、投影位置和 diffusion 输入都变；重叠区即使物理场景相同也可能得到不同结果。

5. **内参必须完整变换。** crop 后 `cx'=cx-x0`、`cy'=cy-y0`；pad 也要计入。现有 [`scaled_K`](/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/pw_diffmvs_run.py:60) 只缩放 Y 行；直接把常数改成 full-res 会漏掉 X 标定变换。

### 可行的两档实现

**严格/数值等价研究档（INFERENCE）**：

- 不是 model-call 级独立 crop，而是 layer/operator 级 scheduler；
- 全局深度范围固定，48 个初始 planes 不变；
- 为每个 reference core 计算所有 source/depth 投影的 ROI union；按需加载 source feature tile；
- 在中间层交换足够 halo，并只保留中心有效区；
- 使用全局坐标 canonical noise；
- 流式输出，不保留整套 frame depth/confidence；
- 在能放下整图的较小分辨率先要求 bitwise 或预注册数值等价。

**近似工程档（SUPPORTED，但不等价）**：

- 每次模型输入仍是 896×512，halo 包含在这个窗口内；
- 丢弃边界、重叠 core、raised-cosine 融合；
- projection footprint 超出 source tile 时递归拆 core 或记为失败；
- 单独报告 seam band 与 interior 的误差。

无 overlap 覆盖目标至少需 5×5=25 次；若按 DeepMVS 只保留半宽半高 core，约需 10×10=100 次。真实数量取决于经实测确定的 halo 和 source ROI，不能先拍定。

## A3 更优路线：粗到细、自适应深度与压缩

### 路线比较

| 路线 | 峰值作用 | 质量风险 | 本报告判断 |
|---|---|---|---|
| 固定 envelope 的 operator tiling + 全局粗上下文 | 空间活动张量受 tile 上界约束 | halo、source ROI、随机场和 seam 需验证 | **首选 CasDiff 保真研究路线** |
| 低分辨率全局深度 → 高分辨率窄区间 refinement | 可减少高分辨率候选范围；只有同时减少 D/改变图才省 activation | 当前 `forward` 不暴露该拆分；可能是训练分布外路径 | **有希望，但属于模型改造/再验证** |
| 稀疏点 tile-local interval | 固定 D 时不省内存；只提高采样密度 | 低纹理/未三角化表面可能漏出范围 | **只能作为 ablation，必须有 coverage 和 global fallback** |
| R-MVSNet 式 depth-axis recurrence | 降 D 维内存 | 换架构、输出通常更粗 | **不是 CasDiff 等价实现** |
| PatchMatchNet/DVP-MVS 类候选传播 | 通常比 dense cost volume 省 | 换算法和 checkpoint；质量域不同 | **长期替代候选，不回答当前 CasDiff 目标** |
| 只在高置信/高梯度处输出 full-res | 输出和融合量可降 | 直接删除弱纹理白墙样本，恰与目标痛点冲突 | **在弱支撑指标通过前不采用** |

### 深度压缩能省什么

| 表示 | 4224×2376 单张原始量 | 100 张 | 作用范围 |
|---|---:|---:|---|
| fp32 | 38.29 MiB | 3.74 GiB | 仅深度 raster；不含 confidence |
| fp16 / uint16 | 19.14 MiB | 1.87 GiB | 2× 存储/传输压缩；不改变 cost-volume activation |
| lossless 压缩 | 场景相关 | 场景相关 | 不能预先保证倍率；噪声深度通常压缩较差 |

uniform metric uint16 的最大量化误差是

\[
\epsilon_{max}=\frac{d_{max}-d_{min}}{2\cdot65535}.
\]

inverse-depth uint16 的 metric error 随深度变化。是否可用必须把量化后的几何一致性 decision 与最终 5/10/20 mm 网格指标一起测；不能用“肉眼无差”判断。

### “即算即融合即丢”并非当前实现

官方 `filter.py` 会重读 source depth，并把有效像素累积到内存列表；当前 runner 还用 `lru_cache(maxsize=512)` 缓存解码后的 float RGB。414 张在 896×512 约 2.12 GiB，在 4224×2376 约 46.44 GiB。[runner cache](/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/pw_diffmvs_run.py:38) 因此真正 bounded 的实现必须具备：

- reference-counted depth dependency；
- 有上限的 spill/cache 或可接受的重算；
- 不缓存全数据集 RGB/features；
- tile 完成后释放 depth/confidence/intermediate；
- 融合状态本身按空间分块或稀疏结构设上限。

“点云大小与图像分辨率无关”也没有源码支持。现有路径最多每个有效像素出一个点；一张 full-res 的 `xyz(float32)+rgb(uint8)+confidence(float32)+depth(float32)` 原始 payload 约 220 MiB。只有明确的 fusion/voxel/density policy 才能限制点数；流式只限制驻留内存，不限制总产物。

## A4 端上内存估算方法与 A16 可达峰值

### 不能把“约 3GB”当设备常数

Apple 的 [`os_proc_available_memory()`](https://developer.apple.com/documentation/os/os_proc_available_memory) 返回当前进程在当前状态下还能分配的字节，并明确是动态许可，不等于物理 RAM或固定 jetsam 阈值。应同时使用 [jetsam report](https://developer.apple.com/documentation/xcode/identifying-high-memory-use-with-jetsam-event-reports) 和 [WWDC22 memory profiling](https://developer.apple.com/videos/play/wwdc2022/10106/) 的 footprint 方法。没有找到 Apple 发布的“iPhone 14 Pro 统一 3GB 门”。因此：

- **3GB 是提示词中的工程假设，不是文档化事实。**
- 本报告为初始试验预注册 **2.4 GiB 安全上限**，这是保守验收值，不是系统事实；最终以实机多轮 footprint、memory warning、thermal 和 jetsam 证据替换。

### 可核算预算

在模型已加载、allocator warm-up 策略固定后，`os_proc_available_memory()` 已经是“当前限制减去当前 footprint”的剩余量，不能再扣一次 current footprint。预算应分成 API headroom 与产品安全 cap 两条，再取较小者：

\[
\begin{aligned}
H &= os\_proc\_available\_memory() \\
B_{api} &= H-M_{camera/UI/engine\ reserve}-M_{runtime\ transient\ reserve} \\
B_{cap} &= 2.4\ GiB-M_{current\ footprint}-M_{camera/UI/engine\ reserve}-M_{runtime\ transient\ reserve} \\
M_{tile,budget} &= \min(B_{api},B_{cap}).
\end{aligned}
\]

这里 2.4 GiB 仍是本报告的预注册安全 cap，不是系统公布的固定门；任一 budget ≤0 立即停止。[XNU `os_proc_available_memory` 语义](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/os/proc.h#L45-L73)

运行期峰值建模为：

\[
M_{peak}=M_{fixed}+b\max_t\sum_i c_{i,t}P_i+M_{workspace}+M_{output/fusion}.
\]

必须分别记录：

1. model-loaded idle footprint；
2. 20 Hz `TASK_VM_INFO.phys_footprint`；
3. CoreML/Metal 活动阶段；
4. 输入解码、tile、output、fusion 的生命周期；
5. `os_proc_available_memory()`、memory warning、thermal state 与 jetsam outcome。

CoreML 测试固定 `.cpuAndGPU`，不依赖 ANE。统一内存环境不要把 Metal/driver bytes 再加到已包含它们的 process footprint 上。

### A16 可达峰值结论

- **整图 fp32：仅三个同时存活的 stage-1 大张量已约 4.08 GiB；完整 eager 可见量估算 >5.7 GiB，NO。**
- **整图理想 fp16：遗漏运行时前仍近 2.9 GiB，且单张全尺寸输出/相机/UI/allocator 尚未计，不能声称可达。**
- **896×512 tile：模型活动工作集可接近基线，是唯一合理入口；总峰值必须实机测。**
- “内存持平”预注册为：tiled absolute footprint 和 backend peak 都不得超过 `B896 peak + max(32 MiB, 5% × B896 peak)`；每对 A/B 采用六个 fresh process 的 `A-B-B-A-A-B` 平衡顺序（每个变体三次），六次均须通过。

## A5 最终判定

**判定：PARTIAL。**

| 解释层级 | YES/NO | 理由 |
|---|---|---|
| stock CasDiffMVS 整图 4224×2376 | **NO** | 尺寸不合法、空间张量约 21.88×、没有 tile path。|
| 现有 `pw_diffmvs_run.py` 直接改常数 | **NO** | K 变换不完整、全数据集 LRU、全像素点 materialization；总峰值会暴涨。|
| 独立同坐标 crop 后拼接 | **NO（等价性主张）** | source 投影非局部、边界/上下文/RNG 改变。|
| 自定义 operator tiling 后“模型工作集约持平” | **理论 YES / 实测 UNVERIFIED** | 空间图没有全局 attention；固定 envelope 能设工作集上界，但必须支持非局部 source ROI、halo 和 canonical noise。|
| 同时满足总进程峰值持平 + 质量无损 | **UNVERIFIED** | 没有论文或本地 whole-vs-tile 证据；要通过后文验收矩阵才能升级为 YES。|

因此不能现在对产品承诺“4224×2376 且内存持平已可做到”；可以承诺的是：有一条明确、可证伪的 rearchitecture 路线，stock 路线已被源码反证。

# Q-B fuseCut 落地

## B1 CUDA 闸门逐可执行文件

固定 AliceVision `8fac66f8…` 的 stock CMake 结论如下。构建 target 带 `_exe`，安装后的 binary 不带；这是 helper 的 `OUTPUT_NAME` 行为。[target helper](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/cmake/Helpers.cmake#L175-L263)

| binary / target | CMake 创建条件 | 实际后端 | 判定 |
|---|---|---|---|
| `aliceVision_depthMapEstimation` / `aliceVision_depthMapEstimation_exe` | `ALICEVISION_BUILD_MVS && (ALICEVISION_HAVE_CUDA || ALICEVISION_HAVE_SYCL)` | CUDA 调 `computeOnMultiGPUs`；SYCL 调 `computeOnMultiDevices`；无 CPU 分支 | **需要 CUDA 或 SYCL** |
| `aliceVision_depthMapFiltering` / `..._exe` | 同上 | 核心 `fuseCut::Fuser` 是 CPU/OpenMP；只有 `computeNormalMaps=true` 才走 CUDA/SYCL | **算法主体可 CPU，但 stock target 无后端时根本不生成** |
| `aliceVision_meshing` / `aliceVision_meshing_exe` | `ALICEVISION_BUILD_MVS` | `aliceVision_fuseCut`、Geogram、Boost | **不需要 CUDA/SYCL** |
| `aliceVision_meshFiltering` / `..._exe` | `ALICEVISION_BUILD_MVS` | CPU mesh/mvsUtils | **不需要 CUDA/SYCL** |
| `aliceVision_texturing` / `..._exe` | `ALICEVISION_BUILD_MVS` | CPU mesh/SfM/image stack | **不需要 CUDA/SYCL** |

五个目标的直接证据在 [`pipeline/CMakeLists.txt` L499–553](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/CMakeLists.txt#L499-L553) 和 [L632–681](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/CMakeLists.txt#L632-L681)。`fuseCut` 的 direct link closure 没有 CUDA。[fuseCut CMake](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/CMakeLists.txt#L27-L42)

两个容易误读的点：

- Apple 上 `ALICEVISION_USE_CUDA` 默认 OFF，SYCL 默认 AUTO。[src CMake](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/CMakeLists.txt#L66-L80)
- root 的 `AV_USE_CUDA` 在本 revision 没有第二处 CMake 引用，是 inert/misleading；控制实际 depth backend 的是 `ALICEVISION_USE_CUDA`。macOS 文档还写 DepthMap CUDA-only，但当前源码已有 SYCL 分支；Apple GPU 上 SYCL 能否运行仍是 **UNVERIFIED**，且本任务不需要它。

`fuseCut` 执行顺序是 point cloud → tetrahedralization → graph fill → max-flow/binarization → postprocess/mesh。[main meshing](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L400-L427) Delaunay 是 Geogram `GEO::Delaunay::create(3,"BDEL")`，[源码](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/Tetrahedralization.cpp#L18-L46)；max-flow 是 Boost `boykov_kolmogorov_max_flow`。[源码](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/MaxFlow_AdjList.hpp#L113-L143)

## B2 meshing 输入契约与能否直接吃点云

### CLI 必需项

[`main_meshing.cpp`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L172-L180) 要求：

```text
--input       输入 SfMData
--output      输出 dense SfMData
--outputMesh  输出 mesh
```

两个 output 短选项都错误地声明成 `-o`；应只用长参数。默认 `partitioning=singleBlock`、`repartition=multiResolution`、`maxInputPoints=50,000,000`、`maxPoints=5,000,000`、`minVis=2`、`voteFilteringForWeaklySupportedSurfaces=true`。`seed=0` 表示随机，受控实验必须显式给非零 seed。[参数定义](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L135-L271)

源码还暴露两个构建后运行陷阱：

- `partitioning=auto` 能 parse，但随后抛出 “not yet implemented”。[源码](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L343-L350)
- help 写 `repartition=regularGrid`，parser 实际只接受 `multiResolution`；前者会 throw。[源码](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L67-L84)

### 深度图模式

提供 `--depthMapsFolder` 时，SfMData 必须含 views、有效 pose 和 intrinsics。文件名：

```text
<viewId>_depthMap.exr   # 一通道 float，>0 有效
<viewId>_simMap.exr     # meshing 可缺；filtering 要求同尺寸
<viewId>_nmodMap.png    # 可缺
```

命名来自 [`fileIO.cpp`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/mvsUtils/fileIO.cpp#L217-L296)。关键语义是 AliceVision 以 `cameraCenter + normalized(ray) × depth` 回投，所以 EXR depth 是**沿 ray 的距离**，不应把 CasDiffMVS camera-Z 原样写入。[PointCloud.cpp](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/PointCloud.cpp#L301-L415)

整图 EXR 在尺寸与 view 呈统一整数 scale 时可用 SfM projection fallback；若输出 tile EXR，要写 `AliceVision:roi*`、`tileBuffer*`、`tilePadding` 等 metadata 让 reader 复原。[mapIO](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/mvsUtils/mapIO.cpp#L314-L399)

### SfM landmark / 已融合点云模式

省掉 `--depthMapsFolder`，保持 `singleBlock + multiResolution`，程序会关闭 `meshingFromDepthMaps` 并强制 ingest landmarks。[分支](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/software/pipeline/main_meshing.cpp#L283-L309) 输入必须含：

- calibrated views 及 image dimensions；
- intrinsics 和 poses；
- `structure` landmarks 的 XYZ；
- 每个 landmark 对有效 view ID 的 observations。

`addPointsFromSfM` 把 observation 数写成 `nrc`，并把 view IDs 转为 camera list；GraphFiller 对每个 observed camera 做 ray voting。[PointCloud.cpp](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/PointCloud.cpp#L593-L643)、[GraphFiller.cpp](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/GraphFiller.cpp#L82-L110)

**回答“能否直接吃点云”：**

- **YES，条件式**：把 CasDiffMVS 融合云转成上述 SfMData landmarks + 真实 observations，即可完全绕过 AliceVision depth estimation/filtering。
- **NO，对裸 PLY/XYZ**：AliceVision 的 PLY loader 只导顶点/颜色、清空 SfMData、没有 cameras/observations；`main_meshing` 随后会报没有 camera。[PLY loader](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/sfmDataIO/plyIO.cpp#L110-L166)
- 给每点伪造“所有相机均可见”可能跑起来，但会破坏自由空间投票语义，不能作为保真输入。

本地 3.62M PLY 没有 visibility，capture sparse 又是 0 points/0 observations，因此要从 masked depth、相机和 fusion provenance **重新生成每点可见相机列表**。这是当前第一输入阻塞。

## B3 COLMAP `delaunay_mesher`：算法族、输入、license 与质量差距

### 同族，但方法来源不同

| 维度 | COLMAP `853506…` | AliceVision `8fac66…` |
|---|---|---|
| 论文族 | [Labatut–Pons–Keriven 2009](https://doi.org/10.1111/j.1467-8659.2009.01530.x)，header 明示 | [Jancosek–Pajdla 2011/2014](https://doi.org/10.1155/2014/798595) 弱支撑扩展 |
| Delaunay | CGAL `Delaunay_triangulation_3`，exact predicates/inexact constructions | Geogram internal `BDEL` |
| unary/visibility | camera-to-point rays，visibility/distance likelihood | empty/full ray votes、`nrc`、弱支撑 T-edge forcing |
| regularization / 后处理 | Labatut facet shape regularization | bubble/dust/camera-cell/consistency/solid-angle 等额外处理 |
| max-flow | Boost Boykov–Kolmogorov | Boost Boykov–Kolmogorov |
| CUDA | 不需要 | 不需要 |

COLMAP header 明示 Labatut 实现。[delaunay_meshing.h](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/delaunay_meshing.h#L72-L89) CGAL 和 ray integration 分别见 [Delaunay include](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/delaunay_meshing.cc#L47-L59) 与 [ray votes](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/delaunay_meshing.cc#L627-L782)。AliceVision 的 weak-support classifier 直接关联论文 Equation 6。[GraphFiller](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/GraphFiller.cpp#L267-L475)

### COLMAP 输入不是普通 PLY

CLI 的 `input_type` 只有 `dense` / `sparse`。[mvs.cc](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/exe/mvs.cc#L75-L112)

- `sparse`：读 COLMAP reconstruction，用 points3D 的 tracks 当 visibility。
- `dense`：读 `sparse/`、`fused.ply`、`fused.ply.vis`。[loader](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/delaunay_meshing.cc#L180-L215)
- `.vis` 与 PLY 顶点按位置一一对应：`uint64 point_count`，每点 `uint32 visibility_count` 加若干 `uint32 image_index`。[fusion format](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/fusion.cc#L561-L594)
- `image_index` 是 registered-image 的加载顺序 offset，不是数据库 image ID。adapter 必须逐项验证。

所以 CasDiff 云可导入 minimal dense workspace，但必须有相机和正确 `.vis`；单独 PLY 不够。

### 本地 vendor 并没有这条执行路径

PocketWorld vendor CMake 只 glob `util/math/geometry/sensor/scene/estimators/optim`，没有 `colmap/mvs`；还显式移除 `graph_cut.cc`，并明确让 `COLMAP_CGAL_ENABLED` 等 optional features 不定义：

- [`CMakeLists.txt` source set](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/CMakeLists.txt:17)
- [`graph_cut.cc` exclusion](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/CMakeLists.txt:34)
- [optional features undefined](/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/CMakeLists.txt:123)

**CONFIRMED**：源码文件存在不等于产品 binary 含 `delaunay_mesher`。要接入必须新增 MVS/Delaunay、graph-cut、PLY/fusion 依赖和 CGAL；这会触发下面的许可证硬冲突。

### License 与质量证据

- COLMAP 自身 BSD-3-Clause：`conditional`，需 notices/non-endorsement。[COPYING](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/COPYING.txt#L1-L33)
- 所用 CGAL `Delaunay_triangulation_3.h` 属 `GPL-3.0-or-later OR LicenseRef-Commercial`；对计划中的闭源组合分发是 **`conflict`**，除非取得覆盖版本/平台的 CGAL commercial rights 或不用该实现。本机 Homebrew 研究 route 的 SBOM 冻结为 CGAL 6.1.1；对应 tag 的 [header SPDX](https://github.com/CGAL/cgal/blob/08b27d3db14039d926c3a89d12955aa28fd55171/Triangulation_3/include/CGAL/Delaunay_triangulation_3.h#L1-L20) 与发行许可证文件 [Installation/LICENSE](https://github.com/CGAL/cgal/blob/08b27d3db14039d926c3a89d12955aa28fd55171/Installation/LICENSE#L1-L15) 直接支持该结论。不同 source build 若解析到别的 CGAL 版本，必须重新冻结。
- Jancosek 2014 论文在弱支撑/欠采样实验上优于论文中的 Labatut baseline，且强支撑输入精度总体可比；这只支持算法扩展的动机。
- **没有找到当前 COLMAP vs 当前 AliceVision、同 points/cameras/visibility/参数的公开客观 A/B。** 当前软件质量差距是 **UNVERIFIED**，不能把论文 baseline 差异直接当实现排名。
- 固定 AliceVision 源码能确认其 Jancosek/Pajdla 算法血缘；本次没有找到可审计的一手材料证明当前 RealityCapture/RealityScan 生产 mesher 与当前 `fuseCut` 代码等价、参数等价或输出等价。发明人/团队沿革不能替代 proprietary implementation 证据，因此“同源”只能作历史背景，不能进入质量结论。

## B4 macOS arm64：最省力路线、真实代价与失败模式

### 路线 1：立即做研究基线——现有 Homebrew COLMAP

本机 `/opt/homebrew/bin/colmap` 已安装：formula `3.13.0_4`、CLI 3.13.0、arm64、without CUDA；binary SHA-256 `934031d17ca79364c140008296ed71499e6e74db4cf6c5f1135e8438e5760e56`，`delaunay_mesher -h` 已确认有 `dense/sparse` 和全部 Delaunay 参数。其 Homebrew SBOM SHA-256 为 `786cb2dd323fde839862762e8876ec6d7f8414fb2bebbd399bbd1cd2aba1ad92`，明确列 CGAL 6.1.1；install receipt SHA-256 `e387e9ac7d369eb0f9670e409e97f8e033a397a6eefff307947619991dfdd134`。当前 `Delaunay_triangulation_3.h` SHA-256 `a34c64bc74f39877e777d2de669ecb52e540e56aee56a15e9be8614947812ba8`。

这是一条**最低操作量的研究基线**，不是固定 `853506…` 的精确复现，也不能跨过 CGAL 的产品分发门。可在 visibility adapter 完成后先跑小的 bounded subset。

### 路线 2：固定 COLMAP revision 的 source-pinned Mac 基线

固定 SHA 的上游 workflow 已在 `macos-15 arm64 Release` 完成 Homebrew 依赖、Ninja build 和 tests；Delaunay 测试覆盖 sparse、dense 和 non-subsampled 小用例。[不可变成功 run/job](https://github.com/colmap/colmap/actions/runs/29781397883/job/88483228732)、[workflow source](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/.github/workflows/build-mac.yml)、[test source](https://github.com/colmap/colmap/blob/85350623e67c5a074dd36808de4aefadd4e805f2/src/colmap/mvs/delaunay_meshing_test.cc)

```bash
cmake -S /path/to/colmap-85350623 -B /path/to/colmap-build -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCUDA_ENABLED=OFF \
  -DONNX_ENABLED=OFF \
  -DGUI_ENABLED=OFF \
  -DOPENGL_ENABLED=OFF \
  -DDOWNLOAD_ENABLED=OFF \
  -DMVS_ENABLED=ON \
  -DCGAL_ENABLED=ON \
  -DTESTS_ENABLED=ON

cmake --build /path/to/colmap-build \
  --target colmap_main colmap_mvs_delaunay_meshing_test

ctest --test-dir /path/to/colmap-build \
  -R '^mvs/delaunay_meshing_test$' --output-on-failure
```

该**裁剪配置组合**没有在本机执行，仍标记 UNVERIFIED；上游证明的是同 source revision 的 arm64 CI，不是 3.62M 数据峰值。命令中的 Homebrew dependencies 没有 lock manifest/SBOM，因此这里只能称 **source-pinned**，不能称整体可复现。

### 路线 3：目标 fuseCut——AliceVision 无 CUDA 构建

2026-04 合并的 macOS 支持声明 arm64/x86_64 与 Ninja/Make 可用，但没有 macOS CI；PR 记录两个 macOS 单测失败，维护者也没有 Apple hardware 独立验证。[PR #2019](https://github.com/alicevision/AliceVision/pull/2019) 官方文档推荐 embedded dependencies，明确外部 package-manager 依赖不受支持，Xcode generator 不适用于 embedded superbuild。[INSTALL_macOS](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/INSTALL_macOS.md)

在官方仓库、Homebrew/conda-forge/vcpkg 路径的有界检索中，没有找到与固定 SHA 对应、由 AliceVision 官方验证的 Apple-Silicon 预编译包；也没有可替代 embedded route 的受支持 Homebrew/conda 安装说明。仓库有 vcpkg manifest，但项目的 macOS 文档不把它列为受支持路线，而且其默认 Geogram closure 有 B5 的许可证阻塞。应把“有 manifest”与“有可复现 arm64 binary”分开。

外层 superbuild **不会自动转发** `ALICEVISION_USE_SYCL`：固定 [`ConfigureOptionsMerger.cmake`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/cmake/ConfigureOptionsMerger.cmake#L25-L30) 明确转发 CUDA，[但列表中没有 SYCL](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/cmake/ConfigureOptionsMerger.cmake#L83-L85)。因此在执行下列命令前，必须给该 merger 增加并记录补丁 SHA：

```cmake
if(DEFINED ALICEVISION_USE_SYCL)
  list(APPEND AV_TOPLEVEL_FLAGS
       -DALICEVISION_USE_SYCL=${ALICEVISION_USE_SYCL})
endif()
```

同时在固定 [`src/cmake/deps/geogram.cmake` L37–50](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/cmake/deps/geogram.cmake#L37-L50) 的 `EXTRA_CMAKE_FLAGS` 加 `-DGEOGRAM_WITH_TRIANGLE=OFF`。完成并冻结这两个补丁后，官方方向的命令形状才是：

```bash
cmake -S /path/to/AliceVision-8fac66f8 \
  -B /path/to/av-build -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_INSTALL_PREFIX=/path/to/av-install \
  -DALICEVISION_BUILD_DEPENDENCIES=ON \
  -DAV_BUILD_DEPENDENCIES_PARALLEL=4 \
  -DAV_USE_CUDA=OFF \
  -DAV_BUILD_CUDA=OFF \
  -DALICEVISION_USE_CUDA=OFF \
  -DALICEVISION_USE_SYCL=OFF \
  -DALICEVISION_BUILD_TESTS=OFF

cmake --build /path/to/av-build
cmake --install /path/to/av-build
```

原因见 B5。只在外层 CLI 写 SYCL/Triangle 变量都不足以证明内层收到；AliceVision 的 inner tree 是 `/path/to/av-build/aliceVision_build`，[由 `ExternalProject` 定义](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/cmake/Dependencies.cmake#L225-L274)。必须检查 inner 与 Geogram effective CMake cache。

如果已经有一套 ABI 一致的 arm64 dependency prefix，理论上可 direct configure 并只 build `aliceVision_meshing_exe`；但 MVS 会在 SFM OFF 时被强制关闭，配置仍拉入 Ceres、Lemon、OpenImageIO/OpenEXR、Geogram、Assimp、OpenMesh、Boost 等闭包。官方 superbuild 又不暴露内部 leaf target，实际上会构建完整 inner project。**“只编 meshing 就很轻”不成立。**

### 真实失败模式

- `/opt/homebrew`、`/usr/local`、MacPorts 或 x86_64/arm64 混用，导致 late link architecture mismatch 或运行期 `dyld` 缺库。
- CMake 4、旧 Bison/autoconf/automake/pkg-config/gettext/m4、错误 generator 提前失败。
- superbuild 会拉 ONNX/OpenCV/USD/FFmpeg 等大量组件；上游没有空间账，当前 24 GiB 可用空间风险很高，故本次不启动。
- 首次启动可能被 XProtect 扫描大量 dylib 阻塞数分钟，不能立即判死锁。
- `partitioning=auto` 实际未实现，不能用它解决大输入。
- Apple-arm64 能 build `aliceVision_meshing`、能读自制 `.sfm`、能在 3.62M 点完成，三件事目前都分别是 **UNVERIFIED**。

## B5 上手机：license、内存量级与公开先例

### 许可证硬门

| 路线 | 精确问题 | 工程结论 |
|---|---|---|
| AliceVision source | MPL-2.0 文件级 copyleft；分发 executable 时需提供 Covered Software 源码、保留 notices，并说明获取方式 | `conditional` |
| AliceVision 内建 Geogram 1.9.6 | 顶层 BSD-3，但 AliceVision recipe 只关 HLBFGS/TetGen，**未关默认 ON 的 Triangle**；Triangle 要求商业系统另行直接安排。Triangle object 会进入 `geogram` library。 | 当前配置 `block`；加 `GEOGRAM_WITH_TRIANGLE=OFF` 且产物扫描后再判 |
| AliceVision vcpkg Geogram | 默认还包含 HLBFGS、TetGen、Triangle；分别有 noncommercial/AGPL-or-contact/commercial-arrangement 问题 | `block` |
| COLMAP Delaunay | COLMAP BSD，但 CGAL 3D Triangulations 是 GPL-3-or-commercial | 闭源组合分发 `conflict`；commercial CGAL 后可重新判 |
| OpenMVS 2.4 | 顶层 AGPL、CGAL；默认 IBFS bundled license 限 research | `conflict` / IBFS `block` |
| DiffMVS source | Apache-2.0，需 license/notice/修改标记，含专利 grant | source `conditional` |
| CasDiffMVS checkpoint | Drive artifact 未给独立权重许可证、NOTICE、可追溯 revision；当前本地 DTU checkpoint 虽有 hash，权利链仍缺 | `insufficient-evidence` |

Geogram 的证据链是直接的：1.9.6 顶层是 [BSD-3-Clause](https://github.com/BrunoLevy/geogram/blob/fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8/LICENSE#L1-L28)，但默认 [`GEOGRAM_WITH_TRIANGLE=ON`](https://github.com/BrunoLevy/geogram/blob/fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8/CMakeLists.txt#L40-L45)，第三方 object list 在开关 ON 时[加入 Triangle](https://github.com/BrunoLevy/geogram/blob/fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8/src/lib/geogram/third_party/CMakeLists.txt#L72-L76) 并链接进 geogram；Triangle 源文件写明 commercial system 只能通过 direct arrangement。[triangle.c license header](https://github.com/BrunoLevy/geogram/blob/fc3eb9bf44d2ee29686592e3ef5f5f4daeda27f8/src/lib/geogram/third_party/triangle/triangle.c#L23-L35) fuseCut 的 `BDEL` 是 Geogram internal 3D Delaunay，不需要这个 2D Triangle，因此关闭它是技术上合理但仍需 build/test 证明的清理。

没有运行 ScanCode/ORT；实际 resolved build、optional I/O、静态/动态链接、notices 和平台打包闭包仍是 `insufficient-evidence`。这也是为什么不能用“顶层 BSD/MPL”替代产物审计。

### 3.62M 点的内存量级

对固定 AliceVision `8fac66f8…` 的 source-visible fields 做下界账。相关结构与 v3.3.0 对应文件的 Git blob 逐字节相同。令 `n` 为点、`T` 为 tetra cells、`J` 为 vertex-cell incidences、`I_ff` 为 finite-finite 无向 facets、`B_f∞` 为 finite-infinite facets，实际 `addEdge()` 循环次数 `P=2I_ff+B_f∞`。`addNode` 与 `addEdge` 每次都创建正反 records，因此 directed graph records 的精确计数是：

\[
A=2T+2P=2T+4I_{ff}+2B_{f\infty}.
\]

只丢掉非负的边界项即可得保守下界：

\[
M_{min}\ge24n+64T+4J+8(2T+4I_{ff}).
\]

这里使用标准 non-GARGANTUA Geogram 的 32-bit `GEO::index_t`；若实际是 64-bit，地板只会增加。字段证据来自 [`Point3d`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/mvsData/Point3d.hpp#L24-L34)、[`Cell`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/Tetrahedralization.hpp#L87-L90)、[`GC_cellInfo`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/delaunayGraphCutTypes.hpp#L17-L24) 和 [`MaxFlow_AdjList`](https://github.com/alicevision/AliceVision/blob/8fac66f838014022b5b9ea00af5b72e28a06d79e/src/aliceVision/fuseCut/MaxFlow_AdjList.hpp#L30-L108)。

在边界可忽略时 `J≈4T`、`I_ff≈2T`，得 `M_min≈24n+160T`。这是**给定实际 `T` 后**的字段下界。以 3D homogeneous Poisson-Delaunay 的解析期望 `T/n=24π²/35=6.7677` 作为**拓扑锚点而非 PocketWorld 实测**，`n=3.62M` 时得到 graph-phase 可见字段的**场景估计**约 **4.0067 GB / 3.7316 GiB**；它不是当前表面型点云的严格下界或 RSS 预测。

这个估计还不含：graph endpoints/reverse descriptors、Boost containers/allocator、max-flow working arrays、camera lists、Geogram construction workspace、ray traversal、mesh extraction和 App 其他内存。Poisson 比率不是 surface-biased MVS cloud 的预测；实际必须记录 `T/n`。按相同字段模型，超过 2.4 GiB 需要实际 `T/n>4.2981`，超过十进制 3.0 GB 需要 `T/n>5.0283`（超过 3 GiB 则约 `>5.4115`）；这些门目前都**未测**。因此可以判“global layout 高风险、当前不应直接投入产品移植”，不能判数学上已经由这份点云证实 OOM。

历史实测提供第二条独立证据：Labatut 2009 Table 1 报告 362K points 306 MB、1.77M 1.6 GB、4.413M 6.5 GB、6.592M 9.9 GB；算法和机器较旧，不能当当前实现预测，但与“数百万点 global tetra graph 很重”方向一致。[论文 DOI](https://doi.org/10.1111/j.1467-8659.2009.01530.x)

CGAL 旧版 64-bit benchmark 的 triangulation-only 为 519–553 B/point；线性外推 3.62M 是 1.88–2.00 GB，仍没图割。3D Delaunay 最坏可达 `Θ(n²)` cells，不能给出线性安全上界。[CGAL manual](https://doc.cgal.org/Manual/latest/doc_html/cgal_manual/Triangulation_3/Chapter_main.html)

### 移动公开先例

最接近的真实先例是 Pan et al. ISMAR 2011 [“Rapid Scene Reconstruction on Mobile Phones from Panoramic Images”](https://www.edwardrosten.com/work/pan_2011_rapid.pdf)：Nokia N900、600 MHz Cortex-A8、256 MB，QHull Delaunay + probabilistic visibility space carving，**没有 global graph cut**。三个样例只有 499/511/539 landmarks；Delaunay 0.5–0.7s、space carving 4.1–6.7s、输出 1,013–1,249 triangles。[DOI](https://doi.org/10.1109/ISMAR.2011.6092370) 3.62M/539≈6716，因此它只证明微型 visibility carving 能在手机跑。

有手机端 TSDF/voxel、连续 max-flow、ARKit mesh-anchor 先例，但它们不是 tetrahedral Delaunay + visibility + global cut。经 IEEE/CVF、官方仓库与平台文档的有界检索，**未找到百万点级 iOS/Android 完整同族公开实现**；这是 bounded negative result，不是不存在证明。

跨端源码可编译性也未闭环：Geogram 有 Android/Apple/arm64 条件分支，但 AliceVision 没有 iOS、Android 或鸿蒙的 install/CI target；当前 macOS preset 不能当 iOS 证据。Boost Graph 是 C++ 模板并不等于整个 OpenMP、image/SfM I/O、allocator 和打包闭包可上各端。固定源码检索也未找到鸿蒙公开先例。若走 packed 自研路线，应把核心收敛成无异常/无 RTTI 假设可控、无 OpenMP 硬依赖、packed arrays + 自有线程池的纯 C++ 模块，再分别建立 iOS/Android/鸿蒙 CI；Dawn/WGSL 只在有独立验证后用于局部并行步骤，不能先假定可替代全局 Delaunay/max-flow。

因此，本次**没有找到**同时满足“现成、同族、百万点移动端、闭源商业分发证据完整”的更轻实现。Mostegel-style partitioning 是论文级架构先例，不是已审计可直接嵌入的库；自研 packed core 仍要处理专利/FTO、第三方源码和平台构建审计。

## B6 Mac 与手机推荐路线（可行性硬门 × 算法保真度）

### Mac

| 顺序 | 路线 | 可行性证据 | 保真度 | 硬门/停止条件 |
|---:|---|---|---|---|
| 1 | 现有 Homebrew COLMAP 做**研究基线** | 本机 binary/CLI 已确认；无 CUDA | 同一广义家族，Labatut 而非弱支撑扩展 | 只用于研究；adapter `.vis` 必须通过；不得把 CGAL 冲突带入产品 |
| 2 | Triangle-free AliceVision `meshing` 做**目标候选** | CMake 无 CUDA；Apple arm64 source support | 当前候选中最接近 Jancosek weak-support | 先释放空间；patch dependency recipe；build/SBOM/license scan；small fixture；再上 3.62M |
| 3 | 固定 SHA COLMAP source build | 上游 arm64 CI 已通过 | 与路线 1 相同；source-pinned | dependencies/SBOM 仍需锁；仍有 CGAL 产品门 |
| 4 | 继续当前 TSDF | 已有认证产物 | 不同算法 | 作为非劣基线，不是 fuseCut 复现 |

Mac 的“最快看到结果”和“最终产品候选”不是同一条：前者是已安装 COLMAP，后者应是清理许可证后的 AliceVision fuseCut。只有同输入 A/B 指标通过后才决定是否替换 TSDF。

### 手机

| 顺序 | 路线 | 可行性 | 保真度 | 判断 |
|---:|---|---|---|---|
| 1 | packed 分区：局部 Delaunay + 局部 cut + 二次 hypothesis-merging cut | Mostegel 2017 有桌面算法先例；需全新 packed/streamed 实现 | 比 TSDF 更保留 Delaunay visibility 思路 | **首选研究路线；尚非可发货实现** |
| 2 | halo-tiled fuseCut + compact CSR/max-flow + 边界假设合并 | 机制上可界定局部峰值 | 可保留更多 fuseCut energy，但全局 weak-support 与 seam 未确立 | **次选研究路线** |
| 3 | 当前 TSDF | 移动端先例和现有产品路径最强 | 与目标算法不同 | **生产基线，直到 1/2 通过完整非劣门** |
| 4 | 去图割的 Delaunay visibility carving | 只有极小规模手机先例 | 拓扑优化不同 | **不作为弱支撑等价替代** |
| 5 | current global AliceVision/COLMAP/OpenMVS 直移植 | 内存为强风险但实际 `T/n` 未测；平台、许可证另有独立阻塞 | 表面上最接近，但当前证据不足以通过产品门 | **当前计划拒绝；不是理论不可能证明** |

[Mostegel et al., CVPR 2017](https://openaccess.thecvf.com/content_cvpr_2017/papers/Mostegel_Scalable_Surface_Reconstruction_CVPR_2017_paper.pdf) 的 partitioned 方法以局部重建再 graph-cut 合并 surface hypotheses；但其桌面实现即使最大 leaf 仅 8K points，峰值仍为 2.2 GB（32K/128K/512K 时 3.1/8.9/25.3 GB）。所以可借算法结构，不能照搬数据结构。

# 客观评测方案

以下是**实现前预注册的验收协议**，不是已经取得的结果。阈值应在看最终输出前冻结；任何变更都作为 deviation 记录。

## 1. 全分辨率 MVS 对照

### Cohort 与变量

- full run 用 `lapa` 注册帧与 native 4224×2376 的交集：395 帧。
- 第一阶段只跑 24 个 spatial-order quantile references；列表 hash `3f166524cd6925f3dc621b23290753586689315e103c67a2a874043e0f3a5134`。
- 18 张 3840×2160 单列 robustness cohort；不能 upscale 后称为 native 4224 结果。
- 主实验固定为当前 runner 的 **3 个总视图（1 reference + 2 source）**、同一 source ranking、checkpoint/hash、相机、depth sample count、fusion gates、dtype/backend、seed 与 output coordinate system。[当前 view 选择](/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/pw_diffmvs_run.py:96)、[CLI default](/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/pw_diffmvs_run.py:162)
- 5 个总视图另列 `-V5` ablation；每个 V5 变体都必须有同样 V5 的 whole/baseline 对照，不能与 V3 峰值或质量直接相减。

| ID | 定义 | 隔离的变量 |
|---|---|---|
| `B896` | 当前 3-view 语义的 896×512 resize，global per-reference range | 基线 |
| `TG` | native 4224×2376 → frozen pad 4224×2400；896×512 envelope tiled；global range | resolution + tiling |
| `TL` | 与 TG 相同，但用 deterministic tile-local range + global fallback | range narrowing |
| `TG-shift` | TG 的 grid 平移半个 retained stride | seam/grid-phase sensitivity |
| `U1792` | 同一张图确定性 resize/pad 到 1792×1024 后 whole inference | 同分辨率 whole reference |
| `T1792` | 与 `U1792` **完全相同的 1792×1024 raster/K/views**，只改为 896×512 envelope tiled | 因果隔离 tiling |
| `UF` | 4224×2400 whole inference，只在安全预检通过时 | 最强 whole reference；不强行执行 |

Tile contract：每次 model tensor envelope 不超过 896×512；halo 必须包含在 envelope 内，不能在 896×512 core 外再加。先做 `h={64,128,192,224}` 的受控 sweep；由于 stage-1 静态下界约 188 px，`h<192` 只能作为反例，不能先验视为安全。若后续层所需 halo 使有效 core 退化，应转为 operator-level intermediate exchange，不可默默缩 halo。

source crop 必须覆盖 reference core 在 `[dmin,dmax]`、所有 48 初始 hypotheses、所有 source cameras 下的投影 footprint，再加 feature/bilinear halo。超出 896×512 时递归拆 core 或返回 `SOURCE_FOOTPRINT_OVERFLOW`，不得静默换 source。输出严格 crop 回 4224×2376。

### Determinism

- primary seed `20260721`，同时固定 Python/NumPy/Torch/PYTHONHASHSEED，single worker，feature cache off。
- 对每个 seed、raster 与 refinement stage，预先生成一份按全图坐标索引的 canonical-noise tensor，持久化 dtype/shape/layout 与逐文件 SHA-256；whole 与 tile 路径都只能从同一随机场按坐标读取，不能各自调用 `randn_like`。报告必须同时保存 noise manifest hash；相同 seed 但随机调用 shape/顺序不同，不算同一噪声条件。
- 24-ref gate 另以 seeds `0,1,2` 重复，因为官方 refinement 使用非零 DDIM eta。
- 同 seed duplicate 必须复现 depth/mask hashes；否则标 `NONDETERMINISTIC_BACKEND`，报告分布而不是单值。

### 深度/融合指标与门

Tiling 本身的受控因果比较必须是 **`T1792` vs `U1792`**：相同 raster、K、views、range、seed、backend，只改变 tiling。Full-resolution 的严格比较只允许 **`TG` vs `UF`**。若 `UF` 被资源门阻止，绝不能用 `U1792` 代替 TG 的 whole reference；TG 只能报告 shifted-grid、seam、cross-view 和 held-out observation consistency，最终结论上限为 PARTIAL。没有独立真值时，下列是**数值等价/观察一致性**，不能称绝对 accuracy。

| 指标 | 建议非劣门 |
|---|---:|
| reference 有效覆盖 | ≥98% |
| valid-mask IoU | ≥95% |
| AbsRel depth | median ≤0.5%，P95 ≤2%，≥90% pixels <1% |
| shifted-grid disagreement | P95 AbsRel ≤1%，mask IoU ≥98% |
| seam band（join ±8 px）对 matched interior 的 P95 增量 | ≤0.5 percentage points |
| seam valid-coverage deficit | ≤1 percentage point |
| 几何一致保留率 | 1 px / 1% depth；主实验须由全部 3 个总视图（reference + 两个 source）支持；比同配置 whole reference 低不超过 2 points |
| 统一 5 mm voxel 后 cloud bidirectional agreement/completeness | ≥95% @5 mm |
| symmetric cloud distance | mean ≤2.5 mm，P95 ≤5 mm |
| normal consistency | median dot ≥0.95 |

同时报告 cross-seam log-depth-gradient residual、confidence delta、invalid rate，并按 texture、depth discontinuity、view support 分层。`TL` 额外报告 sparse-range anchor coverage、fallback frequency、interval width、clip/miss rate；没有这些数，不能说范围收窄无损。

fp16、metric-uint16、inverse-depth-uint16 分开做 spool ablation：P99 relative quantization error ≤0.1%，且最终 5 mm cloud agreement with fp32 ≥99.5% 才通过。

### 内存与停止规则

Mac 对每个 A/B pair 跑六个 fresh process，固定 `A-B-B-A-A-B` 平衡顺序，即每个变体三次：

- `TASK_VM_INFO.phys_footprint` 20 Hz；
- `/usr/bin/time -lp` maximum RSS 交叉检查；
- MPS `driver_allocated_memory/current_allocated_memory` 20 Hz；
- 分开报告 absolute peak 与 model-loaded idle 增量；统一内存不重复相加。

`UF` 只在 896×512、1344×768、1792×1024 probe 的 robust upper prediction <70% physical RAM 且剩余 >4 GiB 时启动；否则 `UNTILED_REF_UNAVAILABLE_RESOURCE`。

iPhone 14 Pro 固定 `.cpuAndGPU`，20 Hz footprint/available-memory/thermal；无 memory warning/jetsam，峰值 ≤2.4 GiB。主内存门使用相同 3-view `B896`/`TG`；V5 只能和 `B896-V5` 比。tiled “持平”门为：

```text
TG peak <= B896 peak + max(32 MiB, 5% * B896 peak)
```

Scale ladder 只能诊断；不能替代 full-resolution/full-cohort pass。

## 2. 成面方案共同输入 A/B

### 两层 canonical contract

1. `observations-v1`：冻结 413 frame 的 depth/confidence/mask/K/world-to-camera/images/source lists/normals/per-pixel view provenance。
2. `cloud-visibility-v1`：同一 fused XYZ/RGB/confidence 加每点**排序后的 observing image IDs**。

AliceVision、COLMAP、TSDF adapter 都必须来自同一 canonical observations；camera ray round-trip relative error ≤`1e-6`，point coordinates ≤`1e-6` model units。只在所有 mesh 结束后施加同一 frozen `lapa→ARKit` Sim(3)，不得各自 ICP。

现存 PLY 没 visibility，必须从 masked depth cache 重建。若 AliceVision 吃 depth maps 而 COLMAP 吃另一个过滤云，标 `ROUTE_INPUT_NOT_EQUIVALENT`，该 A/B 无效。

### Reconstruction / held-out split

- full resource run：413 registered frames。
- held-out run：spatial refs 每五个取一个，自 index 4 起；331 reconstruction / 82 evaluation。
- held-out list hash `5e16f68e603af0b3e27b6957ba0dad0fc0fbeec1d068a04e0b22a2ed78696805`。
- training list hash `d2dca3eac2f8efbf18b1efdd9e08b0a6e9b504eb71af378b4444bff035e54a41`。

### Ground-truth-free 指标

- held-out rendered-depth completeness，tolerance `max(20 mm, 2% depth)`；
- median/P95 signed 与 absolute relative held-out depth discrepancy；
- low-texture、3–4 supporting views 的分层 coverage；
- canonical cloud→mesh、mesh→cloud 5/10/20 mm 距离；truncated Chamfer 只称 input-agreement；
- normal angular agreement @10°/@20°；
- observed-ray missing fraction 与 5 mm voxel deduplicated missing-area proxy；
- boundary-loop count/length、components、surface area、vertices/faces、degenerate/non-manifold fractions、self-intersections；
- frozen wall/floor plane ROIs 的 residual RMS/P95、double-shell rate/separation；
- held-out multiview Census/gradient reprojection residual；
- peak footprint、swap、wall/CPU time、input points、tetra cells、graph nodes/edges。

当前 ARKit PNG 契约未验证，因此不能把上述指标叫 true completeness、true hole area 或 ground-truth accuracy。若以后获得标定可靠的独立几何真值，再加 absolute Chamfer/F-score。

### 相对当前 6 mm TSDF 的非劣门

| 指标 | 门 |
|---|---:|
| total / low-texture / weak-support coverage | 不低于 −2 percentage points |
| unsupported surface >20 mm | 不高于 +2 points |
| median AbsRel | 不高于 +0.5 points |
| P95 AbsRel | 不高于 +2 points |
| median normal error | 不高于 +2° |
| double-shell rate / P95 separation | 不高于 +1 point / +5 mm |
| non-manifold edge fraction | ≤`1e-4` |
| finite output | 不允许 non-finite vertex/face |

声称“更好保存弱支撑面”还必须：以 frame 为单位 paired bootstrap 10,000 次、seed `20260721`，low-texture/weak-support coverage 改善的 95% lower CI ≥+5 percentage points，同时所有非劣门通过。

### Resource gates

- Mac M3 Pro：3.62M full route 峰值 ≤12 GiB、swap growth ≤4 GiB、wall time ≤4 h。
- iPhone 14 Pro：full route <2.4 GiB、无 warning/jetsam、wall time ≤2 h。
- 开始前 free disk ≥15 GiB 且 ≥声明 worst-case intermediate/output 的 3 倍；否则 `DISK_GUARD`。

这些是产品工程停止规则，不是算法理论极限。timeout 记 `TIMEOUT`，不能推出算法不可能。

## 3. 必需 artifact schema

每个 run 保存：

- `contract.json`：prompt/repo/input/checkpoint hashes、cohort/view lists、参数、阈值、seeds、hardware/backend、stop rules；
- `status.json`：`COMPLETE/INVALID/STOPPED`、reason code、command、binary/tool hashes、exit/signal；
- `resources.ndjson`：footprint/RSS/MPS 或 iOS memory、CPU、disk、thermal；
- `tiles.jsonl`：frame/source IDs、crop/pad、shifted K、depth range、projection coverage、output hashes、valid counts；
- selected raw depth/conf/mask、canonical cloud+visibility、raw/normalized meshes；
- `metrics/frame.jsonl`、`metrics/aggregate.json`、CI、topology report、stdout/stderr、`artifacts.sha256`。

失败和 partial run 不删除。标准 reason codes 至少包括：`INPUT_HASH_MISMATCH`、`CALIBRATION_DIM_MISMATCH`、`SOURCE_FOOTPRINT_OVERFLOW`、`RANGE_CLIP`、`ADAPTER_ROUNDTRIP_FAIL`、`ROUTE_INPUT_NOT_EQUIVALENT`、`NONFINITE_OUTPUT`、`EMPTY_MESH`、`OOM_HOST`、`OOM_BACKEND`、`JETSAM`、`DISK_GUARD`、`THERMAL_ABORT`、`TIMEOUT`、`NONDETERMINISTIC_BACKEND`、`UNTILED_REF_UNAVAILABLE_RESOURCE`。

# 未确立：要什么文件/命令才能定论

## U1 实际部署的 CasDiffMVS artifact 和调用仍未冻结

当前 runner CLI default 是 `diffmvs`，checkpoint default 是 DTU；不能仅凭文件存在断言产品实际 method/weights/export shape。

所需文件：CoreML converter source、`.mlpackage/.mlmodelc`、实际 checkpoint、build config、调用日志。

```bash
shasum -a 256 /ABS/casdiffmvs.ckpt /ABS/model.mlmodel
find /ABS/model.mlpackage /ABS/model.mlmodelc -type f -exec shasum -a 256 {} \;
/usr/bin/plutil -p /ABS/model.mlmodelc/metadata.json 2>/dev/null
rg -n 'CasDiffMVS|AETHER_CKPT|computeUnits|cpuAndGPU|mlmodel' /ABS/product /ABS/converter
```

冻结 input/output shapes、dtypes、compute-unit policy、view count、depth bounds、checkpoint domain 与 seed 后，A4 才能从源码估算升级为设备结论。

## U2 tiled driver 不存在，halo/source footprint/质量未知

建议的新接口（**规格，不是现有文件**）：

```bash
python3.11 tools/python/pw_fullres_eval.py plan \
  --capture /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229 \
  --pose-bundle tools/python/diffmvs_out/trio_model_lapa.npz \
  --checkpoint tools/python/diffmvs/checkpoints_unz/casdiffmvs_dtu.ckpt \
  --seed 20260721 \
  --canonical-noise-dir /ABS/RUN/canonical_noise \
  --out /ABS/RUN/contract

/usr/bin/time -lp env PYTHONHASHSEED=20260721 AETHER_CKPT=dtu \
  python3.11 tools/python/pw_fullres_eval.py run \
  --contract /ABS/RUN/contract/contract.json \
  --variant B896,TG,TL,TG-shift,U1792,T1792,UF \
  --num-views 3 \
  --backend mps --stream-fuse --out /ABS/RUN/mvs

python3.11 tools/python/pw_fullres_eval.py score \
  --contract /ABS/RUN/contract/contract.json \
  --runs /ABS/RUN/mvs --out /ABS/RUN/metrics
```

`contract.json` 必须记录 canonical-noise manifest SHA-256，并在 score 前验证 `U1792/T1792`、`UF/TG` 分别消费同一组逐坐标随机场；仅记录相同 seed 不足以通过 determinism 门。

只有 A1–A5 的 whole-vs-tile、shifted-grid、seam 和 footprint 门都通过，才能把 PARTIAL 改为 YES。

## U3 AliceVision arm64 binary、Triangle-free closure 和 input adapter 未验证

先在空间充足的隔离目录配置固定 SHA；检查实际 target 和 CMake cache：

```bash
av_inner=/ABS/av-build/aliceVision_build
test -f "$av_inner/CMakeCache.txt"

rg -n '^ALICEVISION_USE_(CUDA|SYCL):.*=OFF$' \
  "$av_inner/CMakeCache.txt"

cmake --build "$av_inner" --target help | \
  rg 'aliceVision_(depthMapEstimation|depthMapFiltering|meshing|meshFiltering|texturing)_exe'

find /ABS/av-build -name CMakeCache.txt -exec \
  rg -n '^GEOGRAM_WITH_(TRIANGLE|TETGEN|HLBFGS):.*=OFF$' {} \;

find "$av_inner" -type f -name aliceVision_meshing -exec otool -L {} \; | \
  rg -i 'cuda|cudart|nvrtc|triangle|tetgen'

git -C /ABS/AliceVision diff -- \
  src/cmake/ConfigureOptionsMerger.cmake src/cmake/deps/geogram.cmake | \
  shasum -a 256
```

期望：inner target list 中 `depthMapEstimation/depthMapFiltering` 缺席，`meshing/meshFiltering/texturing` 存在；CUDA/SYCL 都 OFF；Geogram 三个受限模块均 OFF。空的 `otool | rg` 结果只证明无动态依赖，不能证明静态对象未进入，所以还要保存 build graph/SBOM、两个补丁 SHA，并运行 pinned broker：

```bash
/Users/kaidongwang/.codex/plugins/cache/personal/research-evidence-stack/1.0.0/scripts/research-audit versions

/Users/kaidongwang/.codex/plugins/cache/personal/research-evidence-stack/1.0.0/scripts/research-audit \
  scancode /ABS/pinned-source \
  /Users/kaidongwang/.codex/research-evidence-stack/reports/alicevision-scancode.json

/Users/kaidongwang/.codex/plugins/cache/personal/research-evidence-stack/1.0.0/scripts/research-audit \
  ort --trusted-repository /ABS/pinned-source \
  /Users/kaidongwang/.codex/research-evidence-stack/reports/alicevision-ort.json
```

本次锁定 broker 版本：ScanCode 32.5.0、ORT 91.0.1、OSV 2.4.0 snapshot 2026-07-13。只有扫描**实际 resolved revision 与产物 closure**后才能把整体 license 从 `insufficient-evidence` 升级。

然后跑最小 `.sfm` fixture：

```bash
aliceVision_meshing \
  --input /ABS/dense_with_visibility.sfm \
  --output /ABS/dense_after_cut.sfm \
  --outputMesh /ABS/mesh.obj \
  --partitioning singleBlock \
  --repartition multiResolution \
  --seed 20260721
```

再逐级 8K/32K/128K/.../3.62M 点，记录 `n,T,I,J,A,O` 和每阶段 footprint；任一级超过预注册 upper bound 即停止。

## U4 COLMAP dense adapter 的 `.vis` 顺序与同输入质量差距未知

在运行前验证 PLY 和 `.vis` point count、文件耗尽、最大 image offset：

```bash
python3 - /ABS/DENSE_WS <<'PY'
from pathlib import Path
import struct, sys

root = Path(sys.argv[1])
with (root / 'fused.ply').open('rb') as f:
    nply = None
    while True:
        line = f.readline()
        if not line:
            raise RuntimeError('PLY end_header not found')
        s = line.decode('ascii').strip()
        if s.startswith('element vertex '): nply = int(s.split()[-1])
        if s == 'end_header': break

raw = (root / 'fused.ply.vis').read_bytes()
off = 0
nvis, = struct.unpack_from('<Q', raw, off); off += 8
maxidx = -1
for _ in range(nvis):
    k, = struct.unpack_from('<I', raw, off); off += 4
    ids = struct.unpack_from(f'<{k}I', raw, off); off += 4*k
    if ids: maxidx = max(maxidx, max(ids))
assert nply == nvis, (nply, nvis)
assert off == len(raw), (off, len(raw))
print({'points': nvis, 'max_visibility_index': maxidx, 'bytes': len(raw)})
PY
```

还要把 `max_visibility_index` 和同一 sparse model 的 `RegImageIds()` 精确顺序比对。随后在同 canonical input 上跑 COLMAP/AliceVision/TSDF，按成面协议判断；在此之前“谁质量更好”保持 UNVERIFIED。

本机研究基线命令：

```bash
/usr/bin/time -lp /opt/homebrew/bin/colmap delaunay_mesher \
  --input_path /ABS/DENSE_WS \
  --input_type dense \
  --output_path /ABS/OUT/colmap_delaunay.ply \
  --default_random_seed 20260721 \
  --DelaunayMeshing.max_proj_dist 20 \
  --DelaunayMeshing.max_depth_dist 0.05 \
  --DelaunayMeshing.visibility_sigma 3 \
  --DelaunayMeshing.distance_sigma_factor 1 \
  --DelaunayMeshing.quality_regularization 1 \
  --DelaunayMeshing.max_side_length_factor 25 \
  --DelaunayMeshing.max_side_length_percentile 95 \
  --DelaunayMeshing.num_threads 1
```

先 small subset，且这是研究执行，不改变 CGAL 的产品许可判定。

## U5 A16 设备上限与完整 3.62M topology 未知

需要实机、Release arm64、相同背景/thermal/battery protocol；按阶段 `os_signpost`：input、Delaunay、cell copy、incidence cache、visibility、graph fill、max-flow、surface extraction。

```bash
xcrun xctrace list devices
xcrun xctrace list templates
xcrun xctrace record \
  --device "$UDID" --template "Allocations" \
  --attach "PocketWorld" --output /ABS/fusecut-alloc.trace --time-limit 30m
xcrun xctrace record \
  --device "$UDID" --template "Time Profiler" \
  --attach "PocketWorld" --output /ABS/fusecut-time.trace --time-limit 30m
xcrun xctrace export --input /ABS/fusecut-alloc.trace --toc \
  --output /ABS/fusecut-alloc-toc.xml
```

记录 `n,T,Tfinite,Tinfinite,I,J,A,observations,ray-crossing quantiles`、各 vector size/capacity、ABI `sizeof`、current/lifetime footprint、available memory、thermal 与 jetsam `.ips`。没有这些数，4.0067 GB 只能作为 Poisson-anchor 场景估计和风险信号，不是 PocketWorld 内存下界或 RSS 预测。

## U6 数据真值、visibility 与磁盘仍是实际阻塞

- `photos_depth` 的单位/标定/时间同步：需要原 producer version、schema、decode code 和已知平面/标尺校验。
- `lapa` 原始 2D tracks 已丢：需要恢复原 reconstruction，或用 frozen reprojection+occlusion 规则生成 synthetic observations，并明确是派生 visibility。
- 当前 PLY 不带 visibility：必须重建 `cloud-visibility-v1`，不能猜。
- free space 约 24 GiB：AliceVision full superbuild 和多全尺寸 cache 不启动；先清理到满足 3× declared intermediate guard。

# 证据账本与最终决策边界

| 核心 claim | 状态 | 直接支持 | 限制 |
|---|---|---|---|
| learned MVS 可 patch-wise | CONFIRMED | DeepMVS | 不证明 CasDiff 数值等价/恒定总峰值 |
| overlap/全局粗上下文能减 tile inconsistency | SUPPORTED | WACV satellite、PatchFusion | 相邻任务，不是 multi-view diffusion |
| stock CasDiff full-res 可与基线持平 | CONFIRMED FALSE | 固定源码张量/尺寸 | CoreML 实际优化只能改变常数，不能支持现有承诺 |
| custom tiled model working set 可设界 | INFERENCE | 空间局部网络 + fixed envelope | source warping/halo/RNG 要实现并实测 |
| narrow range 固定 D 省内存 | CONFIRMED FALSE | tensor shapes | 改 D 是另一项模型变更 |
| AliceVision fuseCut 无 CUDA | CONFIRMED | pipeline/fuseCut CMake | 完整 arm64 build 未运行 |
| 裸 PLY 可直接进 fuseCut | CONFIRMED FALSE | PLY loader/main/PointCloud | 带 observations 的 SfMData 可以 |
| COLMAP 与 fuseCut 同族 | CONFIRMED | 两套 fixed source + papers | 不同论文分支/实现/后处理 |
| 当前 COLMAP vs AliceVision 质量差 | UNRESOLVED | 未找到同输入 A/B | 必须执行协议 |
| 现有 vendor 已含 Delaunay product path | CONFIRMED FALSE | 本地 CMake/build flags | 接入还受 CGAL 许可阻塞 |
| global 3.62M fuseCut 适合 A16 | SUPPORTED: LIKELY NO；exact UNVERIFIED | conditional source-field formula + Poisson scenario + historical measurements | 实际 `T/n`、容器和设备 RSS 未测；当前只足以拒绝直接产品投入 |
| 百万点移动同族公开先例 | NOT FOUND | 有界检索；最近仅 499–539 点且无 graph cut | 不是绝对不存在证明 |

最终可执行决策：

1. **Q-A 立项条件**：先做 24-ref whole-vs-tile gate；若 source ROI 或 halo 无法放入 896×512 envelope，停止 model-call crop 路线，转 operator tiling。
2. **Mac 成面立项条件**：先生成 common visibility input；用现成 COLMAP 得研究基线；并行解决 Triangle-free AliceVision build。任何不等价输入结果不进入排名。
3. **手机立项条件**：不移植 global graph；只允许一个 representative packed local tile prototype。若 topology/RSS 外推无法满足 2.4 GiB full-route gate，停止，不继续扩大。
4. **产品合规条件**：权重授权、实际依赖 closure、MPL notices/source offer、Triangle OFF 和 CGAL 路径选择必须在发布前全部有文件级证据。
