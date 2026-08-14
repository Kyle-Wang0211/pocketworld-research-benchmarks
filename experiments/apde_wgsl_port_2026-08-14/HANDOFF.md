# 交接说明:APDe-MVS → WGSL 跨端移植

> 写于 2026-08-14。目标读者:接手这项工作的下一个会话/工程师。
> 本文自包含 —— 读完这一篇就能接着干,不需要回看对话历史。

---

## 0. 一分钟速览

**在做什么**:把 APDe-MVS(传统 PatchMatch MVS,MIT 许可,ETH3D F1 89.15)
从 CUDA 移植到 WGSL,走「一份 WGSL → 编译期转译 → iOS 原生 Metal /
Android+鸿蒙原生 Vulkan」的路线,运行时不带任何第三方图形层。

**为什么**:跨端要求(iOS/Android/鸿蒙)把原本的 CasDiffMVS 方案逼到了墙角
(详见第 1 节),而 APDe-MVS 不需要任何 NN 运行时、零强制权重、分还高 3 分。

**进度**:**90%**。2011 行 WGSL,14 个 kernel 全部编译链接通过,
M3 Pro 上占用率全 1024。**剩 17 个函数 / 690 行,集中在"弱纹理传播"那一支。**

**下一步**:搬完弱纹理传播支 → 写输入转换 → 写多 kernel 驱动 →
用 414 帧素材跑出深度图 → 和 CasDiffMVS 的真彩 PLY 做质量对比。

**🔴 上生产前的硬阻断**:Gipuma(GPL-3.0)血统取证未做。见第 8 节。

---

## 1. 项目背景:为什么会走到这一步

### 1.1 起点

原计划是把 **CasDiffMVS**(学习式 MVS,cvg/diffmvs,Apache-2.0)上生产。
它在 A16 上有认证实测:**896×512 = 710ms / 485MB**,CoreML 导出、
端上 runner(403 行 Swift)都曾上过产品仓(2026-07-12 上、07-20 被签决删除,
删除理由是"零消费者",不是"有问题",可从 `pocketworld` 的 `332fc94^` 完整取回)。

### 1.2 三件事改变了计算

**① 权重许可**:CasDiffMVS 三个权重(dtu/blend/blendmvg)**全部带 DTU 血统**,
而 DTU 官网**没有任何许可声明**(只有一句 "available freely as citeware")——
无授权比明示 NC 更难办。干净出路是删掉 DTU、纯 BlendedMVG(CC BY 4.0)重训,
`train.py:45` 的 `--loadckpt` 默认 None、`:338` 是 `elif`,不传即从头训。
成本推算约 50 GPU-h(2080Ti 级),但用户定过"Mac 开发、手机测试、不用盒子"。

**② 跨端**:我们手上的 CasDiffMVS 资产是 **CoreML,iOS 独占**。
跨端调研结论:**只有 MNN**(Apache-2.0)一条路 —— 它是唯一在 Android GPU 上
同时具备 `grid_sample` 和(转换期重写成 2D 的)3D 卷积的运行时。
ONNX Runtime **没有任何移动端 GPU EP**(25 个 provider 里无 Vulkan/OpenCL/Metal),
TFLite 的 210 个 builtin **没有 GridSample**,华为 MindSpore Lite 算子表同样缺。
而 MNN issue #4110 报告 **GPU 内存约为 CPU 的 2 倍** ⇒ 485MB×2 + App 自身
1020MB ≈ 1990MB,**超出 iPhone 11 的 1700MB 预算**。

**③ 不可复现**:实测 CasDiffMVS/DiffMVS 推理**天生随机**(图里有
`RandomNormalLike`,PyTorch eager 同输入连跑 3 次输出不同),这是扩散采样
注入的噪声,不是导出 artifact。直接撞"交付绝对无损/可复现"铁律。

### 1.3 APDe-MVS 为什么被选中

