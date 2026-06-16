# 任务简报：在桌面验证 DiffMVS 能否「替掉 DA3」做 PocketWorld 的上游几何

> 把这整份贴给一个新会话即可。它是完全自包含的：包含背景、动机、要抄的仓库、磁盘上的真实数据位置与读法、分步方法论、成功判据、以及前序所有经验教训（避免重走弯路）。

---

## 0. 你是谁、在做什么

你在帮我开发 **PocketWorld**：一个**商用**移动端（iOS 优先，兼顾 Android/HarmonyOS）3D 扫描 App。
当前上游几何用的是 **DA3（Depth Anything 3）单目/多视深度**。

**本次任务的唯一目标**：在**桌面（macOS，本机）**把 **DiffMVS** 跑通，验证一个关键假设 ——
**用 DiffMVS（纯 MVS）彻底替掉 DA3，作为上游几何来源**，而不是补充 DA3。

**这是验证性实验，不是上线移植。** 先在桌面用我已有的真实拍摄数据证伪/证实假设，再谈手机适配。

### 硬约束（任何方案都要过这关）
- **可商用 license**：只接受 MIT/BSD/Apache。**禁止** GPL/AGPL/CC-BY-NC。每个产物（代码 vs 权重 vs 训练数据）**分别**查 license。
- **手机可部署**：iPhone jetsam RAM ≈ 3072MB，散热受限，CoreML 端上推理，**全本地**。
- **不要碰 UV 贴图/纹理烘焙**——那是整条管线最后一步，本任务完全不涉及。
- **能抄就抄，不要自研算法**。直接读官方代码改。

---

## 1. 为什么要替掉 DA3（动机，必须理解）

DA3 是 410M 参数的 ViT 基础模型，按「窗口」(K 帧一组) 做神经推理。它给 PocketWorld 带来**三个固有税**，全是单目神经深度的结构性代价：

1. **慢**：完整跑一遍要**几小时**起步；手机上 K=3@252px 单窗 ≈ 517ms/898MB，K=4 直接 NaN，K=5 崩溃。一个 18 帧的窗在手机要约 10 分钟。**不可部署。**
2. **多视不一致**：每个窗的深度是独立预测的，尺度/位移对不齐，需要 FixB（每窗单尺度）+ BA（尺度+位移联合）去对齐，地板对齐下限也只能到 ~18mm，且会有双层/重影。
3. **不可框选加速**：DA3 是整窗神经推理，**没法只算用户框定区域**（不像 MVS 逐像素可跳过）。

**MVS（Multi-View Stereo）把这三个税一次性消掉**：
- MVS 是逐帧**跨视光度匹配**（已知位姿）→ 快（~100ms 级）。
- 多视**天生一致**（靠匹配，不需要 FixB/BA 对齐）。
- 逐像素、**可框选**（只算框内）。这就是 RealityScan 拍完一秒出点云、还能让你拉框选范围的原因。

**位姿哪来？** ARKit 实时免费给（每帧 6DoF + 内参）。所以流程是：
```
ARKit 位姿（免费） → DiffMVS 每帧匹配出深度+置信度 → 反投影融合点云 → screened Poisson → mesh
                                   ↑
                        全程没有 DA3，没有几小时推理，没有 FixB/BA
```

**唯一代价**：纯 MVS 在**无纹理/反光面**（白墙、木地板光滑处、玻璃）匹配会失败。但有三层缓冲兜住：
1. 我们的成面器是 **screened Poisson（Open3D，MIT）**，它是全局插值，**无纹理空洞会被自动平滑桥接**，而无纹理区通常恰好是平面（地板/墙），Poisson 插平面插得最好。
2. **DiffMVS 原生输出逐像素置信度图**，低置信度精确落在无纹理处 → 可直接 mask 掉烂点再喂 Poisson，或引导用户补拍。
3. 需要更狠还能叠加经典 planar-prior MVS（ACMMP，MIT），本任务暂不做。

**战略含义**：这等于放弃「DA3 当差异点」，变成「轻量学习版 RealityScan」。但 DA3 本来就在手机上跑不动，这个差异点兑现不了。**把不可部署的差异点，换成可部署的快，是划算的。**

---

## 2. 要抄的仓库：DiffMVS / CasDiffMVS

