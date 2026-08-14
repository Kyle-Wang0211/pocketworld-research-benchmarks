# APDe-MVS → WGSL 跨端移植(进行中,2026-08-14)

## 为什么做这件事

跨端要求(iOS / Android / 鸿蒙)改变了 MVS 选型的计算:

- **CasDiffMVS(学习式)**:我们手上的是 CoreML,**iOS 独占**。跨端只有 MNN 一条路
  (唯一在 Android GPU 上同时有 grid_sample 与 3D 卷积的运行时)。而 MNN issue #4110
  报告 GPU 内存约为 CPU 的 2 倍 —— 485MB × 2 + App 自身 1020MB 会**超出 iPhone 11 的
  1700MB 预算**。且权重带 DTU 血统(DTU 无任何许可授予)。
- **APDe-MVS(传统)**:**不需要任何 NN 运行时**,只依赖 GPU compute。
  MIT 许可,SAM 是可关插件(`--no_sam`),**零强制权重**。
  ETH3D test F1 **89.15** vs CasDiffMVS 85.11(新 ckpt 85.99)。

⇒ 值得把它移到我们的跨端 GPU 栈上,先量速度、再比质量。

## 技术路线:编译期转译,运行时不带第三方图形层

```
一份 WGSL
  ├─ naga ──→ SPIR-V ──→ Android / 鸿蒙(原生 Vulkan)
  └─ naga ──→ SPIR-V ──→ spirv-cross ──→ MSL ──→ iOS(原生 Metal)
```

这是 **bgfx shaderc / Qt qsb / Filament matc / sokol-shdc / Godot / Unreal**
六个出货项目在跑的同一条配方。工具全留在 CI,**出货二进制里一行第三方代码都不进** ——
这是它相对 Dawn(iOS "best effort" / Android "WIP" / 鸿蒙零支持)与
wgpu(strip 后 6.8MB/ABI,naga 剔不掉)的本质区别。

鸿蒙侧的依据:OpenHarmony NDK 官方支持 Vulkan(华为提交的 Khronos 一致性产品
Maleoon 910/920/935 **全部 Vulkan 1.3**),`vkCmdDispatch`/`vkCreateComputePipelines`
等 compute 入口全在导出符号表里。

## 六条跨端约束(全部由编译器实测确认,不是读文档得来的)

| | 约束 | 怎么发现的 |
|---|---|---|
| C1 | iOS 每 stage storage buffer 上限约 10 | **逐 kernel 生效** —— naga 会剥掉未使用的 binding。实测最胖的 `*_pixel_update_weak` = 1 uniform + **9 storage**,贴线 |
| C2 | Metal 没有 runtime array length | 查长度会让 spirv-cross 注入额外的 sizes buffer,**占一个槽位**。我们全程用 `Params` 传长度 ⇒ 实测 `grep spvBufferSizeConstants k_*.metal` **零命中**,槽位红利已兑现 |
| C3 | workgroup size 在 Metal 是 host 侧参数 | MSL entry 里**消失**;SPIR-V 保留 `LocalSize=16x16x1` |
| C4 | 纹理用 f16 而非 f32 | `rgba16float` 默认可过滤;`r32float` 需 `float32-filterable` |
| C5 | binding 布局必须转译期冻结 | naga 出 `[[user(fake0)]]` 占位符;spirv-cross 才给真索引 |
| C6 | **storage 指针不能当函数参数** | naga 直接报错 ⇒ **binding 是共享层契约,不是调用方自由** |

## 实测速度(M3 Pro / Metal / 从 WGSL 转译)

斜率法(repeat 1→16 @1920×1440)分离固定开销与净成本:

| 量 | 值 |
|---|---|
| 单次 NCC 净成本 | **0.53 → 0.89 ms/MP**(缓存友好 → 访问发散) |
| dispatch 固定开销 | 0.43 ms |
| 每参考图 @896×512 | **29–47 ms**(仅 NCC) |
| 414 帧全做参考图 | **12–19 秒**(仅 NCC,M3 Pro) |

