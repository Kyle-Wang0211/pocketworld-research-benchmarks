# Apple GPU 上 simdgroup_matrix GEMM 的业界做法 — 一手源码调研

调研日期 2026-09-04。目标机器 **Apple M3 Pro / 18 GPU core**。
纪律:凡「X 这么写」与「X 因此更快」分开标注;没有数字的地方明确写「查不到」。

---

## 0. 先把本机的身份钉死(一手,本机文件系统)

MLX 的 GEMM 分块参数是按 **GPU 架构字符串的最后一个字母** 分档的,所以必须先确定本机是哪个字母。

| 证据 | 命令/路径 | 结果 |
|---|---|---|
| 已加载的 GPU 驱动 kext | `kmutil showloaded \| grep AGX` | `com.apple.AGXG15S (341.11)` |
| IORegistry | `ioreg -c IOAccelerator -r -d 1` | class `AGXAcceleratorG15X`,`MetalPluginClassName = "AGXG15SDevice"`,`MetalPluginName = "AGXMetalG15X_M1"`,`"gpu-core-count" = 18` |
| Apple 自己的 Metal 工具链里的架构名单 | `strings .../Metal.xctoolchain/usr/metal/32023/bin/air-config \| grep -o "applegpu_g[0-9][0-9][a-z]*"` | `applegpu_g10p g11g g11m g11p g12p g13c g13d g13g g13p g13s g14d g14g g14p g14s **g15d g15g g15p g15s** g16g g16p g16s g17g g17p g17s g18p` |

⇒ 本机 = **`applegpu_g15s`**,MLX 里 `devc == 's'`。

「G15 == M3 世代」这一点有 MLX 源码自己的注释作旁证(一手):

- `mlx/backend/metal/matmul.cpp` L1306-1309(SHA `b6368984b8e02a3fb3ee7986846c0fb85e1fccf7`):
  ```cpp
  // Pre-M3 generations are limited by load issue rate rather than
  // bandwidth and do not profit from the amortized stream; they keep the
  // existing kernels.
  if (d.get_architecture_gen() < 15) {
    return std::nullopt;
  }
  ```
  `get_architecture_gen()` 的解析在 `mlx/backend/metal/device.cpp` L595-601:取架构名倒数第 3、第 2 个字符当十位/个位。⇒ gen 15 = G15 = M3。

---

## 1. MLX(Apple 自家,MIT)`steel` GEMM

仓库 `ml-explore/mlx`,pin 到 **SHA `b6368984b8e02a3fb3ee7986846c0fb85e1fccf7`**(main,2026-09-04 抓取)。
LICENSE 文件首行 `MIT License / Copyright © 2023 Apple Inc.` — **MIT,可商用**(已核源文件本身,非二手转述)。

### 1.1 累加器数量:公式在源码里,不用猜

`mlx/backend/metal/kernels/steel/gemm/mma.h` L453-483:

```cpp
struct BlockMMA {
  STEEL_CONST short kFragSize = 8;                       // L455
  using MMAFrag_acc_t = BaseMMAFrag<AccumType, kFragSize, kFragSize>;
  STEEL_CONST short TM = BM / (kFragSize * WM);          // L464  Warp tile size along M
  STEEL_CONST short TN = BN / (kFragSize * WN);          // L466  Warp tile size along N
  ...
  MMATile<AccumType, TM, 1,  MMAFrag_acc_t> Atile;       // L481
  MMATile<AccumType, 1,  TN, MMAFrag_acc_t> Btile;       // L482
  MMATile<AccumType, TM, TN, MMAFrag_acc_t> Ctile;       // L483
};
```

`MMATile<T, R, C>` 里 `frag_type val_frags[kNumFrags]`,`kNumFrags = kTileRows*kTileCols`(mma.h L227、L233)。
所以 **每个 simdgroup 持有 `TM × TN` 个 8×8 累加器**,并同时持有 `TM` 个 A fragment、`TN` 个 B fragment。

内层循环 `BlockMMA::mma()`(mma.h L513-537)每前进 8 个 k:
载入 `TM` 个 A fragment + `TN` 个 B fragment ⇒ 发出 `TM × TN` 次 MMA(`tile_matmad`,mma.h L407-427)。

> **算术强度 = TM·TN / (TM+TN)**,单位是「MMA 次数 / fragment 载入次数」。

### 1.2 实际用到的分块参数(全部实例化)

`mlx/backend/metal/kernels/steel/gemm/kernels/steel_gemm_fused.metal` L22-27:

| BM | BN | BK | WM | WN | simdgroup 数 | 线程数 | **TM** | **TN** | **累加器/simdgroup** | 每 k 步载入 | 每 k 步 MMA | **MMA:载入** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 | 64 | 16 | 2 | 2 | 4 | 128 | 4 | 4 | **16** | 8 | 16 | **2.00** |
| 64 | 64 | 16 | 1 | 2 | 2 | 64 | 8 | 4 | **32** | 12 | 32 | **2.67** |
| 64 | 32 | 32 | 2 | 2 | 4 | 128 | 4 | 2 | **8** | 6 | 8 | 1.33 |
| 32 | 64 | 16 | 1 | 2 | 2 | 64 | 4 | 4 | **16** | 8 | 16 | 2.00 |
| 32 | 32 | 16 | 2 | 2 | 4 | 128 | 2 | 2 | **4** | 4 | 4 | 1.00 |
| 64 | 32 | 8 | 4 | 1 | 4 | 128 | 2 | 4 | **8** | 6 | 8 | 1.33 |

(`tgp_size = WM*WN*32`,见 `gemm.h` L46;`group_dims = MTLSize(32, wn, wm)`,见 `matmul.cpp` L307。)

### 1.3 M3 Pro 上实际会选哪一档

`matmul.cpp` L91-172 的 `GEMM_TPARAM_MACRO(devc)`:

```
if (devc == 'g' || devc == 'p')  { /* Small device  */ ... }
else if (devc == 'd')            { /* Large device  */ ... }
else                             { /* Medium device */ bm=64; bn=64; bk=16; wm=2; wn=2; }
```

本机 `devc == 's'` ⇒ **Medium device ⇒ BM=64, BN=64, BK=16, WM=2, WN=2 ⇒ TM=TN=4 ⇒ 每 simdgroup 16 个 8×8 累加器,MMA:载入 = 2.0**。

('d' 档 + 大 matmul + half 会走 `bm=64,bn=64,bk=16,wm=1,wn=2` ⇒ **32 个累加器 / 比值 2.67**,那是 Ultra 级机器。)

### 1.4 MLX 的其它三个非显然设计决定(都能直接抄)

1. **不用 `simdgroup_load`,自己按 lane 坐标手动拼 fragment。**
   `BaseMMAFrag<T,8,8>::get_coord()`(mma.h L48-55)给出每个 lane 在 8×8 里的 (row, col),
   `kElemRows=1, kElemCols=2`(L38-39)⇒ **每 lane 每 fragment 只做 2 个标量读**(mma.h L57-67),
   然后 `reinterpret_cast` 塞进 `simdgroup_matrix::thread_elements()`(mma.h L186-196)。
   好处:载入时顺手做类型转换、可以任意 stride(转置不用付 `transpose_matrix=true` 的代价)。
2. **threadgroup 数组一律加 16 字节 padding。** `gemm.h` L38-44:
   `tgp_padding = 16 / sizeof(T)`(half ⇒ 8 个元素),`tgp_mem_size_a = BM*(BK+8)`。
   ⇒ 行 stride 永远不是 2 的幂,避开 threadgroup 内存 bank 冲突。
   64/64/16 nt 档的总 threadgroup 用量 = `64*(16+8) + 64*(16+8) = 3072` half = **6 KiB**。
3. **`tile_matmad` 用蛇形(serpentine)顺序遍历 N。** mma.h L416:`short n_serp = (m % 2) ? (N - 1 - n) : n;`
   ⇒ 相邻两行 m 的 B fragment 访问顺序反向,B 寄存器复用更好。
4. **主循环没有 double buffering。** `gemm.h` L97-120:每个 k 迭代是
   `barrier → load_a → load_b → barrier → mma`,单缓冲、两道 barrier。
   全局→threadgroup 的搬运是 16 字节向量拷贝(`loader.h` L22 `n_reads=(BCOLS*BROWS)/tgp_size`、L42-44 `ReadVector`、L74-80)。