- **仓库**：https://github.com/cvg/diffmvs  （论文 T-PAMI 2025，arXiv:2509.15220）
- **代码 license：Apache-2.0 ✅** 可商用。
- **权重**：README 给 Google Drive checkpoint。**注意：权重在 DTU/BlendedMVS 上训练（数据集有学术条款）** → 上线前最好用商用干净数据重训（~1M 参数，重训便宜）。本任务先用官方权重验证可行性即可。

### 已做过的深读，直接用，别重复研究：
- **「Diffusion」不慢**：推理只跑 **1 步 DDIM = 空操作**（跳过 alpha/噪声计算），真正计算是 RAFT 式 **ConvGRU 迭代**（DiffMVS K=4 次 / CasDiffMVS K=3 次），从一个粗深度起步而非纯噪声。所以它是轻量快速的，不是 Stable-Diffusion 那种多步采样。
- **大小**：DiffMVS ≈ 0.5–1M 参数（~2–6MB），CasDiffMVS ≈ 1–1.5M。比 DA3-BASE（410M）小约 400×。
- **架构**：只有**一个很小的 3D-CNN cost-volume 初始化块**（base_channels=8），其余细化全是 **2D conv + ConvGRU，无注意力**。
- **原生置信度**：`models/diffusion.py` 返回 `photometric_confidence`（全分辨率）+ `conf`（多尺度），由 GRU 头 sigmoid 出 `C∈[0,1]`，**低置信度落在无纹理/天空/边界**（论文 Fig.10）。这是本次验证的关键产物。
- **关键文件**：`models/diffusion.py`（主流程 + 置信度输出）、`models/update.py`（DDIM+GRU 推理循环，约 466–521 行）、`models/module.py`（`FeatureNet` 约 357 行、`CostRegNet_small` 3D-CNN 约 422 行、`grid_sample` 约 212 行）、`test.py`（推理入口，默认 `--sampling_timesteps [1,1,1] --num_view 5`）。
- **CoreML 拦路**（手机适配时才管，本任务只记录）：`grid_sample`（2 处：单应 warp + GetCost）、那个小 3D-CNN、GRU for 循环要展开。比 MonoMVSNet 干净一个量级。
- **benchmark**：DiffMVS 单级就全面超过 CasMVSNet/PatchmatchNet/MVSTER（DTU/T&T/ETH3D）；CasDiffMVS 是 SOTA 级。**建议先用 DiffMVS（轻），需要更准再试 CasDiffMVS。**

---

## 3. 磁盘上的真实数据（本机，已【实地核验】存在 — 不要再说"数据缺失"）

**研究仓库根目录（绝对路径）**：`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks`
下面所有相对路径都从这里算。**先 `cd` 到这个目录**，否则会以为数据不在。

这是一段室内拍摄：木地板房间，中心是**一张蓝色凳子 + 凳子上的地球仪**（有凳子横杠、地球仪底座这类**薄结构**，是检验细节保留的关键物）。窗外强光（高光），木地板大片**弱纹理/反光**（正是要考验 MVS 的地方）。

### ★ 最干净的数据来源 = 全局 manifest（本身就带每帧位姿+内参+图路径，无需碰 DA3 的任何东西）
```
绝对路径:
/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json
```
结构（已核验）：`{"frames": [ {...}, ... ]}`，共 **414 帧**，每帧 4 个键：
- `frameID`           例 "cap-1"
- `jpegPath`          例 "photos_highres/cell_85_slot_0.jpg"（相对 `capture_seq_k35_strict/`）
- `cameraExtrinsic4x4` 16 元素扁平 → reshape(4,4)。**这是 ARKit 相机位姿 = camera→world（平移列就是相机在世界的位置）。MVSNet/DiffMVS 要的是 world→camera 外参，所以要取逆 `w2c = inv(extrinsic4x4)`。务必用重投影自检方向是否对。**
- `cameraIntrinsicFxFyCxCy`  `[fx, fy, cx, cy]`，对应**全分辨率 4224×2376**。下采样图像时内参要同比缩放。

### ★ 真图（已核验 414 张，高清）
```
/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/photos_highres/cell_XX_slot_Y.jpg
```
分辨率 **4224×2376**（H,W=2376,4224）。路径 = `capture_seq_k35_strict/` + manifest 的 `jpegPath`。

