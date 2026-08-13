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
| C1 | iOS 每 stage storage buffer 上限约 10 | **逐 kernel 生效** —— naga 会剥掉未使用的 binding |
| C2 | Metal 没有 runtime array length | naga 自动注入 `_mslBufferSizes`,**占一个槽位** |
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

**生成器本身(`xorwow_next` / `rand_uniform`)是逐行照抄 cuRAND 的 XORWOW。**

## 翻译中抓到的原版细节(差点漏掉)

- `FindMinCostIndex` 用 `<=` 不是 `<` ⇒ **相等时取后面那个**,影响 tie-break
- `ComputeGeomConsistencyCost` 取深度是 `(int)x + 0.5f` ⇒ **先取整再加半像素,是最近邻不是双线性**。深度图上做双线性会在不连续处造假值
- `ComputeBilateralNCCOld` 名字里有 bilateral,但**两条分支的 weight 都硬编码 1.0f** ——
  双边权重从未启用,内循环没有 `exp()`。对 GPU 比名字暗示的友好
- `Get3DPointonWorld_cu` 的旋转用的是 R 的**列**(即 R^T),别写成 R

三次"漏字段"都是被下一层的调用暴露出来的(完整 K[9]/R[9] → `width`/`height` → 相机中心 `c`)
⇒ **逐行照抄比"理解后重写"安全**。

## 进度

| | |
|---|---|
| ✅ 已搬 | 类型 + 叶子数学 + binding 契约 + 单应/投影 + XORWOW/法向 + 几何一致性 + **热点 NCC** |
| ⬛ 待搬 | `CheckerboardPropagationStrong`(343 行)+ `PlaneHypothesisRefinementStrong`(57)+ 17 个 kernel |
| ⬛ 待做 | 输入转换(npz → 相机/图像/深度范围/邻居表)、多 kernel 驱动、414 帧质量对比 |

约 25% → 现在约 35%。

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