| | CasDiffMVS | **APDe-MVS** |
|---|---|---|
| ETH3D test F1 | 85.11(新 ckpt 85.99) | **89.15** |
| 需要 NN 运行时 | ✅ MNN(唯一解) | **❌ 完全不需要** |
| 权重 | 🔴 DTU 血统未解 | ✅ **零强制权重**(SAM 是可关插件 `--no_sam`,且 SAM 权重本身 Apache-2.0) |
| 许可 | Apache-2.0(代码) | **MIT**,版权人=作者本人 |
| 内存(算出来的) | 485MB@896×512 | **≈106MB@896×512** |
| 真机实测 | ✅ 有 | 🔴 **无** |

⚠️ 关键辨伪:ETH3D 榜首 **DVP-MVS++(90.23)/ SED-MVS(90.08)/ MSP-MVS(89.51)
仓库里全是只有 README 零源文件**,且 DVP-MVS++ 依赖 Apple DepthPro
(权重明文禁商用)。HPM-MVS 系有代码但**无 LICENSE 文件**。
⇒ **能商用 × 有代码 × 无禁商用权重** 的交集里,最高分就是 APDe-MVS。

### 1.4 已量到的速度(M3 Pro)

斜率法(repeat 1→16 @1920×1440)分离固定开销与净成本:

| 量 | 值 |
|---|---|
| 单次 NCC 净成本 | **0.53 → 0.89 ms/MP**(缓存友好 → 访问发散) |
| dispatch 固定开销 | 0.43 ms |
| 每参考图 @896×512 | **29–47 ms**(仅 NCC) |
| 414 帧全做参考图 | **12–19 秒**(仅 NCC,M3 Pro) |

**判读**:19 秒已吃掉 30s 预算三分之二,且**只有 NCC**、且**跑在 M3 Pro 不是手机**
⇒ 手机上一定超。三条减法:减参考图数(最大一刀,选 1/4 ⇒ ~5 秒)、
降分辨率、`max_iterations` 3→2。**A16/M3 Pro 实际比值未测,不外推。**

---

## 2. 文件位置(全部绝对路径)

### 2.1 工作副本(耐久,主编辑处)

```
~/Documents/progecttwo/_host_experiments/apde_wgsl_spike/
├── wgsl/                     ← 13 个 WGSL 文件,2011 行
├── host/
│   ├── ncc_bench.mm          ← Metal 打点载具(含有效性自检)
│   └── occupancy_probe.mm    ← 占用率探针
└── upstream/APDe-MVS/        ← 上游源码(git clone --depth 1)
    ├── APD.cu                ← 2736 行,全部 kernel 在这
    ├── APD.cpp / APD.h / main.h / main.cpp
    └── run.py                ← 看 --no_sam 怎么关 SAM
```

⚠️ **上游源码故意放耐久目录** —— scratchpad(`/private/tmp/claude-501/...`)
在本次工作中**被系统清空过一次**,这是备忘里那条 `/tmp 会被系统清空` 的实例。

### 2.2 研究仓(已提交并推送)

```
~/Developer/Aether3D-cross/pocketworld_research_benchmarks/
└── experiments/apde_wgsl_port_2026-08-14/
    ├── README.md             ← 约束/速度/偏离账/复现步骤
    ├── HANDOFF.md            ← 本文件
    ├── wgsl/*.wgsl
    ├── host/*.mm
    └── tools/build.sh        ← 一条命令从零构建,已验证可复现
```

分支:`research/apde-wgsl-crossplatform-2026-08-14`
远端:`git@github.com:Kyle-Wang0211/pocketworld-research-benchmarks.git`

提交历史:
- `d86cb4b` 首个速度数字 + 六条约束
- `a5e2d44` 传播主体 + 精修 + 弱纹理链前半(65%)
- `025f6cd` GenAnchors(75%)
- `86cc27b` 初始化/中值滤波/局部精修/DepthToWeak(90%)

### 2.3 414 帧测试素材(质量对比用)