### 1.5 一个容易被忽略的点:MLX 的 A/B fragment 是 **float**,不是 half

`Atile`/`Btile` 用的是 `MMAFrag_acc_t = BaseMMAFrag<AccumType,8,8>`,而 `AccumType` 在实例化时被硬编成 `float`
(`steel_gemm_fused.metal` L13 宏最后一个参数)。所以 MLX 走的是 **fp32 8×8×8 MMA**,不是 half×half→f32。
我们的核用 half×half→f32,这在 MSL 里是合法的(见 §3.1),但两者不是同一条指令路径。
**没有查到 MLX 为什么这么选的公开说明,也没查到两者在 Apple GPU 上的吞吐对比数字。**

### 1.6 MLX 的 Metal 4 张量路径(`nax`)在 M3 上不启用

`mlx/backend/metal/device.cpp` L947-966:

```cpp
bool is_nax_available() {
  ...
  if (__builtin_available(macOS 26.2, iOS 26.2, tvOS 26.2, visionOS 26.2, *)) can_use_nax = true;
  auto arch = d.get_architecture().back();
  auto gen  = d.get_architecture_gen();
  can_use_nax &= gen >= (arch == 'p' ? 18 : 17);   // ← G17 / G18P 起
  ...
}
```

⇒ **`mpp::tensor_ops::matmul2d` 路径只在 gen ≥ 17(M5 世代)/ gen ≥ 18('p' 即 A19 Pro)才启用。**
本机 gen = 15,**不走**那条路。这是「M3 上 `simdgroup_matrix` 背后没有专用矩阵单元」的强旁证
(注意:这是 MLX 的分档事实,不等于 Apple 官方承认 M3 无 MXU —— 后者查不到官方声明)。

那条路径的参数顺便记录(`matmul.cpp` L206-215):默认 `bm=128,bn=128,bk=512,wm=4,wn=4`;
对 `'s'/'c'/'d'` 机器降为 `bm=64, wm=2`,`bk = (K>=8192 && K>M+N) ? 64 : 256`。
每次 `mpp::tensor_ops::matmul2d_descriptor(16, 32, 16, ...)`(`steel/gemm/nax.h` L401-408)—— 即 M=16,N=32,K=16 的单次 simdgroup 级 matmul,比 8×8×8 大得多。

---

## 2. CUTLASS / CuTe(NVIDIA 参照系)

仓库 `NVIDIA/cutlass`,pin 到 **SHA `59e3a3338d516ca6ce0e073af8da65289678a35c`**。

`include/cutlass/gemm/device/default_gemm_configuration.h` L459-482,SM80 TensorOp 的**默认**配置:

```cpp
struct DefaultGemmConfiguration<arch::OpClassTensorOp, arch::Sm80, ElementA, ElementB, ElementC, ElementAccumulator> {
  using ThreadblockShape  = GemmShape<128, 256, 64>;   // L467
  using WarpShape         = GemmShape<64, 64, 64>;     // L468
  using InstructionShape  = GemmShape<16, 8, 16>;      // L469
  static int const kStages = 3;                        // L470
};
```

推导(可自行核算):

- warp tile 64×64,指令 m16n8k16 ⇒ 每 warp 每个 k 段持有 **(64/16) × (64/8) = 4 × 8 = 32 个累加器 fragment**。
- 每个 m16n8k16 累加器 = 16×8 = 128 个 f32 / 32 lane = **4 个 f32 寄存器/lane** ⇒ **128 个 f32 累加寄存器/lane**。
- 每个 k 步(k=16):载入 4 个 A fragment + 8 个 B fragment = **12 次载入 ⇒ 32 次 MMA ⇒ 比值 2.67**。
- threadblock 128×256 / warp 64×64 ⇒ 2×4 = **8 个 warp = 256 线程**;`kStages=3` = 三级 async 流水(不是 double,是 triple buffering)。

CUTLASS 官方文档把「寄存器分块」当作第一性设计原则(`media/docs/cpp/efficient_gemm.md`,同 SHA):

- L94-95:"To maximize data reuse within the warp, a large warp-level GEMM tile should be chosen."
- L100-103:"Threads cannot access each other's registers, so we choose an organization that enables reuse of values held in registers for multiple math instructions. This results in a 2D tiled structure within a thread…"
- L133-134:"The accumulator elements typically occupy **at least half a thread's total register budget**."

⇒ **业界标准就是「累加器吃掉一半以上寄存器」。** CUTLASS 128 个累加寄存器 vs 我们的 2 个。

---

## 3. Apple 官方口径

### 3.1 MSL 的 `simdgroup_matrix` 只有 8×8,但**允许混合精度**(一手:本机工具链头文件)

`/var/run/com.apple.security.cryptexd/mnt/com.apple.MobileAsset.MetalToolchain-v17.3.7003.10.*/Metal.xctoolchain/usr/metal/32023/lib/clang/32023.864/include/metal/metal_simdgroup_matrix`
(工具链版本 `Apple metal version 32023.864 (metalfe-32023.864)`):

```cpp
METAL_FUNC constexpr bool _valid_simdgroup_matrix_size(int cols, int rows)   // L24-28
{ return (cols == 8 && rows == 8); }                                          // ← 只有 8×8
```

```cpp
template <typename R, typename T, typename U, typename V, int K, int Rows, int Cols>   // L204-210
METAL_FUNC enable_if_t<_valid_simdgroup_multiply_accumulate_v<R,T,U,V,K>>
simdgroup_multiply_accumulate(thread simdgroup_matrix<R,Cols,Rows> &d,
                              simdgroup_matrix<T,K,Rows> a,
                              simdgroup_matrix<U,Cols,K> b,
                              simdgroup_matrix<V,Cols,Rows> c);
```
D/A/B/C 四个类型参数彼此独立,约束只有 `is_floating_point`(L197-199)⇒ **half×half→float 是官方支持的组合**,
我们的核没有走野路子。底层内建函数只有一组:`__metal_simdgroup_matrix_8x8_{init_diag,init_filled,load,store,multiply_accumulate}`
(在 `/System/Library/PrivateFrameworks/GPUCompiler.framework/.../libGPUCompilerImplLazy.dylib` 里 `strings` 可见,本机核实)。

编译器宏(本机 `xcrun metal` 实测):`-std=metal3.2` 定义 `__HAVE_SIMDGROUP_MATRIX__`;
`-std=metal4.0` 额外定义 `__HAVE_TENSOR__`。

### 3.2 Apple 官方给过分块建议 —— 在 MetalPerformancePrimitives 的头文件注释里(带数字的完整版见 §8.2)

`MacOSX26.2.sdk/System/Library/Frameworks/MetalPerformancePrimitives.framework/Headers/MPPTensorOpsMatMul2d.h`
(`Copyright (c) 2025 Apple Inc.`),文件顶部 L41-58 的官方示例:

> "It tiles this matrix multiplication in thread groups, where each thread group computes a **64 x 32 tile of output** …
>  It uses **4 SIMD-Groups per threadgroup**"

⇒ Apple 自己的推荐样例:**每 threadgroup 64×32 输出 / 4 个 simdgroup ⇒ 每 simdgroup 512 个输出 = 8 个 8×8 tile**。
我们是每 simdgroup 8×32 = 256 个输出、但一次只活着 1 个 8×8 累加器。

同头文件 L11-38 列出 `matmul2d` 支持的 A/B/C 类型组合(含 `half half float`、`int8_t int8_t int32_t`);
L328-368 是 `matmul2d_descriptor(m, n, k, transpose_left, transpose_right, relaxed_precision, mode)`;
L284-289 说明执行域可以是 `execution_thread` / `execution_simdgroup` / `execution_simdgroups<N>`。
**注意:这套 API 需要 `__HAVE_TENSOR__`(Metal 4),而按 MLX 的分档它在 M3 上不启用(§1.6)。分块建议本身仍然可参考。**

---

## 4. 理论侧:8×8×8 MMA 的算术强度,以及我们缺的到底是什么

### 4.1 通用公式