**斜率随 repeat 单调上升**(0.53→0.89):重复时每次换源视图与假设深度,
纹理访问发散把缓存打穿。真实算法正是 9 假设 × 4 视图的发散访问,
**所以 0.894 才是该用的数**。

外推依据全部取自源码,非估计:`max_iterations=3`(main.h:81)、
`num_images=5` ⇒ 4 个源视图、`strong_radius=5/increment=2` ⇒ 6×6=36 次取样、
`CheckerboardPropagationStrong` 调 `ComputeMultiViewCostVector` 9 次
⇒ 每参考图 NCC 次数 ≈ 像素 × 3 × 9 × 4。

### 判读

19 秒已吃掉 30s 预算的三分之二,而且**只有 NCC**(不含传播/精修/RANSAC/锚点/融合),
**跑在 M3 Pro 而非手机**。手机上一定超。

三条减法:① 减参考图数(414 帧不必都做参考,选 1/4 ⇒ ~5 秒,**这是最大的一刀**)
② 降分辨率(896×512 已很低,再降伤质量)③ `max_iterations` 3→2(省 33%)。

⚠️ A16/A13 与 M3 Pro 的实际比值**未测**,不外推。

## 移植偏离账(逐条列出,不藏)

| # | 偏离 | 原因 | 状态 |
|---|---|---|---|
| 1 | `Camera` 用 vec4 填充的扁平数组,非 `float[9]` | WGSL 对齐规则,机械必需 | ✅ 无选择 |
| 2 | 4 张 uchar 图打包成 1 个 buffer | C1 | ✅ 行为等价 |
| 3 | `curand_init` 的 2^67 skipahead 未复刻,改哈希播种 | WGSL 里代价过高 | ⚠️ **数列不与 CUDA 逐位相同**,parity 对拍时随机路径的差异是预期内的 |
| 4 | 种子从 `clock64()` 改成 host 传入的固定值 | 原版跑两次结果不同,撞"交付绝对无损"铁律 | ✅ 必须。想复现原版行为传时间戳即可 |
| 5 | `while(s>=1.0)` 加 64 次上限 | GPU 无界循环挂死风险 | ⚠️ 加固,不改分布 |
| 6 | `ncc_finalize` 抽成共享函数(原版两分支各自复制粘贴) | 我的失误 | 🔴 已标注。行为等价但违反逐行照抄 |
| 7 | 自适应棋盘 8 向做了结构化(原版复制粘贴 8 遍) | 8 份复制在 WGSL 里极易抄错边界 | ⚠️ 行为逐点等价,parity 对不上时要多查一层 |
| 8 | `InitRandomStates` 不再是独立 kernel | 确定性播种后不需要常驻状态 | ✅ 省一个 dispatch + 24 B/px |
| 9 | **`ComputeBilateralNCCNew` 的 `ref_pt` 越界读被钳制** | 原版(APD.cu:527)对 `sa_mask[ref_pt...]` **没有任何边界检查**,在 CUDA 上是越界读相邻显存;WGSL/naga 会把 storage 索引钳到界内 | ⚠️ **图像四边一圈的行为与 CUDA 版不同**。属于"移植使之更安全",不是抄错,但 parity 对拍要把边界像素排除 |
| 10 | 8 个上游死函数**不搬** | 逐个 grep 复核后确认零调用点(见下节) | ✅ 不搬死代码不构成偏离,登记以备核查 |

**生成器本身(`xorwow_next` / `rand_uniform`)是逐行照抄 cuRAND 的 XORWOW。**

## 🔴 复核后推翻的两条旧结论(2026-08-14 搬弱纹理支时)

**① 「NCCNew 里双边权重是真启用的」—— 错的。**
旧结论的依据是「`SpatialGauss`/`RangeGauss` 存在」。逐行核对源码后两条反证:

- `APD.cu:534` 是 `float weight = 1.0f;` —— NCCNew 内循环的权重同样硬编码 1.0,
  和 NCCOld 一模一样,内循环里**没有任何 `exp()`**。
- `grep -n "SpatialGauss\|RangeGauss" APD.cu` **只有 2 行(定义本身),零调用点**。

⇒ "Bilateral" 这个名字在整份 `APD.cu` 里都是空头衔。对 GPU 反而是好消息。

**② 「还剩 17 个函数 / 690 行」—— 实际只有 9 个 / 约 590 行是活的。**
另外 **8 个是上游死代码**,逐个 grep 复核过调用点:

| 死函数 | 行 | 调用点 |
|---|---|---|
| `getTopNIndex` | 19 | 0 |
| `ComputeMultiViewInitialCost` | 32 | 0 |
| `GeneratePertubedPlaneHypothesis` | 18 | 0 |
| `TriangleArea` | 11 | 0 |
| `Vec3CrossVec3` | 8 | 0 |
| `SpatialGauss` / `RangeGauss` | 5 + 5 | 0 |
| `unSetBit` | 4 | 1 处 —— 但唯一调用点(`APD.cu:797`)**就在死函数 `ComputeMultiViewInitialCost` 体内** ⇒ 一并死 |

⇒ 这 8 个**不搬**,并在此登记,免得下一个接手的人以为漏了。

## 翻译中抓到的原版细节(差点漏掉)

- `FindMinCostIndex` 用 `<=` 不是 `<` ⇒ **相等时取后面那个**,影响 tie-break
- `ComputeGeomConsistencyCost` 取深度是 `(int)x + 0.5f` ⇒ **先取整再加半像素,是最近邻不是双线性**。深度图上做双线性会在不连续处造假值
- `ComputeBilateralNCCOld` 名字里有 bilateral,但**两条分支的 weight 都硬编码 1.0f** ——
  双边权重从未启用,内循环没有 `exp()`。对 GPU 比名字暗示的友好
- `Get3DPointonWorld_cu` 的旋转用的是 R 的**列**(即 R^T),别写成 R
- `PlaneHypothesisRefinementWeak` 里拟合平面为零向量时是 **`return`(整个函数放弃)**,
  不是 `continue` —— 抄成 continue 会让弱纹理像素多吃一轮随机精修
- `CheckerboardPropagationWeak` 在精修**之前**就写了一次 `costs[center] = cost_now`,
  而末尾 `REFINE_INIT` 的比较基准正是这一次写进去的值 ⇒ **写回时序本身是语义**,
  挪到函数末尾统一写会改变判据
- Weak 支的几何一致性判据**只看 `geom_consistency`**,Strong 支是
  `geom_consistency && use_impetus`;Weak 的代价累加带 `view_weights[j] > 0` 守卫,
  Strong 没有 —— 两处极易照 Strong 抄串
- `CheckerboardPropagationWeak` 里「算代价」那轮要求锚点是 STRONG,
  「算先验」那轮**不要求** ⇒ 两个循环不能合并
- 无效方向的几何代价用**常数 3.0** 顶上(= `ComputeGeomConsistencyCost` 的 max_cost),
  不是跳过
- **两段 RANSAC 不是同一个**:`GenAnchors` 里那段按**内点计数**评分(带阈值)、
  把 `.w` 当深度直接用;`RANSACToGetFitPlane` 按**内点距离求和**评分(无阈值)、
  先 `ComputeDepthfromPlaneHypothesis` 反解深度,而且最后要按视线**给法向定向**
  (取反时**连 `.w` 一起取反**)
- `ComputeBilateralNCCNew` 里锚点投影的边界检查用的是 **ref 图的 width/height**,
  不是 `src_camera` 的 —— 与同一函数开头那次早退检查口径不一致(上游笔误,照抄)

