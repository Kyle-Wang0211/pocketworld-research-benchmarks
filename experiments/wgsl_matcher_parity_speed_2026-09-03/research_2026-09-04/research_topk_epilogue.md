# GEMM 之后紧跟 top-k 归约:业界怎么写

调查日期 2026-09-04。目标问题:A(8192×128 u8)× B(8192×128)ᵀ 的全部内积,
每行 top-2 + 每列 top-2,比值检验 + 互检,中间结果不落显存。
现状:subgroup matrix 算出 128×32 块 → `subgroupMatrixStore` 落 threadgroup →
两个方向各扫一遍。GEMM 段已追平手写 Metal(4.133 vs 4.330),加扫描段后总体 5.649 vs 4.544(慢 1.11ms)。

**纪律说明**:本文严格区分「规范/源码原文」与「二手转述」;区分「X 用了 Y」与「Y 更快(带数字)」。
凡未找到数字的地方明确写「无数字」。

---

## 0. 结论速览

| 生态 | accumulator 能否按元素索引 | 能否知道元素的 (row, col) | 依据 |
|---|---|---|---|
| **CUDA / PTX `mma.sync`** | 能 | **能,且是规范承诺的** | PTX ISA 矩阵片段布局表(见 §2) |
| **CUDA / WMMA C++ API** | 能(`frag.x[i]`) | **不能,映射 opaque** | CUDA C++ Programming Guide(见 §2) |
| **Vulkan / SPIR-V KHR 基线** | 能,但只有**每 invocation 的扁平索引** | **不能** | `SPV_KHR_cooperative_matrix` §2.2(见 §3.1) |
| **Vulkan + `NV_cooperative_matrix2`** | 间接 | 间接(行/列归约内建 + 带 row/col 的逐元素回调) | `SPV_NV_cooperative_matrix2` §3.49(见 §3.2) |
| **Vulkan + `EXT_cooperative_matrix_maintenance1`** | 能 | **能**(`OpCooperativeMatrixGetCoordinateEXT`) | 2026-07-31 过 Khronos BoP(见 §3.3) |
| **WGSL `chromium_experimental_subgroup_matrix`** | **不能。类型不可分解** | **不能** | Dawn `core.def` 穷举 + gpuweb 提案原文(见 §4) |
| **Metal MSL(原生)** | 能(`thread_elements()`,**未文档化**) | 规范明说 unspecified;MLX 靠硬编码经验公式 | MSL Spec §2.4 / MLX 源码(见 §5) |

**对我们的直接含义**:
1. **在 WGSL 里,「落 threadgroup 内存再扫」是结构性必然。** 无逃逸路径。见 §4,证据是穷举级的。
2. **但这不解释那 1.11ms。** 原因是:你们的手写 native 对照臂 **也用 `simdgroup_store` 落内存**
   (`native_scan2.metal:168`),全目录 grep `thread_elements` 零命中;而且两边扫描段的算法
   **逐段同构**(§7.2)。所以差距既不是「WGSL 逼我们落内存」,也不是算法结构 ——
   **是同一算法下的实现/codegen 差距**,可攻。见 §7.3–7.4。
3. 原生 MSL 确实有 WGSL 没有的能力(`thread_elements()`,§5),理论上能全寄存器做双向归约,
   **但你们和对照臂都没用过它,所以这条路的收益从未被测过**(§9 第 5 条)。
   且它依赖未文档化的布局,与逐字节可复现的红线冲突(§5.5)。
4. 即使被迫落 threadgroup,**扫描段仍有可观的优化空间**,且有 production 源码先例。见 §6,
   其中 §6.7(打包进一次 shuffle)+ §6.8(无分支合并)最可直接落地。

---

## 1. 最重要的负面发现:业界龙头在这个问题上比我们更保守

### FAISS 根本不融合 GEMM 与 top-k —— 它连 shared memory 都不用,直接过全局显存

源码:`faiss/gpu/impl/Distance.cu`,函数 `runDistance()`(约 186–400 行)。

结构是:cuBLAS GEMM(`runMatrixMult`)把距离矩阵写进**全局显存**的分块缓冲
(`distanceBuf1/2`,由 `chooseTileSize` 决定分块,默认目标 512MB),
然后一个**独立的** select 核(`runL2SelectMin` / `runBlockSelect`)再把它读回来。

FAISS 自己在源码注释里承认这笔代价(`Distance.cu` 第 300–305 行,逐字):

> ```
> // For L2 distance, we use this fused kernel that performs both
> // adding ||c||^2 to -2qc and k-selection, so we only need two
> // passes (one write by the gemm, one read here) over the huge
> // region of output memory
> ```

注意它说的 "fused" 是 **norm-add 与 k-selection 的融合**,不是 GEMM 与 k-selection 的融合。
GEMM 的输出**必然**过一次全局显存往返。

**这对我们是个重要的定标**:我们现在的「落 threadgroup 再扫」在数据搬运层级上
**已经严格优于 FAISS 的生产结构**(threadgroup vs global)。所以「扫描段占 1.11ms」
不代表我们的结构落后于业界,恰恰相反。真正在寄存器里做的只有 §2 的 CUTLASS 路线,
而那条路线依赖 WGSL 没有的能力。

---

## 2. CUDA:accumulator 可按元素访问,且 (row,col) 映射是**规范承诺**的 —— 但只限 `mma.sync`

### 2.1 PTX `mma.m16n8k16` 的累加器布局是闭式公式

PTX ISA §9.7.15.5.8「Matrix Fragments for mma.m16n8k16 with floating point type」→ `Accumulators (C or D)`。
每个 lane 持有 **4 个 f32**(32 lanes × 4 = 128 = 16×8)。映射公式**逐字**:

```
groupID           = %laneid >> 2
threadID_in_group = %laneid % 4

row =         groupID   for ci where i <  2
      groupID + 8       for ci where i >= 2

col = (threadID_in_group * 2) + (i & 0x1)   for ci where i = {0,..,3}
```

代入 `groupID ∈ [0,8)`、`threadID_in_group ∈ [0,4)`、`i ∈ [0,4)`:
`(laneid, i) → (row, col)` 是 128→128 的**双射**,没有留任何自由度给实现。
**给定 lane 和 fragment 下标 i,(row,col) 唯一确定,反解也唯一。**

是不是 normative?文档没有用 "normative" 一词,但有强对照证据:
在整个 `9.7.15.5 mma` 章节里,"unspecified" 只出现 3 次,**全部是数值语义**
(`The accumulation order, rounding and handling of subnormal inputs are unspecified.`),
**一次都没有用于布局**。

### 2.2 反例就在隔壁:WMMA C++ API 的映射是 opaque 的

PTX §9.7.15.4.1「Matrix Fragments for WMMA」,逐字:

> "The distribution of fragments loaded by the threads in a warp is **unspecified and is
> target architecture dependent**, and hence the identity of the fragment within the matrix
> is also unspecified and is target architecture dependent."

CUDA C++ Programming Guide §7.24.1「Description」,逐字:

> "**The mapping of matrix elements into fragment internal storage is unspecified and subject
> to change in future architectures.**"
>
> "**Because the map of matrix elements into each thread's fragment is unspecified, individual
> matrix elements must be accessed from memory (shared or global) after calling
> store_matrix_sync.** In the special case where all threads in the warp will apply an
> **element-wise operation uniformly to all fragment elements**, direct element access can be
> implemented using the following fragment class members."

§7.24.5 Restrictions 进一步点名:

> "threads holding only a fragment (**opaque architecture-specific ABI data structure**) ...
> **with the developer not allowed to make assumptions on how the individual parameters are
> mapped to the registers**"
>
> "An example of two link-compatible architectures, **where the layout of the fragment differs,
> is sm_70 and sm_75.**"

| | PTX `mma.sync.m16n8k16` | `nvcuda::wmma::fragment` |
|---|---|---|
| (row,col) ↔ (lane,i) | 闭式公式,双射 | "unspecified and subject to change" |
| 可否做跨 lane 的行/列归约 | **可以** | **不可以**,必须先 `store_matrix_sync` 落内存 |

**⚠️ 这一栏对我们是重要的定标**:即使在 CUDA 里,只要你用的是**高层 API**(WMMA),
「落内存再扫」也同样是规范强制的。WGSL 的 `subgroup_matrix` 在抽象层级上对应的是 WMMA
那一档,不是 `mma.sync` 那一档。**我们不是被 WGSL 特殊针对了,是选了高层 API 就要付这个价。**

