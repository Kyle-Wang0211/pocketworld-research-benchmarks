# M3 Pro (AGX / Apple family 9) threadgroup 内存性能模型
### —— 一手来源 + 本机实测,以及对「扫描段 1.11ms」的机制定案

日期 2026-09-04 · 机器 Apple M3 Pro / 18 GPU 核 / macOS · 全程只在 Mac 上,未启动任何 iOS app、未连手机、未改系统设置。

**阳性对照**:`k.metal` 的 `formA` 在本文全部 8 轮台架里读数 3.870 / 3.871 / 3.872 / 3.873 / 3.874 / 3.876(规格 3.87 ± 0.02),括号 ≤ 0.05ms。机器状态健康,全部数据可用。
一处环境偏差已记录:开测时机器在**电池供电**(94%,低电量模式关),中途接上电源;`formA` 读数在前后两段无差异,故不影响结论。

---

## 0. 一页结论

| 问题 | 结论 |
|---|---|
| M3 有没有 bank? | **有,而且非常干净:32 bank × 8 字节 = 256 字节一"行"**。冲突度 `D = gcd(字节跨距, 256) / 8`,`D ≥ 4` 时**每多一路正好多 1 个周期**,拟合斜率 1.015、截距 0.1。无冲突地板 ≈ 1.45 周期/条 SIMD 局部 load。 |
| 这跟 M1 一样吗? | **不一样。M1 是 32 bank × 4 字节**(唯一一手实测:techboards 论坛 leman)。M3 的 bank **宽了一倍**。跨代结论不可迁移。 |
| 官方说过吗? | **一个字都没说过。** MSL Spec v4.1(383 页)、Feature Set Tables、MPP Guide、10 场 WWDC/Tech Talk 字幕逐字节 grep,`bank` 命中 **0**(阳性对照 `occupancy` 命中 52 次,`threadgroup` 大量命中)。Mesa asahi 树与 dougallj/applegpu 全仓 `bank`/`conflict`/`crossbar` 也是 **0**。 |
| 那 1.11ms 是 bank 冲突吗? | **不是。已被三把刀分别证伪。** 行方向扫描确实带 **4 路 bank 冲突**(实测 4.11 周期/条),但把 `accSh` 行距 32→33 打散冲突后,tint 版 −0.007ms、手写版 −0.004ms —— **在真核里这些 load 根本不在关键路径上**。 |
| 那是什么? | 见 §4:tail 差值 1.22ms 里,**0.67ms 已定位到 tint 的跨-SG 归约形态**(全 512 线程做 4 级 shuffle 蝶形 vs 手写只让 1 个 simdgroup 做且与预取重叠),其余 ~0.55ms 是扫描段的**比较/选择链与循环开销**,不是访存。 |
| 有能量到 bank 冲突的计数器吗? | **程序化路径不存在。** `MTLCommonCounter` 全 15 项**没有一个内存类**计数器。Xcode 里有 `Tile memory read/write` 的 limiter+utilization(Apple 原文:*"Tile memory ... is synonymous with threadgroup memory"*),但**只在 GUI**,且采集会强制 pass 串行化。全部官方文档 `sudo`/`entitle`/`privile` 命中 0 —— 未文档化任何特权要求。 |

---

## 1. 一手来源(问题 1、2、3、4、5)

### 1.1 threadgroup 内存 = tile 内存,同一块片上存储

Mesa `src/asahi/lib/agx_tilebuffer.h` L57:
```c
   /* USC word corresponding to this configuration of the tilebuffer */
   struct agx_usc_shared_packed usc;
```
tilebuffer 的字节预算被写进一个名叫 **`bytes_per_threadgroup`** 的字段(`src/asahi/lib/agx_tilebuffer.c` L155-176)。两者**互斥**,`src/asahi/lib/agx_usc.h` L44:
```c
   if (imageblock_stride) {
      assert(local_size == 0 && "we don't handle this interaction");
```
容量,`src/asahi/lib/agx_tilebuffer.c` L11:
```c
/* Maximum number of bytes per tile on G13G. */
#define MAX_BYTES_PER_TILE (32768 - 1)
```
与 GL `caps->max_local_size = 32768`(`src/gallium/drivers/asahi/agx_pipe.c` L1988)、Vulkan `HK_MAX_SHARED_SIZE (32 * 1024)`(`src/asahi/vulkan/hk_private.h` L35)一致。