```
① 原图 JPEG(4224×2376,414 帧,673MB)
   ~/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/
     official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/photos_highres/
   文件名形如 cell_85_slot_0.jpg

② 帧序清单(决定哪 414 帧、什么顺序)
   .../capture_seq_k35_strict/../diagnostics/
     external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json
   frames[i].jpegPath 相对 capture_seq_k35_strict/

③ 位姿 + 内参窗口(1.2GB,33 个 npz)
   .../data/expAC_rewindow_span_2026_06_13/windows/win_00.npz … win_32.npz
   键:depth(18,504,896) f32 / conf(18,504,896) f16 / K(18,3,3) / w2c(18,4,4)
   ⚠️ 这里的 depth/conf 就是 **CasDiffMVS 的输出深度图**,是对比基线

④ SfM 锚点(算每帧深度范围用)
   .../data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz
   键:pts(29071,3) / obs_frame(143202) / obs_uv(143202,2) / obs_aidx(143202)

⑤ 稀疏模型 dump(今天所有臂真正读的)
   .../tools/python/diffmvs_out/trio_model_lapa.npz
   键:names(413) / K(413,3,3) / w2c(413,4,4) / centers(413,3)
       obs_idx(1602834) / obs_off(414) / pts(204096,3)

⑥ 对比基线点云(16 个臂,全部真彩带法向)
   .../tools/python/diffmvs_out/fused_trio_*.ply
   关键几个:fused_trio_official 756,171 点 /
             fused_trio_realcfg 1,792,752 点 / fused_trio_ofull15 3,667,559 点
   属性:x,y,z,nx,ny,nz,red,green,blue
```

⚠️ **这批数据全被 `.gitignore` 排除,只在本地**。
⚠️ ①③⑥ 曾被我列为"可删的 44G",**已撤回** —— 它们是测试素材,不要删。

### 2.4 复用资产

- **同一个融合器**:`.../tools/python/pw_diffmvs_geomcons.py`
  (生产口径的几何一致性融合器)。**两条路都喂给它**,对比就只测深度图质量,
  不掺融合器差异。这是省下整个融合模块的捷径。
- **COLMAP `mvs::StereoFusion`**:`~/Developer/Aether3D-cross/aether_cpp/
  third_party/glomap_vendor/colmap-src/colmap/mvs/fusion.{h,cc}`,BSD-3,
  **纯 CPU**(CUDA 只包 PatchMatch 不包 fusion),已实测 9 个 TU 用产品同款
  include/宏编译通过,链接侧只缺 3 个 `JetColormap::*`(调试用,4 行打桩)。
  端上融合器要用它,不用自己写。

---

## 3. 移植进度:已搬 / 未搬

### 3.1 已搬(2011 行 WGSL,13 个文件)

| 文件 | 行 | 内容 |
|---|---|---|
| `apde_common.wgsl` | 158 | Camera/Params 结构、8 个叶子数学、packed_maps 解包、六条约束的文字说明 |
| `apde_bindings.wgsl` | 59 | **binding 契约**(C6 逼出来的)+ `vw_get` |
| `apde_geom.wgsl` | 83 | ComputeHomography / ComputeCorrespondingPoint / ProjectonCamera |
| `apde_rand.wgsl` | 139 | **官方 XORWOW** + GenerateRandomNormal / GeneratePerturbedNormal / Get3DPointonWorld |
| `apde_geomcons.wgsl` | 73 | ComputeGeomConsistencyCost / TransformPDFToCDF / FindMinCostIndex |
| `apde_ncc.wgsl` | 133 | **ComputeBilateralNCCOld**(热点,两分支) |
| `apde_refine.wgsl` | 86 | ComputeMultiViewCostVector / PlaneHypothesisRefinementStrong |
| `apde_init.wgsl` | 221 | sort_small / TransformNormal(2RefCam) / GenerateRandomPlaneHypothesis / ComputeMultiViewInitialCostandSelectedViews / CheckerboardFilterStrong / LocalRefine |
| `apde_propagate.wgsl` | 366 | **CheckerboardPropagationStrong**(自适应棋盘 8 向 + 多假设联合视图选择) |
| `apde_weak.wgsl` | 115 | ConfidenceCompute / FindNearestStrongPoint |
| `apde_depth2weak.wgsl` | 119 | **DepthToWeak**(STRONG/WEAK/UNKNOWN 判定) |
| `apde_anchors.wgsl` | 249 | **GenAnchors**(APD 的核心:方向搜索 + RANSAC 平面 + 排序取锚点) |
| `apde_entries.wgsl` | 210 | 14 个 kernel 入口点 |