→ **DiffMVS 的输入就这两样：读 manifest 拿 (jpegPath→图, intrinsic, inv(extrinsic)=w2c)，对 414 帧做源帧选择(N=2~3 最近邻)即可。完全不需要 DA3、不需要 win_npz。**

### （备选）每窗 npz —— 如果想直接复用 DA3 的分窗
```
data/expAC_rewindow_span_2026_06_13/windows/win_00.npz … win_32.npz   （33 个，已核验）
  键(已核验): depth (18,504,896) float32  ← DA3 深度，【丢弃】
              conf  (18,504,896) float16  ← DA3 置信度，【丢弃】
              K     (18,3,3)    float32   ← 内参，但对应 896×504 处理分辨率（非全分辨率！）
              w2c   (18,4,4)    float32   ← 已经是 world→cam，可直接用（不用取逆）
窗定义: data/expAC_rewindow_span_2026_06_13/expAC_results.jsonl
```
注意：npz 的 K 是 896×504 分辨率，用它就要把图 resize 到 896×504；manifest 的内参是全分辨率 4224×2376。**别混用。**

参考现有 loader：`tools/python/expAT_geomcons_tsdf.py` 第 30–92 行（`load_windows()` + flatten）展示了怎么把窗解析成 per-frame (K,w2c,image)。**复用它，但把 `dk`(DA3 深度)扔掉，让 DiffMVS 自己算深度。**

### Python 环境（已核验）
- `/opt/homebrew/bin/python3.11` —— 已装 open3d 0.19 + opencv + numpy（成面/读图够用）。
- **缺 torch** —— DiffMVS 需要，另装（macOS 用 CPU 或 MPS 版 torch 即可，验证不追速度）。
- **cvg/diffmvs 仓库还没 clone** —— 需 `git clone https://github.com/cvg/diffmvs`。
- → 这台 Mac 上**唯一真正缺的就这两样（torch + clone diffmvs）**，数据/图/位姿/对比 mesh/open3d 全都在。

### 对比基线（你的产物要和这些比）
- **当前 DA3 最优 mesh**：`~/Desktop/expF2_easy_clouds_2026_06_12/poisson/colored_mesh_fixb93_poi.ply`
  （= FixB 深度 + COLMAP 几何一致性 MIN_WIN=1 保 93% → screened Poisson，4.3M 顶点，主体最全 + 薄结构在）。
- **细节最足的 TSDF 版**：`~/Desktop/expF2_easy_clouds_2026_06_12/poisson/colored_mesh_geomcons2.ply`（地板纹理/微起伏清晰，但薄结构被体素平均抹掉）。
- 现成的 three.js 对比 viewer 模板：`~/Desktop/expF2_easy_clouds_2026_06_12/filterpoi_compare.html`（AgX tonemap + sRGB→linear 顶点色，可照抄做新对比页）。

---

## 4. 分步方法论

1. **克隆 + 环境**：`git clone https://github.com/cvg/diffmvs`，建 venv 装 torch（CPU/MPS 即可）+ 依赖。确认 `test.py` 能在官方 DTU 样例上跑出一帧深度（先证明环境通）。
2. **下权重**：从 README 的 Google Drive 取 DiffMVS（和 CasDiffMVS）checkpoint。
3. **写数据适配器**：把 PocketWorld 的 (image, K, w2c) 转成 DiffMVS 的输入格式（MVSNet 风格：每视一个 cam 文件含 4×4 外参 + 3×3 内参 + depth_min/depth_interval；外加 pair.txt 指定每个参考帧的 N 个源帧）。
   - **深度范围**：从现有点云/SfM anchors 估，或从 DA3 深度统计借（场景约 0.4–3m）。`data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz` 有 SfM 稀疏锚点可参考尺度。
   - **源帧选择（pair.txt）**：先简单用「相机位置最近的 N 帧」（N=2 或 3），保证有基线又有重叠。expAT 里有「nearest N_CAND frames」的现成逻辑（约 103–108 行）可借。