Apple 侧独立印证 —— Metal Feature Set Tables(2026-05-21),`Maximum total threadgroup memory allocation`:**Apple7 / Apple8 / Apple9 全部 32 KB**,`Threadgroup memory length alignment` 全部 **16 B**。本机 `MTLDevice.maxThreadgroupMemoryLength` 实读 **32768** ✓。

Apple Tech Talk 111375(family 9 架构变更):
> *"The flexible on-chip memory feature extends this treatment to the rest of the shader core's memory types, such as threadgroup and tile memory, making that a cache too. And now that register, threadgroup, tile, stack, and buffer data are all cached on chip, this has allowed us to redesign the on-chip memories into fewer larger caches that service all these memory types."*

**这是 M3 与 M1 bank 结构不同的官方线索**:M3 起 threadgroup 内存被并进统一片上 cache,重新设计过。

### 1.2 ISA:局部访存是同步的,没有 scoreboard

Mesa `src/asahi/compiler/agx_opcodes.py` L279-297:`local_load`(`0b1101001`)、`local_store`(`0b0101001`),imms 只有 `[FORMAT, MASK]`。
对照 L276 的 `device_load`:`imms = [FORMAT, MASK, SHIFT, SCOREBOARD, COHERENT]`。

`src/asahi/compiler/agx_insert_waits.c` L15:
```c
static bool
instr_is_async(agx_instr *I)
{
   return agx_opcodes_info[I->op].immediates & AGX_IMMEDIATE_SCOREBOARD;
}
```
⇒ **局部 load/store 永远不会产生 `wait` 指令,它们是同步、按序的**。dougallj `applegpu.py` L5722 的注释同向:
> `# This is because threadgroup memory is fast and on-chip and so can be accessed in constant time`

⚠️ **"constant time" 这句是 G13/M1 时代的推断,不是测量,而且被本文 §2 的 M3 实测直接推翻**(同一条指令 1.45 → 32.6 周期)。

寻址:base 与 index **都可以是普通逐 lane 16 位 GPR**(`applegpu.py` L2192-2199 `ThreadgroupMemoryBaseDesc` / L1880 `ThreadgroupIndexDesc`;Mesa `agx_pack.c` L226-258)。⇒ **gather/scatter 是原生的,不要求 lane 合并**。宽度 1–4 分量(`applegpu.py` L2148:`if not 0 < len(regs) <= 4`),即每 lane 每条指令最多 128 bit。

### 1.3 屏障

- `threadgroup_barrier` = **2 字节、无操作数**指令 `0x68`(`applegpu.py` L5622;`AGX2.xml` L1430)。
- **simdgroup 屏障在 AGX 上是 no-op** —— `src/asahi/compiler/agx_compile.c` L1544:
```c
      /* Nothing to do for subgroup barriers */
      if (nir_intrinsic_execution_scope(instr) >= SCOPE_WORKGROUP) {
```
- **仅 shared 作用域的 memory barrier 什么都不发**(L1509-1542 的 mode 判断里没有 `nir_var_mem_shared`)。
- **执行屏障确实要排空未决访存,但是编译器插的**,`agx_insert_waits.c` L86-94:遇到 `THREADGROUP_BARRIER` 或 `MEMORY_BARRIER` 时,对每个非空 scoreboard slot 插 `wait`。由于局部访存**不占 slot**,`threadgroup_barrier` 对 threadgroup 内存**不产生任何排空代价**;它排空的是 device load/texture/stack。
- `wait` 的操作数**不是掩码**(修正提问里的前提):是 **1 bit 的 slot 号**,共 2 个 slot,每 slot 最多 8 条未决消息(`agx_insert_waits.c` L10 `#define AGX_MAX_PENDING (8)`、L56 `struct slot slots[2]`)。

MSL Spec v4.1 §6.10.1 p.216 对两种屏障的官方语义:
> *"A barrier function (threadgroup_barrier or simdgroup_barrier) acts as an execution and memory barrier."*
> *"On Apple silicon, a thread that has ended no longer participates or blocks remaining threads at a barrier."*

🔴 **`lockstep` 在 MSL Spec v4.1 中命中 0 次** —— 规范从不承诺 SIMD-group 内锁步。规范唯一的正面陈述在 §5.2.3.6 且是关于 SIMD-group **之间**的:*"SIMD-groups execute concurrently ... and make independent forward progress with respect to each other, in the absence of threadgroup barrier operations."*

WWDC20 10631 是 Apple 唯一一句关于屏障成本的话:
> *"For best performance you might want to rewrite your shaders with a 32 simdgroup size in mind to avoid threadgroup barriers as they are expensive."*

