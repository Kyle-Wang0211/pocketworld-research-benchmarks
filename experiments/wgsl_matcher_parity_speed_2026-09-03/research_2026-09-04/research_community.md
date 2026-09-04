# WGSL/tint vs 手写 Metal 的分段差距 —— 多语言社区检索 + 产物取证

检索日期 2026-09-04。机器 Apple M3 Pro,Xcode SDK `MacOSX26.2.sdk`。
本文只读 `/private/tmp/mmaform/` 的既有文件,新写的探针一律放 scratchpad。

**与同目录另两份报告的分工**(避免重复,交叉引用):
- `research_tint_codegen.md` —— tint MSL 后端代码生成、robustness/toggle、指针别名/`restrict`、AIR 层别名丢失。
  它已经查明「robustness 你已经关掉了」,与本文 §0.5 的产物取证互相印证。
- `research_topk_epilogue.md` —— **你问题里的第 3 条(GEMM 之后如何不落 threadgroup 做归约)已在那份里穷举回答**
  (CUDA `mma.sync` 布局是规范承诺 / WMMA opaque / Vulkan KHR 基线不能而 `EXT_cooperative_matrix_maintenance1` 补上 /
  WGSL 明文禁止 / Metal `thread_elements()` 未文档化但 MLX 生产在用)。**本文不重复。**
- **本文的独有贡献**:
  1. 多语言社区扫描(中/日/俄/英,含完整零命中清单);
  2. 带数字的同类测量 8 条,其中 §1.9 是**目前最贴题的一条**(M2 上同一 WGSL、只换归约方式,1.29×);
  3. **两个所有现存探针都没切过的跨臂变量**:`#pragma METAL fp math_mode(relaxed)`(§M1)
     与 **WGSL 没有 subgroup barrier ⇒ 只能付全 threadgroup 同步**(§M1b)。

谜题复述:

```
                    tint 生成    手写 Metal
MMA + 预取 + barrier   4.133      4.330    ← 生成的反而更快
完整主核               5.649      4.544    ← 加上「扫描段」后反超 1.11ms(24%)
```

---

## 0. 先说结论:两侧不是单变量对照

在做任何机制推断之前,我从你自己的产物里查到**三个未受控的源码级变量**,三个都只出现在 tint 一侧:

| 变量 | tint 侧 (`cur*.metal`) | 手写侧 (`native*.metal`, `k.metal`) | 谁在查 |
|---|---|---|---|
| `#pragma METAL fp math_mode(relaxed)` | **有**(全部 20 个文件第 1 行) | **无**(全部 native 文件) | **无人**(§M1) |
| `[[max_total_threads_per_threadgroup(512)]]` | **有** | **无** | `v3_nomaxtt.metal` 已在做 |
| barrier 作用域:`simdgroup_barrier` | **0 次**(只能发 `threadgroup_barrier` ×5) | **3 次**(+ `threadgroup_barrier` ×3) | `cur_sgb.metal` 只换了 1/5(§M1b) |

证据(只读 grep):

```
cur.metal:1          #pragma METAL fp math_mode(relaxed)
cur.metal:371        [[max_total_threads_per_threadgroup(512)]]
native2.metal:1      #include <metal_stdlib>          ← 无 pragma
native_scan2.metal   grep max_total_threads_per_threadgroup → 0 命中
```

两侧的 `MTLCompileOptions` 都是 `[MTLCompileOptions new]`(`main20~25.mm` 第 21/26/29/39/45 行),
所以差异**完全来自源码内的 pragma / 属性**。

### 0.1 这台机器上 `[MTLCompileOptions new]` 的默认是 Fast(实测)

我写了一个探针(scratchpad,不碰 mmaform),在这台 M3 Pro 上跑:

```
default mathMode enum = 2 (0=Safe 1=Relaxed 2=Fast)
default languageVersion = 0x40000        (MSL 4.0)
macros bitfield = 3 (bit0=__FAST_MATH__, bit1=__FINITE_MATH_ONLY__)
```

即:**手写 Metal 编译在 `MTLMathModeFast`,`__FINITE_MATH_ONLY__=1`;tint 侧被 pragma 钉在 `relaxed`。**

一手依据(Apple 自家头文件,本机 SDK,`MTLLibrary.h` 第 254–272 行):

> `@constant MTLMathModeSafe` Disables unsafe floating-point optimizations
> `@constant MTLMathModeRelaxed` Allows aggressive, unsafe floating-point optimizations **but preserves infs and nans**
> `@constant MTLMathModeFast` Allows aggressive, unsafe floating-point optimizations

`/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.2.sdk/System/Library/Frameworks/Metal.framework/Headers/MTLLibrary.h`

### 0.2 这个 pragma 是 Dawn 无条件加的,不是 tint 生成的,而且**压过编译选项**

一手源码(我 curl 下来 base64 解码,`src/dawn/native/metal/ShaderModuleMTL.mm` 第 460–479 行):

```cpp
// Metal supports math_mode as both compiler option and as a pragma. We add the
// math_mode here as a string conditional on OSx version as the compiler option only
// exists for MacOS after 15. See the Metal 4 spec for more information.
// Note: this math_mode takes precedence over global flags provide to the compiler
// (including the deprecated fastMathEnabled compiler option).
std::string math_mode_heading;
if (@available(macOS 15.0, iOS 18.0, *)) {
    math_mode_heading = "\n#pragma METAL fp math_mode(";
    math_mode_heading += r.useStrictMath ? "safe" : "relaxed";
    math_mode_heading += +")\n";
}
```

<https://dawn.googlesource.com/dawn/+/refs/heads/main/src/dawn/native/metal/ShaderModuleMTL.mm>

三点要害:

1. `useStrictMath` 来自 `wgpu::ShaderModuleCompilationOptions.strictMath`,默认 false ⇒ **走 `relaxed` 分支**。
2. Dawn **永远不会发 `fast`**——最好的情况就是 `relaxed`。这是策略,不是 bug。
3. 注释自己说「takes precedence over global flags」⇒ 你在 `MTLCompileOptions` 里设 `mathMode = Fast` **也压不住**,唯一办法是从 MSL 文本里把这一行删掉。

同文件第 564 行还有:`(*compileOptions).fastMathEnabled = !GetStrictMath().value_or(false);`
——即 Dawn 同时把已废弃的 `fastMathEnabled` 设成 true,但被 pragma 覆盖。

**★ 而 WGSL 规范其实是允许 `fast` 的 —— Dawn 比规范要求得更严。**