边界(以下是转述+推断,非文档原话):布局是**逐 shape、逐 dtype** 绑定的,
`m16n8k16` 的公式不适用于 `m16n8k8`;Hopper `wgmma` 只给了图没给闭式公式;
Blackwell `tcgen05.mma` 的累加器根本不在寄存器里而在 Tensor Memory。

### 2.3 CUTLASS:element-wise epilogue 零 smem,但归约的行/列代价不对称

**(a) 纯 element-wise epilogue 不需要 smem。**
`include/cutlass/epilogue/collective/default_epilogue.hpp` 第 93 / 143 行:
```cpp
struct SharedStorage { };                              // 空
// Note: SharedStorage is unused for DefaultEpilogue   // 原文注释
```
主循环(第 236–243 行)寄存器 → gmem,不碰 smem。
SM90 路径断言 `static_assert(is_rmem<AccEngine>::value, "Accumulator must be RF resident.");`
(`sm90_epilogue_tma_warpspecialized.hpp` 第 553 行)。

**smem 存在的理由是访存合并,不是计算。** `media/docs/cpp/efficient_gemm.md`「Epilogue」逐字:

> "**The mapping of logical elements in the output tile to each thread is chosen to maximize
> performance of the matrix multiply computation but does not result in efficient, coalesced
> loads and stores to global memory.**"
>
> "**The epilogue is a separate phase in which threads exchange data through shared memory
> then cooperatively access global memory using efficient striped access patterns.**"

⇒ **对我们不成立的理由**:我们输出的是很小的 top-2 结果,不是完整的 D 矩阵,
所以「为了合并写 D」这条动机在我们这里不存在。

**(b) 行/列归约的代价不对称是真的,根源在 warp tiling 而非算法。**

> ⚠️ **命名陷阱,必须先讲清楚**:CUTLASS 按**输出向量的形状**命名,不是按归约方向。
> `Sm90RowReduction`(源码注释 `// Row vector reduction`)产出 1×N 的 row vector ⇒ **沿 M 归约**;
> `Sm90ColReduction`(`// Col vector reduction`)产出 M×1 的 col vector ⇒ **沿 N 归约**。
> 和日常「row-wise reduction」的直觉相反。
> **我们说的「行方向 top-2」(每行取 top-2,沿 N 扫)对应的是 CUTLASS 的 `Col` 系列。**

`sm90_visitor_store_tma_warpspecialized.hpp` 里 `Sm90RowReduction`(第 1078 行)与
`Sm90ColReduction`(第 1666 行)代码形状同构(都是 warp shuffle → 可选 smem → atomic → 最终 gmem 归约),
但走不走 smem 的条件不同:
```cpp
// Sm90RowReduction: else if constexpr (decltype(size<0>(warp_layout_MN))::value <= 1)
// Sm90ColReduction: else if constexpr (decltype(size<1>(warp_layout_MN))::value <= 1)
```
SM90 epilogue 的 4 个 consumer warp **沿 M 铺**,故 `size<1>(warp_layout_MN) == 1` 恒成立。
CUTLASS 甚至敢对 N 方向下死断言(`sm90_visitor_topk_softmax.hpp` 第 712–713 行,逐字):
```cpp
// Make sure there's only one warp across N so we can use warp shuffle intrinsics for reduction.
static_assert(decltype(size<1>(warp_layout_MN))::value <= 1);
```
⇒ **沿 N 归约永远走不到 smem;沿 M 归约在默认配置下必然走 smem。**

代价表(源码推得):

| 归约方向 | warp 内 | 跨 warp | 跨 CTA |
|---|---|---|---|
| 沿 **N**(每行的 top-2 = CUTLASS `Col`) | 2 步 shuffle | **不需要** | 需要,除非 `CTA_N >= N` |
| 沿 **M**(每列的 top-2 = CUTLASS `Row`) | 3 步 shuffle | **smem + `__syncthreads`,必须** | 需要,除非 `CTA_M >= M` |

`Sm90RowReduction` 因此还额外实现了一条 "Swap Shuffle" 蝶形快路(第 1336–1362 行),
其注释解释了朴素折半树的问题(逐字):

> "After each step of reduction, a half of threads won't work in the following steps. That is,
> as the reduction progresses, **the efficiency of shuffle & reduction instructions gradually
> change from 1/2, 1/4 to 1/32 (the worst case)**."

`Sm90ColReduction` **没有**这条快路 —— 因为沿 N 的 lane 跨度只有 4,log2(4)=2 步就完了,不值得优化。

⇒ **CUTLASS 只实现了便宜的那一半;没有任何一个 epilogue 节点同时做行和列。
两个方向要么跑两遍 EVT,要么自己写。「同时做行和列的 top-2」在 CUTLASS 里没有先例。**

### 2.4 🔴 CUTLASS 有 top-k epilogue,而且**恰好只做 k=2 和 k=4**

**这是本次调查最可直接抄的一条。**
文件:`include/cutlass/epilogue/fusion/sm90_visitor_topk_softmax.hpp`
类:`cutlass::epilogue::fusion::Sm90TopKSoftmaxColReduction`(第 335 行)
许可:**BSD-3-Clause**(每个文件头 `SPDX-License-Identifier: BSD-3-Clause`)
—— 按我们的红线属于「可逐字节 port」那一类。
⚠️ **但专利 FTO 是另一条独立的闸,本次调查没查,上机前必须单独过。**

断言原文(逐字):
```cpp
static_assert(TopK == 2 || TopK == 4,
"Fused Top-K + Softmax reduction only allows K=2 and K=4, because those cases have been
performance-optimized. Other values of K can be enabled by removing this assertion, but they
may come with serious performance implications.");
```

**零 smem、零 atomic、零 workspace**:
```cpp
struct SharedStorage { };                              // 第 466 行
static size_t get_workspace_size(...) { return 0; }
```

**k 被限死在 2/4 的真正原因 —— top-k 状态必须整体塞进 shuffle 字宽**(第 404–422 行):
```cpp
if constexpr (TopK == 2) {
  static_assert(sizeof(TopKResult) == sizeof(uint64_t));
  uint64_t top_k = reinterpret_cast<uint64_t&>(*this);
  top_k = __shfl_xor_sync(0xFFFFFFFF, top_k, laneMask);   // ← 一次 shuffle 传完整个 top-2
  ...
}
else if constexpr (TopK == 4) {
  static_assert(sizeof(TopKResult) == 2 * sizeof(uint64_t));
  ... 两次 __shfl_xor_sync ...
}
```

标量插入用手写 PTX,k=2 只要 1 max + 1 setp + 2 selp(`detail::top_2_reduce_scalar`,第 69 行):
```
max.f32 mx, %3, %4;
setp.gtu.f32 p, %2, %4;
selp.f32 %1, mx, %2, p;
selp.f32 %0, %2, %4, p;
```
注释原文:

> "// ... with fast paths for lists of size 2 and 4 (Top-2 and Top-4). **Generic implementations
> may result in greater register use and branching, and should be avoided.** Fast paths for
> Top-2 and Top-4 are written in inline PTX directly."

归约默认走**蝶形**(`UseButterflyReduce = true`,第 599–616 行),所有 lane 都拿到结果,省掉广播。

**合并两个有序 top-2 表**也是手写无分支 PTX(`detail::top_2_reduce`,第 84–98 行,逐字):
```
.reg .v2 .f32 mx;
.reg .pred p;
max.f32 mx.x, %3, %4;        // max(a1, b0)
max.f32 mx.y, %2, %5;        // max(a0, b1)
setp.gtu.f32 p, %2, %4;      // a0 > b0
selp.f32 %1, mx.x, mx.y, p;  // a0 > b0 ? max(a1,b0) : max(a0,b1)
selp.f32 %0, %2, %4, p;      // a0 > b0 ? a0 : b0
```
**四条指令合并两个有序对,零分支。** 这个配方与语言无关,WGSL 里就是
2 个 `max` + 2 个 `select`,可直接照搬(我们现在用的是 if/else 分支)。

**`reduce()` 的三段式 API 形状(最该抄的架构)**:`visit()` 边算边插 top-k →
`reduce()` 做跨 lane 归约 → **原地回写 `visit_results` 寄存器**(第 4 步 "Re-visit and apply top-K and softmax")。
「GEMM 之后紧跟 top-k」能在寄存器里闭环,靠的就是这个 visit → reduce → 回写三段式。

硬约束(第 52–59 行 + `can_implement` 第 479–489 行):
```cpp
// Cross CTA reduction is not possible because there is no guarantee that all CTAs run concurrently.
return N <= tile_N && N <= epi_N && N >= TopK;
```
即归约轴必须整个落在一个 epilogue tile 内。且**全仓库只有 Col 方向,不存在
`Sm90TopKSoftmaxRowReduction`**;SM100(Blackwell)也没接线。