### 1.4 占用率(问题 2 后半)

Mesa `src/asahi/compiler/agx_performance.c` L10-19 —— **这是唯一权威的寄存器↔线程数表**:
```c
static const struct agx_occupancy occupancies[] = {
   {104, 1024}, {112, 896}, {128, 832}, {136, 768}, {144, 704},
   {160, 640},  {184, 576}, {208, 512}, {232, 448}, {256, 384},
};
```
读作 `{最大半寄存器数, 最大常驻线程数}`。`AGX_NUM_REGS = 256`(16 位寄存器)= 每线程最多 128 个 32 位 GPR。

**关键架构事实** —— `src/asahi/compiler/agx_register_allocate.c` L1328:
```c
   /* Compute shaders need to have their entire workgroup together, so our
    * register usage is bounded by the workgroup size. */
```
⇒ 整个 workgroup 必须同核常驻;workgroup 大小是寄存器数的**硬上限**,不是软偏好。

🔴 **threadgroup 内存对常驻 threadgroup 数的限制:Mesa 完全没有建模。**
`grep -E "local_size|shared_size" agx_register_allocate.c agx_performance.c agx_spill.c` → **0 命中**。物理上必然存在(32 KiB 池 ÷ 每 TG 字节数),但**无任何一手来源给出这个模型**。

Apple 侧只有定性说法,Tech Talk 10580:
> *"With a high thread-group memory usage, the only way to increase occupancy is to reduce the amount of shared memory used."*

以及 family 9 的根本变化,Tech Talk 111375:
> *"thanks to the Apple family 9 GPU's new dynamic shader core memory feature, the maximum register usage no longer dictates how many SIMDgroups can be run. ... your shader's occupancy will be impacted by how your shader's access threadgroup, tile, stack, and buffer memory in addition to its dynamic register usage."*

经验目标值,WWDC22 10159:
> *"For relatively complex kernels, 1K to 2K concurrent threads per shader core is considered a very good occupancy."*

**⇒ 我们这个核 30720 B / 32768 B,只能常驻 1 个 threadgroup = 512 线程/核,处在 Apple 建议值的下沿。** 这是全局背景条件,tint 与手写完全相同。

### 1.5 simdgroup_matrix(问题 3)

MSL Spec §2.4 p.38:引入于 Metal 2.3;类型只有 8×8;
> *"Operations on SIMD-group matrices are executed cooperatively by threads in the SIMD-group. Therefore, all operations must be executed only under uniform control-flow within the SIMD-group or the behavior is undefined."*
> *"The mapping of matrix elements to threads in the SIMD-group is unspecified."*

Table 6.9 的 `simdgroup_load` / `simdgroup_store` 对 `threadgroup T*` 与 `device T*` 两个重载**参数完全对称**,规范**没有任何关于 threadgroup 版更贵的说法**。

🔴 **规范 §6.8(v4.1 新增)反而在劝退**:
> *"Instead of using simdgroup matrix multiplication, consider using Tensors (section 2.22) and Metal Performance Primitives (section 7)."*

MPP Programming Guide §2.2 更直接:
> *"Theadgroup memory staging isn't necessary for the most optimized GEMM kernels. The on-chip memory hierarchy works best when you directly access device memory and allow the different levels of caching to work as designed."*

Mesa 对矩阵单元 **0 命中**(`grep -i matrix src/asahi` = 0);dougallj 有 `simd_matrix_fmadd16/32`(`applegpu.py` L4295-4331)但那是 **G13/M1** 的,且是纯寄存器 FMA、无内存操作数、无语义文档。**G16/M3/M4 的矩阵单元没有任何一手逆向资料。**
唯一的 M4 实测(arXiv 2606.12765,preprint,M4 Max 40 核):fp16 `matmul2d` 14.8 TFLOP/s = ALU roofline 的 46%,
> *"matmul2d executes entirely on the GPU shader cores with no dedicated matrix datapath"*

### 1.6 性能计数器(问题 5)

**`MTLCommonCounter` 全 15 项**:`timestamp` / `tessellationInputPatches` / `vertexInvocations` / `postTessellationVertexInvocations` / `clipperInvocations` / `clipperPrimitivesOut` / `fragmentInvocations` / `fragmentsPassed` / `computeKernelInvocations` / `totalCycles` / `vertexCycles` / `postTessellationVertexCycles` / `fragmentCycles` / `tessellationCycles` / `renderTargetWriteCycles`。计数器集只有 3 个(`timestamp` / `stageUtilization` / `statistic`),15 = 1+8+6,枚举闭合。