三次"漏字段"都是被下一层的调用暴露出来的(完整 K[9]/R[9] → `width`/`height` → 相机中心 `c`)
⇒ **逐行照抄比"理解后重写"安全**。

## 进度

| | |
|---|---|
| ✅ 已搬 | 类型 + 叶子数学 + binding 契约 + 单应/投影 + XORWOW/法向 + 几何一致性 + 热点 NCC + 传播/精修(Strong)+ 初始化/中值滤波/局部精修 + GenAnchors + DepthToWeak + **弱纹理传播支全部** |
| ✅ kernel | **17 个入口点全部编译链接通过**,M3 Pro 占用率**全 1024** |
| ⬛ 待做 | 输入转换(npz → 相机/图像/深度范围/邻居表)、多 kernel 驱动、414 帧质量对比 |

**kernel 侧移植已完成**(35% → 90% → **100%**)。剩下的全是"接上去"的工程,不再是搬运。

### 本轮(弱纹理传播支)搬了什么

| 文件 | 行 | 内容 |
|---|---|---|
| `apde_ncc_new.wgsl` | 208 | `GetAnchorPoint` / `Softmax` / **`ComputeBilateralNCCNew`**(可变形 NCC) |
| `apde_weak_prop.wgsl` | 283 | `ComputeMultiViewCostVectorNew` / `PlaneHypothesisRefinementWeak` / **`CheckerboardPropagationWeak`** |
| `apde_ransac.wgsl` | 120 | **`RANSACToGetFitPlane`** |
| `apde_entries.wgsl` | +35 | `black/red_pixel_update_weak` + `ransac_fit_plane_kernel` |

新增 binding 12 `fit_plane_hypos`(RANSAC 的输出 → 弱纹理精修的第一候选),
`Params` 新增 `weak_radius` / `weak_increment`(main.h:90-91,默认 5/5)。

**代价规模**:单次 NCCNew ≈ `36 + 8×9 = 108` 次取样,是 NCCOld(36 次)的 **3 倍** ——
k=0 用 `strong_radius/increment`(5/2 ⇒ 6×6),k=1..8 用 `weak_radius/increment`(5/5 ⇒ 3×3)。
弱纹理像素的代价评估天然比强纹理贵 3 倍,这是 APD 的设计成本,不是移植开销。

### 🔴 顺手修掉的一个静默隐患

`host/ncc_bench.mm` 的 `Params` 结构体**早已与 WGSL 脱节**:WGSL 侧在搬
refine/init/anchors/depth2weak 时长到了 21 个字段(84 B),host 侧还停在 10 个(40 B)。
`ncc_bench` 用到的几个字段偏移恰好没变,所以"看起来还能跑",但 uniform buffer 只给了 40 B
而 shader 按 96 B 读 —— 正是交接说明 §10.3 点名的那类**不报错的静默错位**。

已改成两边**显式补齐到 24 个 4 字节字段 = 96 B**(不留隐式尾部 padding),
并在 host 侧加了 `static_assert(sizeof(Params) == 96)` 当门 ——
这道门在本轮**当场拦下了一次**我自己的字段数算错(25 个字段 = 100 B)。

## 🔴 上生产前的硬阻断

**Gipuma(GPL-3.0)血统取证未完成。** ACM 全家与 APD 系的 README 都写着
"largely benefits from Gipuma",而 **MIT 声明不能自动洗白逐行抄自 GPL 的代码**。
spike 只测性能不进产品,不受影响;**要真上,取证必须先过。**

## 复现

```bash
brew install naga-cli spirv-cross glslang     # Xcode 提供 metal 编译器
./tools/build.sh /tmp/apde_build
/tmp/apde_build/ncc_bench 896 512 0.0 /tmp/apde_build/apde.metallib 1
```

载具内建**有效性自检**:若 `代价=COST_MAX 占比` 过高,说明内循环被 early-out 跳过,
数字不可信。移植期它真的抓到过一次 host/WGSL 结构体错位(占比 100%、耗时假性快 33 倍)。