一个 simdgroup 若持有 `Rm × Rn` 个 8×8 累加器(即负责 `8Rm × 8Rn` 的输出块),
每前进 8 个 k 需要 `Rm` 个 A fragment + `Rn` 个 B fragment,发出 `Rm·Rn` 次 MMA:

```
算术强度 I = Rm·Rn / (Rm + Rn)          [MMA 次数 / fragment 载入次数]
```

`Rm=Rn=R` 时 `I = R/2`。**这就是「寄存器分块」的全部数学内容。**

### 4.2 我们的核落在哪

我们的结构特殊在:**A 是完全常驻的**(`aFrag[16]`,整个 128 维 k 都在寄存器里,跨所有列块复用),
所以 A 的载入次数在稳态里是 0,公式退化为:

```
I = Rm·Rn / Rn = Rm          ← A 常驻时,算术强度恰好等于每个 simdgroup 负责的 A 行块数
```

我们 **Rm = 1**(每 simdgroup 8 行)⇒ **I = 1.0**,即 **每 1 次 `subgroupMatrixLoad<Right>` 只摊到 1 次 MMA**。

逐层账(一个 512 线程 workgroup、一个 32 列块):

| 层级 | MMA 次数 | B fragment 载入次数 | 比值 |
|---|---|---|---|
| 单 simdgroup(4 个 nt × 16 个 k) | 64 | 64 | **1.0** |
| 整个 workgroup(16 simdgroup) | 1024 | 1024 | **1.0** |
| Bsh 里实际不同的 B fragment | — | 64(每个被 16 个 simdgroup 各读一遍) | — |

对照:

| 实现 | 分块(BM×BN×BK) | 线程/simdgroup 数 | 每 simdgroup 输出块 | **累加器数** | 每 lane 累加寄存器 | **MMA:载入** |
|---|---|---|---|---|---|---|
| **我们** | 128×32×128 | 512 / 16 | **8×32(一次只活 8×8)** | **1** | **2** | **1.0** |
| MLX steel,M3 Pro 实际档 | 64×64×16 (wm2 wn2) | 128 / 4 | 32×32 | **16** | 32 | **2.0** |
| MLX steel,大机器 half 档 | 64×64×16 (wm1 wn2) | 64 / 2 | 64×32 | **32** | 64 | **2.67** |
| llama.cpp 现役 Metal 内核 | 64×32×32 | 128 / 4 | 32×16 | **8** | 16 | **1.33** |
| llama.cpp Metal-4 tensor 路径(仅 M5+) | 64×128×32 | 128 / 4 | 32×64 | (等效 32) | 64 | — |
| Apple MPP 官方样例 | — ×(64×32 输出) | 4 simdgroup | 512 个输出 | **8** | 16 | —(API 不暴露 fragment 层) |
| CUTLASS SM80 默认 | 128×256×64 | 256 / 8 warp | warp 64×64 | **32**(m16n8k16) | **128** | **2.67** |

**结论:寄存器分块确实是我们缺的那一块,而且缺得非常彻底(1 vs 8~32)。**

### 4.3 寄存器预算核算(Apple GPU,SIMD 宽度 32)

一个 8×8 fragment 分摊到 32 lane ⇒ 每 lane 2 个元素:

| fragment 类型 | 每 lane 元素 | 每 lane 32 位寄存器 |
|---|---|---|
| `simdgroup_matrix<half, 8,8>` | 2 × half | **1** |
| `simdgroup_matrix<float,8,8>` | 2 × float | **2** |

**结构上其实只有一个旋钮。** 保持 512 线程 / 16 simdgroup / `accSh = 16 KiB` 不变,
令 workgroup 行数为 `R_wg`、列块宽为 `C = 4096 / R_wg`(这样 `accSh = R_wg × C × 4B` 恒等于 16 KiB),
则每个 simdgroup 的行块数 `Rm = R_wg / 128`、列块数 `nt = C / 8`,循环写成

```
for nt in 0..nt_max:            # nt 在外
  acc[0..Rm-1] = 0              # Rm 个 8×8 f32 累加器同时活
  for k in 0..15:
    bF = load(Bsh, nt, k)       # ← 每 k 只载入 1 个 B fragment
    for m in 0..Rm-1:
      acc[m] = mma(aFrag[m][k], bF, acc[m])   # ← 摊到 Rm 次 MMA
  store acc[0..Rm-1] -> accSh
```

⇒ **算术强度 I = Rm,一条链贯通:**

| 方案 | R_wg(行) | C(列) | **Rm = I** | nt | aFrag | acc | bF | 小计 | +寻址(估) | **合计(估)** | Bsh | accSh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **现状** | 128 | 32 | **1** | 4 | 16 | 2 | 1 | 19 | ~10 | **~29** | 8 KiB | 16 KiB |
| **R2(推荐)** | **256** | **16** | **2** | 2 | 32 | 4 | 1 | 37 | ~12 | **~49** | **4 KiB** | 16 KiB |
| **R4(激进)** | **512** | **8** | **4** | 1 | 64 | 8 | 1 | 73 | ~12 | **~85** | **2 KiB** | 16 KiB |

**R2 的账,逐条核对:**

| 指标 | 现状 | R2 | 变化 |
|---|---|---|---|
| 线程/workgroup | 512 | 512 | **不变** |
| simdgroup 数 | 16 | 16 | **不变** |
| 线程组内存 | 8+16+6 = 30 KiB | 4+16+6 = **26 KiB** | **−4 KiB** |
| 每列块的 MMA 条数(整 workgroup) | 1024 | 1024 | **不变** |
| 每列块的 B fragment 载入条数 | 1024 | **512** | **减半** |
| 全 GPU 的 barrier 总数 | (N/128)·(N/32)·2 = N²/2048 | (N/256)·(N/16)·2 = N²/2048 | **不变** |
| 每 lane 寄存器(估) | ~29 | ~49 | +20 |

**结论:R2 在「线程数、simdgroup 数、MMA 条数、barrier 数」四项完全不变的前提下,
把 B fragment 的载入指令数砍掉一半,还省 4 KiB 线程组内存。代价只有 ~20 个寄存器。**

**本质**:A 常驻时,同一块 Bsh 被 16 个 simdgroup 各读一遍,冗余度是 16。
把每个 simdgroup 负责的行数从 8 加到 16,同一次载入就摊到 2 次 MMA。**这就是全部的收益来源。**

- ❌ **一条我先想到又自己推翻的路:「把 K 拆两段以省 aFrag 寄存器」不成立。**
  A 之所以「免费」,恰恰是因为它整条 K=128 常驻、跨所有列块复用。一旦按 K 分段,
  aFrag 就必须在**每个列块内**重新载入两次,而且为了在换段前把所有 nt 做完,
  `acc` 必须同时活 `Rm × nt` 个。Rm=4 的 K 分段版:寄存器 32(aFrag)+32(acc)+1 = 65,比值只有 **2.0**
  —— **比 R2(49 寄存器 / 比值 2.0)严格更差。这条路不要走。**

- ⚠️ **R2/R4 需要改的地方**:归约段的几何(现在是 128 行 × 32 列一趟,变成 256×16 / 512×8),
  以及 Bsh 预取的列数。**top-2 的语义完全不变,只是分块形状变了。**

- ✅ **寄存器上限已查到**(§8.3,Asahi/Mesa 的 AGX 占用率表):
  每 lane 上限 **128 个 32 位寄存器**;**≤52 个 32 位寄存器**时占用率满档(每核心 1024 线程 / 32 simdgroup);
  且 **512 线程的 workgroup 硬上限是 104 个 32 位寄存器**(1024 线程的 workgroup 只有 52 个)。
  换算后 R2(~49)**仍然卡在满档门槛以内**,R4(~85)会掉到「每核心 576 线程」那一档。
  完整核算见 **§9**。

### 4.4 顺手可以抄的三把小刀(和寄存器分块正交)

1. **B 的 `transpose=true` 载入**:我们每次 `subgroupMatrixLoad<Right>(..., transpose=true, stride=128)`,
   在 MSL 里是 `simdgroup_load(..., transpose_matrix=true)`。**MLX 完全不用 `simdgroup_load`** ——
   它用 `get_coord()` + 每 lane 2 个标量读手动拼 fragment(mma.h L48-67),转置只是换 stride、零额外代价。
   **没有查到 Apple 官方或任何公开来源给出「transposing simdgroup_load 比普通 load 慢多少」的数字** —— 这是个待测项,不是已知事实。