> **判决:比"没有 bank 计数器"更强 —— 15 个里连一个内存类计数器都没有(无带宽、无 cache、无 tile)。程序化拿 threadgroup 停顿数据,这条路在 API 层不存在。**

而且 `Sampling GPU data into counter sample buffers`:
> *"Each GPU vendor defines its own private data format for its counter sample buffers, which means your app can't read the contents of each buffer directly."*

**Xcode GUI 里才有的**(developer.apple.com/documentation/xcode/reducing-shader-bottlenecks,limiter/utilization 表):
| Counter | Limiter | Utilization | Apple 原文 |
|---|---|---|---|
| **Tile memory read** | Yes | Yes | *"Tile memory is local to the GPU and is synonymous with threadgroup memory and imageblock memory."* |
| **Tile memory write** | Yes | Yes | 同上 |

WWDC20 10603 确认命名:
> *"Tile Memory is referred to in the tools as Imageblock and Threadgroup Memory. ... typing "Imageblock" in Xcode will reveal all of the Tile Memory counters."*

逐行 Shader Profiler 的四类是 **ALU / Memory / Control flow / Synchronization**,最接近共享内存开销的逐行项是 `Synchronization (barrier)` 与 `Synchronization (atomics)`,**没有独立的 threadgroup memory 逐行类目**。

**需要 GUI 的**:逐行 profiling、heat maps(且 heat map *"don't support compute command encoders or compute pipeline states"*)、counter statistics(且采集时 *"only one pass runs at a time on the device"* —— 会污染我们的 GPU 毫秒口径)。
**需要 sudo 吗**:对 ~54 份官方文档 JSON + 10 份字幕 + MSL Spec 全量逐字节扫描,`sudo` / `privile` / `entitle` / `get-task-allow` / `administrator` **全部命中 0**(阳性对照 `counter` 命中 320 次、`capture` 208 次)。**只报"未文档化",不推断运行时行为。**
**命令行工具**:`gpucapture` / `gpudebug` / `metalperftrace` 是 macOS 27 / 下代 Xcode 的东西 —— **本机 Xcode 26.2 上三个二进制均不存在**(`xcrun --find` 与 `which` 都未命中)。落不了地。

---

## 2. 本机实测:M3 Pro 的 bank 结构(问题 1、2)

台架 `/private/tmp/mmaform/tgprobe2.metal` + `main_sw2.mm` → `bench_sw2`。
32 KiB threadgroup 数组;每 lane 每轮 8 条独立标量 float load;地址 `lane*stride + j*256 + base`,`base` 每轮变且带一个来自 buffer 的运行期 0(阻断 LICM/CSE);72 个 threadgroup × 512 线程;预热按累计 GPU 毫秒;p50 of 9。

周期换算按 1398 MHz;每核 SIMD 局部访存指令数 = 72×16×8×4096/18。

```
stride  gcd32 | LOAD ms  周期/条 | D=gcd(4·s,256)/8  预测
    1      1 |   2.171    1.45  |  0.5   (地板)
    2      2 |   3.465    2.31  |  1
    3      1 |   4.300    2.87  |  0.5
    4      4 |   3.842    2.56  |  2
    5      1 |   5.015    3.34  |  0.5
    6      2 |   4.242    2.83  |  1
    7      1 |   6.204    4.14  |  0.5
    8      8 |   6.173    4.11  |  4    ✓ 4.11
    9      1 |   6.553    4.37  |  0.5
   10      2 |   4.809    3.21  |  1
   12      4 |   4.563    3.04  |  2
   14      2 |   5.264    3.51  |  1
   16     16 |  12.171    8.11  |  8    ✓ 8.11
   17      1 |   5.327    3.55  |  0.5
   18      2 |   6.051    4.03  |  1
   20      4 |   5.881    3.92  |  2
   24      8 |   6.230    4.15  |  4    ✓ 4.15
   28      4 |   6.863    4.57  |  2
   31      1 |   5.785    3.86  |  0.5
   32     32 |  24.350   16.23  | 16    ✓ 16.23
   33      1 |   6.251    4.17  |  0.5
   34      2 |   5.459    3.64  |  1
   40      8 |   6.205    4.14  |  4    ✓ 4.14
   48     16 |  12.180    8.12  |  8    ✓ 8.12
   64     32 |  48.838   32.56  | 32    ✓ 32.56
   65      1 |  10.887    7.26  |  0.5
   96     32 |  24.335   16.22  | 16    ✓ 16.22
  128     32 |  49.815   33.21  | 32    ✓ 33.21
```