---
## 3. Vulkan / SPIR-V:KHR 基线不能,而业界已正式立法补上这个洞

### 3.1 KHR 基线:映射被**主动定义为未定义**

`SPV_KHR_cooperative_matrix`,§2.2 Terms(Add new terms to 2.2.2 Types),逐字:

> "Add 'Cooperative Matrix' to the definition of 'Composite'. A cooperative matrix is a
> composite with an implementation-dependent number of components (which can be queried
> with *OpCooperativeMatrixLengthKHR*). It can be used as a composite for all operations
> that act on composite types.
> **The mapping of components to invocations and indexes is implementation-dependent.**"

`OpCooperativeMatrixLengthKHR` 的定义(§3.42.1 Miscellaneous Instructions),逐字:

> "Number of components of a cooperative matrix type **accessible to the current invocation**
> when treated as a composite."

即 `length() ≠ Rows×Cols`,而是「本 invocation 持有几个」。

能否用 `OpAccessChain` / `OpCompositeExtract` 取元素?**能**,规范 Issues 正面确认:

> "*RESOLVED*: Yes, control flow uniformity requirements apply to instructions whose operands
> are cooperative matrix objects but not pointers to cooperative matrix objects.
> **Dereferencing a pointer to an element of a cooperative matrix object can be done in
> non-uniform control flow.**"

**但取到的是「本 invocation 的第 i 个」,不是 (row, col)。** 这正是缺口。

GLSL 侧 `GL_KHR_cooperative_matrix`(新增 §5.X Cooperative Matrix Components)逐字:

> "The components of a cooperative matrix are spread across the invocations in its scope,
> **in an implementation-dependent manner**. The components owned by a given invocation can be
> accessed using array subscripting syntax, and the number of components owned by each
> invocation can be queried using the *length* method."

官方示例只演示了**与坐标无关**的纯逐元素函数 `m[i] = f(m[i])`,恰好说明了能力边界。

Vulkan 主规范(`chapters/shaders.adoc`,`[[cooperative-matrices]]`)没有补充任何映射条款,
其 VUID 只约束尺寸/类型/scope/stage 组合。

### 3.2 `NV_cooperative_matrix2`(2024,单厂商):绕过映射,包装成受控内建

`SPV_NV_cooperative_matrix2` §3.49.13,`OpCooperativeMatrixReduceNV`
(Capability `CooperativeMatrixReductionsNV` = 5430,opcode 5366),逐字:

> "Computes a matrix where each element of the result matrix is computed from a row, column,
> or neighborhood of the source matrix."
>
> "The type of 'Matrix' and 'Result Type' **must each have 'Use' of *MatrixAccumulatorKHR***
> and must have matching 'Scope'."
>
> "If 'Reduce' equals *Row*, then 'Result Type' must have the same number of rows as 'Matrix'
> but can have any supported number of columns. All elements of a row in the result matrix have
> the same value, which is computed by combining all elements of the corresponding row of 'Matrix'."
>
> "'CombineFunc' must be an *OpFunction* with two parameters whose types and result type all
> match the component type of 'Matrix'. ... **This function should be mathematically commutative
> and associative**."

Reduce 模式:`Row`(0x1)/ `Column`(0x2)/ `2x2`(0x4);Row 与 Column 可组合,2x2 不可与之组合。

**这就是「在 accumulator 上做行/列归约」的官方内建。** 但对我们有三条硬限制:
- 只支持 accumulator use;GLSL 侧还要求浮点分量类型;
- `CombineFunc` 必须可交换可结合 ⇒ **能做 sum/max/min,不能做 argmax,不能做有序 top-2**;
- 只有 row / column / row+column / 2x2 四种模式。

`OpCooperativeMatrixPerElementOpNV`(Capability 5432,opcode 5369)则给了 **read-only 的坐标感知**:

> "'Func' must be an *OpFunction* ... **the row and column number of the matrix are passed as
> the first and second parameters**, and any optional operands are passed in order as the
> remaining parameters."
>
> "The calls are considered unordered against each other, and **calls may occur more than once**."

GLSL 侧还额外规定回调内**禁用 tangled 指令**(不能做 subgroup 操作、不能嵌套 coopmat 运算)。
所以它能「知道我是谁」,不能「去读别人」。

另有一条对我们有用的官方备注(`GLSL_NV_cooperative_matrix2`):

> "Note that sum-reductions can be efficiently performed on UseA and UseB matrices by
> **multiplying by a matrix filled with the value one**."

即「乘全 1 矩阵」是纯 KHR 基线下做行/列**求和**的可移植替代 —— 但对 max/top-2 无效。

### 3.3 🔴 `EXT_cooperative_matrix_maintenance1`(2026,六厂商):正面把洞堵上

`SPV_EXT_cooperative_matrix_maintenance1` / `VK_EXT_...` / `GLSL_EXT_...`。
Contributors:Jeff Bolz、Karthik Vaidyanathan(NVIDIA)、Kevin Petit、Stuart Brady(Arm)、
Hans-Kristian Arntzen、Georg Lehmann(Valve)、Vikram Tarikere(Imagination),
Vulkan 侧另加 Matthew Netsch(Qualcomm)、Mariusz Merecki(Intel)。
Status:"Approved by the SPIR-V Working Group: 2026-06-17 /
**Approved by the Khronos Board of Promoters: 2026-07-31**"。

GLSL 版 Overview 自述定位,逐字:

> "The goal is to add and accelerate features beyond just simple GEMM kernels, including
> adding support for type/use conversions, reductions, per-element operations,
> **and conversion of an element index to a matrix coordinate**."
>
> "**This extension is based on a subset of GL_NV_cooperative_matrix2, with the addition of
> coopMatGetCoordinateEXT** and support for some additional conversions."

新增指令 `OpCooperativeMatrixGetCoordinateEXT`(Capability `CooperativeMatrixGetCoordinateEXT`
= 5438,opcode 5363),§3.49.1 Miscellaneous Instructions,逐字:

> "**Converts an index in range [0, *OpCooperativeMatrixLengthKHR* - 1] to a (row,column)
> coordinate.** The element of the matrix at that index (when treated as a composite) is the
> element located at (row,column) in the matrix. If 'Index' is out of bounds, the resulting
> value is undefined."

GLSL 侧:`uvec2 coopMatGetCoordinateEXT(coopmat m, uint index);`

Vulkan 特性位:
```
VkPhysicalDeviceCooperativeMatrixMaintenance1FeaturesEXT {
    VkBool32 cooperativeMatrixProperties2;
    VkBool32 cooperativeMatrixReductions;
    VkBool32 cooperativeMatrixConversions;
    VkBool32 cooperativeMatrixPerElementOperations;
    VkBool32 cooperativeMatrixGetCoordinate;      // ← 就是这一位
}
```
EXT 版**刻意剔除**了 NV2 独有的 workgroup scope / flexible dimensions / tensor addressing /
block loads,只挑「所有厂商都能实现的最小公共集 + 那条缺失的坐标查询」。

**这条证据链的意义**:一个能力被六家厂商联合、跨 SPIR-V/Vulkan/GLSL 三层规范、
单独开一个 capability bit 补上 —— 这就是业界对「accumulator 不能按坐标访问是个结构性缺口」
的正式签字。**我们撞到的不是自己的实现问题,是一个 2026 年才刚被标准化解决的行业级缺口。**

---

## 4. 🔴 WGSL:不能。这是穷举级的证据,我们的结构是必然的

### 4.1 Dawn `core.def` 里 `subgroupMatrix*` 内建的**完整**清单

源码:`google/dawn` @ `main`,`src/tint/lang/core/core.def`。
`grep -i "subgroupMatrix"` 的全部函数级命中(第 1765–1844 行):

| 内建 | 行号 | 作用 |
|---|---|---|
| `subgroupMatrixLoad<T, Majorness>(ptr, offset, stride) -> T` | 1766 / 1771 | 从 workgroup/storage 载入 |
| `subgroupMatrixStore<Majorness>(ptr, offset, m, stride)` | 1777 / 1782 | 存回 workgroup/storage |
| `subgroupMatrixMultiply<TR>(left, right) -> result` | 1788 / 1792 / 1796 / 1800 | 矩阵乘 |
| `subgroupMatrixMultiplyAccumulate(left, right, acc) -> result` | 1805 / 1810 / 1815 / 1820 | 乘加 |
| `subgroupMatrixScalarAdd(m, s) -> m` | 1826 / 1828 / 1830 | 与**标量**逐元素加 |
| `subgroupMatrixScalarSubtract(m, s) -> m` | 1833 / 1835 / 1837 | 与**标量**逐元素减 |
| `subgroupMatrixScalarMultiply(m, s) -> m` | 1840 / 1842 / 1844 | 与**标量**逐元素乘 |
| `subgroup_matrix_{left,right,result}<T,C,R>()` 构造子 | 1934 / 1937 / 1940 | 零初始化 |