2. **Bsh 的行 stride 是 128 个 half = 256 字节,正好是 2 的幂** —— threadgroup 内存 bank 冲突的最坏情况。
   MLX 一律 `+16 字节` padding(`gemm.h` L38-39,half ⇒ +8 个元素)。改成 stride 136 是一行的事。
3. **蛇形遍历**:`tile_matmad` 的 `n_serp = (m%2) ? (N-1-n) : n`(mma.h L416)。只有在 Rm≥2 之后才有意义。

---

## 5. 「为什么同一个 kernel 在更大规模下每单位工作更省」

### 5.1 Apple 官方能给的硬数字(一手:Metal Feature Set Tables PDF,今日抓取,8 页)

`https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf`

- 第 1 页机型表:**M3-series = Apple9**(A17 Pro / A18 / M3 / M4 都是 Apple9;M5 = Apple10)。
- Feature 表:`SIMD-scoped matrix multiply operations — Metal 3 & 4 — Apple7` ⇒ 从 A14/M1 起就有,不是新东西。
- Limits 表:
  - `Maximum threads per threadgroup` = **1024**(Apple3+)
  - `Maximum total threadgroup memory allocation` = **32 KB**(Apple3+)
  - `Threadgroup memory length alignment` = **16 B** ← MLX 那个 `16 / sizeof(T)` 的 padding 正是照这个对齐来的
  - `Maximum explicit image block allocation` = 32 KB,脚注 6:"You can allocate memory between imageblock and
    threadgroup memory, but the sum of these allocations can't exceed the maximum total image block memory limit."

**Apple 官方文档里没有任何「每核心有多少 threadgroup 内存 / 用多少寄存器会掉几档占用率」的表。** 这是查不到的部分,
只能靠 Asahi/Mesa 的逆向数据(见 §6)。

### 5.2 我们这个核的规模伸缩:两条可算的机制

给定题面的几何(每 workgroup 128 行 × 全部列,30 KiB 线程组内存,18 个 GPU core):

**(a) 波次量化(wave quantization / 尾效应)——可以直接算**

**前提(未证实,标红)**:若每个 GPU core 的线程组内存总量就是 32 KiB,那么 30 KiB 的占用意味着
**每核心最多同时驻留 1 个 workgroup**,于是「一波」= 18 个 workgroup。
Apple 的 Feature Set Tables 只给了「单个 threadgroup 最多申请 32 KB」,**没有给每核心总量**;
脚注 6 又说 imageblock 与 threadgroup 内存共享同一个池子,而 Apple9 的 implicit imageblock 上限是 128 KB,
所以每核心总量**有可能大于 32 KiB**。下表的算术只有在「每核心 1 个 workgroup」成立时才有效。

| N | workgroup 数 = N/128 | 波数 = ⌈·/18⌉ | 最后一波占用 | 波次效率 |
|---|---|---|---|---|
| 8192 | 64 | 4 | 10/18 | 64 / (4×18) = **88.9%** |
| 13312 | 104 | 6 | 14/18 | 104 / (6×18) = **96.3%** |

⇒ 光是波次量化就能解释 **96.3/88.9 = 1.083,即 8.3% 的「变大更省」**。
实测原生的「变省」是 2.64/2.33 = **1.133(13.3%)**,我们是 2.64/2.60 = **1.015(1.5%)**。

**⚠️ 但这条机制对两个核应该是同等作用的**(几何一样、驻留度一样),所以它解释不了两者的差异,
只能说明「变大更省」这个现象本身在这个几何下是预期内的。
**可证伪的检验**:把 N 从 128×54 扫到 128×126(即 3 到 7 波),
每单位工作的成本应该出现**周期 = 18 个 workgroup = 2304 行**的锯齿。如果没有锯齿,这条机制被否掉。

**(b) 固定开销(冷频爬坡 / 首次访存延迟 / 指令缓存冷启动)—— 只是假设,但可以量化**

设成本 = 固定项 + 与工作量成正比项:`t(w) = a + c·w`。工作量比 = (13312/8192)² = 2.64。

- 我们:`(a + 2.64c)/(a + c) = 2.60` ⇒ **a ≈ 0.025 c**(固定开销占 8192 稳态的 ~2.5%)
- 原生:`(a' + 2.64c')/(a' + c') = 2.33` ⇒ **a' ≈ 0.233 c'**(固定开销占 ~23%)

把 8192 处原生的总时间归一为 1、我们的为 1.128:
`c' = 1/1.233 = 0.811, a' = 0.189`;`c = 1.128/1.025 = 1.100, a = 0.028`。
⇒ **稳态(去掉固定项)的吞吐差距 = c/c' = 1.100/0.811 ≈ 1.36×**。

**⚠️ 这是纯模型推断,不是证据。** 两个数据点拟合两个参数,自由度为 0,一定「拟合得上」。
它唯一的价值是给出一个**可证伪的预测**:成本对工作量应是**带正截距的直线**。
**检验方法**:再测 2~3 个 N(例如 10240、11776),把 t 对 N² 作图。
- 若是直线且截距为正 ⇒ 固定开销模型成立,且我们的稳态劣势比 25.8% 更大(约 36%),寄存器分块的收益上限也更大。
- 若不是直线 ⇒ 这条模型作废,回到波次量化 / 占用率解释。

本项目已经有一条相关的既有结论(09-04 的隔离台架):**GPU 冷频对「原生受影响更大」**。
这与 `a' ≫ a` 的方向一致,是这条假设最强的旁证 —— 但它仍然只是方向一致,不是定案。

### 5.3 「同样的 MMA 条数却更贵」的最可能落点

在 MMA 条数相同的前提下,差异只能来自**非 MMA 指令**。按本次调研,候选顺序:

1. **B fragment 的载入指令条数(= MMA 条数,比值 1:1)。** 这是最大的一块,也是唯一有业界共识解法的一块(§4)。
2. **`transpose_matrix = true` 的 `simdgroup_load`**(§4.4.1)。MLX 完全绕开了这条指令。
3. **Bsh 行 stride = 256 字节(2 的幂)导致的 bank 冲突**(§4.4.2)。
4. tint 生成的 MSL 相对手写 Metal 的多余 barrier / 多余地址计算 —— **本次调研范围之外,没查**。

---

## 6. llama.cpp 的 Metal GEMM

仓库 `ggml-org/llama.cpp`,pin 到 **SHA `49c0dc82b849344f945b14ab997386bd793369ae`**(master,2026-09-04)。
LICENSE(21 行标准 MIT 全文):`MIT License / Copyright (c) 2023-2026 The ggml authors` ⇒ **MIT,可商用**。

### 6.1 文件已经拆了