### 定案模型

**M3 Pro 的 threadgroup 内存 = 32 个 bank × 8 字节 = 一"行" 256 字节。**
bank 号 = `(字节地址 / 8) mod 32`。一条 32-lane 局部 load 的冲突度

```
D = gcd(逐 lane 字节跨距, 256) / 8
代价(周期/条 SIMD 指令) ≈ max(1.45, D)      对 D ≥ 4 精确成立
```

拟合 `D ∈ {4,8,16,32}` 四点:斜率 **1.015**,截距 **0.10** —— **每多一路正好多一个周期**。

**三对同足迹对照证明这是 bank 而不是 cache line / 事务数**:
- `gcd32=32` 的 stride 32(足迹 4 KiB)与 stride 96(足迹 12 KiB)→ 16.23 与 16.22,**足迹差 3 倍、代价完全相同**;
- stride 16(2 KiB)与 stride 48(6 KiB)→ 8.11 与 8.12;
- stride 16(8.11)与 stride 17(3.55)足迹几乎相同、代价差 2.3 倍。

**为什么是 8 字节而不是 M1 的 4 字节**:如果是 32×4B,`stride 64`(gcd(64,32)=32)与 `stride 32` 应当同价;实测 32.56 vs 16.23,**正好 2 倍**。只有 bank 宽 8 字节、"行"宽 256 字节才能同时解释 `{32,96}→16` 与 `{64,128}→32`。

**`D ≤ 2` 区间不服从这个模型**(1.45–4.6 周期,与足迹弱相关但不单调),我没有找到干净的解释,**不编模型**。

### 已知的与文献的冲突,必须说清楚
- **M1 是 32 bank × 4 B**(唯一一手实测:techboards.net/threads/4452,作者 leman,2023-12;三张图、代码从未公开;store-only 曲线在 gcd≥4 后精确减半 67→37→19→10)。同一位作者在 **M3** 上的 load-accumulate 曲线是**乱的**,原文:*"M3 instead is a hot mess. I don't understand anything. ... stride of 32 is really fast."*
  他的 M3 load 结果(stride 32 最快)与本文(stride 32 最慢 16.2 周期)**方向相反**。差异来源可能是:他的数组只有 1024 float(4 KiB,能整个进 cache)且地址带 `+ iteration` 位移;本文用 32 KiB、地址由 `lane*stride` 单独决定。**本文的读数括号 < 0.1%、8 个跨距点精确落在 D 上,我采信本文的;但这是 M3 Pro,base M3 未测。**
- **philipturner/metal-benchmarks 把 Apple 的 `Shared Banks` / `Shared Bank Size` / `Shared BW/Cycle` 三行全部标为 `TBD`** —— 业界最详细的 Apple GPU 微架构仓库,在这三格是空的。本文填的就是这三格(M3 Pro)。
- **threadgroup load 延迟(周期)在任何来源里都不存在**,包括 philipturner。Chips and Cheese 对 M2 Pro 只有一句相对陈述:*"M2 Pro's local memory takes slightly longer to access than the 8 KB L1 data cache."* —— 且他们的探针是**单 lane 指针追逐**(`if (get_local_id(0) == 0)`),结构上不可能观测到 bank 冲突。
- 🔴 调研中两次出现过 "M1 threadgroup 延迟约 5 周期"、"M2 Pro 约 8-10 周期" 的说法 —— **回源确认原文不存在,是二次摘要编造的。不要传播。**

### 本次实测的一个失败臂(必须记账)
store 臂(`kOp==1`)读数在全部 28 个跨距上恒为 0.276–0.284ms(= ALU 空循环),**被编译器整体 DCE 掉了**:写进 threadgroup 之后从未读回的存储是死存储。**本文因此没有 M3 的 store 侧 bank 数据。** 要补需要在循环里加一次读回或 barrier,但那会引入新变量。**没测到就是没测到,不外推。**

---

## 3. 把模型套回我们的核

`accSh` 是 128 行 × 32 列 float(行距 128 字节)。