W3C WGSL §15.7.2 "Finite Math Assumption"(我 curl 抓 <https://www.w3.org/TR/WGSL/> 全文核对):

> "**Implementations may assume that overflow, infinities, and NaNs are not present during shader execution.**
> In such an implementation, if the intermediate result of evaluating a runtime expression overflows, or yields
> an infinity or a NaN, the final result will be an indeterminate value of the target type."
> "Note: **This means some functions (e.g. min and max) may not return the expected result** due to optimizations
> about the presence of NaNs and infinities."

规范原话就点名了 `min`/`max` —— 正是 top-2 归约里用的那两个。
⇒ **把 pragma 从 `relaxed` 改成 `fast` 不违反 WGSL 规范。**
Dawn 选 `relaxed` 是保守的实现决定(可能为了跨后端结果一致性),不是规范约束。
如果 E1 证实这就是 1.11ms 的来源,这是一条可以直接向 Dawn 提的 issue,也是你自建 Dawn TU 上一行就能改的补丁。

### 0.3 pragma 确实改变了 IR(实测,非推断)

把 `native_scan2.metal` 原样和加一行 pragma 的副本各编一遍(scratchpad,原文件未动):

```
$ xcrun metal -std=metal3.2 -S -o a.ll a_fast.metal        # 无 pragma
$ xcrun metal -std=metal3.2 -S -o b.ll b_relaxed.metal     # 有 pragma
$ diff a.ll b.ll
<   %278 = fcmp fast ogt float %277, 0x3D71979980000000
---
>   %278 = fcmp reassoc nsz arcp contract afn ogt float %277, 0x3D71979980000000
```

LLVM 的 `fast` = `nnan ninf nsz arcp contract reassoc afn`。
**relaxed 版少了 `nnan` 和 `ninf`**,即后端必须假设操作数可能是 NaN/Inf。

**这正好只打扫描段,不打 MMA 段**:扫描段是 `if (d > pb) {...} else if (d > ps) {...}` 的有序比较链 + `max()`;
MMA 段几乎没有标量浮点比较,`simdgroup_multiply_accumulate` 是内建指令,不受 fp 语义影响。
**这和「MMA 持平 / 扫描段慢 24%」的形状完全对上。**

诚实边界:我只证明了 **AIR 层的 flag 不同**;没证明 AGX 后端最终 ISA 不同(Apple 不公开反汇编器)。
最后一公里必须靠运行时 A/B(见 §3 实验 E1)。

### 0.4 `max_total_threads_per_threadgroup(512)` 大概率是空变量(实测)

我用 `MTLComputePipelineState` 探了两侧的寄存器预算(scratchpad):

```
device=Apple M3 Pro
cur (带属性)              maxTotalThreads=512   execWidth=32  staticTGmem=0
cur (删掉属性)            maxTotalThreads=1024  execWidth=32  staticTGmem=0
cur_noscan (删掉属性)     maxTotalThreads=1024
cur_mma    (删掉属性)     maxTotalThreads=1024
pw_match_gemm2 (原生)     maxTotalThreads=1024  execWidth=32  staticTGmem=30720
pw_match_gemm2_mma        maxTotalThreads=1024                staticTGmem=24576
pw_match_gemm2_scan2      maxTotalThreads=1024                staticTGmem=30720
```

**两侧的完整核在不加属性时都能装下 1024 线程的寄存器 ⇒ 都没到寄存器墙,也不会 spill。**
所以这个属性不太可能是 1.11ms 的来源。仍建议做一次 5 分钟对拍把它划掉(§3 实验 E2)。

Apple 一手口径(Tech Talk 10580《Metal Compute on MacBook Pro》逐字):

> "There is scope for the compiler to spill registers more efficiently when the maximum thread count in a thread group is known at pipeline state creation time. These optimizations can be enabled by setting either maxThreadsPerThreadgroup on the compute pipeline state descriptor or by using the Metal Shader langauge max_total_threads_per threadgroup attribute directly in your kernel source."

<https://developer.apple.com/videos/play/tech-talks/10580/>

### 0.5 两条「WebGPU 税」的常见嫌疑人,被你手上的产物直接洗清

社区里最常被点名的两条 tint 开销,在 `cur.metal` 这份具体产物里**根本不存在**:

| 嫌疑人 | 社区依据 | 在 `cur.metal` 里的实况 |
|---|---|---|
| robustness 越界钳制(workgroup 地址空间无条件 clamp) | `src/tint/lang/core/ir/transform/robustness.cc` 的 `ShouldClamp()` 对 `kWorkgroup` 直接 `return true`,`RobustnessConfig` 里连 `clamp_workgroup` 字段都没有 | **零命中**。对 `tint_member_17/18/19/20`(那四个 workgroup 数组)的 14 处访问,`min(`/`clamp(` 一个都没有;全文件仅有的两个 `min(` 在第 64/65 行、是 `acos(min(x,1.0f))` 的数学钳位 |
| workgroup 内存零初始化(WebGPU 规范要求,Metal 无原生设施 ⇒ tint 在入口生成清零循环 + barrier) | W3C WebGPU §security-shader:"If the native API does not provide facilities to clear it, the WebGPU implementation transforms the compute shader to first do a clear across all invocations, synchronize them, and continue executing developer's code." | **零命中**。`kernel void cur`(第 372–375 行)只有一个 `tint_struct` 构造 + 一次 `v_14(...)` 调用,没有任何清零循环、没有入口 barrier |

（robustness.cc / robustness.h：<https://dawn.googlesource.com/dawn/+/refs/heads/main/src/tint/lang/core/ir/transform/robustness.cc>；
W3C：<https://www.w3.org/TR/webgpu/#security-shader>）

⇒ 你这份 MSL 要么是在 `disable_robustness` / `disable_workgroup_init` 打开的配置下导出的,
要么整数范围分析把 clamp 全证掉了。**不管哪种,这两条都不能拿来解释 1.11ms。**
（Dawn 侧开关:`enable_integer_range_analysis_in_robustness`、`disable_workgroup_init`,见
<https://dawn.googlesource.com/dawn/+/refs/heads/main/src/dawn/native/Toggles.cpp>）

### 0.6 tint 侧真正剩下的结构差异

逐字对照 `cur.metal` 与 `native2.metal`,除了上面两个变量,还剩三条形态差异:

1. **workgroup 数组全部合并进一个 struct、经指针参数访问。**
   ```cpp
   // cur.metal:38-49, 372-373
   struct tint_struct {                       // 按值传进每个函数
     threadgroup tint_array<half, 4096>*  tint_member_16;
     threadgroup tint_array<float, 4096>* tint_member_17;   // ← 扫描的 128×32
     threadgroup tint_array<float, 512>*  tint_member_18;
     ...
   };
   kernel void cur(..., threadgroup tint_struct_4* v_103 [[threadgroup(0)]]) {
     tint_struct const v_104 = tint_struct{ .tint_member_17=(&(*v_103).tint_member_24), ... };
   ```
   每次扫描访问写成 `(*v_19.tint_member_17)[(v_56 + v_58)]`。
   手写侧是 kernel 内的静态数组 + 一次性提出来的裸指针:
   ```cpp
   // native2.metal:88, 177-178
   threadgroup float accSG[kSG * 8u * kBN];
   threadgroup const float* accRow = accSG + sgid * (8u * kBN) + lrow * kBN;
   ```
   → 你已经用 `cur_static.metal` 探过一半(把 `[[threadgroup(0)]]` 动态分配换成 kernel 内 `threadgroup tint_struct_4 tg;`,
   探针显示它的 `staticTGmem` 从 0 变成 30720)。**但 `tint_array` 包装 + struct 合并这两层还没单独拆过。**
   注意 struct 合并会改变扫描数组的基址相位:`half[4096]` 排在 `float[4096]` 前面 ⇒ 偏移 8192 字节,
   而手写侧 `accSG` 排在 `Bsh4` 后面 ⇒ 也是 8192。**这一条相位其实是对齐的,bank 假设不成立**
   （你的 `cur_pad33.metal` 已经在探 bank,预期是空刀)。

2. **循环形态**:tint 全部降成 `while(true) { if (cond) {} else break; ... { i = i + 1; } }`,
   手写侧是 `for (uint t = 0; t < per; ++t)`。见 §2.3。

3. **整数 div/mod 走 helper**:`v_8`/`v_11` 是 tint 的除零守卫
   ```cpp
   uint v_8(uint v_9, uint v_10) { return (v_9 - ((v_9 / select(v_10,1u,(v_10==0u))) * select(v_10,1u,(v_10==0u)))); }
   ```
   扫描段里 `v_11(v_16, 16u)` / `v_8(v_16, 16u)` 的除数都是字面量 ⇒ 会被常量折叠。**低风险,可划掉。**

---

## 1. 别人量过的同类数字(带数值的一手测量)

按「和本谜题的同构度」排序。

### 1.1 ★ Dan Ginsburg / Valve:Metal 上关掉 fast math ⇒ M1 上 Dota 2 慢约 4ms/帧

**KhronosGroup/MoltenVK issue #1209 "Performance regession on Macbook Air (M1, 2020)"**
<https://github.com/KhronosGroup/MoltenVK/issues/1209>

- 硬件:MacBook Air (M1, 2020),1440×900
- 负载:Dota 2 (Source 2)
- 幅度:**~4 ms/帧回归**,bisect 到改动 fast math 处理的 commit `4440a64`
- 原文:**"setting MVK_CONFIG_FAST_MATH_ENABLED=1 fixes the performance regression."**

MoltenVK 文档对该开关的口径(<https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/MoltenVK_Configuration_Parameters.md>):

> "Shaders compiled with the _Metal_ fast math option enabled perform floating point math **significantly faster**, but may optimize floating point operations in ways that violate the IEEE 754 standard."
> 默认值 `2`(始终开 fast math,但允许 shader 用 `VK_KHR_shader_float_controls2` / `SignedZeroInfNanPreserve` 局部收紧)

