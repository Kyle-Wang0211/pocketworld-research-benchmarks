# 可移植着色器工具链调研:一份源码 → Metal + Vulkan,且支持 cooperative matrix

调研日期:2026-09-04。所有结论后面直接跟一手来源(仓库文件路径 + 行号 / 官方文档 / PR 编号)。
凡是「查不到」的地方都显式标注,没有用推测填空。本次调研未跑任何 GPU 实验。

---

## 0. 结论速览

| 路线 | 一份源码 → MSL + SPIR-V | cooperative matrix(8×8×8, f16→f32) | 能否解掉 H1/H2 天花板 | 结论 |
|---|---|---|---|---|
| **Slang**(Khronos, Apache-2.0 WITH LLVM-exception) | **能**(`-target metal` / `metallib` / `spirv` / `wgsl` / `hlsl` / `glsl` / `cuda`) | **能**(`linalg.CoopMat` → Metal `simdgroup_matrix<T,8,8>` + `simdgroup_multiply_accumulate`;SPIR-V → `OpTypeCooperativeMatrixKHR`) | **H1 能**(`subgroupMemoryBarrierShared()` → `simdgroup_barrier(mem_threadgroup)`)<br>**H2 要用 `__target_switch`/`__requirePrelude` 逃生舱** | **推荐候选**,但有两个必须自己打的钉子(§6.2) |
| **SPIRV-Cross**(Khronos, Apache-2.0) | SPIR-V → MSL **能**(2026-03 合入,PR #2596) | **能**,且我们的混合精度会被原样透传成**合法** MSL(§2.3);但上游零测试覆盖 | ❌ 不解决 —— 它只是转译,SPIR-V 里没有的东西它变不出来 | 可作为「SPIR-V 当真源」的离线备胎;**但 MoltenVK 完全不支持,Apple 上不能走运行时 Vulkan** |
| **给 tint 打补丁 / inline MSL** | — | — | — | **❌ 不可行**:`tint::msl::writer::Options` 全字段已逐条列出,**没有任何 passthrough / inline-MSL 机制**(§3.1);社区无维护 fork(§3.2) |
| **维持 WGSL + iOS 手写 Metal 第二后端** | 一个核两份源码 | 已在跑 | 天花板保留 | 现状。代价固定在这一个核上 |

**五条最重要的更正 / 新事实**

1. 🔴 **「MSL 的 `simdgroup_multiply_accumulate` 不支持混合精度」是错的。**
   本机 Apple 工具链头文件 `metal_simdgroup_matrix` 第 206–211 行有 **R/T/U/V 四个独立类型参数**,
   约束只要求四者都是浮点;`half×half→float` 已在本机 `xcrun metal -c` **编译通过(EXIT=0,3792 字节 AIR)**。
   Apple 的 MSL Spec PDF §6.8.2 Table 6.10 印的单-T 签名是**不完整的**,凡据此得出的「不支持」结论都要撤回。
   同一头文件第 24–27 行 `_valid_simdgroup_matrix_size` 只允许 `cols==8 && rows==8` ⇒ **8×8 是 Metal 层硬上限,不是转译器的锅**。
   第三方佐证:llama.cpp 的 `ggml-metal/kernels/mul_mm.metal` 生产代码里 A/B 是 `simdgroup_half8x8`、
   累加器 `mc` 是 `simdgroup_float8x8`(第 205/309/737 行),几十个模板实例都在跑混合精度。
2. 🔴 **「SPIRV-Cross 不懂 cooperative matrix」也是错的。** `spirv_msl.cpp` 里 21 处命中,
   Load/Store/MulAdd/Length + 类型映射全齐(PR #2596,merged 2026-03-13),限制正好是 8×8 + Subgroup + half/float/bfloat。
3. 🟢 **Slang 能表达 WGSL 表达不了的 `simdgroup_barrier`**(§5.1)——
   这是你 `research_tint_codegen.md` 里 H1 的直接解药,而且是核心模块自带的一行 API,三端各自映射齐全。

4. 🟢 **兜底方案的答案(§4)**:「一份算子定义 + 每端一份手写 kernel」**是行业标准做法,没有例外** ——
   ggml(5 套独立 kernel,9MB,零共享)、MNN(4 份 GEMM)、TFLite GPU(168 个共享算子定义 + 每端一张宏替换表)、
   TVM(一份 TIR + N 个平级 emitter,Metal 与 WGSL 是兄弟不是翻译关系)。
   而且 **Slang 自己的 MMA 标准模块也是三份 kernel**(§6.1b)。
   ⚠️ 反过来:**「因为 codegen 运行期性能而放弃 WGSL/中间层」的公开决策记录,一例都查不到**(§4.0)。
5. 🔴 **长期战略成本(§4.2 b)**:llama.cpp 的 Metal GEMM 已经接上 **Metal 4 Tensor API
   (`mpp::tensor_ops::matmul2d`)**,而 WebGPU subgroup matrix 提案**至今是 Draft**,
   规范里 Metal 映射写死为 `simdgroup_matrix<T,8,8>` —— **WGSL 结构上进不去 Apple 下一代矩阵单元**。
   (SPIRV-Cross 与 Slang 目前也都没有 `matmul2d` 映射;只有手写 MSL 能进。)

**关于 12.8% / 25.8% 本身**:Dawn toggle 层与 `math_mode` 跨臂变量你自己的三份调研已经挖穿了,
本报告不重复(§3.3 只做交叉引用);并行调研另外提出的三个 toggle(`disable_polyfills_on_integer_div_and_mod`
等)我拿你们的实际产物 `cur.metal` 逐条核过,**全部不成立**(§4.10)。
⇒ **沙箱税这条线已经见底。本报告的增量是:H1/H2 是 WGSL 语言天花板,
换编译器能不能解决,取决于新编译器有没有逃生舱 —— Slang 有,tint 没有。**

---

## 1. Slang

### 1.0 归属与 License(已核到原文)

- 仓库:`shader-slang/slang`,默认分支 `master`。
- `LICENSE` 第 1 行原文:`SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception`
  —— https://github.com/shader-slang/slang/blob/master/LICENSE
  (GitHub 的 license 探测返回 `NOASSERTION`,是因为文件带 LLVM exception 段落,**不是**许可不明;
  以 SPDX 行为准。**用户给的假设成立。**)
- `README.md` 头部 SPDX 头:`SPDX-FileCopyrightText: The Khronos Group, Inc.`
  —— https://github.com/shader-slang/slang/blob/master/README.md
  即版权归 Khronos,与「现由 Khronos 托管」一致。
- FTO:本次**没有**做专利 FTO 检索(超出委托范围),按红线要求需要单独走一遍。

### 1.1 一份源码 → 多目标:能

`slangc -target <target>` 的完整取值表(官方生成的 CLI 参考,`docs/command-line-slangc-reference.md`
的 `## target` 小节):

```
hlsl / dxbc / dxbc-asm / dxil / dxil-asm
glsl                      : GLSL(Vulkan) source code
spirv / spirv-asm         : SPIR-V binary / assembly
metal                     : Metal shader source
metallib                  : Metal Library Bytecode
metallib-asm              : Metal Library Bytecode assembly
wgsl                      : WebGPU shading language source
wgsl-spirv / wgsl-spirv-asm
cuda / ptx / cuobj ...
c / cpp / host-cpp / llvm-ir / slangvm ...
```
—— https://github.com/shader-slang/slang/blob/master/docs/command-line-slangc-reference.md
(`<a id="target-1">` 之后的列表)

所以 **MSL 源码和 metallib 字节码都是一等目标**,SPIR-V 也是,`wgsl` 也在(可以当过渡)。

### 1.2 cooperative matrix:能,但 Metal 侧有明确的能力边界

**(a) 语言层的类型与内建**(核心模块 `source/slang/hlsl.meta.slang`):

- `namespace linalg`(第 28137 行)
- `struct CoopMat<T, S, M, N, R>`(第 28521 行),`__intrinsic_type($(kIROp_CoopMatrixType))`,
  带 `[require(cooperative_matrix)]`
- `coopMatMulAdd<T, saturatingAccumulation, U, V, W, S, M, K, N>(matA, matB, matC)`(第 30403–30419 行),
  **A / B / C / 结果各有独立的元素类型参数 `U / V / W / T`** —— 语言层允许混合精度
- 底层 `__intrinsic_op($(kIROp_CoopMatMulAdd)) __coopMatMulAdd<...>`(第 30370–30387 行)

—— https://github.com/shader-slang/slang/blob/master/source/slang/hlsl.meta.slang

**(b) 能力原子:Metal 是 cooperative_matrix 的一等提供者**

`source/slang/slang-capabilities.capdef` 第 1438 行原文:
```
alias cooperative_matrix = spvCooperativeMatrixKHR | cuda | _sm_6_10 | metal;
```
—— https://github.com/shader-slang/slang/blob/master/source/slang/slang-capabilities.capdef#L1438

即:同一段 `[require(cooperative_matrix)]` 的代码,`spirv` / `cuda` / `sm_6_10`(DXIL) / `metal`
四个目标都能满足能力检查。

**(c) Metal 后端的实际 emit 代码**(`source/slang/slang-emit-metal.cpp`):

- 类型:第 1449–1462 行
  ```cpp
  case kIROp_CoopMatrixType:
      auto coopType = as<IRCoopMatrixType>(type);
      _validateCoopMatrixType(coopType);
      // Metal's simdgroup_matrix<T, Cols, Rows> uses Cols, Rows order
      m_writer->emit("simdgroup_matrix<");   // ← 落到 simdgroup_matrix
  ```
- MMA:第 692–717 行
  ```cpp
  case kIROp_CoopMatMulAdd:
      ...
      m_writer->emit("simdgroup_multiply_accumulate(");  // ← 落到 simdgroup_multiply_accumulate
  ```
- 校验:`_validateCoopMatrixType`,第 1256–1279 行,只允许
  - `rows == 8 && cols == 8`(否则报 `Unimplemented`)
  - `MemoryScope::Subgroup`
  - 元素类型 `kIROp_HalfType` 或 `kIROp_FloatType`

—— https://github.com/shader-slang/slang/blob/master/source/slang/slang-emit-metal.cpp

**(d) SPIR-V 后端**:`source/slang/slang-emit-spirv-ops.h` 第 179 行 `SpvOpTypeCooperativeMatrixKHR`
—— https://github.com/shader-slang/slang/blob/master/source/slang/slang-emit-spirv-ops.h
即 SPIR-V 侧走的是 **KHR**(不是 NV-only)cooperative matrix。
另:`docs/user-guide/a2-01-spirv-target-specific.md` 第 30 行:
「If the shader uses `CoopVec` or `CoopMat` intrinsics, then the Slang compiler will automatically
use `vk_mem_model` capability.」

**(e) 官方文档里写死的 Metal 能力边界**(`hlsl.meta.slang` 第 28506–28511 行,`CoopMat` 的文档注释):
```
Metal backend (simdgroup_matrix):
- Only 8x8 matrix dimensions
- Only half and float element types
- Supported operations: fill, Load, Store, coopMatMulAdd
- No per-element access (subscript, GetLength, getCount)
- No scalar multiply, copyFrom, transpose, reduce, or MapElement
```

**对我们的适配度**:
- 8×8×8 ✅(正好落在唯一支持的形状上)
- f16 / f32 元素类型 ✅
- `fill / Load / Store / coopMatMulAdd` ✅ —— 我们 GEMM 段只需要这四个
- 「无逐元素访问」:**大概率不影响**,因为 WGSL 的 subgroup matrix 本来也只能 `subgroupMatrixStore`
  到 workgroup/storage 再做归约;双向 top-2 归约本来就在 store 之后做。但这一条需要按我们现有 WGSL
  内核的实际写法对一遍。

**(f2) threadgroup 存取已被测试覆盖**:`tests/cooperative-matrix/` 下有 10 个 `metal-*` 用例,
其中 `metal-load-store-groupshared.slang`(threadgroup 内存)、`metal-load-store-pointer.slang`、
`metal-load-store-rwbyteaddressbuffer.slang`、`metal-load-store-rwstructuredbuffer.slang`、
`metal-fill.slang`、`metal-mat-mul-add.slang`、`metal-coverage.slang` —— 覆盖了我们 GEMM 段需要的
「Load 到 CoopMat / MMA / Store 回 threadgroup 做尾段归约」这条完整链路。
—— https://github.com/shader-slang/slang/tree/master/tests/cooperative-matrix

**(f) 硬性负面清单**:`tests/cooperative-matrix/metal-unsupported.slang` 是一份 DIAGNOSTIC_TEST,
逐条钉死 Metal 上会被拒的操作(getCount / subscript / GetLength / 标量乘 / 非 8×8 / 非 half-float /
saturating accumulation)。第 9–10 行注释原话:
「Verify the compiler rejects unsupported CoopMat operations on Metal.
 Metal's simdgroup_matrix only supports fill, Load, Store, and coopMatMulAdd.」
—— https://github.com/shader-slang/slang/blob/master/tests/cooperative-matrix/metal-unsupported.slang

### 1.3 ✅ 混合精度(f16 输入 / f32 累加)—— 已当场证伪「不支持」的说法

这是我们的确切形状,单独拿出来讲,因为**网上和 Slang 自己的注释都说不支持,但那是错的**。

**(a) 一手判据:Apple 自己的 Metal 工具链头文件,四个类型参数完全独立。**
本机 `metal_simdgroup_matrix` 头(Apple metal 32023.864 / `Metal.xctoolchain` v17.3.7003.10,
路径 `.../Metal.xctoolchain/usr/metal/32023/lib/clang/32023.864/include/metal/metal_simdgroup_matrix`)
第 206–211 行:
```cpp
template <typename R, typename T, typename U, typename V, int K, int Rows, int Cols>
METAL_FUNC enable_if_t<_valid_simdgroup_multiply_accumulate_v<R, T, U, V, K>>
simdgroup_multiply_accumulate(thread simdgroup_matrix<R, Cols, Rows> &d,
                              simdgroup_matrix<T, K,    Rows>  a,
                              simdgroup_matrix<U, Cols, K>     b,
                              simdgroup_matrix<V, Cols, Rows>  c)
```
第 201–204 行的约束只要求四者**都是浮点**:
```cpp
using _valid_simdgroup_multiply_accumulate_types =
  conjunction<is_floating_point<R>, _valid_simdgroup_multiply_operand_type<T, K>,
              _valid_simdgroup_multiply_operand_type<U, K>, is_floating_point<V>>;
```
⇒ **R/T/U/V 四个独立类型参数,half×half→float 完全合法。**
(注:Apple 的 MSL Spec PDF §6.8.2 Table 6.10 印的是简化的「单一 T」签名 —— **规格书那张表是不完整的**,
以头文件为准。凡引用规格表得出「MSL 不支持混合精度」的结论都要撤回。)

同一头文件第 24–27 行还钉死了尺寸:
```cpp
METAL_FUNC constexpr bool _valid_simdgroup_matrix_size(int cols, int rows)
{ return (cols == 8 && rows == 8); }
```
⇒ **8×8 是 Metal 头文件层的硬上限**,不是任何转译器的锅。我们正好只用 8×8。

**(b0) 为什么很多人「查不到」这个头文件 —— 路径变了,不是不存在。**
Xcode 26 把 Metal toolchain 拆成单独下载组件,**`/Applications/Xcode.app` 里 `find` 不到任何
`metal_simdgroup_matrix` / `metal_stdlib`**;`~/Library/Developer/DVTDownloads/MetalToolchain/mounts/…`
在本机也是空占位目录。真实位置是 cryptex 挂载点:
```
$(dirname $(dirname $(xcrun -f metal)))/metal/32023/lib/clang/32023.864/include/metal/metal_simdgroup_matrix
# 展开 = /var/run/com.apple.security.cryptexd/mnt/com.apple.MobileAsset.MetalToolchain-v17.3.7003.10.Z1Zvim/
#          Metal.xctoolchain/usr/metal/32023/lib/clang/32023.864/include/metal/metal_simdgroup_matrix
```
⇒ 任何基于「Xcode.app 里搜不到头文件」而停在「无法验证」的结论都应该撤回;
用 `xcrun -f metal` 反推目录即可拿到。

**(b) 当场编译验证(纯 CPU,无 GPU):**
```metal
simdgroup_matrix<half,8,8> a, b;
simdgroup_matrix<float,8,8> c(0.0f), d;
simdgroup_multiply_accumulate(d, a, b, c);
```
`xcrun metal -c` → **EXIT=0,产出 3792 字节 AIR,零警告**
(工具链 `Apple metal version 32023.864 (metalfe-32023.864)`, target `air64-apple-darwin25.1.0`)。

**(b2) 一条需要点名撤回的规格推断。**
有一种读法是:MSL Spec §6.8 / Table 7.3 把 half×half→float 列在 Metal 4 `matmul2d` 名下,
所以 `simdgroup_matrix` 不该有混合重载。**这条推断被三重证据推翻**:
(i) 头文件 `:201-211` 的四个独立类型参数;(ii) 本机 `xcrun metal -c` EXIT=0;
(iii) llama.cpp `ggml-metal/kernels/mul_mm.metal` 生产代码里几十个 `simdgroup_half8x8` ×
`simdgroup_half8x8` → `simdgroup_float8x8` 的模板实例。
规格书那张表是**不完整的**,不是**排他的**。

**(c) 因此 Slang 侧的状态是:语言层可表达、emitter 不拦、Metal 收货 —— 但零测试覆盖。**
- `coopMatMulAdd` 签名有独立的 `U / V / W / T`(§1.2a),Vulkan 标准模块已在用
  (`mma-tiled-vulkan.slang:165` `coopMatMulAdd<T, false, half, half, T, ...>`)
- Metal emitter 的 `_validateCoopMatrixType` **只逐个类型查 half|float,不查 A/B/C 是否同类型**(§1.2c),
  `kIROp_CoopMatMulAdd` 的 emit 也只是原样吐四个操作数(§1.2c)
- ⚠️ 但 `source/standard-modules/neural/mma-tiled-metal.slang:64` 的注释写着
  `// Metal: no hybrid precision -- A, B, C all use the same type T.`,且该模块全篇用单一 `T`;
  `tests/cooperative-matrix/` 下 10 个 `metal-*` 测试**没有一个跑混合精度**

**判定**:按 (a)(b),混合精度在 Metal 层**确定可用**;Slang 那句注释与它自己的代码相矛盾,
最可能是该 neural 模块自身的设计约束(要跨 CUDA/Vulkan/Metal 复用同一套 `T`)被写成了平台限制。
**这是迁移前第一个要打的钉子,一条命令即可定案**:
```
slangc -target metal -stage compute -entry main mixed.slang
# mixed.slang 里写 coopMatMulAdd<float, false, half, half, float, MemoryScope.Subgroup, 8, 8, 8>(...)
```
若被前端拒,fallback 是 `__target_switch`(§1.7)把这一句换成 `__intrinsic_asm`,其余不变。
(本次未下载 slangc 二进制执行 —— 下载可执行文件需要你本人授权,所以这一步留给你跑。
 官方 macOS arm64 包:`slang-2026.17-macos-aarch64.tar.gz`,55MB,
 https://github.com/shader-slang/slang/releases/tag/v2026.17)

### 1.3b Slang 会往 MSL 里注入什么(逐字节可复现的第一个观察点)

`source/slang/slang-emit-metal-prelude.cpp` 的 `kMetalBuiltinPreludeSimdgroupMatrixOps`
是 CoopMat 触发时被 `ensurePrelude(...)` 注入的**全部**内容,可以直接和我们手写的 MSL 对比:

```cpp
#include <metal_simdgroup_matrix>
template<typename T, int Cols, int Rows, typename V>
void _slang_simdgroup_fill(thread simdgroup_matrix<T, Cols, Rows>* dest, V val) {
    *dest = make_filled_simdgroup_matrix<T, Cols, Rows>(T(val));
}
template<typename Matrix, typename T>
Matrix _slang_simdgroup_load(const device T* src, ulong elements_per_row) {
    Matrix result; simdgroup_load(result, src, elements_per_row); return result;
}
template<typename Matrix, typename T>
Matrix _slang_simdgroup_load_transpose(const device T* src, ulong elements_per_row) {
    Matrix result; simdgroup_load(result, src, elements_per_row, ulong2(0), true); return result;
}
// 同名的 threadgroup T* 两个重载
```
—— https://github.com/shader-slang/slang/blob/master/source/slang/slang-emit-metal-prelude.cpp

三点值得注意:
1. ✅ **`device T*` 和 `threadgroup T*` 都有重载**,我们「Load→MMA→Store 回 threadgroup 做尾段」的链路可用。
2. ⚠️ **Load 是「构造临时 + 传出返回值」而不是原地写**(`Matrix result; simdgroup_load(result,...); return result;`)。
   你们已经排除过「原地累加」这个变量;这里是同型问题的另一处,**要在 AIR 层 diff 一次**确认临时被消掉了。
3. ⚠️ **`matrix_origin` 被写死成 `ulong2(0)`**,即分块寻址只能靠指针偏移做,不能用 `simdgroup_load` 的
   origin 参数。若我们现有手写核用了 non-zero origin,这一处要改写法。
4. **没有 `_slang_simdgroup_store` 辅助模板** —— Store 由 `hlsl.meta.slang` 里的 intrinsic 直接内联发出。

### 1.4 成熟度:不是 experimental,但 Metal coopmat 很新(4 个月)

- Slang 官方的实验性功能清单 `docs/user-guide/a3-experimental-features.md` **只列了一项**:
  Shader Execution Coverage。Metal 目标**不在**实验清单里。
  —— https://github.com/shader-slang/slang/blob/master/docs/user-guide/a3-experimental-features.md
- Metal 目标有专门的 known-limitations 章节:`docs/user-guide/a2-02-metal-target-specific.md`
  (逐条列出 SV 语义映射、资源类型映射、`isParameterLocationUsed` 限制、SubpassInput 限制等)。
  **该文档里没有提 cooperative matrix**(文档滞后于代码)。
- Metal cooperative matrix 的落地时间:
  **PR #10902 "Add Metal cooperative matrix (simdgroup_matrix) support"**,作者 kaizhangNV,
  merged **2026-04-24T02:33:46Z**,commit `cfce571cc`。
  —— https://github.com/shader-slang/slang/pull/10902
  PR 正文里的 "Metal constraints" 三条与 §1.2e 的文档完全一致。
  PR 的 Test plan 里 **"Verify VK/CUDA tests still pass (no regressions) on a machine with GPU support"
  这一项是未勾选的**。
  按发布时间推,第一个包含它的正式版本是 **v2026.8(2026-05-02)**;当前最新 v2026.17(2026-09-04)。
- 维护活跃度证据:`mma-tiled-metal.slang` 的头注释里有**在 Apple M4 上实测出来的调参记录**,
  例如第 14–19 行:tile-grid 布局相比 row-major「costing 8–14% at half and 1–6% at float」,
  重测后「the half gap has mostly collapsed (0–3%), but float still pays 1–16% ...」;
  第 200 行「~5% faster at half on M4」。说明 Slang 团队真的在 Apple 硅上做逐刀 A/B,不是纸面支持。

### 1.4b ⚠️ 成熟度的反面证据:Slang 的 Metal 路径确有从未被编译过的角落

`source/slang/hlsl.meta.slang:12034–12048` 的内部函数 `__subgroupBarrier()`:
```slang
case metal: __intrinsic_asm "simdgroup_barrier(mem_flags::none)";
```
但 Apple 的 `metal_compute` 头文件里 `enum class mem_flags` 的成员是 **`mem_none`**,不是 `none`
(本机 `.../include/metal/metal_compute` 第 13–16 行:`mem_none = __METAL_MEMORY_FLAGS_NONE__`)。
⇒ **这一条路径一旦被触发,生成的 MSL 编译不过。**
(公开 API `subgroupBarrier()`(`glsl.meta.slang:7347`)写的是正确的 `mem_flags::mem_none`,所以主线不受影响。)

**结论**:Slang 的 Metal 后端在**主干路径**上有测试(`tests/metal/` + 10 个 `metal-*` coopmat 用例),
但**边角路径存在从未编译过的代码**。迁移时要按「我们实际用到的每一个内建都过一遍 `slangc -target metal`
+ `xcrun metal -c`」来验,不能假定全语言面都可用。

### 1.5 ⚠️ 查不到的:Slang→Metal 的 codegen 质量 vs 手写 MSL

**Slang 官方没有发布任何「Slang 生成的 MSL vs 手写 MSL」的运行时性能对比。**
`tools/benchmark/` 下只有 `compile.py`(编译期性能),没有运行时基准。
`mma-tiled-metal.slang` 里的百分比都是 **Slang 内部两种布局互比**,不是 Slang vs 手写。
⇒ **换到 Slang 不能假定 codegen 就更快;它解决的是「一份源码」,不自动解决 12.8%。**

### 1.6 Slang 的 WGSL 目标不支持 cooperative matrix(不影响我们)

`docs/user-guide/a2-03-wgsl-target-specific.md` 通篇没有 coopmat / subgroup matrix 条目;
仓库里另有 `docs/generated/tests/design/target-pipelines/wgsl/cooperative-metadata-not-collected-on-wgsl.slang`。
—— 但这对我们无所谓:走 Slang 的话三端应该是
**iOS = `-target metal`/`metallib`,Android + 鸿蒙 = `-target spirv`(Vulkan)**,WGSL 不在链路上。

### 1.7 🟢 Slang 自带逃生舱:手写 MSL 可以留在同一份源文件里

这是 tint 结构性做不到、而 Slang 做得到的一件事。
`docs/user-guide/a1-04-interop.md` 列出四种机制:
- `__intrinsic_asm` —— 把一次函数调用映射成一段目标语言文本(支持 `$0`/`$T0`/`$TR`/`$*0` 等占位符)
- `__requirePrelude` —— 往生成的目标代码里注入任意文本(可以塞一整个手写 MSL 函数)
- `__target_switch` —— 同一个函数按目标分派不同实现;
  文档原话:「Currently, the following targets are supported in a `case` statement:
  `cpp`, `cuda`, `glsl`, `hlsl`, `metal`, `spirv`, and `wgsl`.」
- `spirv_asm` —— 内联 SPIR-V 汇编块

—— https://github.com/shader-slang/slang/blob/master/docs/user-guide/a1-04-interop.md

**含义**:即使 Slang 的 Metal codegen 在某个内层循环上不如手写,也可以只把那一段用
`__target_switch { case metal: __intrinsic_asm "..." ; case spirv: ... }` 换掉,
**其余 99% 逻辑仍然是一份源码**。SOP 仍然是「改一个文件、三端一起升级」。
⚠️ 但文档自己带了警告(第 14–17 行):「The language mechanisms described in this chapter are
considered internal compiler features. ... These mechanisms are also subject to breaking changes
in future releases.」—— 即这些是**内部特性、不保证跨版本稳定**,要锁 Slang 版本。

### 1.8 浮点可复现相关的开关

`slangc` 有 `-fp-mode <precise|fast|default>`(`-floating-point-mode` 同义),
`precise` 的官方描述:「Disable optimization that could change the output of floating-point
computations, including around infinities, NaNs, denormalized values, and negative zero.」
另有 `-denorm-mode-fp16/fp32/fp64 <any|preserve|ftz>`(fp16 那条只对 SPIR-V 生效)、`-O<level>`。
—— https://github.com/shader-slang/slang/blob/master/docs/command-line-slangc-reference.md

---

## 2. SPIRV-Cross

### 2.0 结论先行:**「SPIRV-Cross 不懂 cooperative matrix」这个前提是错的 —— 它懂,而且限制正好匹配我们的 8×8×8。**

基准 commit `a9d9b314472b425b196ec3794f373a0a2a964813`(main,2026-09-03)。

### 2.1 `spirv_msl.cpp` 里的 cooperative matrix 处理(21 处命中,不是零命中)

| 落点 | 行号 | 发出的 MSL |
|---|---|---|
| `case OpCooperativeMatrixLoadKHR:` | 10759(发射在 10827–10832) | `simdgroup_load(...)`(列主序走 `ulong2(0), true`) |
| `case OpCooperativeMatrixStoreKHR:` | 10839(发射在 10904–10909) | `simdgroup_store(...)` |
| `case OpCooperativeMatrixMulAddKHR:` | 10916(发射在 10927) | `simdgroup_multiply_accumulate(D, A, B, C);` |
| `case OpCooperativeMatrixLengthKHR:` | 10938 | `sizeof(T::storage_type)/sizeof(component)` |
| `OpTypeCooperativeMatrixKHR` 类型映射 | 17113–17152 | `simdgroup_float8x8` / `simdgroup_half8x8` / `simdgroup_bfloat8x8` |
| 自动插 header | 1949–1954 | `#include <metal_simdgroup_matrix>` |
| `uses_cooperative_matrix` 标记 | 19326–19335 / `spirv_msl.hpp:1418` | — |
| 非法操作拦截(`default:`) | 10957+ | 抛 `"Unsupported operation on cooperative matrix in MSL backend."` |

通用层解析:`spirv_parser.cpp:783–797`(`OpTypeCooperativeMatrixKHR`,存 `scope_id/rows_id/columns_id/use_id`)、
`spirv_common.hpp:637–645`(`struct { uint32_t use_id, rows_id, columns_id, scope_id; } cooperative;`)、
`spirv_cross.cpp`(16 处,access-chain 与 resource-write 追踪)。

—— https://github.com/KhronosGroup/SPIRV-Cross/blob/a9d9b314472b425b196ec3794f373a0a2a964813/spirv_msl.cpp

### 2.2 MSL 后端的硬性门(源码即门)

1. `msl_options.supports_msl_version(3, 1)`,低于 MSL 3.1 抛异常(`spirv_msl.cpp:17121`)
2. 仅 `ScopeSubgroup`(`:17129`)
3. **仅 8×8**(`:17137`)
4. 分量类型仅 Float / Half / BFloat16(`:17141–17150`)
5. `CooperativeMatrixOperands` 任何 flag(含 `SaturatingAccumulationKHR`)一律抛(`:10922–10923`)
6. Layout 仅 RowMajorKHR / ColumnMajorKHR,且不许 spec-constant

实测复现(本机 homebrew `spirv-cross 1.4.357.0`):
`16×16` → `MSL cooperative matrices only support 8x8 dimensions.`;
`MSL 3.0` → `Cooperative matrices require MSL 3.1 or later.`

### 2.3 混合精度:SPIRV-Cross 直接透传,而透传出来的 MSL 是**合法**的

`spirv_msl.cpp:10916–10937` 的 MulAdd 分支不校验 A/B 与 C/D 的分量类型是否一致,直接 `statement(...)`。
喂它一份 A/B=`%half`、C/D=`%float` 的 `OpCooperativeMatrixMulAddKHR`(`spirv-val` 判为合法 SPIR-V),
`spirv-cross --msl --msl-version 30100` 输出:
```metal
simdgroup_half8x8  _28; simdgroup_load(_28, &_3._m0[0u], 8u);
simdgroup_half8x8  _29; simdgroup_load(_29, &_3._m0[0u], 8u);
simdgroup_float8x8 _30; simdgroup_load(_30, &_2._m0[0u], 8u);
simdgroup_float8x8 _31;
simdgroup_multiply_accumulate(_31, _28, _29, _30);
```
**按 §1.3(a)(b),这段 MSL 是合法且能编译的** —— 也就是说 SPIRV-Cross 这条路对我们的
f16 in / f32 accum **是通的**,不是「静默出口」。
⚠️ 但上游确实**零测试覆盖**:PR #2596 的 6 组参考输出只有 f32×f32→f32 和 f16×f16→f16
(`reference/shaders-msl-no-opt/asm/comp/cooperative-matrix-muladd.asm.msl31.comp`),
所以这是「能跑但没人保证」的状态,回归风险需要我们自己用 696 对台架兜住。

### 2.4 上游态度:不是 wontfix,是「我不做,但别人做了可以合」

- **Issue #2478**("MSL: Support for SPV_KHR_cooperative_matrix (and SPV_KHR_shader_bfloat16)",2025-05-01,**至今 open**,因为 bfloat16 部分未完)
  - HansKristian-Work(2025-05-02)原话:
    *"Not interested in implementing this myself, but if someone implements it natively, it can probably be merged."*
  - dboyan(2025-05-02)原话(限制预判,后来全部应验):*"MSL only allows 8x8 `simdgroup_matrix`"*、
    *"MSL does not support specifying behavior related to `SaturatingAccumulationKHR`"*
- **PR #2596**(kabu1204,**merged 2026-03-13**,由 HansKristian-Work 合入),
  diff `spirv_msl.cpp +333/-4`、`spirv_msl.hpp +1/-0`、`spirv_cross.cpp +8/-1`、12 个测试文件。
  作者原话列的三条限制:subgroup scope only / 8x8 only / matrix operand mask 一律抛;
  并解释第三条:*"`SaturatingAccumulationKHRMask`, although MSL spec doesn't document, experiment shows
  that simdgroup_multiply_accumulate doesn't saturate or clamp and cannot be controlled."*
- 相关 commit:`2047b7b88`(2026-02-10 initial)、`6fc910e9b`、`cda74fe58`(2026-02-28)、`8f3792430`、merge `e52532a60`

—— https://github.com/KhronosGroup/SPIRV-Cross/issues/2478 、 https://github.com/KhronosGroup/SPIRV-Cross/pull/2596

### 2.5 HLSL 后端:零命中(与主线关系次要)

`spirv_hlsl.cpp` + `spirv_hlsl.hpp` grep `Cooperative|coopmat|WaveMatrix|linalg` → **ZERO HITS**。
`CompilerHLSL::type_to_glsl`(`spirv_hlsl.cpp:399`)不处理 `OpTypeCooperativeMatrixKHR`。
参考输出里所有 coop matrix 用例都是 `.vk` 后缀,没有 `.hlsl`。
实测同一份 SPIR-V 走 `--hlsl --shader-model 60` 报的是无关的通用错误
(`Access chains have no default expression representation.`),**失败方式是误导性的**。

### 2.6 项目维护状态:活跃,没有 maintenance-mode 声明

- `README.md` grep `maintenance mode|in maintenance|feature freeze|frozen` → ZERO HITS。
  唯一的弃用字样是 `README.md:19` 的 "Convert SPIR-V to debuggable C++ **[DEPRECATED]**"(指 C++ 后端)。
- repo meta:`archived:false`、`pushed_at: 2026-09-04`、`open_issues_count: 149`;2026-06-01 起 37 个 commit。
- Tag 与 Vulkan SDK 同步(`vulkan-sdk-1.4.357.0` 最新)。GitHub Releases 页停在 2021 是因为只打 tag 不发 release。
- **Khronos 官方推荐替代品:搜不到任何这样的声明**(属「没搜到」,不等于「确认不存在」)。

### 2.7 🔴 MoltenVK 对 `VK_KHR_cooperative_matrix`:**确认不支持**(不是没搜到)

- `MoltenVK/MoltenVK/Layers/MVKExtensions.def`(main,176 个 `MVK_EXTENSION` 条目)grep `cooperative` → **ZERO HITS**
- `MoltenVK/MoltenVK/GPUObjects/MVKDevice.mm`(main,5672 行)grep `cooperative` → **ZERO HITS**
- 全仓 code search `cooperative` 只有 1 条命中,在 `Docs/Whats_New.md` 的
  **MoltenVK 1.4.3(Released TBD,尚未发布)** 段落的 "Update to latest SPIRV-Cross" 子列表里
  ——即 MoltenVK 只是 vendor 了 SPIRV-Cross 那段代码,**没有在 Vulkan 层暴露扩展**
  (没有 `VkPhysicalDeviceCooperativeMatrixFeaturesKHR`、没有 `vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR`)
- **Issue KhronosGroup/MoltenVK#2507**(2025-04-27):**open,零 maintainer 回复**;
  2026-03-15 有人在 SPIRV-Cross #2478 里点名 PR 作者问要不要做 MoltenVK 侧,**无人接手**

⇒ **「在 Apple 上跑 Vulkan 拿 cooperative matrix」今天是断路。**
SPIR-V 当唯一真源这条路,在 Apple 侧只能是
**离线 SPIR-V → SPIRV-Cross → MSL 源码 → 自己 `xcrun metal` 编译**,不能指望 MoltenVK 运行时。

—— https://github.com/KhronosGroup/MoltenVK/issues/2507 、
   https://github.com/KhronosGroup/MoltenVK/blob/main/MoltenVK/MoltenVK/Layers/MVKExtensions.def

---

## 3. 「给 tint 打补丁」这条路

### 3.0 引用基准说明:Dawn/tint 的行号已在**你们实际 vendored 的那个 revision** 上复核过

本节的 Dawn/tint 引用同时给两套坐标:`dawn.googlesource.com/dawn` 的 `main`,以及你们本地
`~/Developer/Aether3D-cross/aether_cpp/third_party/dawn`(`README.chromium` 记 `Revision:
a117f96e09e88e76c0a9e3b553b7316cda50633d`)。五条载重结论在**你们 pinned 的 revision 上逐条复核,全部成立**:

| 结论 | 本地 revision 上的证据 |
|---|---|
| `msl/writer/common/options.h` 无 passthrough/inline/verbatim/asm | grep **零命中** |
| MSL printer 对 `SubgroupMatrix` 发 `simdgroup_*` | `msl/writer/printer/printer.cc:1419,1424`;`make_filled_simdgroup_matrix` @ `:1019-1020, 1892-1893` |
| `ChromiumExperimentalSubgroupMatrix` = Experimental | `src/dawn/native/Features.cpp:412-414` |
| 注入 `#pragma METAL fp math_mode(relaxed)`,且注明优先于全局标志 | `src/dawn/native/metal/ShaderModuleMTL.mm:419-427` |
| SPIR-V writer 把 subgroup matrix 发成 KHR coopmat | `spirv/writer/printer/printer.cc:610-626`(`SpvCapabilityCooperativeMatrixKHR` / `OpTypeCooperativeMatrixKHR`) |

(行号在 `main` 上略有偏移,正文引用的是 `main`;差异只是位移,语义一致。)

### 3.1 ❌ tint 没有任何 inline-MSL / intrinsic passthrough 机制

`tint::msl::writer::Options` 的**全部**字段(`src/tint/lang/msl/writer/common/options.h`,
main 分支,共 290 行,已逐字节抓取并通读):

```
entry_point_name, remapped_entry_point_name, strip_all_names,
disable_robustness, disable_integer_range_analysis, disable_workgroup_init,
emit_vertex_point_size, disable_polyfill_integer_div_mod, use_argument_buffers,
workarounds{ scalarize_max_min_clamp, disable_module_constant_f16,
             polyfill_subgroup_broadcast_f16, polyfill_clamp_float,
             polyfill_unpack_2x16_snorm, polyfill_unpack_2x16_unorm,
             polyfill_tanh_f16, replace_workgroup_bool_with_u32,
             collapse_subgroup_min_max, fix_u32_div_mod,
             polyfill_bool_vec_dynamic_store },
extensions{ disable_demote_to_helper, enable_tensors },
fixed_sample_mask, pixel_local_attachments, array_length_from_constants,
vertex_pulling_config, immediate_binding_point, group_to_argument_buffer_info,
depth_range_offsets, non_constant_zero_offset, bindings, resource_table,
substitute_overrides_config
```
grep `passthrough|inline|raw|verbatim|escape|asm` 在 `options.h` + `writer.h` 里 **零命中**。
—— https://dawn.googlesource.com/dawn/+/refs/heads/main/src/tint/lang/msl/writer/common/options.h

WGSL 语言本身也没有内联汇编/内联 MSL 的语法。**⇒「只替换 MSL 的一小段」在 tint 现有 API 下不成立**,
只能自己 fork 并改 printer,那就等于自己维护一个编译器后端,与「SOP 最短」的产品约束正面冲突。

补充确认 tint 的 MSL 后端**确实**支持 subgroup matrix(即我们现在这条路是真的):
`src/tint/lang/msl/writer/printer/printer.cc` 第 1509–1516 行对 `core::type::SubgroupMatrix`
吐 `simdgroup_*`;第 1068/1075–1077/2005–2006 行处理
`msl::BuiltinFn::kMakeDiagonalSimdgroupMatrix` / `kMakeFilledSimdgroupMatrix`。
—— https://dawn.googlesource.com/dawn/+/refs/heads/main/src/tint/lang/msl/writer/printer/printer.cc

### 3.2 社区维护的 tint fork / 已知性能补丁

**查不到**任何「社区维护的 tint fork 专门修 MSL codegen 性能」。tint 已经并入 Dawn 主仓
(`dawn.googlesource.com/dawn` 的 `src/tint/`,老的 `dawn.googlesource.com/tint` 只剩历史分支),
唯一的下游是 Chromium。没有找到独立 fork。

### 3.3 关于「换工具链之前先排掉的 Dawn 旋钮」—— 你自己已经做完了,这里不重复

在写这份报告的过程中我读到了同目录下你已有的三份调研
(`~/Developer/pw_isolation_bench_20260904/research_tint_codegen.md`、`research_community.md`、
`research_agx_tgmem.md`),它们已经把这一层挖穿了,**本报告不再重复,只做交叉引用**:

- `#pragma METAL fp math_mode(relaxed)` 跨臂变量:已在 `research_community.md` §M1 定位,
  并且已经量到「手写臂 default mathMode enum = 2(Fast)、`__FINITE_MATH_ONLY__=1`,
  tint 臂被 pragma 钉在 relaxed(AIR 里少 `nnan`/`ninf`)」;`native_relaxed.metal` 对照件也已经建好。
- `disable_robustness`:已开;`raise.cc:136` 是整 pass 开关,覆盖 threadgroup。
- `disable_workgroup_init`:对应代码本来就不存在。
- 164 条 Dawn toggle 已逐条筛完,没有第三条影响 Metal 上的 threadgroup codegen。

**⇒ 本报告只在此之上补一条:那份调研里的 H1 / H2 两条,恰好是「WGSL 语言天花板」而不是「tint bug」,
而它们正是本次工具链选型能不能真正解决问题的判据。见 §5.1。**

补充一条你那份调研没覆盖、但对「WGSL 这条路的长期风险」有意义的一手事实:
`chromium_experimental_subgroup_matrix` 在 **Dawn 自己的 feature 表里被标为 Experimental**
(`src/dawn/native/Features.cpp:420–422`):
```cpp
{Feature::ChromiumExperimentalSubgroupMatrix,
 {"Support the \"enable chromium_experimental_subgroup_matrix;\" directive in WGSL.",
  "https://github.com/gpuweb/gpuweb/issues/4195", FeatureInfo::FeatureState::Experimental}},
```
—— https://dawn.googlesource.com/dawn/+/refs/heads/main/src/dawn/native/Features.cpp
即我们「一套管线三端跑」的那条腿,**今天架在一个未标准化的 Chromium 实验扩展上**
(gpuweb issue #4195 至今未定案)。相比之下 Slang 的 `linalg.CoopMat` 是一等语言特性 + 能力系统托底。

---

## 4. 别人怎么解决同一个问题

### 4.0 结论:**「一份算子定义 + 每端一份手写 kernel」是行业标准做法,没有例外;
### 而「因为 codegen 运行期性能而放弃 WGSL/中间层」的先例,一例都查不到。**

如果 PocketWorld 做这个决定,**是在写第一份公开决策记录。**

### 4.1 llama.cpp / ggml —— GPU kernel 五套完全独立,零共享

`ggml/src/` 下 20+ 个后端目录。kernel 源文件全量统计(git tree API,`master` recursive):

| 后端 | kernel 文件 | 目录大小 |
|---|---|---|
| `ggml-metal` | **20 个 `.metal`** | 1.40 MB |
| `ggml-vulkan` | **152 个 `.comp` + 27 个 `.glsl`** | 2.00 MB |
| `ggml-opencl` | **175 个 `.cl`** | 3.02 MB |
| `ggml-cuda` | **188 个 `.cu` + 89 个 `.cuh`** | 2.04 MB |
| `ggml-webgpu` | **43 个 `.wgsl` + 7 个 `.tmpl`** | 0.85 MB |

约 9 MB 源码,**GPU kernel 之间零共享**。唯一共享的 `ggml-common.h` 只被 C-like 后端 include;
Vulkan 有自己的 `types.glsl`,WebGPU 有 `common_decls.tmpl`,OpenCL 在每个 `.cl` 里重新 `#define QK4_0 32`
—— **连量化常量都各写一遍**。

GEMM 具体到文件(四份独立实现,分块策略/内存布局/绑定模型全不同):
- https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-metal/kernels/mul_mm.metal (52 KB)
- https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-vulkan/vulkan-shaders/mul_mm.comp
- https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-webgpu/wgsl-shaders/mul_mat_reg_tile.wgsl

**「一份算子定义」的实际形态**:`ggml_backend_i` 的 vtable 里**没有逐算子入口**,抽象在**图**这一层
(`ggml/src/ggml-backend-impl.h`:`graph_compute(backend, cgraph)` + `supports_op(dev, op)`)。
契约由 **`tests/test-backend-ops.cpp`** 钉死——文件头第 2 行原文:
*"For the forward pass it asserts that the results of multiple backends computing the same GGML ops are consistent."*
**这正是我们「696 对逐字节无损闸」的同构物。**
`CONTRIBUTING.md:194` 还明说后端专属代码可豁免全局规范:
*"Exceptions are allowed in isolated, backend-specific parts of the code that do not interface directly with the ggml interfaces."*

**维护成本的真实形状**(CODEOWNERS):ggml-metal = 1 人;ggml-vulkan = 2 人;ggml-webgpu = 2 人;ggml-cuda = 4 人。
**每端一份 kernel = 每端一个专职 owner。**

**设计决策记录**:issue #7773(2024-11-19),维护者 ggerganov 对 WebGPU 后端选择手写:
*"I think we can implement the kernels from scratch."* 同串讨论里「用 naga 把 GLSL/SPIR-V 反向转成 WGSL」的提议**从未被采纳**。
—— https://github.com/ggml-org/llama.cpp/issues/7773

### 4.2 🔴 ggml-metal 对我们最有价值的两条一手证据

**(a) 混合精度 half×half→float 在生产里被大规模使用 —— 独立佐证 §1.3**
`ggml/src/ggml-metal/kernels/mul_mm.metal`:
```metal
205:  simdgroup_float8x8 mc[8];
309:  simdgroup_multiply_accumulate(mc[i], mb[i/4], ma[i%4], mc[i]);
737:  typedef decltype(kernel_mul_mm<half, half4x4, simdgroup_half8x8, half, half2x4,
                                    simdgroup_half8x8, float4x4, ...>) mul_mm_t;
```
即 A/B 是 `simdgroup_half8x8`、累加器 `mc` 是 `simdgroup_float8x8`,**f16 in / f32 accum,几十个模板实例**。
⇒ **「MSL 不支持混合精度」彻底证否**(头文件 + 本机编译 + llama.cpp 生产代码,三重独立证据)。

**(b) Metal 侧已经走到 WGSL 结构性够不着的地方**
同一文件第 69–72 / 512–513 行用的是 **Metal 4 Tensor API / Metal Performance Primitives**:
```cpp
mpp::tensor_ops::matmul2d<
    mpp::tensor_ops::matmul2d_descriptor(..., mpp::tensor_ops::matmul2d_descriptor::mode::multiply_accumulate)
```
(相关 PR:#16634 初始、#17087 A19、#27461 M5+/A19+)
而 WebGPU 的 subgroup matrix 提案**至今仍是 Draft**,规范里 Metal 映射写死为 `simdgroup_matrix<T,8,8>`,
**没有通往 Metal 4 tensor API 的路径**。
—— https://github.com/gpuweb/gpuweb/blob/main/proposals/subgroup-matrix.md
⇒ **这是「留在 WGSL」的长期战略成本:Apple 下一代矩阵单元的入口,WGSL 结构上进不去。**
(顺带:SPIRV-Cross 也没有 `matmul2d` 映射,Slang 目前也没有 —— 三条路都进不去,
 只有手写 MSL 能进。这一条支持「iOS 保留一条手写 Metal 通道」的长期价值。)

### 4.3 ggml-webgpu 的成熟度与跨厂商正确性(与「三端一套」直接相关)

- 初始 PR **#14521**(2025-07-03),持续开发至今。
- 算子覆盖率(`docs/ops.md`,共 111 个算子):Vulkan 104 / Metal 90 / **WebGPU 73**。
- 跨厂商正确性问题是常态:#23558(高通 8+ Gen1 输出乱码)、#23925(Safari mul_mat 失败)、
  #25748(Intel Xe-LPG tiled mul_mat 输出损坏);
  `mul_mat_subgroup_matrix.wgsl:15-16` 源码注释:
  *"this shader path does not work with some models like qwen2.5 on Metal devices, f16 accumulation causes NaNs"*。

### 4.4 ncnn —— ❌ 不能当「一份 GLSL 通吃」的论据

ncnn **只有 Vulkan 一个 GPU 后端**,`src/layer/` 下除 `vulkan` 外全是 CPU SIMD 目录,
CMake 里不存在 `NCNN_OPENCL` / `NCNN_METAL` / `NCNN_CUDA`。作者本人的理由(FAQ 标题即
"why using vulkan over cuda/opencl/metal"):
*"cuda is only available on nvidia device, metal is only available on macos and ios, while loading
opencl library is banned in android 7.0+ and does not work on ios."*
—— https://github.com/Tencent/ncnn/blob/master/docs/how-to-use-and-FAQ/FAQ-ncnn-vulkan.md
**它从未写过第二份 GPU kernel**,所以证明不了「一份源码通吃」。iOS 走 MoltenVK
(`src/simplevk.cpp:346` 有 `load_vulkan_apple_moltenvk()` 分支,产物不含 MoltenVK 要 App 自己链)。

两条对我们有用的反面教训:
1. **即使只有一个后端,变体照样爆炸**:**300 个 `.comp` 对 64 个算子**
   (pack 排布变体 146、cooperative matrix 17、int8 46)。宏系统消掉的是精度/存储维度,
   **消不掉数据排布与算法维度**。
2. **MoltenVK 不是透明的**:8 个 shader 里有 `#if NCNN_moltenvk` 专门 workaround
   (如 `tanh.comp` 要先把 fp16 升到 fp32)。

### 4.5 MNN —— 16 个后端,GEMM 四份手写;跨端 codegen 试过并事实上放弃

`source/backend/`:`arm82 coreml cpu cuda hexagon hiai metal musa neuropilot nnapi opencl opengl qnn rknn tensorrt vulkan`。
kernel:Metal 18 个 `.metal` / OpenCL 76 个 `.cl` / Vulkan 154 个 `.comp` / OpenGL 34 个 `.glsl`。
GEMM 四份签名、布局、分块全不同(`MetalMatMul.metal` / `matmul_buf.cl` / `gemm_m8n4.comp` / `gemm16x16.glsl`)。
官方枚举自己标注:`MNN_FORWARD_METAL = 1,  /*Hand write metal*/`
—— https://github.com/alibaba/MNN/blob/master/include/MNN/MNNForwardType.h

**跨端 codegen 的尸体**:仓库根有 `codegen/` 目录,架构是「一份融合 IR + 每后端一个源码发射器」
(`class Target` 虚基类,`OpenCLTarget::proto()` 发 `__kernel void`,`MetalTarget::proto()` 发
`kernel void ... [[buffer(N)]]`)。但:**只覆盖 elementwise 融合**、**默认编译关闭**
(`option(MNN_BUILD_CODEGEN ... OFF)`)、**提交历史只有 9 次(最后 2025-07)**、
目录里躺着 `codegen/old_opencl/`,`backupcode/` 里还有两个已废弃的同功能不同后端 Winograd 生成器。
⚠️ **查不到**任何「我们尝试统一 shader 然后放弃」的明文讨论 —— 以上全部是**代码物证,不是官方声明**。

### 4.6 TFLite GPU —— 🔴 与我们的兜底方案形态最接近,而且抽象层薄到不引入安全变换税

- `common/tasks/` **168 个文件 = 唯一一份算子定义**,OpenCL 和 Metal 两个后端共用;
  `cl/kernels/`(46)和 `metal/kernels/`(35)现在**只剩测试**。
- 抽象层的实际形态:**宏替换表**,不是 AST / IR。
  `cl/cl_operation.cc` 的 `GetCommonOpenCLDefines()` 直接拼 `#define MAIN_FUNCTION __kernel void main_function`;
  `metal/compute_task.mm` 是一张字符串替换表:
  `{"MAIN_FUNCTION", "kernel void ComputeFunction"}, {"__local", "threadgroup"},
   {"LOCAL_MEM_BARRIER", "threadgroup_barrier(...)"}`。
- **没有 AST、没有 IR、不注入任何安全变换 —— 平台编译器看到的几乎就是原生源码。**
- `gl/kernels/`(79 个)是独立的旧 GLSL 路径,不共享。
- 官方数字:OpenCL 后端比 OpenGL 后端 **~2×**,归因是 API 能力(profiling / 原生 FP16 / constant memory),
  **不是 codegen 差**。⚠️ 查不到三后端同 workload 对照表,也没有架构决策文档。

⇒ **这是介于「WGSL 单源」和「全手写三份」之间的中间落点,而且已被 Google 在生产里验证过多年。**

### 4.7 TVM / MLC —— WGSL 是**平级 target**,不是翻译产物;并给出同量级的数字

TVM 的形状正是「一份算子定义 + N 个独立 codegen」,而且 **Metal 和 WGSL 是兄弟,不是翻译关系**:
```
target.build.metal  → CodeGenMetal  (→ MSL)
target.build.webgpu → CodeGenWebGPU (→ WGSL)
```
两者都从 `CodeGenC` 派生,都从同一份 TIR PrimFunc 发射。
—— https://github.com/apache/tvm/blob/main/docs/arch/codegen.rst

WebLLM 论文(arXiv:2412.15803v2)Table 1,M3 Max,**同一套 TVM kernel 定义**:

| 模型 | WebLLM(WGSL) | MLC-LLM(Metal) | 保留率 |
|---|---|---|---|
| Llama-3.1-8B | 41.1 tok/s | 57.7 tok/s | **71.2%** |
| Phi-3.5-mini | 71.1 tok/s | 89.3 tok/s | **79.6%** |

即 **20.4%–28.8% 慢**,又一次落在我们的 12.8%–25.8% 区间。
⚠️ 但 WebLLM 跑在浏览器沙箱里,含 JS/WASM 开销,**论文明确没有做归因** —— 不能当 codegen 的证据。

**架构含义**:TVM 的 `CodeGenMetal` / `CodeGenWebGPU` 是平级兄弟,和 **Slang 的
`-target metal` / `-target wgsl` 是同一种架构**。这是「一份高层定义 → N 个原生 emitter」
与「一份低层 WGSL → 翻译到 N 端」的分水岭 —— 我们现在在后者。

### 4.8 IREE —— Metal 后端从未被 CI 跑过,不能作为参考

- `runtime/src/iree/hal/drivers/metal/` 在,2026-08 仍有提交,但
  `build_tools/cmake/ctest_all.sh:31` 是 `export IREE_METAL_DISABLE="${IREE_METAL_DISABLE:-1}"`
  + `label_exclude_args+=("^driver=metal$")` —— **默认排除所有 metal 测试**;
  macOS CI 是托管 runner,build-only 无 GPU。Issue #18817(加 Apple GPU runner)开了两年仍 open。
- 佐证:2026-06-29 一个外部贡献者一天连修 6 个基础 bug(#24639–#24644)。
- **codegen 路线**:`Codegen/` 下没有 Metal 目录,Metal 复用 `Codegen/SPIRV`,最后一步用 **SPIRV-Cross** 转 MSL
  (`compiler/plugins/target/MetalSPIRV/SPIRVToMSL.cpp:13-25`)。
  IREE 自己的评价(`MetalSPIRVTarget.cpp:129-138`):
  *"If we were not using spirv-cross we'd never do it like this with one module per function...
  Currently this is **_really_ bad** because it doesn't support linking like the Vulkan SPIR-V target"*
- 投入强度(近 12 个月 commit):LLVMGPU **348** / SPIRV **80** / **WGSL 1**。
- 未修的数值正确性 bug **#23914**:Metal 默认 fast-math 导致 f32 结果错(开了 5 个月)。
- **WebGPU 删过又重建,但删除理由不是性能**:PR #23695(2026-03)正文
  *"They were built on the emscripten loop... **This is intentional, not collateral damage.**"*
  重建的 PR #24463 明确 *"this is a WebGPU driver for the Web platform, **not an Emscripten port and not a native Dawn HAL**"*。
- ⚠️ **IREE Metal 的性能数字一条都查不到。**

### 4.9 Blender / Godot / wgpu —— 三条与「翻译层」相关的旁证

- **Blender 评估过 Slang,最后自研 BSL 方言,但理由不是性能数字。**
  issue #131035,fclem:*"Slang needs to ingest the entire shader code to output the target GLSL or MSL.
  Which is an extra step in runtime shader compilation"*、*"Might conflict with backend dependent shader modification"*;
  JacquesLucke:*"allows for optimizations without being artificially restricted by an additional translation layer."*
  **他们没有测量**,理由是编译期开销 + 不可控 + 后端 workaround 冲突。
  另:Blender 从未用过 SPIRV-Cross(code search 0 命中)。
- **Godot 用 SPIRV-Cross 转 MSL,对翻译层性能只字未提**(PR #88199 只说
  *"should perform as well or better than the current MoltenVK / Vulkan implementation"*)。
- 🔴 **一个结构性区分值得单独记下**:**SPIRV-Cross 是直译器,不注入 robustness clamp / loop bounding;
  tint / naga 注入,因为它们要跑不可信代码。** 「翻译层」和「沙箱层」是两回事 ——
  我们付的税在后者,不在前者。
- **wgpu/naga 的反面教材**(机制相关但不是我们的病):#6518 MSL 无限循环 workaround 让 M1 Mac mini
  1230→312 FPS;#6528 jimblandy 的机制分析(MSL 编译器假设循环终止 ⇒ 把 naga 注入的 bounds check 优化掉);
  #7027 vertex pulling 换手写 storage buffer **+20%**。
  ⚠️ **被证否的一条**:「`while(true)` 转换」不是 naga 侧的性能因素 —— PR #9329 让 naga 生成真 `for`,
  **测不出收益,已关闭**。别把这条当论据。
- **XNNPACK 与 WebGPU 无关**(整棵树 grep `vulkan|opencl|webgpu|metal|cuda|gpu` = 0 命中,纯 CPU),
  `src/f32-gemm/` 498 个文件(152 个手写 `.S` + 291 个 intrinsics `.c` + 54 个 `.in` 模板),
  模板粒度是**每 ISA 家族一份**。README 没有「因为编译器不行才手写」的说明 ⇒ **只能当事实,不能当论据**。

### 4.10 ⚠️ 并行调研给出的三个 Dawn toggle 建议,对我们这个核**已全部证否**

并行调研发现 llama.cpp 生产代码里开了三个 toggle
(`ggml/src/ggml-webgpu/ggml-webgpu.cpp:4109-4122`,PR #16810,2025-11-05):
```cpp
const char * const deviceEnabledToggles[] = { "disable_robustness", "disable_workgroup_init",
                                              "disable_polyfills_on_integer_div_and_mod" };
```
并带出数字(LlamaWeb 论文 arXiv:2605.20706 §6.2:safety checks 在 prefill 上平均 **14% / 23%**,
NVIDIA RTX 5080 上峰值 **42%**;Dawn workgroup zero-init commit `8bd2d99ee1dd`:**12%–24%**;
gpuweb#1202 的 Dawn perf test:`MatMulFloatTwoDimSharedArray` robustness on/off **+84%**,
而 `MatMulVec4TwoDimSharedArray` 只有 **+2.1%**)。

**但我拿你们的实际产物 `/private/tmp/mmaform/cur.metal`(tint 生成)逐条核了,三条全部不成立:**

| 建议 | 在 cur.metal 上的实测 | 判定 |
|---|---|---|
| `disable_robustness` | 你们已开(`research_tint_codegen.md` §6 已记录);cur.metal 扫描段无任何钳制代码 | ❌ 已排除 |
| `disable_workgroup_init` | 对应代码本来就不存在(同上) | ❌ 已排除 |
| `disable_polyfills_on_integer_div_and_mod` | grep `tint_div\|tint_mod` = **零命中**;全文件 `%` 运算符 **0 个** | ❌ 不成立 |
| tint `PreventInfiniteLoops` 的 vec2u 倒计数器 | grep `tint_loop_idx\|4294967295` = **零命中**,该 transform 没触发 | ❌ 不成立 |
| 向量化 shared memory 访存(+84%→+2.1%) | 那是 robustness clamp 的效应,robustness 已关 | ❌ 大概率不成立 |

⇒ **沙箱税这条线,对我们这个核已经挖到底了。剩下的就是 §5 的 H1/H2 语言天花板。**

---

## 5. 🔴 决定性的一节:Slang 能不能解掉 H1 / H2 —— **H1 能,H2 需要用逃生舱**

你已有的 `research_tint_codegen.md` 把两条最可信的机制假设钉成了**WGSL 语言层天花板**,
不是 tint 的 bug。工具链选型只有一个真正的判据:**换过去之后这两条能不能表达。**

### 5.1 H1(simdgroup_barrier)—— ✅ Slang 直接给,而且三端各自映射齐全

你的观测:`cur.metal:212` 是 `threadgroup_barrier`(AIR `air.wg.barrier(2,1)`),
手写版同位置是 `simdgroup_barrier`(AIR `air.simdgroup.barrier(2,4)`);
WGSL 的 `core.def` 只有 `storageBarrier / workgroupBarrier / textureBarrier`,**没有 `subgroupBarrier`**,
所以 tint 只能降级发全局 barrier。

**Slang 核心模块里这个函数是现成的**,`source/slang/glsl.meta.slang`:

| Slang API | 行号 | Metal | GLSL/Vulkan | SPIR-V(直出) | CUDA | HLSL |
|---|---|---|---|---|---|---|
| `subgroupBarrier()` | 7347 | `simdgroup_barrier(mem_flags::mem_none)` | `subgroupBarrier()` | `OpControlBarrier Subgroup Subgroup AcquireRelease\|SubgroupMemory\|ImageMemory\|UniformMemory` | `__syncwarp()` | `AllMemoryBarrierWithGroupSync()` |
| `subgroupMemoryBarrierShared()` | 7448 | **`simdgroup_barrier(mem_flags::mem_threadgroup)`** | `subgroupMemoryBarrierShared()` | `OpMemoryBarrier Subgroup AcquireRelease\|WorkgroupMemory` | `__threadfence_block()` | `GroupMemoryBarrier()` |
| `subgroupMemoryBarrier()` | 7372 | `simdgroup_barrier(mem_flags::mem_device)` | `subgroupMemoryBarrier()` | `OpMemoryBarrier Subgroup ...` | `__threadfence_block()` | `AllMemoryBarrier()` |
| `subgroupMemoryBarrierImage()` | 7424 | `simdgroup_barrier(mem_flags::mem_texture)` | `subgroupMemoryBarrierImage()` | `OpMemoryBarrier Subgroup AcquireRelease\|ImageMemory` | `__threadfence_block()` | `DeviceMemoryBarrier()` |

全部带 `[require(cuda_glsl_hlsl_metal_spirv, subgroup_basic)]` —— **Metal 在 require 列表里**。
—— https://github.com/shader-slang/slang/blob/master/source/slang/glsl.meta.slang

**⇒ H1 在 Slang 里是一行 `subgroupMemoryBarrierShared()`,一份源码三端各发各的正确指令。
这是 WGSL 结构性做不到、Slang 结构性做得到的第一件事。**

### 5.2 H2(`thread_elements()` 寄存器内 top-2)—— ⚠️ Slang 的一等 API 同样不给,但逃生舱可以

- Slang 的 `CoopMat` 文档明写(`hlsl.meta.slang:28506–28511`):
  Metal 后端 **"No per-element access (subscript, GetLength, getCount)"**,
  且 `tests/cooperative-matrix/metal-unsupported.slang` 用 DIAGNOSTIC_TEST 把它钉死。
  ⇒ **一等 API 层面,Slang 和 WGSL 撞的是同一堵墙。**
- **但 Slang 有 WGSL 没有的逃生舱**(§1.7)。理论上可以写:
  ```slang
  float coopAccElem(linalg.CoopMat<float, MemoryScope.Subgroup, 8, 8,
                    linalg.CoopMatMatrixUse.MatrixAccumulator> m, int i)
  {
      __target_switch
      {
      case metal: __intrinsic_asm "($0).thread_elements()[$1]";
      // spirv: 走 OpCompositeExtract / coopmat 的 subscript(Vulkan 侧本来就允许逐元素)
      }
  }
  ```
  你已验证 `c.thread_elements()[0]` 在本机编译成 `extractelement <64 x float> %6, i64 0`
  (`research_tint_codegen.md` H2),所以生成出来的 MSL 一定是对的;
  **⚠️ 但「`__intrinsic_asm` 作用在 `__intrinsic_type` 的 CoopMat 值上是否被 Slang 前端接受」我没有验过
  (没有在本机跑 slangc)。这是第二个必须自己打的钉子。**
- 🟢 **信心加成:Slang 核心模块自己就在 CoopMat 值上用 `__intrinsic_asm`。**
  `hlsl.meta.slang:29036–29095`,`CoopMat.Store<layout>(...)` 的实现是:
  ```slang
  case metal:
      if (matrixLayout == CoopMatMatrixLayout.RowMajor)
          __intrinsic_asm "simdgroup_store($0, (device $[0]*)($1) + $2, (ulong)$3)", T;
      else
          __intrinsic_asm "simdgroup_store($0, (device $[0]*)($1) + $2, (ulong)$3, ulong2(0), true)", T;
  case spirv:
      spirv_asm { OpCooperativeMatrixStoreKHR $pointer $this $matrixLayout $stride Aligned !alignment; };
  case cuda:
      __intrinsic_asm "$0.Store<Slang_CUDA_WMMA::RowMajor>($1, $2, $3)";
  ```
  其中 `$0` 就是 `this`(一个 `CoopMat` 值)。⇒ **「`__intrinsic_asm` 作用在 CoopMat 上」是官方自己在用的模式**,
  只是我还没验证**用户代码**(非核心模块)里能不能这么写。
- 退一步,即使 `__intrinsic_asm` 那条不通,`__requirePrelude` 也能把**整个手写 MSL 的 top-2 尾段函数**
  注入到生成代码里,再用 `__intrinsic_asm` 调它 —— 这条几乎不可能失败,因为 `__requirePrelude`
  就是往目标代码里贴任意文本。

**⇒ H2 的结论:Slang 不是「自动更快」,而是「给了你把手写 MSL 尾段塞回一份源码里的合法通道」。
这正好回答了你的兜底问题(§6):在 Slang 下,「一份源码 + 每端一小段手写 kernel」**不再是两份源码**,
而是同一个 `.slang` 文件里的 `__target_switch` 分支。SOP 仍然是「改一个文件、三端一起升级」。**

---

## 6. 兜底方案:「一份定义 + 每端一份 kernel」算不算违背「一套管线」

### 6.1 先说判据

「一套管线三端跑」这条产品约束的**可操作定义**应该是:
**改一次算法,三端一起升级,不会漏改、不会漂移、SOP 步数不增加。**
它不等于「字面上只有一份 kernel 源码」。按这个定义:
- **一份 WGSL + 三端各一份完全独立的手写 GEMM**:❌ 违背 —— 三份源码会漂移,改一次要改三处并各自对拍
- **一份 Slang + `__target_switch` 里三个 `case`**:✅ 不违背 —— 一个文件、一次提交、一次 CI
- **一份算子定义(C++ 层)+ 每端一份 kernel,但由同一套无损闸同时对拍**:⚠️ 介于两者之间,
  是行业最常见的形态(见 §4)

### 6.1b 一个直接可引的一手先例:**Slang 自己的 MMA 标准模块就是「一份定义 + 每端一份 kernel」**

Slang 的整个卖点是「Write Shaders Once, Run Anywhere」。但它自己实现分块 MMA 时,
`source/standard-modules/neural/` 的组织方式是:

| 层 | 文件 | 大小 |
|---|---|---|
| 模块索引 / 接口 | `neural.slang`, `ilayer.slang`, `ivector.slang`, `iactivation.slang`, `istorages.slang` | 1–5KB |
| 跨端共享的布局与内存池 | `mma-linear-layout-help.slang`(57KB)、`mma-tiled-layout-helper.slang`、`shared-memory-pool.slang`、`WaveMatrix.slang`(36KB) | — |
| **每端一份 MMA kernel** | **`mma-tiled-cuda.slang`(21.8KB)** / **`mma-tiled-vulkan.slang`(17.4KB)** / **`mma-tiled-metal.slang`(29.0KB)** | — |

`neural.slang` 用 `__include "mma-tiled-cuda"; __include "mma-tiled-vulkan"; __include "mma-tiled-metal";`
把三份一起编进同一个 module。
—— https://github.com/shader-slang/slang/tree/master/source/standard-modules/neural

而且 `mma-tiled-metal.slang` 头注释(第 5–23 行)明说 **Metal 那份连权重的内存布局都不一样**:
「Despite the `Tiled*` family name, this Metal backend expects the weight matrix W to be a plain
M × K **row-major** buffer ... NOT the tile-grid layout used by `TiledMMACuda` / `TiledMMAVulkan`.」
「Callers that pack weights for mixed CUDA/Vulkan/Metal deployment should therefore keep a separate
row-major packing for the Metal path」

**⇒ 行业做法的判据在这里非常清楚:一个专门为「一份源码跨端」而生的编译器,
在 MMA 这种贴硬件的算子上,自己也写了三份 kernel。原因不是语法不通用,而是
**最优的数据布局本身由硬件决定**,一份 kernel 强行跨端只会在某一端上留下 8–16% 的成本
(它自己量出来的数字,见 §1.4)。**

所以对我们的问题:**「一份 WGSL + 每端一个薄的手写 GEMM 内核」不违背「一套管线」**,
只要三份 kernel 在**同一个仓库、同一个 module、同一次提交、同一套无损闸**里。
真正违背约束的是「三份 kernel 分散在三个平台工程里、各自有各自的 CI」。

### 6.2 我的建议顺序(纯文献结论,不含实验)

1. **先打两个钉子**(各 <1 小时,不需要改产线):
   - 钉 A:`slangc -target metal` 能不能吃 `coopMatMulAdd<float,false,half,half,float,Subgroup,8,8,8>`(§1.3c)
   - 钉 B:`__target_switch { case metal: __intrinsic_asm "($0).thread_elements()[$1]" }` 前端是否接受(§5.2)
   两个都过 ⇒ Slang 是唯一能同时满足「一份源码 + 8×8 coopmat + 混合精度 + simdgroup_barrier +
   寄存器内 top-2」的方案,H1/H2 全部可表达。
2. **钉 A 过、钉 B 不过** ⇒ 用 `__requirePrelude` 注入手写 MSL 尾段(几乎不可能失败)。
3. **钉 A 不过** ⇒ 退到「全 f16 累加」或「SPIRV-Cross 离线转译」(§2.3 已证明那条路的 MSL 是合法的)。
4. **都不想动** ⇒ 保持 WGSL,接受 H1/H2 造成的天花板,把手写 Metal 作为 iOS 的第二后端
   (你们的分发层 `OFFICIAL_AETHER_MATCH_BACKEND` 已经是这个形态了),
   代价是这一个核在 iOS 上永远有两份源码。

### 6.3 迁移成本的量级(仅就匹配器一个核)

- **不是全量迁移**:`~/Developer/aether_cpp/shaders/wgsl/` 下共 **38 个 .wgsl**,
  但本次讨论的只有匹配器 GEMM 这一个核。**Slang 和 WGSL 可以共存**
  (Slang 甚至能 `-target wgsl` 反向产出 WGSL,过渡期可以先只迁一个核)。
- **重写量**:一个 GEMM + 双向 top-2 的 kernel,数量级是**几百行 WGSL → 几百行 Slang**。
  Slang 语法是 HLSL 系,不是 WGSL 系,所以是**逐行翻译而不是复制**;绑定/资源声明要重写。
- **逐字节可复现的风险点**(按风险排序):
  1. 🔴 **浮点模式**:Slang 出的是 MSL 源码,由**我们自己**调 `newLibraryWithSource:`,
     所以 math mode 由我们定 —— 这既是风险也是机会:可以第一次让两条臂真正同模式。
     配合 `slangc -fp-mode precise` 可以关掉 Slang 侧的浮点重排。
  2. 🔴 **累加顺序**:GEMM 的 K 循环展开方式若与现在不同,f32 累加顺序变化 ⇒ 逐字节必然不同。
     这一条**没有工具能保证**,只能靠人工把循环结构写成与现有 MSL 同形,再用 696 对台架逐字节验。
  3. 🟡 **`fill` 的初值路径**、Load/Store 的 layout(RowMajor/ColumnMajor)与 stride 参数要一一对齐。
  4. 🟢 **好消息**:Slang 出的是**可读的 MSL**(README 明确说保留标识符名与调用结构),
     所以可以直接 `diff` 三份 MSL(手写 / tint / Slang),把差异逐条对出来 —— 这比调试 tint 容易得多。
- **版本锁**:`__intrinsic_asm` / `__requirePrelude` / `__target_switch` 被官方标为
  「internal compiler features ... subject to breaking changes in future releases」(§1.7),
  所以必须把 Slang 版本钉死并 vendored,升级要走对拍闸。

---

## 7. 本次明确查不到的(不用推测填空)

1. **Slang 生成的 MSL 与手写 MSL 的运行时性能对比** —— 官方没有发布任何数字。
   `tools/benchmark/` 下只有 `compile.py`(编译期),没有运行时基准。
   `mma-tiled-metal.slang` 注释里的 8–14% / 1–6% / ~5% 全是 **Slang 内部两种布局互比**,不是 Slang vs 手写。
   ⇒ **换 Slang 不能假定 codegen 更快。**
2. **Slang 前端是否接受 Metal 上的混合精度 `coopMatMulAdd`** —— 代码不拦、Metal 收货,但零测试覆盖。
   本次未下载并执行 slangc 二进制(下载可执行文件需要你本人授权),这一步留给你跑。
3. **`__intrinsic_asm` 作用在 `CoopMat`(一个 `__intrinsic_type`)值上是否被 Slang 前端接受** —— 未验证。
4. **社区维护的 tint fork / 公开的 tint MSL 运行期性能补丁** —— 零命中。
   (你的 `research_tint_codegen.md` §6 已记录同样的空结果,并注明 Chromium tracker 搜索 API 需鉴权,空结果有上限。)
5. **Khronos 官方是否声明用别的工具取代 SPIRV-Cross** —— 搜不到任何这样的声明。
   这是「没搜到」,不等于「确认不存在」。
6. **Slang 的专利 FTO** —— 本次未做检索。按红线「开源可商用 = License 干净**且**专利 FTO 干净」,
   这一项必须单独走一遍再谈落地。
7. **Metal 头文件里 `__metal_simdgroup_matrix_8x8_multiply_accumulate` 在混合精度下的实际数值行为**
   (是否内部先把 half 提升到 float 再乘、还是走硬件原生混合路径)—— 编译通过不等于我知道它的舍入语义。
   逐字节对拍必须真跑。
8. **Dawn 吃进 SPIR-V 之后是不是原样透传给 Vulkan** —— 未验证。
   Dawn native 确实支持 `ShaderSourceSPIRV` / `DawnShaderSourceSPIRV`
   (`src/dawn/native/ShaderModule.cpp:1481–1483, 1815–1825`,受 `Toggle::DisallowSpirv` 与
   `wgpu::InstanceFeatureName::ShaderSourceSPIRV` 门控),`mOriginalSpirv` 也被保留下来
   (`:1823`)。但**我没有确认它是原样递给 `vkCreateShaderModule`,还是经 `tint::spirv::reader`
   读进 IR 再由 SPIR-V writer 重发一遍**。若是后者,Slang→SPIR-V→Dawn(Vulkan) 这条路在 Android/鸿蒙
   仍然要过一次 tint,codegen 风险没有消掉。
   ⇒ 如果决定走 Slang,最干净的架构是**这一个核在三端都绕开 Dawn**
   (iOS 走原生 Metal、Android/鸿蒙走原生 Vulkan),你们的分发层已经具备这个形状。
   顺带一条已确认的事实:tint 的 SPIR-V writer 会把 WGSL 的 subgroup matrix 发成
   `SpvCapabilityCooperativeMatrixKHR` / `OpTypeCooperativeMatrixKHR` / `OpCooperativeMatrixMulAddKHR`
   (`src/tint/lang/spirv/writer/printer/printer.cc:626–647, 1697–1704`),
   也就是说**你们现在的 Android 臂本来就依赖 `VK_KHR_cooperative_matrix` 驱动支持**,
   换成 Slang 直出 SPIR-V 不会改变这一层的风险画像。
9. **没有任何项目因 codegen 运行期性能放弃 WGSL / 中间层的公开记录** —— 查了 dawn、tint、wgpu/naga、
   gpuweb、IREE、Skia、Godot、Blender、TFLite、XNNPACK。找到的全是「保留翻译层 + 提供关闭开关」。
   **若我们做这个决定,是在写第一份。**
10. **Chrome 团队没有公开发布过「tint 生成的 MSL 比手写 Metal 慢 X%」的数字** —— 只有 Buganizer 348701956
   的定性表述("The index clamping incurs runtime overhead, which may be noticeable... Currently 'unstaffed'")。
11. Dawn `ShaderRobustnessPerf` 在 **Metal 上的绝对数**读不到(chromeperf 无匿名访问);测试本身存在。
   旧 Monorail(`crbug.com/tint/*`、`crbug.com/dawn/480`)**已下线,正文全部读不到**。
12. **IREE Metal 的性能数字一条都查不到**;MNN 没有「尝试统一 shader 然后放弃」的明文讨论(只有代码物证);
   TFLite GPU 没有三后端同 workload 对照表,也没有架构决策文档。
13. **`mpp::tensor_ops::matmul2d`(Metal 4 Tensor API)有没有任何可移植前端能达到** —— 三条路
   (tint / SPIRV-Cross / Slang)全部零映射,只有手写 MSL 能进。我没有查到任何在做这件事的项目。