| 访问 | 逐 lane 字节跨距 | D | 预测周期/条 |
|---|---|---|---|
| **行方向**:lane → 行 `sgid*8+lane>>2`,列 `(lane&3)*8+t` | 逐 lane 地址 = `32·lane` 字节 | `gcd(32,256)/8 = 4` | **4.11** |
| **列方向**:lane → 列 `lane`,行 `sgid*8+r` | **4 字节**(32 lane 连续) | `gcd(4,256)/8 = 0.5` | **1.45**(地板) |
| tint 的跨-SG 归约读 `cp[(lid%16)*32 + lid/16]` | 128 字节 | `gcd(128,256)/8 = 16` | **16.2** |
| 手写的跨-SG 归约读 `cp[sg*32 + lid]` | 4 字节 | 0.5 | **1.45** |

⚠️ 提问里说"列方向跨距 32 float = 128 字节 → 按 32 个 4 字节 bank 算无冲突"——**这里有一处口径错位**:那个 128 字节跨距是**同一 lane 在 8 次迭代之间**的跨距,不是 lane 之间的。**bank 冲突只看同一条指令内 32 个 lane 之间的地址关系。** 列方向的 32 个 lane 读的是连续 32 个 float,是**全核最好的模式**;真正带 4 路冲突的是**行方向**。

预测的扫描段总代价:每 SG 每 tile `8×4.11 + 8×1.45 = 44.5` 周期 → `44.5×16×256×64/18 = 6.48e5` 周期 = **0.46 ms**。实测 tint 扫描段 0.39ms、手写 0.27ms。量级吻合。

**但是**(见 §4)把行距改成 33 打散这个 4 路冲突,真核里 **一分钱都不省**。

---

## 4. 1.11ms 的机制:七把刀,五把证伪

台架 `/private/tmp/mmaform/main_{knife,bisect,fact,store,hm,nat,base,acc}.mm`。全部镜像交替、预热按累计 GPU 毫秒 ≥300ms、p50 of 21~41、每轮带 `formA` 阳性对照。

### 4.1 基线拆分(同一轮内测得)

| | tint (`cur`) | 手写 (`native2`) |
|---|---|---|
| MMA + 预取 + barrier | **4.129** | **4.288** ← tint 快 0.16 |
| 完整主核 | **5.620** | **4.554** |
| **tail(扫描+归约+其余)** | **1.49** | **0.27** ← 差 **1.22 ms** |

tint 的 tail 逐项(2×2 因子表,全部保留 cp 写以免 DCE 污染):

| 变体 | p50 | 归因 |
|---|---|---|
| `cur` 全核 | 5.620 | — |
| `cur_norow`(删行扫描) | 5.381 | 行扫描 **0.24** |
| `cur_nocol`(删列扫描) | 5.443 | 列扫描 **0.18** |
| `cur_norowcol`(两扫描都删) | 5.231 | 两扫描 **0.39**(**可加,不是超加性**) |
| `cur_nomerge`(删跨-SG 归约) | 4.947 | 归约 **0.67** |
| `cur_mma` | 4.129 | 其余 ~0.43 |

手写侧:`nat_norowcol` p10 = 4.258 ≈ `native_mma` p10 = 4.276 ⇒ **手写的 cp 写 + 跨-SG 归约在关键路径上几乎为零**,它的 0.27ms tail 基本全是两个扫描。

### 4.2 已证伪的候选(五把刀,全部单变量)

| # | 假说 | 刀 | 结果 | 判决 |
|---|---|---|---|---|
| 1 | tint 归约的 16 路 bank 冲突是主因 | `cp` 数组行距 32→33(读地址从 16 路冲突变 1~2 路),其余逐字不动 | 5.611 → **5.597**(−0.014) | **证伪** |
| 2 | 行扫描的 4 路 bank 冲突是主因 | `accSh` 行距 32→33(含 `simdgroup_store` 的 `elements_per_row`),tint 与手写各做一份 | tint 5.643→**5.636**;手写 4.544→**4.689**(p10 4.524→4.520) | **证伪**(两边都是 0) |
| 3 | `threadgroup_barrier` vs `simdgroup_barrier` | 把 accSh 后那道屏障换成 simdgroup 作用域(accSh 本就是 per-SG,合法) | 5.611 → **5.524**(−0.087) | **量级不够**(且 Mesa 证明 simdgroup 屏障在 AGX 上是 no-op) |
| 4 | 寄存器压力 / 溢出 | 去掉 `[[max_total_threads_per_threadgroup(512)]]` | `maxTotalThreads` 512→**1024**,耗时 5.602→**5.596** | **证伪**(寄存器够放 1024 线程,没有溢出,也不是杠杆) |
| 5 | threadgroup store 本身贵 | 两核各加 3 条冗余 threadgroup store(写到归约确实会读的另一 SG 槽位,防 DCE) | tint +0.04;手写 +0.10 | **证伪**(store 便宜) |

