# tint→MSL 扫描段 +1.11ms 机制调研

调研日期 2026-09-04。所有引用均打到一手来源:本机 Dawn 工作副本
`/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/dawn`
(`README.chromium` 记录 `Revision: a117f96e09e88e76c0a9e3b553b7316cda50633d`)、
Apple Metal 工具链自带头文件、`xcrun metal` 实际编译产物(AIR)、
gpuweb/gpuweb 仓库与 Chromium issue tracker。

被测产物:`/private/tmp/mmaform/cur.metal`(tint 生成)与
`/private/tmp/mmaform/native2.metal`(手写)。本次调研把两者都用
`xcrun metal -std=metal3.2 -S -emit-llvm` 编到 AIR 做逐条对照
(`xcrun metal --version` = Apple metal 32023.864,target `air64-apple-darwin25.1.0`)。

---

## 0. 结论速览

**最有希望的机制假设(按可信度排序)**

| # | 假设 | 一手证据 | 1 小时证伪 |
|---|------|---------|-----------|
| H1 | **同步域被迫从 simdgroup 升级成 threadgroup**,把扫描段的「数据相关抖动」从 `max(SG 的 MMA+扫描)` 变成 `max(MMA) + max(扫描)` | cur.metal:212 是 `threadgroup_barrier`,native2.metal:171 同一位置是 `simdgroup_barrier`;AIR 里分别是 `air.wg.barrier(2,1)` 与 `air.simdgroup.barrier(2,4)`。WGSL 无 `subgroupBarrier`,tint 只能降级发全局 barrier(core.def 只有 storageBarrier/workgroupBarrier/textureBarrier) | 已生成 `/tmp/v1_sgbarrier.metal`(唯一改动=第 212 行改 `simdgroup_barrier`),编译通过且 AIR 里出现 `air.simdgroup.barrier`。直接喂 bench 跑 |
| H2 | **`accSh` 这一层 threadgroup 数组本可以完全不存在**:手写 MSL 可以用 `simdgroup_matrix::thread_elements()` 在寄存器里直接读累加器元素,WGSL 明文禁止 subgroup matrix 的分解表达式 | Apple 头文件 `metal_simdgroup_matrix` 第 63/67 行有 `thread_elements()`;本机实测 `c.thread_elements()[0]` 编译出 `extractelement <64 x float> %6, i64 0`。Dawn 设计文档 `docs/dawn/features/subgroup_matrix.md` 明确写 subgroup matrix 「不是 composite、不可分解、不能引用单个分量」,且「Explicitly not supported: Decomposition expressions」 | 写一个只做 MMA+`thread_elements()` top-2 的原生小核,和现在的 MMA+accSh+扫描比。这不是修 tint,是量「WGSL 天花板」 |
| H3 | 5 个 threadgroup 数组在 tint 里是**同一个 struct 的 5 个成员指针**、且被拆进一个**未内联的辅助函数**,`air-buffer-no-alias` 只挂在 entry point 上、没有传进辅助函数 | cur.ll:75 辅助函数形参只有 `nocapture`,cur.ll:586 kernel 形参才有 `"air-buffer-no-alias"`,cur.ll:592 是真实 `call`(未内联) | 已验证 `__restrict` 在 MSL 可用且**对局部指针也生效**(`/tmp/lr.ll` 出现 `!alias.scope`/`!noalias`)。在 cur.metal 的辅助函数里加 5 个 `threadgroup T* __restrict` 局部指针替换所有 `(*v_19.tint_member_N)[...]`,单变量测 |

**明确判死的方向**:`tint_array::operator[]` 的 `size_t`/64 位地址运算、robustness 越界钳制、
`[[max_total_threads_per_threadgroup]]` 造成寄存器不足、"tint 有已知 MSL 性能 bug"。理由见 §6。

---

## 1. 方向一:tint MSL 后端的 threadgroup 访问代码生成

### 1.1 `tint_array<T,N>::operator[]` 与 64 位索引 —— **死路**

tint 生成的包装类(cur.metal:5-15)确实用 `size_t`(MSL 里 `size_t` 是 64 位无符号,
[MSL Spec 2.1 标量类型表](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf))。
但两边在 AIR 层完全同形:

```
tint  : %189 = zext i32 %188 to i64
        %190 = getelementptr inbounds %struct.tint_array.3, ... addrspace(3)* %10, i64 0, i32 0, i64 %189
native: %334 = zext i32 %235 to i64
        %335 = getelementptr inbounds float, float addrspace(3)* %115, i64 %334
```

手写版同样把 `uint` 索引 `zext` 到 i64(MSL 指针算术本来就这样)。`operator[]` 被前端完全展开,
没有留下任何函数调用、没有边界检查、没有 `tint_array` 结构体开销。**这一条不成立。**

### 1.2 robustness 是否覆盖 threadgroup 数组 —— **覆盖,而且你已经关掉了**

- `RobustnessConfig`(`src/tint/lang/core/ir/transform/robustness.h`)只有
  `clamp_texture / clamp_immediate_data / clamp_storage / clamp_uniform / predicate_subgroup_matrix`
  这几个开关,**没有** workgroup 开关。
- `Robustness::ShouldClamp()`(`src/tint/lang/core/ir/transform/robustness.cc:177-192`)对
  `kFunction / kPrivate / kWorkgroup` 三个地址空间是**无条件 `return true`**。
  也就是说:robustness 一旦跑,threadgroup 数组的每次下标都会被钳。
- 但是 MSL 后端的 `raise.cc:136` 是 `if (!options.disable_robustness) { … Robustness(module, config); }`
  —— **整个 pass 要么全跑、要么全不跑**。所以 `disable_robustness` 确实覆盖 threadgroup 数组。
- Dawn 侧接线:`Device.cpp:1792 IsRobustnessEnabled() = !IsToggleEnabled(DisableRobustness)`,
  `metal/ShaderModuleMTL.mm:316 req.tintOptions.disable_robustness = !device->IsRobustnessEnabled();`
- **本机复核**:cur.metal 扫描段没有任何 `min(`/钳制代码,`grep "min("` 只命中 `acos(min(...))`
  这类算法自带的。→ 你的 toggle 确实生效了,这条已经关死。
- 相关但无关的 toggle:`enable_integer_range_analysis_in_robustness`(Toggles.cpp:730)只在
  robustness **开着**时用区间分析省掉钳制,对你无意义。

### 1.3 Dawn 全部 toggle 中与 workgroup memory / bounds / aliasing / subgroup 相关的条目

`src/dawn/native/Toggles.cpp` 共 164 条。逐条筛完,与这条路径沾边的全部如下
(行号为本地 revision):

**bounds / robustness**
- `disable_robustness`(172,Device)—— 你已开;唯一控制 threadgroup 下标钳制的开关
- `enable_integer_range_analysis_in_robustness`(730,Device)—— robustness 内部优化
- `metal_enable_vertex_pulling`(175)—— 顶点阶段,与 compute 无关
- `vulkan_use_image_robust_access2` / `vulkan_use_buffer_robust_access2` —— Vulkan only
- `skip_validation`(117)—— 只跳过 CPU 侧 Dawn 命令校验,不影响 shader 代码生成

**workgroup memory**
- `disable_workgroup_init`(223,Device)—— 关掉 workgroup 内存零初始化。
  **已核:cur.metal 里不存在任何 30 KiB 零初始化循环**(kernel 体只有构造 struct + 调用辅助函数
  两行,见 cur.metal:371-375),说明这条已经是关掉的状态,没有收益可取。
- `metal_replace_workgroup_bool_with_u32`(772)—— 只针对 workgroup `bool`,你没有 bool
- `vulkan_use_zero_initialize_workgroup_memory_extension` —— Vulkan only

**subgroup**
- `subgroup_shuffle_clamped`(630)—— polyfill `subgroupShuffle`,你用的是
  `subgroupShuffleXor`→`simd_shuffle_xor`,cur.metal 里是裸调用,没被 polyfill
- `enable_subgroups_intel_gen9`(593,Adapter)—— Intel only
- `d3d12_relax_min_subgroup_size_to_8`(707)—— D3D only
- `vulkan_cooperative_matrix_stride_is_matrix_elements`(776)—— Vulkan only

**aliasing**
- **没有任何 toggle 与指针别名相关。** 全表 164 条里没有一条影响 MSL 指针限定符或
  threadgroup 变量的分配形态。

**结论:`disable_robustness` 已开且确实覆盖 threadgroup;`disable_workgroup_init` 对应的零初始化
在 cur.metal 里本来就不存在。除这两条外,Dawn 全表 164 条 toggle 里没有第三条能改变这条代码路径。**
想改只能改 tint printer / raise pass,或者改 WGSL 源。