4. **跑推理**：对若干参考帧跑 DiffMVS，N=2–3 源视，拿到**每帧 depth + photometric_confidence**。
5. **核心检查（成败在此）**：
   - **置信度行为**：把 `photometric_confidence` 渲染成热力图，**确认它在木地板弱纹理/反光处确实塌下去、在有纹理处（凳子、地球仪、地板木纹边缘）高**。这是整条「无 DA3 + Poisson 补洞」计划的基石假设。
   - **深度质量 + 多视一致**：多帧深度反投影到世界系，**确认无需任何 FixB/BA，地板就是单层**（不像 DA3 要对齐）；薄结构（横杠/底座）有没有。
6. **成面对比**：把置信度过滤后的 DiffMVS 点云喂 screened Poisson（可直接调 `tools/python/expAT_geomcons_tsdf.py` 的 `MESHER=poisson` 分支，或 Open3D `create_from_point_cloud_poisson(depth=11~12, scale=1.0, linear_fit=True)`）。和上面两个基线 mesh 同视角对比：**薄结构是否在、地板是否单层薄、无纹理空洞是否被 Poisson 补平**。做一个 three.js 对比页（照抄 filterpoi_compare.html）。
7. **速度 + 手机外推**：记录每帧推理耗时（桌面），按 N=2–3 / 256–384px 粗估手机延迟和 RAM，记录 CoreML 拦路算子（grid_sample / 3D conv）。

---

## 5. 成功判据（明确给出结论）

请最终给我一个清晰判断，逐条回答：
1. **置信度假设成立吗**？DiffMVS 置信度是否在无纹理地板/反光处低、有纹理处高？（若不成立，整条免融合路要重审。）
2. **多视一致吗**？纯 MVS 深度不做任何对齐，地板是否单层、无双层重影？（对比 DA3 必须 FixB/BA 才能压到 18mm。）
3. **薄结构保住了吗**？凳子横杠 / 地球仪底座在最终 mesh 里在不在？
4. **无纹理被兜住了吗**？地板/墙的 MVS 空洞，Poisson 全局插值是否补成可接受的平面？
5. **速度**？每帧推理是不是 ~100ms 级（而非 DA3 的几小时）？
6. **最终对比**：纯 DiffMVS（无 DA3）的 mesh，相比当前 DA3 最优（`colored_mesh_fixb93_poi.ply`）是更好、相当、还是更差？

---

## 6. 前序经验教训（别重走这些弯路）

- **TSDF 会抹掉薄结构**（体素平均）。成面一律用 **screened Poisson**（保薄结构，全局解）。这是已验证结论。
- **Poisson 的「糊」可调**：octree `depth`（用 11–12 别用 8–10）+ 别在成面前过度 `voxel_down_sample`（≤1.5mm）+ scale→1.0。depth 是清晰度总开关。
- **DA3 的多视不一致是固有的**：FixB 给每窗单尺度（地板 ~22mm），BA 加位移联合优化（~18mm，对齐下限）；**逐帧 BA 退化**（不可辨识，位移爆 ±450mm）。→ 这些 MVS 都不需要，是换 MVS 的最大收益。
- **SfM 覆盖度不预测窗质量**（相关 -0.18）、**窗重叠也不预测**（-0.25）：别用这些做门控。
- **导向滤波（He 2010）压不薄地板**：残差是逐帧深度 level 偏置（低频），空间滤波治不了。
- **窗密度只买数量不买质量率**：sep 10° 得 66 窗 conf≥6 占 35%，和 sep 18° 的 36% 同比例。
- **设备硬限**：iPhone jetsam 3072MB；DA3 K=3@252 fp16 CoreML cpuOnly = 517ms/898MB，K=4 NaN，K=5 崩。

完整背景见 memory：`/Users/kaidongwang/.claude/projects/-Users-kaidongwang/memory/`（尤其 `diffmvs-mobile-assessment.md`、`realityscan-pipeline-architectural-tax.md`、`pocketworld-upstream-geometry-winner.md`、`pocketworld-upstream-negative-results.md`）。

---

## 7. 交付物
1. DiffMVS 置信度在无纹理地板上的热力图截图 + 一句话结论（假设成立与否）。
2. 纯 DiffMVS 点云/mesh 与 `colored_mesh_fixb93_poi.ply` 的同视角对比页（three.js）。
3. 每帧推理耗时 + 手机可行性粗估（含 CoreML 拦路算子清单）。
4. 总判断：**纯 DiffMVS 替掉 DA3 这条路，立不立得住。**