> 🔴 **一次自我推翻,必须记账**:我先用 `cur_norowcol`(5.231)减 `cur_noscan`(4.346)得出"3 条 threadgroup store 值 0.885ms"。第 5 把刀反向加 3 条 store 只花 0.04ms,**不对称说明前一个差值不是 store**。查 AIR 确认:`cur_noscan` 删掉 cp 写之后,归约的 3 条 load 变成**循环不变量被 LICM 整体提到 256 次循环外**了。**删代码测归因,随时会连带删掉别的东西 —— 必须用"加"做反向对照。**
> 手写侧 `nat_noscan` 更彻底:cp 数组是函数内局部 `threadgroup` 声明,编译器能证明"从未写入",于是把**整个归约连同它的 device 写全部 DCE**(AIR 里 `addrspace(3)` load 数 8→**0**)。该变体作废。

### 4.3 还站着的候选

**候选 A(已定位 0.67ms,机制清楚)—— tint 的跨-SG 归约形态。**
- tint:barrier 之后 **全部 512 线程**都参与,每 lane 3 条 threadgroup load + **12 条 `simd_shuffle_xor`** + 4 轮比较/选择 ≈ 35 条指令。按 SIMD 指令算 `35×16 SG×256 tile×64 TG/18 核 ≈ 5.1e5` 周期 = **0.36ms @1 IPC**,实测 0.67 ⇒ 平均 ~2 周期/条(shuffle 大概率 2 周期)。**这是纯指令条数,不是访存。**
- 手写:`if (lid < 32)` —— **只有 1/16 的机器**做一个 15 步串行归约,其余 480 线程直接冲进下一 tile 的 **device** 预取,只在下一道 barrier 才汇合。归约躲在 device load 延迟后面,critical path 贡献 ≈ 0。

**⚠️ 但把手写形态移植进 tint 反而更慢**:`cur_hmerge` = **6.495**(+0.87)。所以"少线程 + 重叠"这个形态**不是可移植的赢法** —— 在 tint 的上下文里,SG0 那条 15 步**串行依赖**的 threadgroup load 链没有被预取盖住,反而让另外 15 个 SG 在下一道 barrier 上干等。**这一条是本次唯一没解释掉的现象。**

**候选 B(~0.55ms,机制未定)—— 扫描段的比较/选择链与循环形态,不是访存。**
证据:刀 2 把行方向的 4 路 bank 冲突完全打散,零收益 ⇒ 那 0.39ms 里访存不占份额。剩下的只能是 top-2 更新的分支/选择链、`while(true)+break` 的循环形态、以及索引算术。这条**没有单独称量过**。

### 4.4 一小时内可做的下一步(每条都是单变量)

| 要证伪什么 | 怎么做 | 判据 |
|---|---|---|
| 候选 A:归约是不是纯指令条数 | 把 tint 的 4 级蝶形从 3 个值(best/second/idx)压成 2 个值(把 idx 打包进 best 的低位),shuffle 从 12 条降到 8 条 | 若归约代价按 12→8 线性下降(0.67→~0.45),定案为指令条数;否则另有他因 |
| `cur_hmerge` 为什么反而慢 | 在 `cur_hmerge` 里把 SG0 的 15 步串行链改成 4 级 shuffle 树(仍只 1 个 SG 跑) | 若回到 ~5.0,则是**串行依赖链的 threadgroup load 延迟**,可顺带反推出 M3 的局部 load 延迟周期数(用 15 步链长反解) |
| 候选 B:扫描段代价是不是比较链 | 把 top-2 的 `if/else` 换成无分支 `max`/`select` 三连,访存一字不动 | 若 0.39→~0.2,定案 ALU;若不变,回头查循环形态 |
| M3 局部 load **延迟**(全网空白) | 在 `tgprobe2` 上加一条 mode:`idx = as_type<uint>(v) & 0` 造纯串行依赖链,单 SG,单 threadgroup | 直接读出周期数,填上 philipturner 的 `TBD` |
| store 侧 bank(本次 DCE 作废) | store 后在循环末尾加一次 `acc += lds[pre[0]+base]` 读回 | 阳性对照:load 臂读数必须与本文一致才认 |
| 占用率是不是全局天花板 | 把 threadgroup 内存砍到 ≤16 KiB(缩 `accSh` 到 8 行/SG,分两轮),让 2 个 TG 常驻 | 若 tint 与手写**同比例**改善,说明是共同天花板,与 1.22ms 的差无关 |