### 1.4 `[[max_total_threads_per_threadgroup(512)]]`

tint 为什么发它,printer.cc:335-341 的注释是一手答案(大意):告诉 MSL 编译器 threadgroup 到底多大,
否则 MSL 编译器会按自己的启发式定一个上限,**导致 pipeline 支持不了 WGSL 里声明的 workgroup size**,
引用 `crbug.com/443794633`。

该 issue 用未鉴权 JSON 接口取回标题为
**"MSL compiler produces pipeline that does not support target workgroup size"**,组件 `Dawn>Tint`
(`curl "https://issues.chromium.org/action/issues/443794633"`;网页版需要登录,JSON 端点公开)。

方向:这个属性是**放宽**而不是收紧——不写它,编译器按 1024 线程的保守寄存器预算走;写了 512,
编译器可以给每线程分配更多寄存器。所以它更可能是帮忙而不是拖后腿。
`native2.metal` 里**没有**这个属性(grep 无命中),说明手写版反而是保守预算那一档,
仍然更快 —— 与「属性有害」的方向相反。

`maxTotalThreadsPerThreadgroup` 会随寄存器压力被 Metal 下调,这是 Apple 侧公开事实
([Apple Developer Forums thread 674385](https://developer.apple.com/forums/thread/674385))。
所以**如果**要测「去掉属性」这一臂,必须同时读 `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`,
一旦 <512 这一臂的数字就作废(pipeline 根本跑不了你的 512 线程)。已生成 `/tmp/v3_nomaxtt.metal` 备用。

---

## 2. 方向二:指针别名

### 2.1 tint 的形态与它的来历

`src/tint/lang/msl/writer/raise/module_scope_vars.cc:235-239` 的注释是一手答案:
workgroup 变量被做成**函数参数**,注释写明这是为了**绕过 MSL 编译器在 threadgroup matrices
上的一个 bug**;再把所有 workgroup 变量聚成一个结构体,是为了不撞 MSL 的 threadgroup 参数个数上限。

这一点很关键:**tint 用的正是 wgpu 报告过会踩 Metal barrier 误编译的那种形态。**
[gfx-rs/wgpu#4500](https://github.com/gfx-rs/wgpu/issues/4500)(2023-09-15)记录:当 threadgroup
共享内存声明成 entry-point 参数(动态 threadgroup memory)而不是 kernel 内固定大小局部变量时,
Metal 编译器会破坏内存访问与 barrier 的顺序;当时该 issue 说 **Tint 用的是 kernel 内局部变量**,
并建议 Naga 学 Tint。**现在(2026 Dawn)tint 已经反过来了**,为了 threadgroup matrix 的另一个 bug
改用了 entry-point 参数。这是一条真实的、被记录在案的「这种形态会让 Metal 编译器表现异常」的先例。

### 2.2 AIR 层实测:别名信息在函数边界丢失

```
cur.ll:586  define void @cur(..., %struct.tint_struct_4 addrspace(3)* nocapture noundef "air-buffer-no-alias" %9)
cur.ll:592    tail call void @_Z4v_14Dv3_jjjj11tint_struct(..., %11, %12, %13, %14, %15, ...)
cur.ll:75   define void @_Z4v_14Dv3_jjjj11tint_struct(..., addrspace(3)* nocapture %9, addrspace(3)* nocapture %10, ...)
```

三点事实:
1. 结构体被前端**标量化**成 5 个独立 threadgroup 指针形参 —— 所以「struct 包装」本身不是问题。
2. `"air-buffer-no-alias"` 只挂在 **entry point** 的那一个 threadgroup 指针上;
   传进辅助函数后,5 个形参**只有 `nocapture`,没有 `noalias`**。
3. 主体逻辑在 `_Z4v_1...` 里,kernel 里是真实 `call`,**AIR 层没有内联**。
   手写版是单个大 kernel,5 个 threadgroup 数组是 kernel 内局部对象,别名问题不存在。

驱动侧 AIR→AGX 时大概率还会再内联一次:kernel 体只有两条语句(cur.metal:373-374 构造 struct 然后
单点调用),内联后 5 个指针是同一 struct 的不同字段 GEP,LLVM 可以证明不重叠。
**所以我给这条的可信度只有中低**,列出来是因为刀本身只要 10 分钟、验收有 AIR 阳性对照,
且它是唯一能解释「静态/动态分配手改为什么没收益」的假设。但它是唯一能解释
「为什么静态/动态分配手改没收益」的假设——你把声明改成静态数组,**指针形参和未内联的调用边界还在**,
变量只是换了个来源,别名不确定性一点没减少。

### 2.3 MSL 有没有 restrict —— **有,而且本机验证有效**

- `restrict` 不是 MSL 关键字(`/tmp/rt.metal` 编译报 `expected ')'`)。
- **`__restrict` 可用**。`/tmp/rt2.metal`:
  `kernel void k(threadgroup float* __restrict a [[threadgroup(0)]], …)` →
  AIR `define void @k(float addrspace(3)* noalias nocapture noundef readonly %0, …)`。
- **`__restrict` 用在局部指针上也生效**:`/tmp/lr.metal` 里
  `threadgroup float* __restrict pa = s.a;` → AIR 的 load/store 带上
  `!alias.scope !26, !noalias !29`。

这给了一个**不动 host 绑定、不动 threadgroup 布局**的最小单变量实验:在 tint 生成的辅助函数开头加
5 个 `__restrict` 局部指针,把 `(*v_19.tint_member_N)[expr]` 全部换成 `pN[expr]`。

### 2.4 没找到的

没有找到任何公开报告说「Metal 编译器因为 threadgroup 指针无法证明不别名而产生重复 load /
无法把值留在寄存器」。这是**空结果**,不是否定结论。

---

## 3. 方向三:"Dawn/tint 生成的核比手写 Metal 慢 X%" 的公开记录

**查完:没有。** 这是本次调研最干净的空结果之一。

检索路径:`site:issues.chromium.org` 定向搜索(Dawn/Tint + MSL + performance/slower/generated code)、
gpuweb issue、dawn.googlesource.com。命中的都是**编译期**性能(pipeline / MTLLibrary 缓存):
- [issues.chromium.org/40281459](https://issues.chromium.org/issues/40281459) `[Graphite] Cache Metal shader pipelines`
- [issues.chromium.org/42241511](https://issues.chromium.org/issues/42241511) `graphite: Cache Metal shader module MTLLibrary in memory`

没有一条讨论**运行期**代码质量,更没有 reduction/scan 这类 threadgroup 密集负载的对照。
`issues.chromium.org` 的搜索 API 需要鉴权(`/action/issues?q=` 返回 401),
单条 issue 的 JSON 端点公开可读——所以「按编号取」可行、「按关键词搜」只能靠外部搜索引擎,
这意味着本条空结果的置信度有上限。

唯一与「tint 的 MSL 形态会让 Metal 编译器出问题」直接相关的一手记录,是 §2.1 的
[wgpu#4500](https://github.com/gfx-rs/wgpu/issues/4500) 和 tint 源码里那句
「to workaround an MSL compiler bug with threadgroup matrices」——两者都是**正确性** bug,
不是性能 bug,但它们证明这条代码路径上 Metal 编译器确实有非常规行为。

---

## 4. 方向四:WGSL 子组能力路线图

### 4.1 `subgroupBarrier` —— 提案存在,尚未落地

[gpuweb/gpuweb#4437 "Add subgroup barrier to subgroups proposal"](https://github.com/gpuweb/gpuweb/issues/4437)
- raphlinus 开于 2024-01-03,**至今 Open**,label `wgsl`,milestone `Milestone 4+`
- 语义:与 `workgroupBarrier()` 相同,只是把「同一 workgroup 的 invocation」换成「同一 subgroup 的
  invocation」;内存语义同为 AcquireRelease + WorkgroupMemory;同样要求在 uniform control flow 中
- **MSL 落地就是 `simdgroup_barrier(mem_flags::mem_threadgroup)`**(issue 原文)
- SPIR-V:`OpControlBarrier(3, 2, 0x108)`
- HLSL:没有直接对应,只能退回 `GroupMemoryBarrierWithGroupSync()`
- 动机用例:Onesweep 基数排序里的 warp-local multi-split —— 和你的场景同构
  (SG 私有的 threadgroup 区域,不需要跨 SG 同步)

已发布的 subgroups 提案 [proposals/subgroups.md](https://github.com/gpuweb/gpuweb/blob/main/proposals/subgroups.md)
里**完全没有 barrier**(全文没有 barrier / simdgroup_barrier / reconvergence 的讨论)。
本地 Dawn `src/tint/lang/core/core.def:908-913` 也证实只有
`storageBarrier()` / `workgroupBarrier()` / `textureBarrier()` 三个。

→ **你多付的那一次全局 barrier 是 WGSL 的结构性缺口,不是 tint 的实现问题,今天无解。**

### 4.2 subgroup matrix 能不能读元素 —— **不能,而且是明文写死的**

`src/tint/lang/core/core.def:2771-2899` 的 subgroupMatrix* 内建**全表**:

```
subgroupMatrixLoad             (storage/workgroup ← runtime_array / array,含 i8/u8 打包重载,共 6 个重载)
subgroupMatrixStore            (同上,6 个重载)
subgroupMatrixMultiply         (f16/f32/iu8/iu32,4 个重载)
subgroupMatrixMultiplyAccumulate(f16/f32/iu8/iu32,4 个重载)
subgroupMatrixScalarAdd        (3)
subgroupMatrixScalarSubtract   (3)
subgroupMatrixScalarMultiply   (3)
```

**没有任何元素访问 / 提取 / 逐 lane 访问器。** 且 `Resolver::IndexAccessor()`
(`src/tint/lang/wgsl/resolver/resolver.cc:1867-1878`)的可索引类型 Switch 只列了
`sem::Array / BindingArray / Vector / Matrix`,subgroup_matrix 落到 default 分支报
`cannot index type '…'`。

设计文档 `docs/dawn/features/subgroup_matrix.md`(本地 Dawn 自带,即
`chromium_experimental_subgroup_matrix` 的规范来源)明确写:这些类型在 WGSL 分类学里不是
"composite",因为**不可分解**,不能引用子向量或单个分量;
"Supported expressions" 一节把 **Decomposition expressions 列在 Explicitly not supported** 下,
"Possible future expansion" 里只列了 arithmetic expressions,**没有元素访问**。

标准化进度:[gpuweb/gpuweb#4195 "Subgroup matrix"](https://github.com/gpuweb/gpuweb/issues/4195)
(alan-baker 开于 2023-06-23,Open,Milestone 2,32 个子任务完成 2 个)。

**但是 —— 手写 Metal 可以。** Apple 工具链头文件
`.../lib/clang/32023.864/include/metal/metal_simdgroup_matrix` 第 63/67 行:

```cpp
METAL_FUNC thread storage_type &thread_elements() thread { return t; }
METAL_FUNC storage_type thread_elements() const thread { return t; }
```

`storage_type = vec<T, Cols*Rows>`。本机实测(`/tmp/te2.metal`):
`float b = max(c.thread_elements()[0], c.thread_elements()[1]);` 编译通过,
AIR 是 `extractelement <64 x float> %6, i64 0` / `i64 1` —— 干净的元素提取,无内存往返。

Dawn 自己的设计文档也承认这一非对称:MSL 允许把接口声明成 simdgroup_matrix,
但没有算子让它可用(原文大意),而 WGSL 侧连分解表达式都直接禁掉。

→ **「在寄存器里做 top-2、彻底不要 accSh」这条结构性大赢,在手写 MSL 上路是通的,在 WGSL 上今天是封死的。**
注意两个前提:(1) lane ↔ 矩阵元素的映射 Apple 没有公开文档,要靠对拍标定;
(2) 你的 top-2 是跨 8 列 / 跨 8 行的归约,`thread_elements()` 每 lane 只给 2 个元素,
还得配 `simd_shuffle_xor` 补齐 —— 这是一条要重新设计归约拓扑的路,不是一刀。

### 4.3 已落地 vs 实验中的子组内建

`core.def` 里已有(shipped `subgroups` feature):
`subgroupBallot / subgroupBroadcast / subgroupBroadcastFirst / subgroupShuffle /
subgroupShuffleXor / subgroupShuffleUp / subgroupShuffleDown / subgroupAdd / … /
subgroupMax / quadSwapX / quadSwapY / quadSwapDiagonal`(2656-2769 行)。

subgroup matrix 在 `chromium_experimental_subgroup_matrix` 扩展下,API feature 名
`chromium-experimental-subgroup-matrix`;Metal 侧要求 Apple7+,配置硬编码为
f32/f32 和 f16/f16 的 8×8×8(设计文档 "Metal" 小节)。你现在用的正是 f16→f32 8x8x8,
但注意:**设计文档的 Metal 硬编码表里 componentType=f16 时 resultComponentType 也是 f16**,
f16 输入 / f32 累加是否在你这条 Dawn revision 上被暴露,值得单独核一次
`GPUAdapterInfo.subgroupMatrixConfigs`。

---

## 5. 一小时内可跑的证伪清单(已备好文件)

全部基于「同二进制、单变量、交替 A/B」,产物已生成在 `/tmp`:

1. **H1 barrier 域**:`/tmp/v1_sgbarrier.metal`
   —— 与 cur.metal **只差第 212 行**(`threadgroup_barrier` → `simdgroup_barrier`)。
   已确认编译通过,AIR 出现 `air.simdgroup.barrier`。
   合法性:accSh 的写(`offset = sgid*8*32 + nt*8`)与读(行扫 `(sgid*8+lrow)*32`、
   列扫 `(sgid*8)*32 + lane`)全部限定在本 SG 的 8 行内,无跨 SG 共享 —— 与 native2.metal:156-157
   注释里的判断一致。
   **判据**:如果 5.649 → ~4.6,H1 成立;如果只回 0.1ms,H1 死。
   **顺带**:这同时是对你「加 barrier 量斜率 = 0.4µs/次」那把尺子的阳性对照。
   那把尺子测的是「在已经同步好的点上再加一次 barrier」的边际成本,
   量不到「把 SG 私有的同步升级成全局同步、从而把数据相关的 SG 间抖动串行化」的成本。
   这两件事量纲不同 —— 前者是固定开销,后者是 SG 间时间散布。扫描段是数据相关的分支代码
   (`if (d > pb)`),SG 间耗时本来就不齐,正是这类成本的高发区。而 MMA-only 那一臂里
   barrier 后面没有任何东西,散布无处可去,所以那一臂看不出来 —— 这恰好解释了
   「MMA+barrier 臂我们反而更快、加上扫描就慢 1.11ms」的分裂。

2. **H3 别名**:在 cur.metal 的 `_Z4v_1…` 辅助函数开头插入
   ```cpp
   threadgroup half*  __restrict pB   = &(*v_19.tint_member_16)[0];
   threadgroup float* __restrict pAcc = &(*v_19.tint_member_17)[0];
   threadgroup float* __restrict pCb  = &(*v_19.tint_member_18)[0];
   threadgroup float* __restrict pCs  = &(*v_19.tint_member_19)[0];
   threadgroup int*   __restrict pCi  = &(*v_19.tint_member_20)[0];
   ```
   再把所有 `(*v_19.tint_member_N)[expr]` 换成 `pX[expr]`。
   **验收先看 AIR**:`xcrun metal -S -emit-llvm` 后必须出现 `!alias.scope`/`!noalias`
   (`/tmp/lr.ll` 是阳性对照);出现不了就说明这一刀没落地,别去看时间。
   注意 `/tmp/v2_restrict.metal`(把 `__restrict` 加在 struct 成员上)**已验证无效**
   —— AIR 里 `noalias` 计数为 0,是个反面样本,别用。

3. **H1 的对照臂**:把 native2.metal 第 171 行的 `simdgroup_barrier` 改成 `threadgroup_barrier`,
   跑手写版。如果手写版从 4.544 涨到 ~5.6,H1 直接坐实,而且证明差距**不在 tint**,
   在 WGSL 语言表面。这一臂比第 1 条更强,因为它是在**手写代码**上做单变量,
   排除掉一切 tint 代码生成的其它差异。**建议先跑这一条。**

4. **(可选,须带闸)`/tmp/v3_nomaxtt.metal`**:去掉 `[[max_total_threads_per_threadgroup(512)]]`。
   **必须**同时打印 `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`,
   <512 则该臂作废(crbug 443794633 就是这个失败模式)。

---

## 6. 判死的方向与理由

| 方向 | 判死理由 |
|------|---------|
| `tint_array::operator[]` / `size_t` 64 位地址运算 | AIR 逐条对照:两边都是 `zext i32 → i64` + `getelementptr`,完全同形。包装类被前端展开干净,零残留 |
| robustness 越界钳制 | `raise.cc:136` 是整 pass 开关,`disable_robustness` 覆盖 threadgroup;cur.metal 扫描段无任何钳制代码 |
| Dawn toggle 层面还有别的杠杆 | 164 条逐条筛完:`disable_robustness` 已开、`disable_workgroup_init` 对应的代码本来就不存在,没有第三条影响 Metal 上的 threadgroup 代码生成;**没有任何 aliasing 相关 toggle** |
| `[[max_total_threads_per_threadgroup(512)]]` 拖慢 | 方向相反:它是放宽寄存器预算的提示;手写版**没有**这个属性(更保守的一档)却更快 |
| 「tint 有已知的 MSL 运行期性能 bug」 | 检索无命中。Dawn/Chromium tracker 上 Dawn+Tint+MSL+performance 只命中编译期缓存类 issue。注意此空结果有上限:tracker 搜索 API 需鉴权 |
| WGSL 里读 subgroup matrix 元素做寄存器内 top-2 | 设计文档明文「不可分解 / Decomposition expressions 显式不支持」,core.def 无内建,resolver 直接报错。**今天无路**,而且不在任何已公开的 future expansion 列表里 |
| 「struct 包装 threadgroup 指针」本身 | AIR 里结构体被标量化成独立指针形参,struct 不产生额外访存。真正可疑的是**丢失的 noalias + 未内联的调用边界**(H3),不是 struct 本身 |
| 静态 vs 动态 threadgroup 分配(你已测 5.589/5.628) | 与该结论一致,但**这一测没有排除 H3**:你换掉的是变量来源,指针形参和函数边界还在。H3 要用 §5.2 的 `__restrict` 刀单独测 |

---

## 7. 引用清单

**本地一手(Dawn revision a117f96e09e88e76c0a9e3b553b7316cda50633d)**
- `src/dawn/native/Toggles.cpp`(164 条 toggle 全表)
- `src/dawn/native/Device.cpp:1792`,`src/dawn/native/metal/ShaderModuleMTL.mm:316`
- `src/tint/lang/core/ir/transform/robustness.h`(RobustnessConfig)/ `.cc:177-192`(ShouldClamp)
- `src/tint/lang/msl/writer/raise/raise.cc:136`
- `src/tint/lang/msl/writer/raise/module_scope_vars.cc:235-239`(workgroup→函数参数的原因注释)
- `src/tint/lang/msl/writer/printer/printer.cc:335-341`(max_total_threads 的原因注释 + crbug.com/443794633)
- `src/tint/lang/core/core.def:908-913`(barrier 全表)、`2656-2769`(subgroup 内建)、`2771-2899`(subgroupMatrix 内建)
- `src/tint/lang/wgsl/resolver/resolver.cc:1867-1878`(IndexAccessor 可索引类型)
- `docs/dawn/features/subgroup_matrix.md`(扩展设计文档)

**Apple 一手**
- `Metal.xctoolchain/.../include/metal/metal_simdgroup_matrix:30-100`(`thread_elements()` / `storage_type`)
- 本机 `xcrun metal 32023.864` 实测:`__restrict` → `noalias`;`thread_elements()[i]` → `extractelement`
- [Metal Shading Language Specification](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf)(size_t = 64 位)
- [Apple Developer Forums 674385](https://developer.apple.com/forums/thread/674385)(寄存器压力下调 maxTotalThreadsPerThreadgroup)

**上游一手**
- [gpuweb/gpuweb#4437 Add subgroup barrier to subgroups proposal](https://github.com/gpuweb/gpuweb/issues/4437)(Open,Milestone 4+)
- [gpuweb/gpuweb#4195 Subgroup matrix](https://github.com/gpuweb/gpuweb/issues/4195)(Open,Milestone 2)
- [gpuweb/gpuweb proposals/subgroups.md](https://github.com/gpuweb/gpuweb/blob/main/proposals/subgroups.md)(无 barrier)
- [gpuweb/gpuweb#3950 Considerations for subgroups](https://github.com/gpuweb/gpuweb/issues/3950)(raphlinus,2023-03-10;不含 barrier)
- [gfx-rs/wgpu#4500](https://github.com/gfx-rs/wgpu/issues/4500)(Metal 动态 threadgroup memory 的 barrier 误编译)
- [issues.chromium.org/443794633](https://issues.chromium.org/issues/443794633) "MSL compiler produces pipeline that does not support target workgroup size"(Dawn>Tint)