**清单到此为止。没有元素访问器,没有 `subgroupMatrixLength`,没有 `subgroupMatrixExtract`,
没有归约,没有带 (row,col) 的逐元素回调。**
唯一能把数据从 `subgroup_matrix` 值里取出来的路径是 `subgroupMatrixStore` —— 而它的目标
地址空间被类型签名钉死为 `AS: workgroup_or_storage`(第 1776/1781 行的 `implicit(...)` 约束)。

### 4.2 类型系统层面的正面禁令

gpuweb 提案 `proposals/subgroup-matrix.md`(Status: Draft,Created 2025-10-02,Issue #4195;
Dawn 的 `chromium_experimental_subgroup_matrix` 即其实现),第 200–202 行逐字:

> "These types are not considered “composite” in the WGSL taxonomy, because they
> are not decomposable.
> **You can’t reference a sub-vector or a single component.**"

第 295–297 行,在「Expressions」小节下:

> "Explicitly not supported:
>
> *   Decomposition expressions"

对比 §3.1 的 SPIR-V:SPIR-V 至少把 cooperative matrix **算作** composite(只是映射未定义),
WGSL 更严 —— **它连 composite 都不算,语言层面就不存在下标语法**。

### 4.3 提案自己把「归约」和「逐元素操作」列为未来工作

同一份提案,§Future Expansion(第 779–791 行)逐字:

> "Other possible future features:
> * Workgroup scoped matrices
> * Conversions
> * **Per-element operations**
> * Tensor addressing
> * **Reductions**"

这份清单与 §3.2 的 `NV_cooperative_matrix2` 特性表**逐项对应**
(workgroup scope / conversions / per-element ops / tensor addressing / reductions)。
说明 WGSL 工作组清楚知道这些能力存在于下层扩展里,只是**还没有把它们提上来**。

### 4.4 结论(直接回答交付项 b)

> **在当前的 WGSL / `chromium_experimental_subgroup_matrix` 下,
> 「`subgroupMatrixStore` 落 threadgroup 内存,再扫」是结构性必然,不存在替代方案。**

三重证据互相独立、互相印证:
1. **穷举**:Dawn `core.def` 里 `subgroupMatrix*` 全部 7 个内建 + 3 个构造子,无一提供元素访问;
   唯一出口 `subgroupMatrixStore` 的地址空间被签名限死为 workgroup/storage。
2. **语言规则**:提案原文 "not decomposable / You can't reference a sub-vector or a single component",
   以及 "Explicitly not supported: Decomposition expressions"。
3. **路线图**:Reductions 与 Per-element operations 被明列为 *future* features,即当下确定没有。

因此 GEMM 段追平原生 Metal(4.133 vs 4.330)而总体慢 1.11ms,
**其中「必须走一趟 threadgroup 内存」这部分不是可优化项,是 API 的地板。**
可优化的只有「扫描段本身怎么扫」(见 §6)。

---

## 5. Metal:同一块硬件上,原生 MSL 能做到 WGSL 做不到的事

### 5.1 Apple 规范:映射 unspecified,且 `thread_elements()` 根本未文档化

Metal Shading Language Specification Version 4.1(2026-06-04,383 页),§2.4
"SIMD-group Matrix Data Types",逐字:

> "Metal supports a matrix type simdgroup_matrix<T,Cols,Rows> defined in
> <metal_simdgroup_matrix>. Operations on SIMD-group matrices are executed
> cooperatively by threads in the SIMD-group. Therefore, all operations must be executed only
> under uniform control-flow within the SIMD-group or the behavior is undefined."
>
> "**The mapping of matrix elements to threads in the SIMD-group is unspecified.** For a
> description of which functions Metal supports on SIMD-group matrices, see section 6.8"

§6.8 "SIMD-Group Matrix Functions" 列出的官方函数只有:构造子、`make_filled_simdgroup_matrix`、
`simdgroup_load`、`simdgroup_store`、`simdgroup_multiply`、`simdgroup_multiply_accumulate`。

**核查结果:在这份 383 页规范的全文中,`thread_elements` 出现 0 次。**
(`pdftotext` 全文 grep,697KB 文本,零命中。)

### 5.2 但 `thread_elements()` 真实存在,且 MLX 在生产里依赖它

源码:`ml-explore/mlx` @ `main`,`mlx/backend/metal/kernels/steel/gemm/mma.h`。

第 191–197 行,直接把 accumulator 片段当寄存器向量读写:
```cpp
reinterpret_cast<thread frag_type&>(A_mat.thread_elements()) = A;
reinterpret_cast<thread frag_type&>(B_mat.thread_elements()) = B;
reinterpret_cast<thread frag_type&>(C_mat.thread_elements()) = C;
simdgroup_multiply_accumulate(D_mat, A_mat, B_mat, C_mat);
D = reinterpret_cast<thread frag_type&>(D_mat.thread_elements());
```

第 543–544 行,**在寄存器里做 epilogue,完全不过 threadgroup 内存**:
```cpp
for (short i = 0; i < decltype(Ctile)::kElemsPerTile; i++) {
  Ctile.elems()[i] = Epilogue::apply(Ctile.elems()[i]);
}
```

### 5.3 MLX 硬编码了 lane → (row, col) 的映射公式

同文件,`BaseMMAFrag<T, 8, 8>`(第 32–55 行),逐字:
```cpp
STEEL_CONST int kElemsPerFrag = (kFragRows * kFragCols) / 32;   // = 2
STEEL_CONST int kElemRows = 1;
STEEL_CONST int kElemCols = 2;

METAL_FUNC static constexpr short2 get_coord(
    ushort simd_lane_id [[thread_index_in_simdgroup]]) {
  const short qid = simd_lane_id / 4;
  const short fm  = (qid & 4) + ((simd_lane_id / 2) % 4);
  const short fn  = (qid & 2) * 2 + (simd_lane_id % 2) * 2;
  return short2{fn, fm};
}
```

即 Apple GPU 上 8×8 的 simdgroup matrix:
- 每 lane 持有 **2 个元素**(64/32);
- `kElemRows = 1, kElemCols = 2` ⇒ 每 lane 持有 **同一行的 2 个相邻列**;
- lane → (row = fm, col = fn) 由上式给出。

**这个布局对我们的问题极其友好**:
- **行方向**:一行 8 个元素分布在 4 个 lane(每 lane 2 个)⇒ 行内 top-2 只需 lane 内 2 元素合并
  + 跨 **4 个 lane** 的蝶形。
- **列方向**:一列 8 个元素分布在 8 个 lane(每 lane 1 个)⇒ 跨 **8 个 lane** 的蝶形。

两个方向都能纯寄存器 + shuffle 完成,**一趟 threadgroup 内存都不需要**。

### 5.4 Dawn 在 Metal 后端确实降到 `simdgroup_matrix`,即能力被抽象层吞掉了

`google/dawn` @ `main`,`src/tint/lang/msl/writer/printer/printer.cc` 第 1509–1517 行:
```cpp
[&](const core::type::SubgroupMatrix* sm) {
    TINT_IR_ASSERT(ir_, (sm->Type()->IsAnyOf<core::type::F32, core::type::F16>()));
    TINT_IR_ASSERT(ir_, sm->Columns() == 8);
    TINT_IR_ASSERT(ir_, sm->Rows() == 8);
    out << "simdgroup_";
    EmitType(out, sm->Type());
    out << sm->Columns() << "x" << sm->Rows();
},
```
即 WGSL 的 `subgroup_matrix_result<f32,8,8>` 就是 MSL 的 `simdgroup_float8x8` ——
**同一个类型,同一块硬件**,只是 WGSL 不给你 `thread_elements()`。

### 5.5 判决

- (a) MSL **能**按元素访问(`thread_elements()`),但**该成员在 Apple 官方规范中不存在**;
- (b) 映射规范上明说 unspecified(§2.4),MLX 用的是**逆向/经验硬编码**的 `get_coord()`;
- (c) **Dawn/WGSL 相对 MSL 少暴露了能力**,这是抽象层缺口,不是硬件缺口。