**拼接顺序是契约,不能改**(`build.sh` 里写死):
`common → bindings → geom → rand → geomcons → ncc → refine → init →
propagate → weak → depth2weak → anchors → entries`

### 3.2 未搬(17 个函数 / 690 行,全在 `upstream/APDe-MVS/APD.cu`)

**核心是"弱纹理传播"这一支** —— APD 相对 ACMMP 的加分项:

| 行数 | 源码行 | 类型 | 函数 | 说明 |
|---|---|---|---|---|
| 174 | L1442 | device | **CheckerboardPropagationWeak** | 弱纹理版传播,主干 |
| 146 | L448 | device | **ComputeBilateralNCCNew** | **可变形 NCC**,用 GenAnchors 产出的锚点 |
| 113 | L2486 | global | **RANSACToGetFitPlane** | 独立 kernel |
| 89 | L1008 | device | PlaneHypothesisRefinementWeak | 弱纹理版精修 |
| 32 | L776 | device | ComputeMultiViewInitialCost | |
| 19 | L40 | device | getTopNIndex | |
| 18 | L315 | device | GeneratePertubedPlaneHypothesis | |
| 18 | L1617 | global | BlackPixelUpdateWeak | 薄包装,已知长相 |
| 17 | L1636 | global | RedPixelUpdateWeak | 薄包装,已知长相 |
| 16 | L431 | device | Softmax | |
| 11 | L145 | device | TriangleArea | |
| 10 | L809 | device | ComputeMultiViewCostVectorNew | |
| 8 | L105 | device | Vec3CrossVec3 | |
| 5 | L225 | device | SpatialGauss | |
| 5 | L231 | device | RangeGauss | |
| 5 | L425 | device | GetAnchorPoint | 读 anchors 缓冲 |
| 4 | L78 | device | unSetBit | |

**建议顺序**:先搬 10 个小的(叶子,共 ~120 行)→ `ComputeBilateralNCCNew`
→ `PlaneHypothesisRefinementWeak` → `CheckerboardPropagationWeak`
→ `RANSACToGetFitPlane` → 两个红黑包装。

⚠️ `SpatialGauss`/`RangeGauss` 的存在说明 **NCCNew 里双边权重是真启用的**
(NCCOld 里 `weight=1.0f` 硬编码,从未启用)。搬 NCCNew 时别照搬 Old 的假设。

### 3.3 未搬(非 kernel)

- **输入转换**:npz(②③④⑤)→ 相机数组 + 图像纹理 + 每帧深度范围 + 邻居表。
  相机可从 `trio_model_lapa.npz` 的 K/w2c 直取;深度范围从 `anchors_obs_414.npz`
  的观测算;邻居表从 `obs_idx/obs_off` 的共视统计出。
- **多 kernel 驱动**:现有 `ncc_bench.mm` 只跑单 kernel、只绑 4 个 buffer。
  要扩成完整流水(12 个 buffer + 2 纹理 + 深度纹理数组 + 2 sampler)。
- **深度图导出 + 融合**:融合直接喂 `pw_diffmvs_geomcons.py`(见 2.4)。

---

## 4. 六条跨端约束(全部由编译器实测确认,不是读文档)