`ggml/src/ggml-metal/ggml-metal.metal` **已不存在**(PR #26561 / commit `b615f5b4bd99`,2026-08-24 按 op 拆分)。
GEMM 现在在 **`ggml/src/ggml-metal/kernels/mul_mm.metal`**(853 行),里面有两个 `kernel_mul_mm`:

| | 行号 | 条件 | 实现 |
|---|---|---|---|
| A | L13-141 | `#ifdef GGML_METAL_HAS_TENSOR` | Metal 4 `mpp::tensor_ops::matmul2d` |
| B | L145-358 | `#else` | 传统手写 `simdgroup_float8x8` |

`ggml-metal-device.m` L1127-1144 把 tensor 路径限定在 M5/M6/A19/A20,in-tree 注释原文:

> `// note: disable the tensor API by default for old chips because with the current implementation it is not useful`
> `// - M2 Ultra:   ~5% slower`
> `// - M4, M4 Max: no significant difference`

⇒ **M3 Pro 上跑的是 B。** 与 MLX §1.6 的分档结论完全一致。

### 6.2 传统内核的参数(已独立复核,不是转述)

我自己抓了同一 SHA 的 `mul_mm.metal` 逐行核对过下面每一条:

```
L163-166:  constexpr int NR0 = 64;   // BM
           constexpr int NR1 = 32;   // BN
           constexpr int NK  = 32;   // BK
L202-205:  S0_8x8 ma[4];             // 4 个 A fragment
           S1_8x8 mb[2];             // 2 个 B fragment
           simdgroup_float8x8 mc[8]; // ← 每 simdgroup 8 个 8×8 累加器(4×2)
L293-310:  FOR_UNROLL (short ik = 0; ik < NK/8; ik++) {
             simdgroup_barrier(mem_flags::mem_none);
             FOR_UNROLL (i<4) simdgroup_load(ma[i], lsma + 64*i, 8, 0, false);
             simdgroup_barrier(mem_flags::mem_none);
             FOR_UNROLL (i<2) simdgroup_load(mb[i], lsmb + 64*i, 8, 0, false);
             simdgroup_barrier(mem_flags::mem_none);
             FOR_UNROLL (i<8) simdgroup_multiply_accumulate(mc[i], mb[i/4], ma[i%4], mc[i]);
           }
L160-161:  sa = shmem;  sb = shmem + 4096;    // 4096 + 2048 = 6144 B,单缓冲
```

- 线程组 **128 线程 / 4 simdgroup**(`ggml-metal-device.cpp` L819 `nsg = 2*2`)
- 每 simdgroup 输出块 **32×16**,即 4(M) × 2(N) 个 8×8 = **8 个累加器 = 每 lane 16 个 f32 寄存器**
- **算术强度 = 8 MMA / 6 载入 = 1.33**;`mb[i/4]` 让每个 B fragment 摊到 4 次 MMA,`ma[i%4]` 让每个 A fragment 摊到 2 次
- threadgroup 内存 **6144 B**(边界检查时 8192 B),**没有 double buffering**
- 这套参数从 **2023-08-16 的原始提交 `bf83bff6742c`(PR #2615)** 到今天**一个字没改过**(当时叫 `BLOCK_SIZE_M/N/K` 和 `c_res[8]`)

### 6.3 两条能直接抄的布局技巧

1. **threadgroup 里按 fragment-major(8×8 块)存放**,不是按行主序。
   写入侧 L250 `*(sa + 64*ib + 8*ly + lx) = ...`、L279 `*(threadgroup S1_2x4 *)(sb + 64*ib + 8*ly) = ...`;
   读出侧 L296/L303 `simdgroup_load(ma[i], lsma + 64*i, 8, 0, false)` —— `elements_per_row = 8`,
   即**读一段连续的 64 个元素**,`transpose_matrix` 永远是 `false`,也不存在跨行大 stride。
   ⇒ **转置在写入 threadgroup 的时候一次性做掉,读的时候永远是最便宜的那种 load。**
   我们现在是反过来:按行主序存 Bsh(stride 128),每次读都付 `transpose=true`。
2. **`simdgroup_barrier(mem_flags::mem_none)` 夹在 A 载入 / B 载入 / MMA 三段之间** —— MLX 也一样
   (`mma.h` L521/525/529)。两个独立实现都这么写,说明这是 Apple GPU 上让编译器正确排流水的既定手法。
3. 顺带一提 L247 的 in-tree 吐槽:`// NOTE: this is massively slower.. WTF?` —— 被注释掉的是
   `sa[64*ib + 8*ly + lx] = ...`,留下的是 `*(sa + 64*ib + 8*ly + lx) = ...`。同一语义,数组下标写法「慢得离谱」。
   (**这是上游作者的一句无数字断言,不构成证据**,但和我们 `cur_ptr2.metal` / `cur_inplace.metal` 那组实验是同一类现象。)

### 6.4 带数字的性能证据

| 来源 | 机器 | 内容 | 数字 |
|---|---|---|---|
| PR #16634 comment 3490125571,`test-backend-ops -o MUL_MAT`,m=4096,n=512,k=14336 | **M4 Max** | 传统 64×32 内核的绝对吞吐 | bf16 **8.87–9.11 TFLOPS**、f16 8.95、mxfp4 8.83–8.91、q4_0 8.58–8.76、q8_0 8.31–8.46。同 shape n=1..8(走 mv)只有 **0.31–1.79 TFLOPS** |
| **PR #20962**(Apple Developer-Ecosystem-Engineering,merged `d1649047a33d`,2026-04-25) | **M5 Max 16"** | **tensor 路径分块 64×32 → 64×128,每线程累加器 16 → 64,并去掉 B 的 threadgroup staging** | pp512:DeepSeek-8B-f16 **+86.2%**、L2-7B-Q6_K +49.8%、TL-Q3_K_S +32.7%、G-2B-q8_0 +27.9%、TL-Q4_K_M +18.7%、TL-Q4_0 +6.1%;**Overall GeoMean +26.4%** |
| PR #16634 社区 A/B(`9fce24472` vs `5cca2542a`) | **M5** | tensor vs simdgroup 路径 | pp512:mistral-7B Q4_0 252.82→**608.05**(2.40×)、llama-3.1-8B Q4_0 257.25→609.26(2.37×)、gpt-oss-20B MXFP4 415.45→846.69(2.04×);tg128 基本不变 |
| PR #25377(**未 merge**) | **M4 Pro** | 反方向:小 batch 下 64×32 会把 N 维 zero-pad 掉 75%,改 64×8 | q4_0 4096×14336,bs=5 155.4→97.7 us/tok(1.59×)、bs=8 127.9→63.3(2.02×) |
| PR #27441(**未 merge**) | **M4 Max** | 32×16 tile + split-K | LFM2.5-2.6B F16 pp10 353→478、pp16 563→804、pp32 1138→1316 t/s |
| PR #3168(ggerganov,merged 2023-09-15) | M2 Ultra | **放宽走 mm 的条件**(不是改分块) | LLaMA-7B pp512:F16 1266.05→1490.07、Q8_0 1142.66→1325.69、Q4_0 1167.39→1355.56 t/s(≈+16%);tg128 ~1.00× |

**⚠️ 三条纪律提醒:**

1. **PR #20962 的 +26.4% 与 PR #16634 的 2.4× 不能相加。** 2.4× 主要来自 M5 的 Neural Accelerator 硬件;
   同一份 tensor 内核在 M2 Ultra 上反而 **慢 ~5%**、M4 无差异(§6.1 的 in-tree 注释)。
2. **PR #20962 是「更大分块 + 去 staging」两刀合一**,没有单变量拆分,不能直接归因给「累加器 16→64」。
   但它是我找到的**唯一**一条「加大寄存器分块在 Apple GPU 上值多少」的带数字证据,方向是正的(+26.4% GeoMean)。
3. **加大分块在 M 系列上不是无条件更快**:PR #25377/#27441 证明小 batch(N 维填不满)时**更小**的 tile 反而快 1.6–2.0×。
   对我们无所谓 —— 我们的 N = 8192~13312,永远填得满。

### 6.5 走 mm 还是 mv 的阈值

`ggml/src/ggml-metal/ggml-metal-common.cpp` L9-16:
`!transposed(a) && !transposed(b) && has_simdgroup_mm && ne00 >= 64 && ne11 > 8`
(MoE 版 L18-23 阈值是 `ne21 >= 32`)。`has_simdgroup_mm = supportsFamily:MTLGPUFamilyApple7`(`device.m` L1118)。
`kernels/mul_mv.metal`(3225 行)里 `simdgroup_multiply_accumulate` 出现 **0 次** —— 全靠 `simd_sum`。
所以 pp512 与 tg128 是两套完全无关的代码。

### 6.6 明确查不到

- **discussion 4167 里 M1/M2/M3/M3 Pro/M3 Max 的 pp512/tg128 原始表格 —— 没抓到。**
  唯一间接旁证是 ggerganov 在 #16634 里的一句「M3 10c → M4 10c 的 pp 提升约 20%」。
- **M3 Pro 的官方 FP16 理论峰值 —— 查不到可靠一手源**,所以不给「占峰值百分之多少」。
- **上游没有任何 PR/issue 讨论过「加大传统 simdgroup 内核(非 tensor 路径)的累加器数量」**
  (搜过 `simdgroup_float8x8 in:body` 0 命中、`"BLOCK_SIZE_M" in:body` 1 命中且无关)。这个方向上游没人试过。
- ⛔ **PR #13941「metal: optimize matrix multiplication kernel」声称 M1 Max pp512 437.30 → 5426.66 t/s(+1140%)。
  该 PR 已 closed、未合并(`merged: null`)。这个数字不可采信,不要引用。**

---

## 7. 第三方参照:`philipturner/metal-flash-attention`(Apple GPU 上 simdgroup_matrix 能到多高)

仓库 `philipturner/metal-flash-attention`,HEAD `8671cddc38f19a6eadb804dee6a3ca2954b8bf32`(2024-09-22)。
`LICENSE` = **MIT,Copyright (c) 2024 Philip Turner** ⇒ 可商用(专利 FTO 未查)。

README 里给出的 ALU 利用率(作者自测,**非独立复核**):

| 机器 | 前向 D=64 / 128 / 256 | 前向+反向 D=64 / 128 / 256 |
|---|---|---|
| M1 Max | 86% / 85% / 86% | 62–64% |
| **M3 世代** | **94% / 91% / 82%** | 71% / 69% / 61% |

roofline 口径:M1 Max 5308 GINSTRS(= 10616 GFLOPS)、M4 1790 GINSTRS(= 3580 GFLOPS);
M1 Max 实测「4400 gigainstructions per second(83% ALU utilization)」。

**对我们最有价值的一条推论(注意这是推论,不是原文断言)**:
作者把 roofline 定义成 **ALU 的 FMA 发射率**,而 simdgroup_matrix 内核在 M3 上能打到 **94%** ——
说明在 M1~M4 上 `simdgroup_matrix` 的吞吐**没有超过普通 FMA 管线的上限**,
即这些世代的 8×8×8 MMA 大概率就是编译器铺开成常规 FMA 序列,**没有独立的矩阵单元**。
这与 §1.6(MLX 的 NAX 路径要 gen≥17)、§6.1(llama.cpp 的 tensor 路径在 M2 Ultra 上更慢)三方互证。

**⚠️ 含义**:既然没有独立矩阵单元,那么「MMA 条数相同」就意味着「ALU 发射槽占用相同」,
我们比原生贵的那 12.8%/25.8% **只能**来自额外的非 MMA 指令(载入、地址计算、barrier),
而不可能来自「矩阵单元没喂饱」。这把问题域收窄了。

另有一条 README 提到的技巧:`simdgroup_async_copy`(A14 起,**未文档化**的硬件特性),
用来让全局→threadgroup 的搬运与计算重叠。MLX 和 llama.cpp 都没用它。**我们也没用。**
**查不到 Apple 对这个 API 的任何官方文档**,也查不到它在 M3 上的实测收益数字。

---

## 8. tinygrad / Apple 官方文档 / Asahi 占用率表

### 8.1 tinygrad(MIT,`Copyright (c) 2024, the tiny corp`,SHA `290aa54df54ccfdcaed470f084b728f1c423b30e`)

- `tinygrad/renderer/tc.py` L176-181:METAL 的 `TensorCore(dims=(8,8,8), threads=32, elements_per_thread=(2,2,2), ...)`。
  选中条件 `cstyle.py` L352:`arch.startswith("Apple") and int(arch[5:]) >= 7`。
  MSL 生成在 `cstyle.py` L382-393,每条 WMMA 只声明**一个** `simdgroup_float8x8 mat_c`。
- **但这只是硬件原语描述符,不是 tinygrad 的分块。** 寄存器分块在其上由优化器加:
  `tinygrad/codegen/opt/heuristic.py` L32 先 `apply_opt(Opt(OptOps.TC, ...))`,L40-43 再对 M、N 各尝试
  upcast 5/4/3/2 倍 ⇒ **默认启发式最高 5×5 = 25 个累加器/simdgroup**,BEAM 搜索空间更大。
- **tinygrad 自己手写的对标 Metal GEMM**:`extra/gemm/metal_matmul.py` L38-46
  ```metal
  simdgroup_float8x8 acc[4][4];   // 16 个累加器
  simdgroup_float8x8 A[4];
  simdgroup_float8x8 B[4];
  // 每 k 步:8 次 simdgroup_load,16 次 simdgroup_multiply_accumulate
  ```
  **每 simdgroup 16 个累加器,输出块 32×32,载入:MMA = 8:16 = 比值 2.0。**
- `extra/thunder/metal/`(ThunderMittens 的 Metal 移植)同样落在 32×32 / 16 个累加器
  (`gemm.py` L40 `matmul_naive<T, 4, 2, 4>`;`include/common/utils.metal` L31 `TILE_DIM{8}`)。

### 8.2 Apple 官方:规范里没有分块建议,MPP 指南里有

**《Metal Shading Language Specification》Version 4.1(文件内日期 2026-06-04,383 页)**

| 位置 | 内容 |
|---|---|
| §2.4, p.38 | SIMD-group Matrix Data Types:**"Cols and Rows are 8"**;必须在 uniform control flow 下执行;**"The mapping of matrix elements to threads in the SIMD-group is unspecified."** |
| §6.8, p.212-214 | Table 6.9 = `make_filled/load/store`,Table 6.10 = `multiply_accumulate/multiply/operator*`。`matrix_origin` 与 `transpose_matrix` **只给类型和默认值,没有任何语义或性能说明** |
| §6.8 开头 p.212 | 唯一一句性能取向的话:**"Instead of using simdgroup matrix multiplication, consider using Tensors"** —— 一句 *consider*,无数字无条件,**不能当性能结论** |

**全文 383 页 grep:`"register pressure"` 零命中。规范里没有任何 tile / 累加器数量 / 寄存器占用的建议。**

**WWDC / Tech Talk 逐条查过:**

| Session | 结论 |
|---|---|
| **Tech Talk 10858**(2020,*Discover Metal enhancements for A14 Bionic*) | simdgroup_matrix 的发布 session,Apple 唯一一份 simdgroup_matrix GEMM 代码片段:16×16 输出拆给 4 个 simdgroup,**"Each SIMD group will be responsible for computing one 8 by 8 quadrant"** ⇒ **每 simdgroup 恰好 1 个累加器** —— **和我们现在的写法一模一样。** ⚠️ 这是 Apple 的**入门 demo**,不是 Apple 的生产写法(生产写法见 §1 的 MLX = 16 个) |
| WWDC23 10050《Optimize machine learning for Metal apps》 | `simdgroup` 命中 **0 次**、`tile` **0 次**。**这里查不到分块建议** |
| WWDC22 10063 / WWDC25 205 / WWDC26 330 / WWDC25 262 / WWDC26 359 | 同样无 tile 数字 |
| **Tech Talk 111432**(2026,M5/A19 ML) | 定性:"The key to getting great performance is tiling";"increasing the SIMD group tile size can reduce traffic between cache levels";上界 **"if you go too large, you may start spilling registers, which hurts performance"** |

**《Metal Performance Primitives Programming Guide》Version 1,2026-03-16,13 页**
(`https://developer.apple.com/download/files/Metal-Performance-Primitives-Programming-Guide.pdf`,入口在 developer.apple.com/metal/resources/;framework 级 documentation 网页 **404,不存在**)

§2.3 "Key Optimizations for GEMM Kernels" 是**唯一给出数值建议的 Apple 官方文档**:

| 层级 | Apple 原话 | 章节 |
|---|---|---|
| Threadgroup tile | "On the M5 chip, a **2 x 2 tile of simdgroups** per threadgroup is a good starting point for 16-bit floating-point operands" | §2.3.1 |
| **Simdgroup tile** | **"On the M5 chip, SM == SN == 32 is a good starting point for 16-bit floating-point operands"** ⇒ 32×32 = **16 个 8×8 累加器** | §2.3.2 |
| K 分块 | "On the M5 chip, **BK == 128** is a good starting point" | §2.3.4 |
| Walk order | Morton ordering,"generally sufficient for good performance on the M5 chip" | §2.3.3 |
| 上界 | "Beyond a certain threshold, increasing simdgroup tile size **may reduce performance if operands are too large to fit in fast thread-local memory**" | §2.3.2 |
| 反 CUDA 传统的两条 | "Th[r]eadgroup memory staging isn't necessary for the most optimized GEMM kernels";"Kernels don't require any explicit software pipelining to overlap memory and compute operations" | §2.2 |

**⚠️ 三条纪律边界(必须带着看):**
1. 所有数字都带 **"On the M5 chip"** 前缀,前提是 **M5/A19 的 neural accelerator**。**不能直接外推到 M3 Pro 的 simdgroup_matrix 路径。**
2. Apple 自己说这只是起点:"start with generic heuristics … and augment with tuning as needed"。**没说 2×2 / 32 / 128 更快。**
3. §2.2 那两条(不用 threadgroup staging、不用软件流水)只对 M5 的 tensor 路径成立 —— MLX 自己在 simdgroup_matrix 路径上**就是**从 threadgroup 内存喂 A/B 的。

**Apple 的 documentation 网站上没有 simdgroup_matrix 的 GEMM sample**
(拉 `tutorials/data/index/metal` 索引 1.26 MB,grep `simdgroup` = **0 次**;阳性对照 `threadgroup` 448 次、`tensor` 437 次,**探针有效**)。
《Running inline ML operations in a shader with Metal 4》用的是 MPP TensorOps(`TileSize = 64` + `execution_simdgroups<4>` ⇒ 每 simdgroup 32×32),不是 simdgroup_matrix。
**⇒ Apple 唯一的一手 simdgroup_matrix 生产 GEMM 就是 MLX(§1)。**

### 8.3 Asahi / Mesa 的 AGX 占用率表 ← 决定我们能开到多大

Mesa main HEAD **`84cbbd2a2eef7f13368fc9a1db2c73b2afa41829`**,`src/asahi/compiler/agx_performance.c` L10-19:

```c
/* Table describing the relationship between registers pressure and thread
 * count. Each entry describes a maximum number of registers and the associated
 * best-case thread count. */
static const struct agx_occupancy occupancies[] = {
   {104, 1024}, {112, 896}, {128, 832}, {136, 768}, {144, 704},
   {160, 640},  {184, 576}, {208, 512}, {232, 448}, {256, 384},
};
```

**单位是 16 位半寄存器(halfregs)**,`AGX_NUM_REGS = 256`(`agx_compiler.h` L24)⇒ 每 lane 上限 **128 个 32 位寄存器**。

| halfregs | **32 位寄存器/lane** | 每核心并发线程 | 每核心 simdgroup |
|---|---|---|---|
| **≤ 104** | **≤ 52** | **1024** | 32 |
| 112 | 56 | 896 | 28 |
| 128 | 64 | 832 | 26 |
| 136 | 68 | 768 | 24 |
| 144 | 72 | 704 | 22 |
| 160 | 80 | 640 | 20 |
| **184** | **92** | **576** | 18 |
| 208 | 104 | 512 | 16 |
| 232 | 116 | 448 | 14 |
| 256 | 128 | 384 | 12 |

**另一条同样关键的约束**(`src/asahi/compiler/agx_register_allocate.c` L1327-1349):
compute shader 按 workgroup 大小**反查**寄存器上限 —— 注释原话
"Compute shaders need to have their entire workgroup together, so our register usage is bounded by the workgroup size"。
⇒ **512 线程的 workgroup ⇒ 每 lane 最多 208 halfregs = 104 个 32 位寄存器;
1024 线程的 workgroup ⇒ 最多 104 halfregs = 52 个 32 位寄存器。**

其它一手数字(Mesa `hk` Vulkan 驱动,同 SHA):
`subgroupSize = 32`(`hk_physical_device.c` L822)、`maxComputeWorkGroupInvocations = 1024`(L751)、
`maxComputeWorkgroupSubgroups = 1024/32 = 32`(L903)、`HK_MAX_SHARED_SIZE = 32 KiB`(`hk_private.h` L35)。

**⚠️ 这张表的可信度必须一起说。** 引入 commit `e7139838754e`(2023-04-07,Alyssa Rosenzweig)的原话:

> "This table is **derived from studying the maxTotalThreadsPerThreadgroup property in Metal while varying the register usage** …
>  **It's probably not 100% accurate and it hasn't been tested against hardware**, but it matters 'only' for performance (not correctness)"

即 **M1 时代从 Metal 侧黑盒反推、从未硬件验证**。定性可用,当精确模型不行。
博客(`alyssarosenzweig.ca/blog/asahi-gpu-part-3.html`,2021-04-18)补充:每线程 "256 registers (16-bits each)",
反推寄存器文件 ≈ **208 KiB / 核心**,并说 **"up until a threshold, it doesn't matter how many registers the program uses; occupancy is unaffected."**

**一条重要阴性结论(阳性对照已过)**:
`hk_physical_device.c` grep `cooperative|matrix` = **0**;`src/asahi/isa/AGX2.xml`(46 KB)grep `matrix|mma|wmma|tensor` = **0**。
⇒ **Mesa/Asahi 对 simdgroup_matrix 一无所知,这张表是通用 GPR 的表,不含任何矩阵单元建模。别当矩阵路径的模型读。**

---

## 9. 把占用率表套到我们的核上:寄存器预算的完整核算

单位换算:`simdgroup_matrix<half,8,8>` 每 lane 2 个 half = **2 halfregs**;
`simdgroup_matrix<float,8,8>` 每 lane 2 个 float = **4 halfregs**。
(依据:MLX `mma.h` L37 `kElemsPerFrag = (8*8)/32 = 2`;tinygrad `elements_per_thread=(2,2,2)` 独立印证。)

| 方案 | aFrag | acc | bF | 小计 | +寻址/循环(估) | **合计 halfregs(估)** | = 32 位寄存器 | 占用率档(每核心线程) | 512 线程 workgroup 的硬上限 208 halfregs |
|---|---|---|---|---|---|---|---|---|---|
| **现状**(Rm=1) | 16×2 = 32 | 1×4 = 4 | 2 | 38 | ~20 | **~58** | ~29 | **1024**(满档) | ✅ 远低于 |
| **R2**(Rm=2) | 32×2 = 64 | 2×4 = 8 | 2 | 74 | ~24 | **~98** | ~49 | **1024**(仍满档,门槛 104,余量仅 6) | ✅ |
| **R4**(Rm=4) | 64×2 = 128 | 4×4 = 16 | 2 | 146 | ~24 | **~170** | ~85 | 落入 {184 → **576**} 档 | ✅ 170 < 208,不会溢出 |

### 9.1 一个反直觉但很重要的结论:R4 的「掉占用率」很可能是免费的

我们现在的线程组内存是 **30 KiB**,而单个 threadgroup 的上限是 **32 KiB**
(Apple Feature Set Tables;Mesa `HK_MAX_SHARED_SIZE = 32*1024` 独立印证)。

**如果每个 GPU core 的线程组内存池就是 32 KiB**,那么:

- 现在每核心只能驻留 **1 个 workgroup = 512 线程**,而寄存器档位允许 **1024 线程**。
  ⇒ **我们现在有一半的线程槽是空的,而且空的原因是线程组内存,不是寄存器。**
- R4 把档位降到「每核心 576 线程」—— 但我们本来就只放得下 512 个。**512 ≤ 576 ⇒ 实际占用率一点没掉。**
- R4 同时把线程组内存从 30 KiB 降到 **24 KiB**(Bsh 8→2 KiB),离 16 KiB 还差得远,还是 1 个 workgroup。

**⚠️ 这条推论完全建立在「每核心线程组内存 = 32 KiB」这个未证实前提上**(见 §5.1:Apple 只公布了
「单个 threadgroup 最多 32 KB」,没公布每核心总量;而 Apple9 的 implicit imageblock 上限是 128 KB,
所以每核心池子**有可能更大**)。若每核心池子 ≥ 64 KiB,现在就是 2 个 workgroup / 1024 线程满档,
那 R4 会把每核心线程数从 1024 砍到 576(−44%),**得不偿失**。

### 9.2 一个零成本、零 GPU 负载的判据(强烈建议先做这个)

Alyssa 那张表**就是**用 `MTLComputePipelineState.maxTotalThreadsPerThreadgroup` 反推出来的
(commit `e7139838754e` 的原话:"derived from studying the maxTotalThreadsPerThreadgroup property in Metal
while varying the register usage")。

⇒ **把我们的 kernel 和手写 Metal 的 kernel 各编一个 pipeline,把 `maxTotalThreadsPerThreadgroup` 打印出来。**
这只需要编译 pipeline,**不发起任何 dispatch,不占 GPU**,和现在跑着的测量互不干扰。

它一次性回答三件事:

1. **两个核各自落在哪个寄存器档**(直接对照 §8.3 的表反查 halfregs)。
   如果手写 Metal 的 `maxTotalThreadsPerThreadgroup` 比我们高,说明 tint 生成的 MSL 寄存器压力更大 ——
   那就是 12.8%/25.8% 的一个直接候选原因,而且和「MMA 条数相同」不矛盾。
2. **R2 / R4 改完之后有没有跌档**(改前改后各打一次)。
3. **有没有发生 spill**(档位掉到远超预期的位置)。

### 9.3 四个独立来源全部落在「每 simdgroup 32×32 = 16 个累加器」

| 来源 | 每 simdgroup 输出块 | 累加器数 |
|---|---|---|
| MLX(Apple 自家生产实现)默认档 | 32×32 | **16** |
| MPP 编程指南 §2.3.2(Apple 官方唯一的数值建议) | SM=SN=**32** | **16** |
| tinygrad 手写对标 GEMM `extra/gemm/metal_matmul.py` | 32×32 | **16** |
| ThunderMittens Metal 移植 `extra/thunder/metal/gemm.py` L40 | 32×32 | **16** |
| Apple《Running inline ML operations in a shader with Metal 4》sample | 64×64 / 4 simdgroup = 32×32 | **16** |

而 **Apple 唯一写过「每 simdgroup 1 个累加器」的地方,是 2020 年 Tech Talk 10858 的入门 demo**
("Each SIMD group will be responsible for computing one 8 by 8 quadrant")。
MLX 里唯一用 1 个累加器的配置是 `matmul.cpp` L527-530 的 split-K 路径,条件是 **`M < 40 && N < 40`**。

> **我们现在的结构,是 Apple 的教学示例结构,不是任何人的生产结构。**

⚠️ 但注意:这五条都是「X 这么写」。**唯一带因果措辞的官方句子**是
MPP 指南 §2.3.2 的 "needs to be large enough to promote sufficient data reuse among threads within a simdgroup"
和 Tech Talk 111432 的 "if you go too large, you may start spilling registers" ——
**而这两条都锁在 M5 的 neural accelerator 路径上,不是 M3 的 simdgroup_matrix 路径。**
**「M3 上把分块从 1 提到 2/4 到底赢多少」,现有一手材料回答不了,只能自己在隔离台架上量。**

---

## 10. 收敛:该做什么,按顺序

| # | 动作 | 预期收益 | 风险 | 依据 |
|---|---|---|---|---|
| **0** | **编 pipeline 打印 `maxTotalThreadsPerThreadgroup`(我们 vs 手写 Metal)** | 不是收益,是**判据**:一次性定位寄存器档差异 | 零(只编译不 dispatch) | §9.2 |
| **1** | **Bsh 改成 fragment-major 布局(8×8 块连续存放),消掉 `transpose=true`** | 载入指令变便宜 + 消除 bank 冲突;llama.cpp 就是这么干的 | 极低:只改预取时的写入下标 + 载入时的 stride(128→8) | §6.3、§4.4 |
| **2** | **R2:workgroup 从 128 行 × 32 列 改成 256 行 × 16 列(线程数、simdgroup 数不变)** | **B fragment 载入指令数减半**(算术强度 1.0 → 2.0),线程组内存 −4 KiB | 中:归约段几何要改;寄存器 ~98 halfregs,离 104 门槛余量只有 6 | §4.3、§9 |
| **3** | 视 #0 的结果决定:**R4(512 行 × 8 列)** 或 **R2 + 1024 线程 workgroup** | 算术强度 → 4.0 / 或线程占用率翻倍 | 高:R4 会跌一档占用率(可能免费也可能不免费,取决于每核心线程组内存);1024 线程会把寄存器上限压到 52 个 32 位 | §9.1 |
| **4** | **加测 2~3 个规模点(如 10240、11776),把 t 对 N² 作图** | 判定「固定开销模型」成不成立,从而知道稳态差距到底是 25.8% 还是 ~36% | 零 | §5.2 |

**明确不推荐的**:

- ❌ 把 K 拆段以省 aFrag 寄存器 —— 已在 §4.3 用算术推翻,严格劣于 R2。
- ❌ 直接照抄 MPP 指南的 "SM=SN=32 / BK=128 / 2×2 simdgroups" —— 那些数字带 "On the M5 chip" 前缀,
  且前提是 neural accelerator 硬件。M3 上没有。
- ❌ 引用 llama.cpp PR #13941 的 "+1140%" —— 该 PR 已 closed 未合并,数字不可采信。
- ❌ 把 llama.cpp PR #20962 的 +26.4% 当成「加大分块在 M3 上的预期收益」—— 那是 M5 Max + tensor API,
  同一份内核在 M2 Ultra 上反而慢 5%、M4 无差异。

---

## 11. 明确查不到的

1. **M3 上 `simdgroup_matrix` 到底怎么落到硬件** —— Apple 无任何公开说明;Mesa/Asahi 的 AGX2.xml 里
   `matrix|mma|wmma|tensor` **0 命中**;只能靠三方旁证(MLX NAX 要 gen≥17、llama.cpp tensor 路径在 M4 及以下无收益、
   metal-flash-attention 在 M3 上 94% ALU 利用率)推断「M1~M4 没有独立矩阵单元」。**这是推断,不是官方事实。**
2. **`transpose_matrix = true` 的 `simdgroup_load` 比 `false` 慢多少** —— MSL 规范只给类型和默认值,没有任何性能说明;
   任何公开来源都没有数字。**必须自己量。**
3. **`simdgroup_async_copy`(A14 起)的官方文档** —— 不存在;它在 metal-flash-attention 里被称作
   "undocumented hardware feature"。在 M3 上的收益数字也查不到。
4. **每个 GPU core 的线程组内存池总量** —— Apple 只公布单 threadgroup 上限 32 KB。这直接决定 §9.1 的结论。
5. **M3 Pro 的官方 FP16/FP32 理论峰值** —— 查不到可靠一手源,所以本文不给「占峰值百分之多少」。
6. **llama.cpp discussion 4167 里 M1/M2/M3/M3 Pro/M3 Max 的 pp512/tg128 原始表格** —— 本轮没抓到。
   唯一间接旁证是 ggerganov 在 PR #16634 里的一句「M3 10c → M4 10c 的 pp 提升约 20%」。
7. **Apple 从未用过「多个累加器」这种措辞** —— 一律说 "simdgroup tile size (SM/SN)"。
   「SM=SN=32 ⇒ 16 个累加片」是我们的换算,不是 Apple 原话。
8. **MLX 为什么把 A/B fragment 也用 float(而不是 half)** —— 没有公开说明,也没有两者在 Apple GPU 上的吞吐对比数字。
9. **专利 FTO** —— 本文只核了 license(MLX / llama.cpp / tinygrad / metal-flash-attention **全部 MIT,已逐个读过 LICENSE 原文**)。
   **License 干净 ≠ 专利干净。GEMM 分块本身是 40 年的公开技术,但 FTO 没查。**

---

## 附:所有 pin 住的版本

| 对象 | 版本 |
|---|---|
| MLX | `b6368984b8e02a3fb3ee7986846c0fb85e1fccf7`(MIT,© 2023 Apple Inc.) |
| llama.cpp | `49c0dc82b849344f945b14ab997386bd793369ae`(MIT,© 2023-2026 The ggml authors) |
| tinygrad | `290aa54df54ccfdcaed470f084b728f1c423b30e`(MIT,© 2024 the tiny corp) |
| CUTLASS | `59e3a3338d516ca6ce0e073af8da65289678a35c` |
| metal-flash-attention | `8671cddc38f19a6eadb804dee6a3ca2954b8bf32`(MIT,© 2024 Philip Turner) |
| Mesa | `84cbbd2a2eef7f13368fc9a1db2c73b2afa41829` |
| MSL 规范 | Version 4.1,文件内日期 2026-06-04,383 页 |
| MPP 编程指南 | Version 1,2026-03-16,13 页 |
| Metal Feature Set Tables | 8 页,2026-09-04 抓取 |
| 本机 Metal 工具链 | `Apple metal version 32023.864 (metalfe-32023.864)` |
| 本机 GPU | `applegpu_g15s`(AGXG15S kext / AGXAcceleratorG15X),18 core,Apple9 家族 |