**风险提示(与我们的逐字节可复现红线直接冲突)**:走 MSL `thread_elements()` 路线 =
依赖一个未文档化的头文件成员 + 一个未文档化的元素布局。Apple 随时可以改
(§2.4 已经预先声明了 unspecified 作为免责)。且这条路**只在 Metal 臂成立**,
Vulkan 臂要等 `EXT_cooperative_matrix_maintenance1` 铺开,跨端一套 WGSL 的目标会破。

---

## 6. 即使必须落 threadgroup,这些归约技巧仍然能用(可落地改法)

以下每条都来自 production 源码,不是我推演的。

### 6.1 【立刻可用·与逐字节可复现直接相关】用「(key, index) 字典序」把归约变成全序

源码:`faiss/gpu/utils/Pair.cuh`,`struct Pair<K,V>::operator<`,逐字:
```cpp
__device__ inline bool operator<(const Pair<K, V>& rhs) const {
    return Math<K>::lt(k, rhs.k) ||
            (Math<K>::eq(k, rhs.k) && Math<V>::lt(v, rhs.v));
}
```
配合 `faiss/gpu/utils/ReductionOperators.cuh` 的
```cpp
template <typename T> struct Min {
    __device__ inline T operator()(T a, T b) const { return Math<T>::lt(a, b) ? a : b; }
};
```

**不变量**:比较是 (距离, 下标) 的**字典序**,因而是**全序**(没有两个不同元素互相"不小于")。
一个全序上的 min/max 归约**与结合顺序无关** —— 无论蝶形怎么排、lane 怎么分配、
分块怎么切,结果逐字节相同。

**这正是我们「必须逐字节可复现」需要的性质**,而且它比「靠扫描顺序保证稳定」更强:
后者要求你永远按同一顺序扫,前者对任意归约树都成立。

注意 FAISS 在 k=1 的快路径(`L2Select.cu:l2SelectMin1`)里用的是另一种写法:
```cpp
if (Math<T>::lt(distance[row], threadMin[row].k)) { ... }   // 严格 <,只比 key
```
严格 `<` + 按 col 递增扫 ⇒ 平局保留**先到者**(即最小 col)。两种写法在
「平局取最小下标」这一点上结论一致,但**只有 Pair 的字典序版本对归约树形状免疫**。
我们要改的话,取字典序版本。

### 6.2 【结构性·最重要】k=2 不该用 WarpSelect;RAFT 的 sub-warp 队列才是对的形状

**FAISS 的 WarpSelect 在 k=2 上是浪费的。** 源码 `faiss/gpu/utils/Select.cuh:439`:
```cpp
static constexpr int kNumWarpQRegisters = NumWarpQ / kWarpSize;
```
`kNumWarpQRegisters` 必须 ≥ 1 ⇒ **`NumWarpQ` 有 32 的硬地板**。
`L2Select.cu` 的分派印证了这点(第 246 行起):
```cpp
if (k <= 32 && getWarpSizeCurrentDevice() == 32) { RUN_L2_SELECT(128, 32, 2); }
else if (k <= 64)  { RUN_L2_SELECT(128, 64, 3); }
...
```
**k=2 也走 `NUM_WARP_Q = 32` 的实例化 —— 16 倍过配。**

**RAFT/cuVS 修好了这一点。** 源码
`raft/matrix/detail/select_warpsort.cuh`,`class warp_sort`(第 135–238 行):
```cpp
/** Width of the subwarp. */
static constexpr int kWarpWidth = std::min<int>(Capacity, WarpSize);
...
static constexpr int kMaxArrLen = Capacity / kWarpWidth;
```
以及 host 侧(第 1041–1042 行):
```cpp
int capacity   = bound_by_power_of_two(k);
int warp_width = std::min(capacity, WarpSize);
```
递归实例化的终止条件是 `if constexpr (Capacity > 1)`(第 816 / 852 行),
且第 1050 行确实实例化了 `WarpSortClass<1, true, T, IdxT>`。

⇒ **Capacity = 2 时,`kWarpWidth = 2`、`kMaxArrLen = 1`:一个 32 lane 的 subgroup
同时跑 16 个互相独立的 top-2 队列,每 lane 只占 1 个寄存器。**

**这对我们的列方向是天然形状**:列方向本来就是「32 个互相独立的 top-2」,
不是「一个 top-32」。按 RAFT 的方式切 sub-warp,列归约的蝶形深度从 log2(32)=5 降到 log2(2)=1。

### 6.3 【对应你提的第 4 条】「一趟读喂多个累加器」是 production 做法,FAISS 的数是 8

源码 `faiss/gpu/impl/L2Select.cu`,`l2SelectMin1`,快路径(第 86–105 行):
```cpp
for (idx_t col = threadIdx.x; col < productDistances.getSize(1); col += blockDim.x) {
    T centroidDistance = centroidDistances[col];          // 每列只读一次
    for (idx_t row = 0; row < kRowsPerBlock; ++row)
        distance[row] = productDistances[rowStart + row][col];
    for (idx_t row = 0; row < kRowsPerBlock; ++row)
        distance[row] = Math<T>::add(distance[row], centroidDistance);
    for (idx_t row = 0; row < kRowsPerBlock; ++row)
        if (Math<T>::lt(distance[row], threadMin[row].k)) {
            threadMin[row].k = distance[row]; threadMin[row].v = col;
        }
}
```
启动参数(第 205–207 行):`kThreadsPerBlock = 256`,**`kRowsPerBlock = 8`**。

即:**一个线程同时持有 8 个独立的 top-1 累加器**(`Pair<T,idx_t> threadMin[8]`,
= 8 key + 8 index 寄存器),一次循环迭代读 8 个值喂 8 个累加器。

**你担心的「每 lane 持有 8 组列 top-2,寄存器代价可能过大」——
FAISS 用 8 组 top-1(16 个寄存器)在 production 里跑,而 8 组 top-2 是 32 个寄存器。**
这是同一量级,不是数量级差异。有先例,不是空想。**但注意 FAISS 这 8 个累加器是
「同方向的 8 个独立归约」,不是「一个读同时喂两个方向」——
真正的双向单趟归约我暂未在任何 production 源码里找到先例(见 §7)。**

### 6.4 【立刻可用·省 barrier 与 smem 流量】批量块归约:N 个归约共用一次 barrier

源码 `faiss/gpu/utils/Reductions.cuh`,`blockReduceAll<Num, T, Op, ...>`(第 73–128 行):
```cpp
template <int Num, typename T, typename Op, bool BroadcastAll, bool KillWARDependency>
__device__ inline void blockReduceAll(T val[Num], Op op, T* smem) {
    for (int i = 0; i < Num; ++i) val[i] = warpReduceAll<T, Op>(val[i], op);   // 纯寄存器 shuffle
    if (laneId == 0)
        for (int i = 0; i < Num; ++i) smem[warpId * Num + i] = val[i];         // 只写 numWarps*Num
    __syncthreads();                                                           // ← 只有一次
    if (warpId == 0) { ... }
}
```

**三个可直接搬的性质**:
1. `Num` 个归约只付**一次** `__syncthreads()`,不是 `Num` 次;
2. 落 shared 的流量是 `numWarps × Num` 个元素,**不是整块** —— 跨 lane 的部分全在寄存器里用
   `shfl_xor` 做完了(`warpReduceAll`,第 20–28 行,蝶形 `for (mask = W/2; mask > 0; mask >>= 1)`);
3. smem 布局是 `smem[warpId * Num + i]` —— **Num 连续**,让 lane 0 的写是合并的。

我们现在的做法是「整块 128×32 落 threadgroup,再整块读两遍」。
FAISS 的做法是「跨 lane 的归约在寄存器里做完,只把每个 warp 的 partial 落 shared」。
**这两者的 shared 流量差一个数量级** —— 我们落 4096 个元素,它只落 `numWarps × Num` 个。

⚠️ 但要注意:我们**必须**落一次 threadgroup(§4),因为 accumulator 取不出来。
所以可用的形态是「**落一次、读一次**」:store 之后,让每个 lane 按**它自己要的方向**
把元素捞进寄存器,之后所有跨 lane 归约走 subgroup 蝶形、不再回 threadgroup。
这能把「整块读两遍」降到「整块读一遍」,是 §7 的核心候选。

### 6.5 【可用·省掉大部分归约工作】广播式早拒阈值