| | 约束 | 怎么发现的 | 落地位置 |
|---|---|---|---|
| **C1** | iOS 每 stage storage buffer 上限约 10 | **逐 kernel 生效** —— naga 会剥掉未使用的 binding。原版 14 个 buffer 不会同时出现在一个 kernel 里 | 4 张 uchar 图打包进 `packed_maps` |
| **C2** | Metal 没有 runtime array length | naga 自动注入 `_mslBufferSizes`,**且占一个 buffer 槽** | 所有长度走 `Params` |
| **C3** | workgroup size 在 Metal 是 host 侧参数 | MSL entry 里**消失**;SPIR-V 里保留 `LocalSize=16x16x1` | `WG_X/WG_Y` 是唯一来源,⚠️ **目前 host 侧还是手写 16×16,产品化必须构建期生成** |
| **C4** | 纹理用 f16 而非 f32 | `rgba16float` 默认可过滤(硬件双线性免费);`r32float` 是 `unfilterable-float` 需额外 feature | `sample_gray` |
| **C5** | binding 布局必须转译期冻结 | naga 出 `[[user(fake0)]]` 占位符,**spirv-cross 才给真索引** | 用分离 texture+sampler,不用 combined |
| **C6** | **storage 指针不能当函数参数** | naga 直接报错 ⇒ **binding 是共享层契约,不是调用方自由** | 独立的 `apde_bindings.wgsl` |

---

## 5. 工具链限制(踩过的,已写进 build.sh)

1. **spirv-cross 每次只出一个 entry point**
   官方逐字:"By default, the first entry point in the module is used."
   ⇒ 多 kernel 必须逐个 `--entry <name> --stage comp`,再一起 metallib 链接。

2. **spirv-cross 处理不了「整个 `array<f32,32>` 赋值给二维数组的一行」**
   会生成签名不匹配的 `spvArrayCopyFromDeviceToStack`,MSL 编译直接失败。
   ⇒ 改逐元素拷贝(`apde_propagate.wgsl` 里 8 处)。

3. **`packed_maps` 必须 `read_write`**
   C1 打包后,置信度写位段、NCC 读位段 ⇒ 同 buffer 既读又写。
   ⚠️ **连带要求:不同位段的读写必须落在不同 dispatch**,同一 dispatch 内没有
   顺序保证。产品化时要把这条写进 pass 划分契约。

4. **WGSL 保留字**:`filter` 是保留字(原版局部变量名),已统一改 `filt`。

---

## 6. 移植偏离账(逐条,不藏)

| # | 偏离 | 原因 | 风险 |
|---|---|---|---|
| 1 | `Camera` 用 vec4 填充的扁平数组,非 `float[9]` | WGSL 对齐规则,机械必需 | 无 |
| 2 | 4 张 uchar 图打包进一个 buffer | C1 | 行为等价 |
| 3 | **`curand_init` 的 2^67 skipahead 未复刻**,改哈希播种 | WGSL 里矩阵幂表代价过高 | 🔴 **给定种子的数列不与 CUDA 逐位相同**。做 parity 对拍时,随机路径上的差异是**预期内的,不能当 bug 查** |
| 4 | 种子从 `clock64()` 改成 host 传入的固定值 | 原版跑两次结果不同,撞"交付绝对无损"铁律 | 想复现原版行为传时间戳即可 |
| 5 | `while(s>=1.0)` 加 64 次上限 | GPU 无界循环挂死风险 | 加固,不改分布(期望迭代 1.27 次) |
| 6 | `ncc_finalize` 抽成共享函数(原版两分支各自复制粘贴) | **我的失误** | 已标注;行为等价但违反逐行照抄 |
| 7 | 自适应棋盘 8 向做了结构化(原版复制粘贴 8 遍) | 8 份复制在 WGSL 里极易抄错边界 | 行为逐点等价,但 parity 对不上时要多查一层 |
| 8 | `InitRandomStates` 不再是独立 kernel | 确定性播种后不需要常驻状态 | 省一个 dispatch + 24 B/px |

**生成器本身(`xorwow_next` / `rand_uniform`)是逐行照抄 cuRAND 的 XORWOW。**

---

## 7. 照抄时抓到的原版细节(容易漏,漏了就对不上)

- **`FindMinCostIndex` 用 `<=` 不是 `<`** ⇒ 相等时取**后面**那个,影响 tie-break
- **`ComputeGeomConsistencyCost` 取深度是 `(int)x + 0.5f`** ⇒ 先取整再加半像素,
  是**最近邻不是双线性**。深度图上做双线性会在不连续处造假值