---

## 5. 我查不到的,以及为什么

| 项 | 状态 | 原因 |
|---|---|---|
| **Apple 官方的 bank 结构 / 冲突规则** | **不存在** | 逐字节 grep,`bank` 在 MSL Spec / Feature Set Tables / MPP Guide / 10 场 WWDC 字幕命中 0(阳性对照通过)。Apple 给的替代说法是 quad group(4 线程)邻接:*"Reorder your memory access patterns so that neighboring threads in a quad group write (or read) to neighboring elements in threadgroup memory."* 🔴 **"没提" ≠ "不存在",本文 §2 证明它存在。** 另:developer.apple.com 上唯一的 "bank conflict" 命中是论坛帖(thread/662809,作者 `mattke`,社区成员非 Apple 员工),**两次 WebSearch 摘要把它包装成"苹果说的",已回源证伪。** |
| **AGX ISA 层的 bank / crossbar** | **不存在** | Mesa asahi 树全仓 `bank|conflict|crossbar` 唯一命中是 `agx_compiler.h:419` 的 IR 字段注释;applegpu 全仓 0 相关命中,生成的 345 KB `docs.html` 里 `bank` 出现 **0** 次。逆向工程界从没做过这个结构。 |
| **threadgroup 内存对常驻 threadgroup 数的限制模型** | **无一手来源** | Mesa 的占用率模型只是寄存器数的函数,`local_size`/`shared_size` 在 RA/performance/spill 三个文件里 0 命中。物理上必然存在,但没人建过模。 |
| **threadgroup load 延迟(周期)** | **全网空白** | philipturner 标 TBD;Chips & Cheese 只有相对陈述且探针是单 lane;arXiv 2603.27569 的 "~2-4 周期" 在架构叙述段不在实测表里,仓库里也没有对应 kernel。**本次没测,§4.4 给了做法。** |
| **`threadgroup_barrier` 的周期成本** | **无人直接测过** | 唯一数字来自 arXiv 2603.27569 的 "~2 cycles",我核了它公开的全部 11 个 kernel,**没有一个单独测 barrier**;支撑实验同时变了 barrier 数和访问模式,是混杂的。**当作未知。** |
| **G16 / M3 / M4 的矩阵单元** | **无一手逆向** | Mesa 芯片枚举止于 `AGX_CHIP_G14X`;AsahiLinux docs 里 M3 GPU 标 `WIP`、M4 标 `TBA`;dougallj 的 `simd_matrix_fmadd16/32` 是 G13/M1 的。 |
| **M3 store 侧 bank 行为** | **本次台架失败** | 死存储被 DCE。见 §2 末。 |
| **M2 (G14) / M4 (G16) 的 bank 结构** | **零数据** | 不要从 M1 或 M3 外推 —— M1(32×4B)与 M3(32×8B)已经证明 Apple 在这层改过。 |
| **arXiv 2603.27569 的 threadgroup 带宽数字** | **不采信** | 它的 "sequential" kernel 是 `shared[tid*32+i]`,即满 32 路冲突;"strided" 是 `shared[tid + i*threads]`,即无冲突 —— **标签反了**。且它测的 SIMD shuffle 带宽比 philipturner 实测低 10 倍,说明没饱和硬件。 |

---

## 6. 台架与产物

全部新建,**未改动或覆盖任何既有文件**:
- `tgprobe.metal` / `main_tg.mm` → `bench_tg`(首轮跨距扫描 + 归约模式对照)
- `tgprobe2.metal` / `main_sw2.mm` → `bench_sw2`(**28 点密扫,§2 的定案数据**)
- `cur_pad33 / cur_sgb / cur_both / cur_norow / cur_nocol / cur_norowcol / cur_noattr / cur_add3 / cur_hmerge / cur_acc33 .metal`
- `nat_norow / nat_nocol / nat_norowcol / nat_add3 / nat_acc33 .metal`
- `main_knife.mm main_bisect.mm main_fact.mm main_store.mm main_hm.mm main_nat.mm main_base.mm main_acc.mm` 及对应 `bench_*`

AIR 结构核对用 `xcrun metal -std=metal3.1 -O2 -S -emit-llvm`,每个变体都核过 `multiply_accumulate` / `simdgroup_matrix_8x8_store` / `addrspace(3)` load/store 条数,确认没有被 DCE 污染(§4.2 的两个反例就是这样抓到的)。