源码 `faiss/gpu/utils/Select.cuh`,`WarpSelect::addThreadQ` / `checkThreadQ`(第 469–511 行):
```cpp
__device__ inline void addThreadQ(K k, V v) {
    if (Dir ? Comp::gt(k, warpKTop) : Comp::lt(k, warpKTop)) {   // ← 早拒
        ...插入 per-thread 队列...
    }
}
__device__ inline void checkThreadQ() {
    bool needSort = (numVals == NumThreadQ);
    needSort = __any_sync(0xffffffff, needSort);                 // ← 全 warp 才决定
    if (!needSort) return;                                       // ← 绝大多数迭代在此返回
    mergeWarpQ();
    ...
    warpKTop = shfl(warpK[kNumWarpQRegisters - 1], kLane);        // ← 广播第 k 好的值
}
```
`kLane = (k - 1) % kWarpSize`(构造函数第 447 行)。

**不变量**:`warpKTop` 恒为「当前第 k 好的值」,由持有它的那个 lane 广播给全 warp。
任何打不过它的候选**连队列都不用碰**。昂贵的 bitonic 合并只在
`__any_sync` 报告「有 lane 的暂存队列满了」时才触发。

对 k=2 而言,这退化成极简形式:**每个 lane 维护 (best, second),
新候选先和 `second` 比一下,打不过就整条丢掉**。
这是纯寄存器的两次比较,没有任何 shuffle。

### 6.6 不能用的:FAISS/RAFT 的 bitonic 网络本身

`Select.cuh:mergeWarpQ` 依赖 `warpSortAnyRegisters` / `warpMergeAnyRegisters`
(`MergeNetworkWarp.cuh`),那是为 k ≥ 32 的**长队列**设计的。
k=2 时整个 bitonic 机器都是负担 —— §6.2 已经说明 RAFT 在 Capacity ≤ 32 时
本来就把它退化成 sub-warp 上的 1 元素排序(`util::bitonic<1>(...)`,
`raft_select_warpsort.cuh` 第 467 / 579 行)。**k=2 就该用朴素寄存器比较,不该用排序网络。**

### 6.7 🔴【最可直接抄的一条】把整个 top-2 状态打包进一次 shuffle

**CUTLASS 的判决**:top-k 融合之所以只做 k=2 和 k=4,就是因为
**top-k 状态必须整体塞进 shuffle 的字宽**(§2.4)。k=2 → `Array<float,2>` = 8 字节
→ **一次 `__shfl_xor_sync(uint64)` 完成一次跨 lane top-2 合并**。

**我们现在每级蝶形做了 3 次 shuffle。** `cur_scan2.metal` 第 241–243 行(手写 native 第 196–198 行同形):
```cpp
float const v_60 = simd_shuffle_xor(v_53, 1u);   // best
float const v_61 = simd_shuffle_xor(v_54, 1u);   // second
int   const v_62 = simd_shuffle_xor(v_55, 1u);   // best index
```
即每级 96 bit 的 shuffle 流量。行方向 2 级 = 6 次;跨 SG 合并 4 级(第 393–425 行)= 12 次。

**可以打包成 1 次。** 算术依据(请自行复核这两个上界):
- 描述子是 u8、128 维 ⇒ 内积上界 `255 × 255 × 128 = 8,323,200 < 2^24`
  ⇒ **f32 累加器里存的是精确整数**(f32 对 ≤ 2^24 的整数无误差),打包无损;
- 下标上界 8192 = 2^13。

⇒ `best(24) + best_idx(13) + second(24) = 61 bit ≤ 64 bit`,
**整个 top-2 状态塞进一个 `vec2<u32>`**。

WGSL 支持向量版 shuffle —— `core.def` 第 1669–1670 行:
```
@must_use @stage("fragment", "compute") implicit(N: num, T: fiu32_f16)
  fn subgroupShuffleXor(value: vec<N, T>, mask: u32) -> vec<N, T>
```
所以 `subgroupShuffleXor(packed: vec2<u32>, mask)` 是合法的一次调用。

**预期收益**:蝶形段的 shuffle 调用数 3→1(6+12=18 次 → 6 次)。
即使 Metal 后端把 `vec2<u32>` 降成 2 条 `simd_shuffle_xor`,仍是 18 → 12。

**附带好处**:打包成单个无符号整数后,
「`best` 降序 + 平局取最小下标」可以直接变成**对打包值的单次整数比较** ——
把下标存成 `(8191 - idx)` 即可让「分数高者优先、同分下标小者优先」
恰好等于「打包整数大者优先」。这就是 §6.1 的字典序全序,
用**零额外指令**实现,且天然对归约树形状免疫。

⚠️ 前提是累加器里确实是精确整数。如果 GEMM 走的是 f16 输入 / f32 累加
(你们现在的配置),u8 → f16 是精确的(f16 对 ≤ 2048 的整数精确),
乘积 ≤ 65025、和 ≤ 8,323,200 均在 f32 精确整数范围内,**成立**。
但这条必须先用一个断言/对拍验证,不能假定。

**顺带一提**:`core.def` 第 1796 / 1815 行显示 WGSL 规范上支持
`subgroupMatrixMultiply<TR: iu32_iu8>` 即 **u8 × u8 → u32** 的整数 subgroup matrix。
但 Dawn 的 Metal 后端把类型断言死在 f32/f16
(`printer.cc` 第 1510 行 `TINT_IR_ASSERT(ir_, (sm->Type()->IsAnyOf<core::type::F32, core::type::F16>()))`),
所以 **Metal 臂上 u8 路径不可用**,这解释了为什么现在必须走 f16。
**Vulkan 臂上这条路可能是通的** —— 若成立,整数累加器天然无浮点误差,
上面的打包就不需要「精确整数」的前提论证了。这值得单独一验。

### 6.8 【立刻可用】无分支的 top-2 合并:2 个 max + 2 个 select

我们现在每级蝶形的合并是带分支的(`cur_scan2.metal:244-249`,native 同形):
```cpp
if ((v_60 > v_53)) { v_54 = max(v_61, v_53); v_53 = v_60; v_55 = v_62; }
else               { v_54 = max(v_54, v_60); }
```

CUTLASS 的 `detail::top_2_reduce`(§2.4)用 **4 条无分支 PTX** 做同一件事:
```
max.f32 mx.x, a1, b0;
max.f32 mx.y, a0, b1;
setp.gtu.f32 p, a0, b0;
selp.f32 out1, mx.x, mx.y, p;
selp.f32 out0, a0, b0, p;
```
译成 WGSL 就是:
```wgsl
let p  = a0 > b0;
let o0 = select(b0, a0, p);
let o1 = select(max(a0, b1), max(a1, b0), p);
```
即 **2 个 `max` + 1 个比较 + 2 个 `select`,零分支**。
(索引同理:`select(bi, ai, p)`。)

在 subgroup 蝶形里,所有 lane 走同一条路径本来就没有 divergence,
所以收益不是消除 divergence,而是**减少指令数和寄存器压力**,
并让编译器更容易把连续几级蝶形软件流水化。
CUTLASS 的注释明说了为什么要手写这段(逐字):

> "**Generic implementations may result in greater register use and branching, and should be
> avoided.** Fast paths for Top-2 and Top-4 are written in inline PTX directly."

⚠️ 注意 `setp.gtu.f32` 的 `.gtu` 是 **unordered greater-than**(NaN 参与时返回 true)。
我们的分数是精确整数、不会有 NaN,所以用普通 `>` 即可 —— 但如果将来引入了
可能产生 NaN 的路径,这个语义差异会改变平局/异常值的走向,**逐字节复现的对拍要覆盖到**。

---

## 7. 单趟双向归约:文献上没有先例,但你们的算法结构其实已经是对的

### 7.1 关于「一遍读同时喂两个方向」

**我没有在任何 production 源码或论文里找到「一次读同时喂行方向和列方向归约」的先例。**
明确说明这是**未找到**,不是「不存在」。

找到的最接近的是 §6.3 的 FAISS `l2SelectMin1`:一次读喂 **8 个同方向的独立累加器**。
它证明了「多累加器」这个手法在 production 里是站得住的(8 组 Pair = 16 寄存器),
但它没有跨方向。

### 7.2 🔴 但我读了你们的两份 scan 源码,发现**结构不是问题所在**

我逐段对比了 `/private/tmp/mmaform/cur_scan2.metal`(Tint 生成)与
`/private/tmp/mmaform/native_scan2.metal`(手写)的扫描段。**两者的算法完全相同**:

| | 行方向 | 列方向 |
|---|---|---|
| **手写 native**(第 178–235 行) | lane 读同一行的 8 个连续列(`accRow[cLoc]`,第 191 行,`per = kBN/4 = 8`),寄存器 top-2,然后 **2 级蝶形**(第 196–198 行,`off = 1, 2`)归到 `lcg == 0` | `cc = lane`,每 lane 独占一列,读本 SG 的 8 行(`accCol[r * kBN]`,第 228 行),**0 次 shuffle**,直接写 `cpBest/cpSecond/cpIdx` |
| **我们 WGSL**(第 214–386 行,含 guide/非 guide 两份副本) | 同上:8 次读 + `simd_shuffle_xor(·, 1)` 与 `(·, 2)` 两级 | 同上:`(*tint_member_17)[v_69 + v_70*32]`(第 368 行)读 8 行,**0 次 shuffle**,写 `tint_member_18/19/20` |