- **`ComputeBilateralNCCOld` 的 `weight = 1.0f` 是硬编码的**(两条分支都是)
  ⇒ 双边权重在 Old 里从未启用,内循环没有 `exp()`。⚠️ **NCCNew 里是真启用的**
- **`Get3DPointonWorld_cu` 的旋转用 R 的列**(即 R^T),别写成 R
- **`TransformNormal` 用 R 的列 / `TransformNormal2RefCam` 用 R 的行**,互为转置
- **`PlaneHypothesisRefinementStrong` 的 `do-while` 条件恒为假**
  (`< min && > max` 不可能同时成立)⇒ 循环**只跑一次**,是原版笔误,照抄语义
- **`float cost_vector[32] = { 2.0f }`** ⇒ C 聚合初始化**只把首元素设成 2.0**,
  其余全 0,不是"全填 2.0"
- **GenAnchors 里 `(curand()%2==0?1:-1) * curand() % shift_range`**
  ⇒ C 的运算符优先级使**乘法先于取模**,结果可能为负。别写成 `sign*(rand%range)`
- **GenAnchors 的 radius 推进是 `min(r*2, r+25)`** ⇒ 先倍增后转线性
- **`CheckerboardFilterStrong` 的 20 个邻居偏移是硬编码非规则集合**,不是方窗
- **`DepthToWeak` 的 peak 扫描范围是 `[2, size-2)`**,两端各留 2 个不判
- **`plane.w` 的语义会变**:传播阶段是"到原点距离 d",
  `GetDepthandNormal` 之后变成"深度"。`ConfidenceCompute`/`GenAnchors` 读的是深度

**三次"漏字段"都是被下一层调用暴露的**(完整 K[9]/R[9] → `width`/`height`
→ 相机中心 `c`)⇒ **逐行照抄比"理解后重写"安全**。

---

## 8. 🔴 未解的阻断与待决策

### 8.1 硬阻断:Gipuma(GPL-3.0)血统取证

ACM 全家(ACMH/ACMM/ACMP/ACMMP)与 APD 系的 README 都写着
"largely benefits from **Gipuma** and COLMAP",而 **Gipuma 是 GPL-3.0**。
**MIT 声明不能自动洗白逐行抄自 GPL 的代码。**

⇒ spike 只测性能不进产品,不受影响;**要真上生产,必须先做源码相似度取证。**

### 8.2 待用户签决

1. **随机性**:两条路都必须先做到"同一份照片跑两次逐字节相同"才能上生产。
   APDe 已经解决(固定种子);CasDiffMVS 要动扩散采样(固定 seed 或 `ddim_eta=0`),
   **质量影响未测**。
2. **算力**:若最终选 CasDiffMVS,重训需要 ~50 GPU-h,与"不用盒子"冲突。
   零算力捷径:**向 DTU 作者(Henrik Aanæs / Anders Dahl)索书面许可**,
   拿到则官方 ckpt 直接可用。
3. **磁盘**:`_artifacts/batch5~10_*` 的 ~23G 装机备份删不删(DA3 那 44G 已撤回,
   是测试素材)。当前可用空间约 46GB。

### 8.3 必须真机复测的

- **lane 私有数组的占用率**:`CheckerboardPropagationStrong` 的
  `cost_array[8][32]` = 1KB/线程;`GenAnchors` ≈ 1KB+;`DepthToWeak` ≈ 305B。
  **M3 Pro 上占用率全 1024 没掉,但 M3 Pro 寄存器文件远大于 A13/A16**,
  而我们在 A16 上定罪过"lane 私有数组是占用率真凶"。**不当过关。**
- **A16/M3 Pro 的实际比值** —— 决定所有速度外推。
- **Dawn 在 A13 上的 subgroup reduction**:Dawn 在 Apple6(A13)就开 subgroups,
  但 Apple 官方表说 reduction 要 Apple7(A14),Dawn 源码自己留着 TODO 说没核实。
  我们目前 0 处用 subgroup,不影响;将来若用要实测(iPhone 11 正好是 A13)。

---

## 9. 性能靶子(按优先级)