**为什么这是最强的一条**:它是**同一个 Apple GPU、同一份 shader、只动 fast-math 一个变量**的实测,
而且方向和量级都对得上你的谜题。注意 MoltenVK 的做法恰恰是 Dawn 没做的:**默认开 fast,只在 shader 显式要求时才收紧。**

### 1.2 ★ LlamaWeb (arXiv:2605.20706):同一份 WGSL、只开关安全检查,prefill 慢 14%/23%(最高 42%)

<https://arxiv.org/abs/2605.20706> / <https://arxiv.org/pdf/2605.20706>(第 9 页 §6.2)

> "Similarly, the **Metal backend always outperforms the WebGPU backend, by over 2× during prefill and 50% during decode**, although the difference is not as dramatic due to the lack of tensor cores and the lower overall performance on the smaller Apple GPU."

> "**Comparing performance with and without safety checks reveals that they cause an average 14% and 23% slowdown during prefill** on the q4_k_m and f16 models respectively, and a 5% and 1% slowdown during decode. These slowdowns, which **reached up to 42% during prefill on the NVIDIA RTX 5080**, show that there are opportunities for safe WebGPU to improve its performance, e.g., through better static analysis of memory accesses to remove runtime bounds-checks."

> "The WebGPU backend can also **use the subgroup matrix feature when running natively through the Dawn WebGPU implementation**, increasing the performance of our matrix multiplication and FlashAttention kernels."

硬件含 Apple M4 Pro / RTX 5080 / RX 7900 XT。
**价值**:同一份 WGSL、单变量消融、量级与你的 24% 同一档;
**局限**:14%/23% 是跨四张卡的平均,没有按 GEMM/reduction 分段;
而且 §0.5 已证明**你这份产物里 bounds-check 根本没生成**,所以这条只能当量级参照,不能当归因。

### 1.3 zkmopro:Apple M3 上 Metal vs WebGPU 逐算子表 —— 「不是均匀变慢」

<https://zkmopro.org/blog/client-side-gpu-everyday-ef-privacy/>

| op | Metal GOP/s | WebGPU GOP/s | Metal 快多少 |
|---|---|---|---|
| u32_add | 264.2 | 250.1 | **1.06×(持平)** |
| u64_add | 177.5 | 141.1 | 1.26× |
| m31_field_add | 146.0 | 121.7 | 1.20× |
| m31_field_mul | 112.0 | 57.9 | 1.93× |
| bn254_field_add | 7.9 | 1.0 | 7.64× |
| bn254_field_mul | 0.63 | 0.08 | 7.59× |

> "**Simple u32 ops show parity (1.06x)**; advanced arithmetic like Montgomery multiplication widens to 7x for BN254."
> "Metal's native 64-bit support edges WebGPU (**1.26x slower due to u32 emulation**), compounding on complex ops."

**价值**:第一手证明「翻译层的税按算子形态分化,不是一个统一倍数」——这正是你「MMA 持平、扫描段慢」的合法性依据。
**局限**:它的归因是 u64 仿真,不是 threadgroup 归约,**不能直接搬**。

### 1.4 wgpu Discussion #6688:M3 Max 上 wgpu(Metal) vs 原生 Vulkan 的整体倍数

<https://github.com/gfx-rs/wgpu/discussions/6688>

- "the v22.1.0.5 release version of wgpu-native is **2x slower vs vulkan**"
- 打上 PR #441 后:"takes **1.65x** as long to run a large benchmark model (~50k neurons, ~32 million synapses)"
- "MacBook Pro M3 (metal) performance is **improved by 20% in 25 vs 23**"
- 反向:"NVIDIA A100 ... **20% faster overall** ... vs. the previous direct vulkan-based implementation";"NVIDIA H100 performance is **worse by 20%** in 25 vs. 23"
- 作者自己定位:差距归于 **"the performance of the actual shader code generated from WGSL vs. HLSL"**,不是 CPU 开销

**关键限定(务必注意)**:作者明说
> "**None of the WGSL code uses any workgroup or other sync mechanisms**: just uses atomicAdd in a couple of kernels."

⇒ **这条数字与 threadgroup 归约无关**,只能当「codegen 层整体税」的量级参照。

### 1.5 wgpu Issue #6521:Apple M1 Pro 上 naga 与 tint 的同一份 WGSL 对比(循环形态)

<https://github.com/gfx-rs/wgpu/issues/6521>(b0nes164 开,2024-11-12,仍 open)

> "Currently, naga exclusively generates `while` loops when translating code for downstream compilers."

后果之一:**"downstream compilers cannot unroll loops, degrading performance"**。
Apple M1 Pro 实测(同一份算法分别用 wgpu+naga 与 dawn+tint 实现,统计每 pass 的自旋数):

| 实现 | 平均 spins/pass |
|---|---|
| wgpu+naga 22.0 | 10,181 |
| wgpu+naga 23.0 | 5,527 |
| **dawn+tint** | **3,625** |

相关:<https://github.com/gfx-rs/wgpu/issues/6518>(`[Metal/MSL] Workaround for stopping infinite loops to be optimized out causes performance regression`,由 PR #6285 引入)。

**价值**:唯一一条「循环降级形态 → Apple GPU 上可测性能差」的一手证据。
**注意方向**:这里 **tint 是赢家**;但 §0.6 已证 tint 生成的 MSL **同样**是 `while(true)+break` 形态,
手写侧才是计数 `for`。所以这条是「循环形态确实值钱」的旁证,不是「tint 一定更好」的结论。

### 1.6 ★ nuss-and-bolts:M2 Pro 上,**编译期常量 trip count 的循环在 tint 生成的 Metal 位码里没被展开**;手工展开 → 3×

源头:<https://www.nuss-and-bolts.com/p/optimizing-a-webgpu-matmul-kernel>
(俄译本 <https://habr.com/ru/articles/864330/> 标注 `Перевод`,内容与源头一致;下面的位码细节是在译本里逐字核到的,**结论以英文源头为准**)

- 硬件:Mac M2 Pro(译本原文:"Оговорюсь, что я занимаюсь разработкой на **Mac M2 Pro** с арифметической интенсивностью ~6 ТФЛОП/с")
- 4096×4096:Kernel 4(2D tiling 4×4)→ Kernel 5(手动展开 8×8)跨过 **1 TFLOP/s**
- **关键观察**(译本逐字):
  > "Кроме того, когда пишешь код на WGSL, **ты никак не можешь контролировать директивы компилятора**. Если посмотреть **ассемблерный бит-код из Metal**, то видно, что **в наборе инструкций по-прежнему содержится цикл for**!"
  （写 WGSL 时你完全无法控制编译器指示符。去看 Metal 出来的汇编位码就会发现,**指令序列里那个 for 循环还在**!）
  他贴出的分支是 `%62 = icmp eq i32 %61, 4` —— **trip count 是常量 4,Metal 编译器依然没展开。**
- 手工展开的收益:"**трёхкратное ускорение по сравнению с циклом 4x4**"(比 4×4 的循环版**快三倍**)
- 英文源头对应句:
  > "Because of the manual unrolling, the GPU is able to reduce overhead by not having to initialize and increment the inner loop."
- 且明确承认没用 subgroups:
  > "we didn't take advantage of subgroups, a feature that is new as of Chrome 125 and should allow for faster memory access and sharing across subgroups."

**价值**:这是**唯一一份真的去读 tint 生成产物的 Metal 位码、并给出数字**的公开材料,平台正好是 Apple M 系。
它把 §2 的 M3(循环形态)从「有旁证」提到「有直接产物证据 + 3× 的量级」。
**局限**:没有 WGSL vs 手写 MSL 的直接对比;3× 是 4×4 loop vs 8×8 unroll,不是同形状对拍。

### 1.7 ★ Zenn(yayo1):M4 Pro 上,**padding 消 bank conflict 零效果**;瓶颈被归到 barrier 等待离散度

<https://zenn.dev/yayo1/articles/1273ec6ac3bc17>(「WebGPUでCPUより高速に累積和を取りたいな」)

- 硬件逐字:"**使用マシンはM4 Pro Mac mini 24GBです。**" 栈:Rust + wgpu + Metal 后端
- 逐字:
  > "同様に**バンクコンフリクト回避のためにパディングを入れても見ましたが、これでもほとんど速度に変化はありませんでした**。... **Apple Siliconではバンクコンフリクトがそもそもあまり影響しないのかもしれません。**"
  （试了加 padding 规避 bank conflict,**速度几乎没变化**。…… Apple Silicon 上 bank conflict 本身也许就影响不大。）
  > "1スレッドでの2もしくは4要素の同時処理も実装してみたのですが、**寧ろ遅くなる結果になりました**。またワークグループサイズは32~256を試しましたが、**64が最速でした**。これらおそらく**workgroupBarrierの数が多い分**、... **バリアまでの待ちが長くなってしまっている**のかなと思われます。（ここは想像で書いていて不確かです）"
  （一个线程处理 2/4 个元素**反而更慢**;workgroup size 64 最快。大概是 workgroupBarrier 多、线程间完成时间离散大、等 barrier 变长。——**这段是作者自述的猜想**。）
- 数字:N=10⁸ Hillis-Steele 实测 104.36 ms,理论带宽下限 79.1 ms(273 GB/s);`subgroupExclusiveAdd` 版最快
  （**倍数只在图里,正文无数字,标注未能核实**)