**两边都是「每 lane 8 个元素 + 小蝶形」,块都恰好被读两遍,shuffle 级数都一样。
算法层面没有差距。**

而 §4 已经证明「必须落 threadgroup」这一步是 WGSL 的地板 ——
可手写的 native 也**照样**用 `simdgroup_store`(`native_scan2.metal` 第 168 行),
**没有用 `thread_elements()`**(全目录 grep,零命中)。

⇒ **所以扫描段的差距既不是「WGSL 逼我们落内存」造成的(手写也落),
也不是算法结构造成的(两边同构)。它是同一算法的实现/codegen 差距。**

### 7.3 两处具体的、可检验的 codegen 差异(按可疑度排序)

这两条是我从源码里读出来的**事实差异**;它们是否就是那 1.11ms 的成因,
**需要上机验证,我没有跑(按要求不占 GPU)**。

**(1) 循环形态:常量 trip count 被 Tint 藏进了 `while(true)`**

手写(`native_scan2.metal:183`):
```cpp
for (uint t = 0; t < per; ++t) { ... }        // per = kBN/4u,编译期常量
```
Tint 生成(`cur_scan2.metal:218-238`,列方向同形见 274-283):
```cpp
uint v_57 = 0u;
while(true) {
  if ((v_57 < 8u)) { } else { break; }
  ...
  { v_57 = (v_57 + 1u); }
}
```
两者语义等价、trip count 都是 8,但 `while(true) + if/else break` 是 Tint 的规范化降级形式。
**Metal 前端是否对这两种形式做同样的完全展开,值得一验** —— 如果不展开,
8 次迭代的循环开销 + 无法把 8 次 threadgroup 读软件流水化,足以解释一个数量级。

**(2) 基址提升:手写把 threadgroup 指针提到循环外,Tint 每次迭代重算下标**

手写(`native_scan2.metal:178-179`定义,`191`使用):
```cpp
threadgroup const float* accRow = accSG + sgid * (8u * kBN) + lrow * kBN;  // 循环外
...
const float d = accRow[cLoc];                                              // 循环内
```
以及列方向(第 219 行定义,第 228 行使用):
```cpp
threadgroup const float* accCol = accSG + sgid * (8u * kBN) + cc;
const float d = accCol[r * kBN];
```
Tint 生成(`cur_scan2.metal:217 / 226`,列方向 `273 / 281` 与 `360 / 368`):
```cpp
uint const v_56 = (((v_17 * 8u) + v_22) * 32u);                     // 循环外(好)
float const v_59 = (*v_19.tint_member_17)[(v_56 + v_58)];           // 但每次要过
                                                                    // 结构体指针成员再下标
```
差别在于 **`(*v_19.tint_member_17)[...]` 是「解引用一个装着 threadgroup 指针的结构体,
再取成员,再下标」**,而手写是一个已经算好的裸 `threadgroup const float*`。
Tint 把所有 threadgroup 变量打包进 `tint_struct_4` 再传指针(`cur_scan2.metal:44-48`),
这层间接是 WGSL→MSL 降级的产物。**编译器能不能把它完全穿透,同样值得一验。**

### 7.4 建议的下一刀(单变量,不需要改算法)

按你们「一次一个变量」的纪律,我建议的顺序是:

1. **先量出扫描段的真实成本**:你们已经有 `cur_noscan.metal` 这个臂了。
   把 `cur_scan2` 与 `cur_noscan` 的差、`native_scan2`(或对应 native 臂)与其 noscan 的差
   分别量出来,确认「扫描段 WGSL vs native」的比值。
   ⚠️ 我从你给的四个数推出的差是 1.516ms vs 0.214ms(≈7×),
   但我不确定这四个数分别对应哪个 bench 臂,**这个 7× 请你自己核对后再当依据**。
2. **若确认扫描段有大比值差**:优先验 §7.3(1) —— 在 WGSL 里把 8 次循环**手工完全展开**
   (写成 8 条直白语句,不用 `for`),重新过 Tint,看 `while(true)` 是否消失、时间是否回落。
   这是纯 WGSL 源码改动,不碰算法,不影响逐字节结果。
3. **若展开无效**:验 §7.3(2) —— 把 threadgroup 数组的读改成先取一次局部
   `let base = ...` 再连续下标,减少结构体成员穿透次数。
4. **§6 的三条**(字典序全序、sub-warp top-2、批量块归约)属于**结构性改进**,
   在 1/2/3 之后再上,因为它们会改动归约树的形状 —— 而 §6.1 的字典序恰好是
   「让归约树形状不影响结果」的保险,建议**先上 §6.1,再动树形状**。

### 7.5 关于「每 lane 持有 8 组列 top-2」这个设想

按 §7.2 的实测结构,**你们现在的列方向本来就是每 lane 独占一列、0 次 shuffle** ——
已经是最省的形态了,不需要「一个 lane 持有 8 组列 top-2」。
那个设想适用于「lane 读到的 8 个元素属于 8 个不同列」的布局,
但你们的列方向用的是另一种索引(`cc = lane`,跨行读,stride 32),
**已经绕开了这个问题**。所以第 4 条的寄存器代价担忧在当前布局下不成立。

真正的读量代价是:块被读两遍(行方向连续读 8 个、列方向 stride-32 读 8 个)。
要降到一遍,唯一的办法是让**同一次读**的值同时进两个方向的累加器,
而那要求行方向和列方向用**同一种索引**,与「行方向要连续读、列方向要跨行读」冲突。
**文献里没有先例,而且在你们已经把两个方向各自都优化到 0–2 级蝶形的前提下,
省下的那一遍读大概率不是瓶颈**(瓶颈更可能是 §7.3 的 codegen)。

---

## 8. 交付项直答

### (a) 「accumulator 能否按元素访问」——三个生态的确切答案

| 生态 | 能否取到元素 | 能否知道它是哪个 (row,col) | 规范引用 |
|---|---|---|---|
| **CUDA `mma.sync`**(PTX 级) | **能** | **能,闭式公式,双射** | PTX ISA §9.7.15.5.8 `Accumulators (C or D)`:`groupID = %laneid >> 2` / `row = groupID (i<2), groupID+8 (i>=2)` / `col = (threadID_in_group*2) + (i & 0x1)` |
| **CUDA `nvcuda::wmma`**(C++ API) | 能(`frag.x[i]`) | **不能** | CUDA C++ Prog. Guide §7.24.1:"The mapping of matrix elements into fragment internal storage is **unspecified and subject to change in future architectures**";"individual matrix elements must be accessed from memory ... after calling `store_matrix_sync`" |
| **Vulkan / SPIR-V KHR 基线** | 能,但只是**本 invocation 的扁平索引** | **不能** | `SPV_KHR_cooperative_matrix` §2.2:"**The mapping of components to invocations and indexes is implementation-dependent.**";`OpCooperativeMatrixLengthKHR` = "Number of components ... **accessible to the current invocation**" |
| **Vulkan + `NV_cooperative_matrix2`** | 间接 | 间接 | `OpCooperativeMatrixReduceNV`(行/列/2x2 归约,CombineFunc 须可交换可结合);`OpCooperativeMatrixPerElementOpNV`(回调前两参数 = row, col,只读) |
| **Vulkan + `EXT_cooperative_matrix_maintenance1`** | **能** | **能** | `OpCooperativeMatrixGetCoordinateEXT`:"**Converts an index in range [0, OpCooperativeMatrixLengthKHR - 1] to a (row,column) coordinate.**" —— 2026-06-17 过 SPIR-V WG,**2026-07-31 过 Khronos Board of Promoters** |
| **WGSL `chromium_experimental_subgroup_matrix`** | **不能** | **不能** | gpuweb `proposals/subgroup-matrix.md`:"these types ... **are not decomposable. You can't reference a sub-vector or a single component.**";"Explicitly not supported: Decomposition expressions" |
| **Metal MSL** | 能(`thread_elements()`) | **规范说 unspecified** | MSL Spec 4.1 §2.4:"**The mapping of matrix elements to threads in the SIMD-group is unspecified.**" 且 `thread_elements` 在 383 页规范全文中**出现 0 次** |

### (b) WGSL 不能 ⇒ 我们的结构是必然的。**明确说:是的。**