| 优先级 | 靶子 | 量级 | 为什么可优化 |
|---|---|---|---|
| 🔴🔴 **1** | **`DepthToWeak`** | **244 次 NCC/像素**(61 视差档 × 4 源视图)。对照:整个传播三轮才 108 次 ⇒ **单趟 ≈ 传播全程 2.3 倍** | 视差档数、步长都是参数;代价曲线扫描天然可粗扫+细化两级 |
| 🔴 2 | **`FindNearestStrongPoint`** | radius=100 ⇒ 每像素 201×201 = 40,401 次。896×512 下 **185 亿次迭代** | O(radius²) 朴素搜索,可换跳跃搜索 / 距离变换 |
| 3 | 参考图数量 | 414 帧全做参考 = 12–19 秒(仅 NCC) | 选 1/4 ⇒ ~5 秒。**这是最大的一刀** |
| 4 | `max_iterations` | 3 | → 2 直接省 33% |

⚠️ 这些都是**"减少工作量"**型优化,符合"提速 ≠ 削峰摊平"的标准。

---

## 10. 怎么接着干

### 10.1 环境

```bash
brew install naga-cli spirv-cross glslang     # Xcode 提供 metal 编译器
```

### 10.2 构建 + 打点

```bash
cd ~/Developer/Aether3D-cross/pocketworld_research_benchmarks
bash experiments/apde_wgsl_port_2026-08-14/tools/build.sh /tmp/apde_build
/tmp/apde_build/occupancy_probe /tmp/apde_build/apde.metallib
/tmp/apde_build/ncc_bench 896 512 0.0 /tmp/apde_build/apde.metallib 1
```

### 10.3 载具的有效性自检(重要)

`ncc_bench` 会打印 `代价=COST_MAX 占比`。**这个数过高就说明内循环被 early-out
跳过,数字不可信。** 正常值约 4%。移植期它真的抓到过一次
host/WGSL 结构体错位(占比 100%、耗时假性快 33 倍)。

⚠️ **`ncc_bench.mm` 里的 `Params`/`Camera` 结构体必须与
`apde_common.wgsl` 逐字段一致。错位不报错,会静默读到垃圾数据。改一边必须改另一边。**

### 10.4 搬新 kernel 的流程

1. 从 `upstream/APDe-MVS/APD.cu` 读原函数(用第 3.2 节的行号定位)
2. **逐行照抄,不做任何"顺手优化"** —— 任何重排都会让 parity 对拍失去意义
3. 写进对应的 `wgsl/*.wgsl`,新函数加进 `build.sh` 的拼接列表
4. `naga <拼接后的.wgsl>` 验证
5. 走完整 `build.sh`,看 `occupancy_probe` 有没有占用率下降
6. 有偏离就登记进第 6 节的表和 README

### 10.5 最终里程碑

搬完 → 输入转换 → 多 kernel 驱动 → 414 帧跑出深度图 →
**喂给同一个 `pw_diffmvs_geomcons.py` 融合器** →
和 `fused_trio_*.ply` 并排做**真彩 PLY** 对比。

⚠️ 用户对这一步有明确要求:**"一定要真彩 ply!!!"** —— 交过一次全黑点云被批评过。
输出 PLY 前先确认 RGB 不是全 0。

---

## 11. 相关备忘(用户的持久记忆,值得先读)

- `project_pocketworld_mvs_license_map_and_apde.md` — 许可地图 + APDe 源码实测
- `project_pocketworld_casdiffmvs_production_gap.md` — CasDiffMVS 家底与缺口
- `feedback_verify_it_actually_landed_in_production.md` — "装机≠生效"
- `feedback_delivery_lossless_absolute_no_frame_loss.md` — 交付绝对无损铁律
- `feedback_speedup_means_less_work_not_smoothing.md` — 提速=减少工作量
- `feedback_tmp_is_ephemeral_use_progecttwo.md` — /tmp 会被清空
- `project_pocketworld_gpu_ts_ninestage_unlocked.md` — A16 占用率真凶=lane 私有数组