- 尺子层面的警告,对你的台架直接有用:
  > "本来シェーダーの実行時間を取りたければ`timestamp-query`が使えればベストですが、**Metalバックエンドのバグなのかうまく取得できず**、... ポーリング分で最大体感500μs~1ms程度オーバーヘッドがあるっぽい"
  （想用 timestamp-query 取 shader 时间,**Metal 后端可能有 bug 取不到**;改测 submit→设备空闲,轮询带来最多 500μs~1ms 开销。)

**价值**:独立第三方在 Apple Silicon 上实测「padding 消 bank conflict 无效」——
这正是你 `cur_pad33.metal` 那一刀的先验,预期是空刀。
同时把 workgroup-memory 归约的瓶颈指向 **barrier 等待离散度**而非访存冲突。

### 1.8 willusher:同一块 RTX 3080,WebGPU vs 原生 Vulkan 的 marching cubes(含 scan + stream compaction)

源头 <https://www.willusher.io/graphics/2024/04/22/webgpu-marching-cubes>
(俄译本 <https://habr.com/ru/articles/811519/>,表格逐字核对过)

| 数据集 | WebGPU (M2 Max) | WebGPU (RTX 3080) | Vulkan (RTX 3080) | 同卡差 |
|---|---|---|---|---|
| 头骨 | 43.5 ms | 32 ms | 30.92 ms | +3.5% |
| Bonsai | 42.5 ms | 31 ms | 29.3 ms | +5.8% |
| 脚 | 54.4 ms | 32.5 ms | 33.43 ms | **−2.8%(WebGPU 更快)** |
| 动脉瘤 | 40.8 ms | **37.5 ms** | **27.45 ms** | **+36.6%** |

作者自评:"общем **производительность очень близка** к той, что наблюдается в нативной версии Vulkan"(总体上**非常接近**原生 Vulkan)。

**要害**:作者用一句「非常接近」盖过了同卡 **−2.8% ~ +36.6%** 的离散,而且**全文没有 per-pass 拆解**
(核对确认:文中不存在关于 exclusive scan / stream compaction / workgroup memory 是瓶颈的任何句子)。

**价值**:唯一一份「同硬件、WebGPU vs 原生、kernel 里正好有 scan」的对照,给出的先验是
**差异高度依赖 kernel 形状、可达 30%+ 量级**——与你的 24% 同档。
**局限**:无分段拆解,只能当量级参照,不能当机制证据。

### 1.9 ★★★ llama.cpp PR #22464:**M2 上同一算法,只换归约方式(workgroup 树 → subgroup),快 1.29×**

<https://github.com/ggml-org/llama.cpp/pull/22464>(yomaytk;作者原文 "in my enviroment (M2, Metal 4)")

算子 `MUL_MAT_ID`,`llama-bench -m DeepSeek-V2-Lite-Chat-Q6_K.gguf -fa 1 -p 0,1,512 -n 0,1,128 -r 3`,
tg128 阶段的 GPU kernel 时间(我 fetch PR 页面逐字核对):

| 路径 | master | `wg_reduce`(workgroup 树) | `sg_reduce`(subgroup) | 加速 |
|---|---|---|---|---|
| q8_0 | 941.1 ms | 268.6 ms | **215.2 ms** | 1.25× |
| q6_K | 3112.1 ms | 609.6 ms | **463.1 ms** | 1.32× |
| 合计 | 4053.2 ms | 878.2 ms | **678.3 ms** | **1.29×** |

**为什么这是全文最贴题的一条**:
同一个 WGSL kernel、同一台 Apple GPU、**唯一变量就是「归约落 `var<workgroup>` 走 log₂ 树 barrier」还是「`subgroupAdd` 在寄存器里做」**。
差 **1.29×** —— 和你扫描段的 24% 同一个数量级。

**但要严格区分**:这条量的是「WGSL 内部两种归约写法之差」,不是「WGSL vs 手写 Metal 之差」。
它证明的是**归约段对同步/共享内存策略极度敏感**,不是证明 tint 的 codegen 有问题。

### 1.10 「M3 上 1.35×」的真正出处 —— 是全表最有利的那一格

llama.cpp PR #17031(reeselevine),原文 "**Some preliminary performance numbers on my M3:**"
<https://github.com/ggml-org/llama.cpp/pull/17031>

Llama-3.2-1B-Instruct,`llama-bench`(t/s):

| 工况 | Metal | WebGPU | Metal ÷ WebGPU |
|---|---|---|---|
| F16 **pp512** | 1368.47 | 1014.17 | **1.349×** ← 传闻里的 1.35 就是它 |
| F16 tg128 | 35.99 | 28.71 | 1.254× |
| Q4_0 pp512 | 1346.68 | 960.52 | 1.402× |
| Q4_0 tg128 | 103.92 | 41.76 | **2.489×** |

⚠️ **1.35× 是四格里最有利的一格,不要外推**。同表的 Q4_0 tg128 是 2.49×。

同项目更极端的两条(同样已核到 PR 页):
- MUL_MAT_ID:WebGPU 468.95 GFLOPS vs Metal 3.83 TFLOPS = **8.2×**;n=32 时 41.14 vs 396.16 = 9.6×
  (<https://github.com/ggml-org/llama.cpp/pull/21147>,作者归因 "probably using subgroup matrices would help a lot on native, but won't work in the browser yet")
- Flash-Attn:"performance is not great right now (**< 50% of the same Metal code**). My testing shows that a lot of this slowdown basically boils down to the initial Q * K^T accumulation loop."
  (<https://github.com/ggml-org/llama.cpp/pull/18610>)

**⇒ 「WebGPU 大约是原生 Metal 的 85–90%」这个在中文/英文圈都流传的说法,回到源头零命中,与上面每一条一手数字都矛盾。丢掉它。**

---

## 2. 机制线索(按可证伪性 + 证据强度排序)

### M1 ★★★ `math_mode(relaxed)` 剥掉了 `nnan/ninf`,只惩罚比较链、不惩罚 MMA

**一手证据链**(四段全部在本文档内可复核):

1. Dawn 无条件注入 `#pragma METAL fp math_mode(relaxed)`,且**压过编译选项** —— `ShaderModuleMTL.mm:460-479`(§0.2)
2. 本机 `[MTLCompileOptions new]` 默认 `MTLMathModeFast`,`__FINITE_MATH_ONLY__=1` —— 实测探针(§0.1)
3. Apple 头文件:relaxed 与 fast 的唯一差别就是 **"preserves infs and nans"** —— `MTLLibrary.h:261-265`(§0.1)
4. 加/不加 pragma 编 `native_scan2.metal`,IR 里 `fcmp fast` 变成 `fcmp reassoc nsz arcp contract afn`(**丢了 `nnan ninf`**) —— 实测 diff(§0.3)

**为什么它能解释「只有扫描段变慢」**:
扫描段是 top-2,本质是 `if (d > pb) {ps=pb; pb=d; pbi=c;} else if (d > ps) {ps=d;}` 的**有序比较链**,
外加蝶形归约里的 `max(...)`。在 `nnan` 下编译器可以:
把两级 if/else 压成无分支 select 树、把 `max` 选成单条无序 max 指令、在 8 次展开之间做重结合。
去掉 `nnan` 之后这些全部受限。
MMA 段几乎没有标量浮点比较(全是 `simdgroup_multiply_accumulate` / `simdgroup_load`),**不受影响**。

**旁证有数字**:MoltenVK #1209,同样是 Apple GPU 上「关掉 fast math ⇒ 慢 ~4ms/帧」(§1.1)。
注意 MoltenVK 的策略与 Dawn 相反:**默认 `fast`,只在 shader 用 `VK_KHR_shader_float_controls2` /
`SignedZeroInfNanPreserve` 显式要求时才收紧。** 两个 Metal 翻译层在同一个问题上做了相反的选择,
而 WGSL 规范其实站在 MoltenVK 那一边(§0.2)。

**可操作性**:如果 E1 定罪,补丁只有一行 —— `ShaderModuleMTL.mm:468` 的
`r.useStrictMath ? "safe" : "relaxed"` 改成 `r.useStrictMath ? "safe" : "fast"`;
或者更保守地,在你自建 Dawn TU 上加一个 device toggle。这对你「一套 WGSL 经 Dawn 上三端」的路线是结构性的:
Vulkan/SPIR-V 端很可能不受这条影响 —— gpuweb #2076 里对各后端现状的归纳是
"**Vulkan/SPIR-V**: By default implementations *may perform optimizations ... that ignore sign of a zero,
or assume that arguments and results are not NaNs or infinities*"
(<https://github.com/gpuweb/gpuweb/issues/2076>;这是 issue 里的转述,若要做决策请回 Vulkan 规范
Appendix「Precision and Operation of SPIR-V Instructions」核一遍)。
若属实,**这是 Metal 端被 Dawn 单方面收紧的一条,跨端时会表现为「同一份 WGSL 在 Metal 上偏慢」。**

**这一条同时给出「为什么 MMA 段 tint 反而快 0.2ms」的一个候选**:那 0.2ms 更可能来自
`[[max_total_threads_per_threadgroup(512)]]` 或 tint 的 MMA 形态(你的 `k.metal` FORM_A/FORM_B 已在探),
与 fp 模式无关。

### M1b ★★★ **WGSL 没有 subgroup 级 barrier** ⇒ tint 侧只能付全 threadgroup 同步;而扫描段恰好是发散的

**这是第三个未受控的跨臂差异,而且是语言表达力缺口,不是编译质量问题。**

产物实测(只读 grep,`/private/tmp/mmaform/`):

| 文件 | `threadgroup_barrier` | `simdgroup_barrier` |
|---|---|---|
| `cur.metal` / `cur_noscan.metal` / `cur_mma.metal`(tint) | **5** | **0** |
| `native2.metal` / `native_mma.metal` / `native_scan2.metal`(手写) | 3 | **3** |

手写侧的注释把意图写死了(`native2.metal:157-158`):
```cpp
// GEMM: this SG's 8 rows x the 32-column tile, staged per-SG (no
// cross-SG sharing -> simdgroup_barrier only).
...
simdgroup_barrier(mem_flags::mem_threadgroup);      // L171
```
累加器 `accSG` 是**每 SIMD-group 私有**的,只需要 SIMD 级内存序。
tint 在同一位置(`simdgroup_store` 之后、扫描之前,`cur.metal:212`)只能发全 threadgroup 同步 —— **因为 WGSL 表达不了。**

**穷举证据**:
- WGSL 全部 barrier 内建只有三个 —— tint `core.def`:`storageBarrier()` / `workgroupBarrier()` / `textureBarrier()`,
  全文件 `subgroupBarrier` 命中 0
  <https://github.com/google/dawn/blob/main/src/tint/lang/core/core.def>
- tint 的 MSL 内建函数名表里只有 `threadgroup_barrier`,**没有** `simdgroup_barrier`
  <https://github.com/google/dawn/blob/main/src/tint/lang/msl/builtin_fn.cc>
- 标准委员会自己承认这是洞,**开着两年多没补**:gpuweb issue #4437
  「Add subgroup barrier to subgroups proposal」,@raphlinus 2024-01-03 开,**至今 open**
  <https://github.com/gpuweb/gpuweb/issues/4437>
  > "The current subgroup proposal is **lacking a subgroup barrier**, though it was present in the naga prototype implementation."
  > "…found that **the excessive number of workgroup barriers needed tanked performance**."
  > "Translation to MSL is straightforwardly `simdgroup_barrier(mem_flags::mem_threadgroup)`."
- **另一套 WGSL 实现已经补了,Dawn 没有**:wgpu/naga 有 WGSL 内建 `subgroupBarrier`,MSL 后端发射
  `simdgroup_barrier(mem_flags::mem_threadgroup)`,feature 说明 "Supported Platforms: Vulkan, **Metal**. This is a native only feature."
  <https://github.com/gfx-rs/wgpu/blob/trunk/naga/src/back/msl/writer.rs>
- Apple 自己说这条差价是真的(WWDC16 S606,我已回官方页 transcript 复核):
  > "targeting your thread group to fit within a single SIMD and using SIMD group barrier is **often faster** than trying to use a larger thread group … but having to use thread group barrier as a result."

#### ⚠️ 我对这条的关键修正:**静态 barrier 差在三个臂里是常数,所以它单独解释不了 1.11ms**

`cur_mma.metal`(5/0)vs `native_mma.metal`(3/3)—— **MMA-only 臂的 barrier 差与完整核完全一样**,
可是 MMA-only 臂 **tint 还赢 0.2ms**。
⇒ 「多付几次全组同步」本身不值 1.11ms。

**精化后的机制(这才是可测的假设)**:
barrier 的代价 = 作用域 × **发散度**。
- MMA 段:纯 `simdgroup_load` / `simdgroup_multiply_accumulate`,**无数据相关分支,512 个线程齐步走**
  ⇒ 512 线程 barrier 与 32 线程 barrier 几乎等价 ⇒ tint 不吃亏。
- 扫描段:top-2 是 `if (d > pb) {...} else if (d > ps) {...}` 的**数据相关分支**,每 lane 走的路不同
  ⇒ 到达 barrier 的时刻离散 ⇒ **512 线程 barrier 取的是 512 个里最慢的那个,32 线程 barrier 只取 32 个里最慢的**。
  同样的 barrier 结构,在发散负载后面贵得多。

**旁证(独立第三方,Apple GPU)**:§1.7 的 Zenn 作者把 workgroup-memory scan 的瓶颈明确归到
「**workgroupBarrier の数が多い分 … バリアまでの待ちが長くなってしまっている**」(等 barrier 的时间变长),
而不是访存冲突——他还实测 padding 消 bank conflict 无效。
**旁证(有数字)**:§1.9 的 1.29×,正是「归约走 workgroup 树 barrier」换成「走 subgroup」的差价。

#### 判决刀(**一个 token 的改动,10 分钟**)

把 `native_scan2.metal:171` 的 `simdgroup_barrier` 改成 `threadgroup_barrier`(**复制到 scratchpad 改,别动原文件**),
其余一字不动,四臂交替 A/B。
- 手写侧慢出接近 1.11ms ⇒ **M1b 定罪**,结论是「这是 WGSL 的语言缺口,Dawn 上无解,只能改 Dawn 或改算法把归约收进一个 subgroup」
- 慢出 < 0.2ms ⇒ M1b 出局,回 M1(fp 模式)

**反向刀**:目录里 `cur_sgb.metal` 已经把 `cur.metal:212` 的那一次换成了 `simdgroup_barrier`
(逐字 diff 只差这一行)。它只换了 5 个里的 1 个 —— **如果那一刀已经跑过并且是空刀,再把剩下 4 个也换掉再跑一次。**

### M2 ★★ workgroup 数组的「struct 合并 + 指针参数 + `tint_array` 包装」三层

**一手证据**:`cur.metal:6-15, 38-49, 372-373` 与 `native2.metal:87-92, 177-178` 的逐字对照(§0.6-1)。
Dawn 官方 expectation 文件确认这是通用形态,不是你这份的偶然:
<https://dawn.googlesource.com/dawn/+/refs/heads/main/test/tint/array/assign_to_workgroup_var.wgsl.expected.msl>

Apple 的相关一手口径(WWDC16 Session 606《Advanced Metal Shader Optimization》):

> "The best way to do this is to pass your arguments **by reference rather than pointer** where possible."
> "As of iOS 10, one of our new compiler optimizations, is we will try to **vectorize some loads and stores that go to neighboring memory locations**."

这两句我回 Apple 官方页面的 transcript 逐字复核过(不是只看第三方转录站),
<https://developer.apple.com/videos/play/wwdc2016/606/>

行方向每 lane 读 **8 个连续 float**,正是「neighboring memory locations」向量化的靶子;
经 `(*v_19.tint_member_17)[...]` 的指针间接后,编译器是否还能合并成 2×`float4`,是可测的。

**诚实标注**:**全网没有人量过这三层各自的代价。**
中/日/俄/英文社区均零命中(§4)。这是唯一一条「机制成立、数字为零」的线索。
你已用 `cur_static.metal` 拆掉了「动态 threadgroup 分配」这一层,**另两层没拆过**。

**交叉引用**:同目录 `research_tint_codegen.md` 已经在这条上走得更远
(§2.1 tint 形态的来历、§2.2 AIR 层实测别名信息在函数边界丢失、§2.3 MSL `restrict` 本机验证有效,
对应目录里的 `v2_restrict.metal`)。**本文不重复,只补一条社区侧的结论:这条路上没有任何公开数字可抄。**

### M3 ★★ 循环降级形态(`while(true)+break` vs 计数 `for`)

tint 侧(`cur.metal:220-238`):
```cpp
{ uint v_57 = 0u;
  while(true) {
    if ((v_57 < 8u)) { } else { break; }
    ...
    { v_57 = (v_57 + 1u); } } }
```
手写侧(`native2.metal:182`):`for (uint t = 0; t < per; ++t)`(`per` 是编译期常量 8)

**证据**:
- nuss-and-bolts 在 **M2 Pro** 上读 tint 生成的 Metal 位码,**编译期常量 trip count(4)的循环没被展开**;
  手工展开 8×8 得到 **3×**(§1.6)。这是最直接的一条。
- wgpu #6521 的 M1 Pro 数字:naga 的 `while` 形态让下游编译器无法展开(§1.5)。

**反向证据**:#6521 里 **tint 反而更快**(3,625 vs 5,527 spins),说明 `while(true)` 形态**不必然**阻断展开;
而且你的扫描段 trip count 只有 8,展开与否的绝对代价比 matmul 内层小。

**为什么排在 M1 之后而不是之前**:M3 无法解释「MMA 段持平」——
MMA 段的 16 次 k 循环在 tint 侧同样被降成 `while(true)+break`(`cur.metal:188-205`:
`while(true){ if ((v_49 < 16u)) {} else { break; } ... simdgroup_multiply_accumulate(...); { v_49 = (v_49 + 1u); } }`),
如果 `while` 形态本身有代价,MMA 段也该慢。**它没慢。**
所以 M3 只能是次要项,除非扫描段的循环体形态特殊(有 `continue` / 提前 break)。

### M4 —— 已洗清,不要再花时间

| 已排除项 | 排除依据 |
|---|---|
| robustness 越界 clamp | `cur.metal` 里对 workgroup 数组的 14 处访问**零 clamp**;全文件仅两个 `min(` 是 `acos(min(x,1.0f))`(§0.5) |
| workgroup 零初始化 | `kernel void cur` 入口**无清零循环、无入口 barrier**(§0.5) |
| `workgroupBarrier` 语义 | 生成的就是裸 `threadgroup_barrier(mem_flags::mem_threadgroup)`,与手写逐字一致 |
| 整数 div/mod helper(`v_8`/`v_11`) | 除数全是字面量 `16u`/`32u`,`select(16u,1u,false)` 会被常量折叠(§0.6-3) |
| bank 相位 / stride-32 冲突 | (a) tint struct 里扫描数组偏移 8192B,手写侧 `accSG` 也在 8192B —— **相位对齐**;(b) 独立第三方在 **M4 Pro** 上实测 padding 消 bank conflict **零效果**(§1.7);(c) 两侧访存模式字面相同,bank 冲突本来就解释不了**差值** |
| 寄存器压力 / spill | 两侧不加属性时 PSO 都报 `maxTotalThreads=1024`,都没到寄存器墙(§0.4) |

⚠️ 注意:社区里被提名次数最多的两条(robustness clamp、workgroup zero-init)在**你这份具体产物**里根本没生成。
如果有人拿这两条来解释你的 1.11ms,先让他 grep 一遍 `cur.metal`。

---

## 3. 可证伪的台架实验(每条 ≤1 小时,单变量)

全部复用你现有的 `main25.mm` / `bench25` 结构;**新文件放 scratchpad,不动 mmaform 既有文件**。

### E1 ★ 把手写侧也钉到 relaxed(M1 的判决刀)

```
cp native_scan2.metal  $SCRATCH/native_scan2_relaxed.metal
sed -i '' '1i\
#pragma METAL fp math_mode(relaxed)
' $SCRATCH/native_scan2_relaxed.metal
```
在 `main25.mm` 的副本里多建一条 pipeline 指向它,四臂交替 A/B:
`cur` / `native_scan2` / `native_scan2_relaxed` / `native_mma`。

**判据**:
- `native_scan2_relaxed` 相对 `native_scan2` 慢出接近 1.11ms ⇒ **M1 定罪,谜题解决**,
  且结论是「这不是你的 WGSL 写法问题,是 Dawn 的 fp 策略,只能靠改 Dawn 或后处理 MSL 解决」
- 慢出 < 0.2ms ⇒ M1 出局,转 E3

**反向刀(同一小时内)**:把 `cur.metal` 第 1 行的 pragma 删掉编一份 `cur_nopragma`(我已在 scratchpad 生成过 `c_cur_nopragma.metal`),
如果它把 5.649 拉回 4.5 附近,**双向闭合**。

### E2 属性对拍 —— **已有人在做,不用重复**

目录里 `v3_nomaxtt.metal` 就是 `cur.metal` 删掉 `[[max_total_threads_per_threadgroup(512)]]`(逐字 diff 只差这一行)。
§0.4 的探针预期它是空刀。**只需补一刀反向**:`native_scan2` 加上该属性。

> ### ⚠️ 目录扫描:`math_mode` 是**唯一没有任何人探过**的跨臂变量
>
> 我 grep 了 `/private/tmp/mmaform/` 下全部 `.metal`:
> - **20 个** `cur*` / `v1_` / `v2_` / `v3_` 文件,**第 1 行全部是** `#pragma METAL fp math_mode(relaxed)`
> - 全部 `native*` / `nat_*` / `k.metal` / `tgprobe*`,**一个都没有**
>
> 也就是说:`cur_static` / `cur_pad33` / `cur_sgb` / `cur_xb4` / `cur_norow` / `cur_nocol` / `cur_nomerge` /
> `cur_acc33` / `cur_hmerge` / `v1_sgbarrier` / `v2_restrict` / `v3_nomaxtt` —— 这十几刀
> **全都是在 relaxed 这一侧内部互相比**,没有一刀跨过 fp 语义这条线。
> **E1 是目前唯一一条没被切过的变量。**

### E1b barrier 作用域 —— **已有人在做,但只切了 1/3,需要补全**

目录里已经有两把刀(16:24–16:27 生成):
- `native_tgb.metal` = `native2.metal` 把 **L171 那一处** `simdgroup_barrier` 改成 `threadgroup_barrier`(逐字 diff 只差这行 + 函数名)
- `v1_sgbarrier.metal` / `cur_sgb.metal` = `cur.metal` 把 **L212 那一处** `threadgroup_barrier` 改成 `simdgroup_barrier`

**但两边都只动了 3 处 / 5 处里的 1 处。** 手写侧还有 L126 与另一处 `simdgroup_barrier` 没换。
**要得到干净判据,必须把 3 处全换**(`native2.metal` 的 `simdgroup_barrier` 在 L126 / L171 / 还有一处)。

**判据**:三处全换后手写侧慢出接近 1.11ms ⇒ M1b 定罪;< 0.2ms ⇒ 出局。
**并且**:同时跑 `native_mma` 的对应变体 —— 如果 MMA-only 臂也同样慢,说明这是常数项、不是扫描段的税
(这正是 §M1b 那条修正要验的东西)。

### E3 拆 `tint_array` 包装(M2 的第一刀)

在 `cur_static.metal` 基础上(它已经把 `[[threadgroup(0)]]` 换成 kernel 内静态分配),再做一份:
把 `tint_array<float,4096>` 换成裸 `float[4096]`,并把扫描段的
`(*v_19.tint_member_17)[(v_56 + v_58)]` 改写成先在循环外提出裸指针
`threadgroup const float* row = base + v_56;` 再 `row[v_58]`(**只改扫描段,MMA 段一字不动**)。

**判据**:扫描段时间变化。若 ≥0.5ms ⇒ M2 成立,且直接给出 WGSL 侧的写法建议
(把 workgroup 数组的索引在循环外算成一个基址,让 tint 少生成一层间接)。
**注意**:这一刀改的是生成物,不是 WGSL 源;它只用来**定位**,不能当产品方案。

### E4 循环形态对拍(M3)

把 `native_scan2.metal` 的两个 `for` 手工改写成 tint 的 `while(true){if..else break; ...}` 形态,别的不动。
**判据**:慢出 ≥0.3ms ⇒ M3 成立。

### E5 Dawn 侧开关对拍(如果你要在真正的 WGSL 链路上复现)

在你的 Dawn TU 上加 device toggle,一次一个:
`disable_robustness` / `enable_integer_range_analysis_in_robustness`(默认 on)/ `disable_workgroup_init`。
**预期全是空刀**——§0.5 已证这三样在你手上的产物里根本没生成,
同目录 `research_tint_codegen.md` §1.2 也独立查到「robustness 你已经关掉了」。
**这一刀的价值是反向的**:如果它们居然有效,说明你导出的 MSL 与线上 Dawn 实际编译的不是同一份,那是更严重的问题。

> 顺带:社区(中/日/俄三边的报告)一致把 robustness clamp 和 workgroup zero-init 当作头号嫌疑人。
> 在**一般的 WebGPU 应用**里他们大概率是对的(§1.2 的 14–23% 就是这条)。
> 但**在你这份产物里这两条已经被关掉了**,所以社区的头号答案对你不适用 —— 这正是「必须回到自己的产物取证」的一个实例。

---

## 4. 搜了但零命中(零命中本身是结论)

### 4.1 中文社区:**全站零命中**

| 站点 | 结果 |
|---|---|
| 知乎 zhihu.com / zhuanlan(6 组关键词,含 domain 限定) | **零命中**。只有 WGSL vs GLSL 语法、WebGPU vs WebGL 科普、CUDA 归约教程 |
| CSDN(5 组) | **零命中**。`blog.csdn.net/mutourend/article/details/149947567` 两次 fetch 得 ECONNRESET / HTTP 521,**未能核实** |
| 掘金 juejin.cn(2 组) | **零命中**。只有 WGSL 语法、naga glsl→wgsl、WebGPU 入门 |
| 博客园 cnblogs.com(3 组) | **零命中**(性能层面)。岭南灯火 WebGPU 系列只有 M1 MBA 上 2D 物理模拟 FPS |
| B 站专栏 bilibili.com/read(1 组) | **零命中**。返回的是验证码页 |
| mp.weixin.qq.com(2 组) | **零命中**。GPU 架构科普 / WebGL→WebGPU 介绍 / Chrome 94 试用 |
| GitHub 中文 issue(3 组) | **零命中** |
| 腾讯云/阿里云/百度云社区(2 组) | **零命中**。全是 WebGPU vs WebGL 转载科普 |
| V2EX(核对 t/1021551) | 提问存在但**无人回答**,零数字 |

零命中的中文关键词:「WGSL 性能 Metal 对比」「tint 生成 MSL」「Dawn 后端 性能」「threadgroup 内存 归约 慢」
「simdgroup_matrix 性能」「WebGPU 矩阵乘 性能 对比 Metal」「wgpu 性能损失」「WGSL 数组越界 clamp 性能实测」
「WebGPU workgroup 内存 清零 开销」「手写 Metal vs 编译器生成 性能 差距 实测」
「WebGPU Metal 性能 对比 分阶段 kernel 拆解 归约 GEMM 持平」「MNN WebGPU 后端 性能 对比 Metal」

**低可信、不建议引用的中文材料**(已 fetch 核对,均无方法/无硬件/疑似生成内容):
- ursb.me《一次 dispatch 的八重翻译》<https://ursb.me/immersive/webgpu/> ——「生产 demo 显示 WebGPU 在 matmul 上能达到 Metal native 的 ~85%」,无出处/无硬件/无 kernel 定义
- viai.fun <https://viai.fun/archives/webgpu-browser-ai-inference-20260628> ——「WebGPU 推理大约是原生速度的 70-75%」,无方法、署名仅 "via"
- 中文圈所有「WebGPU 提升 50/65/100 倍」的说法**全是 WebGPU vs WebGL**,与本题无关

### 4.2 日文社区:**除 §1.7 一篇外全零**

| 站点 | 关键词 | 结果 |
|---|---|---|
| Zenn(走 `zenn.dev/api/search`)| `WGSL 最適化` | **0 篇** |
| Zenn | `バンクコンフリクト` | **articles 0 / scraps 0**(全站没有这个词) |
| Zenn | `tint MSL` | **0 篇**(页面显示「検索結果が見つかりませんでした」) |
| Zenn | `WGSL Metal` | **0 篇** |
| Zenn | `WGSL` | 全站仅 **4 篇**,全是入门/移植,无一涉及性能测量 |
| Zenn | `WebGPU 遅い` | 47 篇,逐条看标题,**无一是 vs 原生 Metal 的测量**;仅 §1.7 那篇有 Apple GPU 实测 |
| Qiita | `WebGPU ベンチマーク 行列積` | 5 条,**全部离题** |
| Qiita | `WebGPU Metal 性能` | 10 条,**无一含原生 Metal 对照** |
| Qiita | `Metal シェーダー 生成コード 性能差 threadgroup リダクション 計測` | 5 篇 Metal 入门文;打开核实的 <https://qiita.com/yuky_az/items/2eed6dd79f74949715c3> **明确无数字**:「この辺りはいずれきっちりと実験を行なってみたいと思います。」 |
| はてなブログ / はてなブックマーク | `WebGPU WGSL シェーダ 最適化 Metal 比較 計測` | 只有 shader 移植文(shu223、nekocha 的 HLSL→WGSL)与 Metal 入门,**生成代码性能测量 0 条** |
| Speaker Deck | `WebGPU コンピュートシェーダー 最適化` | 仅入门 deck,**codegen/性能拆解 0 条** |
| note.com | `WGSL` | 约 60 条,全是入门/日记体,**0 条相关** |
| GitHub issues(日语关键词)| `WebGPU 遅い` / `wgpu 遅い` / `Metal 遅い シェーダー` / `tint MSL 遅い` / `シェーダー 性能 WebGPU` | **全部 0 条** |
| Web | 「WebGPU 境界チェック オーバーヘッド robustness」/「simdgroup_matrix WGSL subgroup matrix ベンチマーク」/「tint MSL 生成 workgroup 配列 構造体 ポインタ 性能」 | **全部 0 条日语材料** |

日文社区唯一相关的 bank-conflict 材料是 PyOpenCL 教程 <https://mkguytone.github.io/pyopencl/ch20s03.html>
(「メモリストライド(ローカルメモリの場合はバンクコンフリクト)が発生します」,解法是 `size+1` padding)——
**而这正是 §1.7 在 Apple Silicon 上实测为无效的手法。**

### 4.3 俄文社区:**全零**

| 站点 | 关键词 | 结果 |
|---|---|---|
| Habr(走 `habr.com/kek/v2/articles` API)| `WGSL` | 全站仅 **22 篇**,**无一是 WGSL vs 原生的分段测量** |
| Habr | `банк-конфликты разделяемой памяти` | 20 条,**全是 CUDA/通用**,**0 条 WebGPU、0 条 Apple GPU** |
| Habr | `Metal шейдер Apple GPU производительность` | 20 条,**0 条涉及「生成 MSL vs 手写 MSL」** |
| Habr | `SPIRV-Cross MSL трансляция шейдеров Metal` | 6 条,**全部无数字** |
| Habr | `MoltenVK Metal производительность` | 7 条,**全部无关** |
| Habr | `WebGPU вычисления оптимизация шейдер` | 20 条,除 §1.6/§1.8 的两篇译文外**无新增** |
| Habr 689390《Переход на Metal》 | — | 打开核实:**明确没有数字**,"В реальности — вопрос сложный.",性能留到未见的第二部分 |
| Habr 840904《Открытые инструменты для GPU-вычислений》 | — | 提到 gpu.cpp 用 Dawn,**无任何 benchmark** |
| vc.ru | `WebGPU` | 搜索接口 HTTP 404;改 domain 限定网搜,**0 条相关** |
| GitHub issues(俄语关键词)| `WebGPU производительность` / `WGSL медленно` / `медленнее Metal WebGPU` | **全部 0 条** |

⚠️ **重要限定**:俄文侧两篇最有价值的文章(§1.6 / §1.8)**都标着 `Перевод`(翻译)**,原文是英文。
俄语社区自己在这个话题上的原创产出只有一条口径混淆的评论
(「Нейронки с webgpu у меня запускались в 3-10 медленнее в браузере, чем на хосте」——
这是「浏览器 vs 主机」,含进程/编码/拷贝成本,**不是 tint-MSL vs 手写-MSL**,不作为证据)。

### 4.4 英文社区的零命中

- **Reddit r/GraphicsProgramming / r/vulkan / r/webgpu**:没有搜到任何「同一 kernel、WGSL vs 原生、分段拆解」的帖子
- **Hacker News**:相关线程(22255681 / 23079200 / 23089066 / 39038971)全是 API 设计与生态讨论,**零性能数字**
- **Stack Overflow**:「WGSL workgroup array 比 Metal threadgroup array 慢」**零命中**
- **`#pragma METAL fp math_mode` 的性能代价**:除了 MoltenVK #1209 的间接旁证,**没有任何人直接量过 relaxed vs fast 在 Apple GPU 上的差**
- **`tint_array` 包装 / workgroup struct 合并 / 指针参数的代价**:**全网零测量**

### 4.5 最重要的空白

> **你问题里的第 2 条(「GEMM/矩阵段持平,但 reduction/scan/threadgroup 归约段显著变慢」这个特定形态)——
> 中文、日文、俄文、英文社区全部零直接命中。**
>
> 最接近的四条,以及它们各自差在哪:
> - **§1.9(最近)**:M2 上同一份 WGSL,只换归约方式(workgroup 树 barrier → subgroup),**1.29×**。
>   差在:量的是 WGSL 内部两种写法,不是 WGSL vs 手写 Metal。
> - §1.2:同一份 WGSL 单开关消融(安全检查),14–23%(最高 42%)。差在:没按 GEMM/reduction 分段;
>   而且 §0.5 已证这些检查在**你这份产物里根本没生成**。
> - §1.3:Apple M3 逐算子表,证明「不是均匀变慢」。差在:归因是 u64 仿真。
> - §1.6:M2 Pro 上读 tint 生成的 Metal 位码,常量 trip count 未展开,手工展开 3×。差在:不是同形状对拍。
>
> **换句话说:「同一 kernel、tint vs 手写 Metal、按段拆」这件事,公开社区里没有第二个人做过。**
> 这条谜题的答案只能从你自己的台架出来,而 §0 已经把「两侧不是单变量对照」钉死了 —— **先补 E1 与 E1b。**

---

## 5. 引用清单(全部已逐字核到源头)

**一手源码/规范/头文件**
- Dawn `ShaderModuleMTL.mm`(math_mode pragma 注入)<https://dawn.googlesource.com/dawn/+/refs/heads/main/src/dawn/native/metal/ShaderModuleMTL.mm>
- tint `robustness.cc` / `robustness.h` <https://dawn.googlesource.com/dawn/+/refs/heads/main/src/tint/lang/core/ir/transform/robustness.cc>
- Dawn `Toggles.cpp` <https://dawn.googlesource.com/dawn/+/refs/heads/main/src/dawn/native/Toggles.cpp>
- tint MSL expectation(workgroup struct 形态)<https://dawn.googlesource.com/dawn/+/refs/heads/main/test/tint/array/assign_to_workgroup_var.wgsl.expected.msl>
- Apple `MTLLibrary.h`(本机 SDK,MTLMathMode 语义 + `fastMathEnabled defaults to YES`)
- Metal Shading Language Specification <https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf>
- W3C WebGPU §security-shader <https://www.w3.org/TR/webgpu/#security-shader>

**Apple 一手口径**
- WWDC16 S606 Advanced Metal Shader Optimization <https://developer.apple.com/videos/play/wwdc2016/606/>
- Tech Talk 10580 Metal Compute on MacBook Pro <https://developer.apple.com/videos/play/tech-talks/10580/>
- Tech Talk 10858 Discover Metal enhancements for A14 Bionic <https://developer.apple.com/videos/play/tech-talks/10858/>
  > "By using simd_sum, we have decreased the number of threadgroup barriers and the usage of threadgroup memory."
  > "On A14, using the new SIMD group matrix multiply operations, average performance is improved by 37%."

**带数字的测量**
- MoltenVK #1209 <https://github.com/KhronosGroup/MoltenVK/issues/1209>
- MoltenVK 配置文档 <https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/MoltenVK_Configuration_Parameters.md>
- LlamaWeb arXiv:2605.20706 <https://arxiv.org/abs/2605.20706>
- zkmopro <https://zkmopro.org/blog/client-side-gpu-everyday-ef-privacy/>
- llama.cpp PR #22464(M2:wg_reduce 878.2ms → sg_reduce 678.3ms = 1.29×)<https://github.com/ggml-org/llama.cpp/pull/22464>
- llama.cpp PR #17031(M3:Metal vs WebGPU llama-bench,1.35× 的出处)<https://github.com/ggml-org/llama.cpp/pull/17031>
- llama.cpp PR #21147(MUL_MAT_ID 8.2×)<https://github.com/ggml-org/llama.cpp/pull/21147> / PR #18610(Flash-Attn <50%)<https://github.com/ggml-org/llama.cpp/pull/18610>
- gpuweb #4437 Add subgroup barrier(2024-01-03 开,仍 open)<https://github.com/gpuweb/gpuweb/issues/4437>
- tint `core.def`(barrier 内建穷举)<https://github.com/google/dawn/blob/main/src/tint/lang/core/core.def> / `msl/builtin_fn.cc` <https://github.com/google/dawn/blob/main/src/tint/lang/msl/builtin_fn.cc>
- naga MSL writer(`simdgroup_barrier` 已实现)<https://github.com/gfx-rs/wgpu/blob/trunk/naga/src/back/msl/writer.rs>
- W3C WGSL §15.7.2 Finite Math Assumption <https://www.w3.org/TR/WGSL/#floating-point-evaluation>
- wgpu Discussion #6688 <https://github.com/gfx-rs/wgpu/discussions/6688>
- wgpu Issue #6521 <https://github.com/gfx-rs/wgpu/issues/6521> / #6518 <https://github.com/gfx-rs/wgpu/issues/6518>
- nuss-and-bolts WebGPU matmul(源头)<https://www.nuss-and-bolts.com/p/optimizing-a-webgpu-matmul-kernel> — 俄译本(位码细节)<https://habr.com/ru/articles/864330/>
- Zenn / yayo1(M4 Pro,padding 无效)<https://zenn.dev/yayo1/articles/1273ec6ac3bc17>
- willusher WebGPU marching cubes(源头)<https://www.willusher.io/graphics/2024/04/22/webgpu-marching-cubes> — 俄译本(表格)<https://habr.com/ru/articles/811519/>

**背景**
- gpuweb #2076 Add method to disable fast-math on a per-shader basis <https://github.com/gpuweb/gpuweb/issues/2076>
  > "Metal: fast-math is enabled by default but can be disabled with `-fno-fast-math` option"
- dawn-graphics 邮件列表 "wgsl optmizations?"(Corentin Wallez:tint **"there are no optimizations done at this time"**)<https://groups.google.com/g/dawn-graphics/c/bbCgIrYYdng>