> **在当前 WGSL 下,「`subgroupMatrixStore` 落 threadgroup 内存,再扫」是结构性必然,
> 没有替代方案。**

三条互相独立的证据(详见 §4):
1. **穷举**:Dawn `core.def` 中 `subgroupMatrix*` 的全部内建只有
   Load / Store / Multiply / MultiplyAccumulate / ScalarAdd / ScalarSubtract / ScalarMultiply
   加三个零初始化构造子。**无元素访问器、无 Length、无归约。**
   唯一出口 `subgroupMatrixStore` 的目标地址空间被签名限死为 `workgroup_or_storage`。
2. **语言规则**:提案原文两处正面禁令(not decomposable / Explicitly not supported: Decomposition expressions)。
3. **路线图**:`Reductions` 与 `Per-element operations` 被明列为 **future** features
   —— 与 Vulkan 侧 NV2/EXT 的特性表逐项对应,说明工作组知道缺,只是还没提上来。

**两条重要的补充判断(不要据此过度悲观):**

- **这不是 WGSL 特有的惩罚。** CUDA 里只要你用高层 API(`nvcuda::wmma`),
  规范同样强制「先 `store_matrix_sync` 落内存再访问元素」(§2.2)。
  WGSL 的 `subgroup_matrix` 抽象层级对应的就是 WMMA 那一档,不是 `mma.sync` 那一档。
- **而且落内存不等于慢。** 你们手写的 native 对照臂(`native_scan2.metal` 第 168 行)
  **也用 `simdgroup_store`**,全目录 grep `thread_elements` 零命中。
  两边扫描段算法同构(§7.2)。**所以 1.11ms 不是「被迫落内存」造成的**,
  它是同一算法下的实现/codegen 差距,是可攻的(§7.3–7.4)。

### (c) 即使必须落 threadgroup,仍然可用的归约技巧

按「收益/风险」排序:

| # | 技巧 | 源码 | 可落地改法 | 风险 |
|---|---|---|---|---|
| **1** | **top-2 状态打包进一次 shuffle**(§6.7) | CUTLASS `sm90_visitor_topk_softmax.hpp:404-422`,`static_assert(sizeof(TopKResult) == sizeof(uint64_t))` + `__shfl_xor_sync(uint64)` | 把 (best, best_idx, second) 打包成 `vec2<u32>`,用 `subgroupShuffleXor(vec2<u32>, mask)`(`core.def:1669`)。蝶形 shuffle 调用 18 次 → 6 次 | 低。需先验证累加器是精确整数(u8×128 维 ⇒ 上界 2^23 < 2^24,f32 精确) |
| **2** | **打包顺便换来字典序全序**(§6.1 + §6.7) | FAISS `Pair.cuh::operator<`(key 相等时比 index) | 下标存 `8191 - idx`,则「打包整数大者优先」≡「分数高、同分下标小」。**零额外指令** | 低。**这条是逐字节可复现的保险**:全序上的归约与树形无关,后续任何改动都不会改结果 |
| **3** | **k=2 用朴素寄存器比较,不要用排序网络**(§6.2 / §6.6) | RAFT `select_warpsort.cuh:147` `kWarpWidth = min(Capacity, WarpSize)`;FAISS `Select.cuh:439` 有 32 的硬地板 | 你们现在已经是朴素比较,**这条是「不要往 WarpSelect 方向改」的负面建议** | — |
| **4** | **批量块归约:N 个归约共用一次 barrier**(§6.4) | FAISS `Reductions.cuh:73-128` `blockReduceAll<Num,...>`,smem 布局 `smem[warpId*Num + i]` | 跨 SG 合并阶段(`cur_scan2.metal:387` 的 barrier + 512×3 数组)可以把 best/second/idx 三个数组合并成一个打包数组,barrier 不变但 smem 流量 ÷3 | 低,与 #1 同一改动 |
| **5** | **无分支 top-2 合并**(§6.8) | CUTLASS `detail::top_2_reduce`(`sm90_visitor_topk_softmax.hpp:84-98`) | 蝶形合并的 if/else 换成 `select` + `max`:2 max + 2 select,零分支 | 低,与 #1 同一处代码 |
| **6** | **广播式早拒阈值**(§6.5) | FAISS `Select.cuh:469-511`,`warpKTop` + `__any_sync` 门控 | k=2 退化成「新候选先和 second 比,打不过整条丢掉」——纯寄存器两次比较 | 低,但你们的扫描是定长 8 次,早拒省不了读,收益有限 |
| **7** | **多累加器摊销**(§6.3) | FAISS `L2Select.cu:86-105`,`kRowsPerBlock = 8`,8 组 Pair 累加器 | 你们的列方向已是每 lane 独占一列、0 shuffle,**已经最优,不需要改**(§7.5) | — |

**明确的负面结论(省得你们再去试)**:
- 「一遍读同时喂行和列两个方向」**在任何 production 源码或论文里都没有找到先例**(§7.1)。
  CUTLASS 只实现了便宜的那半边(Col 方向),连 Row 方向的 top-k 都没有(§2.4)。
- 你们担心的「每 lane 持有 8 组列 top-2 寄存器代价过大」——**在你们当前布局下这个问题不存在**,
  列方向已经是每 lane 一列、0 次 shuffle(§7.5)。
- FAISS 的 `WarpSelect` / bitonic 合并网络对 k=2 是纯负担,不要抄(§6.6)。

### 最后一句

调查的结论不是「我们做错了」,而是:
**结构上我们已经跟手写 native 同构,并且严格优于 FAISS 的生产结构(threadgroup vs global);
剩下的 1.11ms 是 codegen/实现层的差距,不是算法层的。**
优先级建议:先做 §6.7 + §6.1 的打包(收益明确、风险低、顺带把逐字节可复现钉死),
再按 §7.4 的顺序验 codegen 假设。

---

## 9. 数字缺口:本次调查**没有**找到的东西(诚实记账)

按「只有带数字的对比才算证据」的纪律,以下是本次**未能**取得数字的项,
不要把它们当成已证结论:

1. **「把 GEMM 结果留在寄存器做 top-k」vs「落共享内存再扫」的加速比 —— 无数字。**
   我没有找到任何论文、博客或 issue 明确报告过这个比值。
   找到的只有**结构性证据**:CUTLASS 的 `Sm90TopKSoftmaxColReduction` 做到了零 smem、
   零 atomic、零 workspace(§2.4),而 FAISS 连 shared memory 都不用、直接过全局显存(§1)。
   **两者都没有给出与对照方案的时间拆分。**

2. **归约段占总时间的比例 —— 无公开数字。**
   RAFT/cuVS 的设计文档与 NVIDIA 博客里我没有找到「GEMM 段 vs top-k 段」的拆分。
   **唯一的数字是你们自己的**(4.133 / 4.330 / 5.649 / 4.544),而且我对这四个数
   分别属于哪个 bench 臂并不确定(§7.4 第 1 条)。

3. **CUTLASS 那句 `TopK == 2 || TopK == 4` 背后的「serious performance implications」
   具体是多少 —— 无数字。** 断言只给了定性说法,没给测量。

4. **`NV_cooperative_matrix2` / `EXT_cooperative_matrix_maintenance1` 的
   `coopMatReduce*` 相对手写 store+scan 快多少 —— 无数字。**
   扩展规范不含性能数据。

5. **Apple GPU 上 `thread_elements()` 路线 vs `simdgroup_store` 路线的实测差 —— 无数字。**
   而且 §7.2 已经发现你们的手写 native 对照臂**根本没走** `thread_elements()` 路线,
   所以这条路的收益在你们的场景里**从来没有被测过**。

6. **仍在进行中**:FAISS 论文(arXiv:1702.08734)WarpSelect 一节的对比表、
   RAFT/cuVS fused kernel 的 k=1 / k>1 分界线源码证据、
   FlashAttention 的 `convert_layout_acc_rowcol` 与行/列不对称、
   COLMAP / OpenCV 的互检是一趟还是两趟 —— 这部分调查尚未回传,本文未收录。
   **§7.1「双向归约无先例」的结论因此是基于我已查到的范围,不是穷尽性结论。**

**结论的强度分级**:
- **穷举级(可当决策依据)**:§4 的 WGSL 判决 —— 内建清单是穷举的,提案有正面禁令。
- **规范级(可当决策依据)**:§2、§3、§5.1 的各生态规范引用 —— 全部逐字打到条目号。
- **源码级(可直接抄)**:§6 的各条 —— 全部来自 production 源码,附文件名与行号。
- **推断级(需上机验证)**:§7.3 的两条 codegen 假设、§6.7 的打包收益估算。

