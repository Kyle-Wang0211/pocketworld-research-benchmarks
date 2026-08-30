# 交接增补：2026-08-30 稠密提速实测账本

> 本文是 `HANDOFF_DENSE_RECONSTRUCTION_2026-08-29.md` 的增补，不替代它。
> 与原交接冲突处，**以本文为准**（本文的数字都经过强制一致性校验，原交接
> 有若干数字是在未验证的构建上取得的）。

---

## 零、先读这一条：08-29 交接里的性能数字全部不可信

原交接第七章记的 `355s → 64.5s → 58.571s → 57.590s` 优化链，以及
「ring-only 61.943s」「subgroup barrier 值 1.7%」，**其测量方法有系统性缺陷**：

`pw_official_dense_moltenvk_host_probe` 是 CMake 的 **`EXCLUDE_FROM_ALL`**
目标，`make` **不会重建它**。改完 shader 后执行
`make → 跑 benchmark` 得到的是**上一次编译的旧二进制**，里面嵌的是旧 SPIR-V。

2026-08-30 用 `MVK_CONFIG_SHADER_DUMP_DIR` dump 出运行时**实际加载**的
SPIR-V 才发现：dump 出的 11 个 shader 里 10 个与 bundle 对得上，唯独 sweep
对不上（bundle 是新的，运行时加载的是几小时前的旧的）。

⚠️ 该缺陷会**伪造出收益**：08-30 上午我据此报告过「barrier 值 5.6 秒 /
8.8%，且深度图逐字节相同」——实际两次跑的是同一个二进制，差值是运行噪声，
「逐字节相同」有平凡解释。全部撤回。

---

## 一、shader 哈希被锁在四个独立位置

改 shader 必须四处同步，漏一处运行时报
`shader, resource, dimension, or image contract is invalid` 并拒绝执行：

| # | 位置 | 作用 |
|---|---|---|
| ① | `vulkan_shader_bundle/frozen_manifest.json` | 冻结脚本的预期值 |
| ② | build gate 生成的 `generated/shaders/manifest.json` | 编译产物记录 |
| ③ | `vulkan_runtime/vulkan_runtime.cc` 的 `kShaderManifest` | 运行时 `ValidShaderBundle()` 准绳 |
| ④ | `vulkan_shader_bundle/shader_bundle.cc` 的 `kFrozenShaderManifest` | 嵌入 bundle 的清单 |

**不要手改任何一处。** 唯一合法入口：

```bash
~/Developer/dense-bench-20260830/bench.sh <标签> [模式=photo_ref0]
```

六步流水线：编译 shader → 四处锁一起更新 → **显式重建 probe** → 12 项契约
测试 → **dump MSL 校验运行时实际加载的 SPIR-V 与 bundle 逐字节一致** →
不一致则**拒绝输出任何耗时数字**。结果自动记入 `ledger.tsv`。

---

## 二、真实基线（本文所有数字均经上述校验）

| 项 | 数值 |
|---|---|
| 官方忠实基线（单 ref photometric） | **57.9 / 56.7 s** |
| full_scene 模式逐 ref | 56.8 / 55.9 / 62.9 / 60.6 / 60.3 s |
| 全量外推（132 refs × 2 阶段 = 264 阶段） | **约 4.2 小时** |

**重要**：full_scene 与单 ref 耗时一致 ⇒ **不存在「全量路径更慢」**。
08-29 全量日志里每 ref 295–344s 是那次运行的旧代码状态（U32 rotation
灾难时代），不是路径差异。

### 当前工作树状态
- `cost_ops.glsl`：circular buffer（PR #4124 的 `112da5e`）**已撤回**，
  恢复为官方 4.1.1 的 shift-rows-up。依据是 vendored 官方源码本身
  （`patch_match_cuda.cu` sha `1aebd448…`、`gpu_mat_ref_image.h` sha `4e869dd8…`，
  与移植文件头声明逐字一致）。
- `sweep_full_openmvs_pcg.comp`：两处无条件 `barrier()`（官方 `__syncthreads()`
  的机械对应），**不依赖 subgroup==workgroup 这种 Apple 专属假设**，
  跨端目标完好。
- ⚠️ 57.590s 基线的源码 `5e5e7566…` **实物已丢失**（未进 git，全盘无副本），
  无法精确复原。但实测证明当前官方忠实版与它同档（56.7–57.9s），
  即那两处 barrier 的形态**没有可辨识的性能差异**——原交接记的 1.7% 不成立。

---

## 三、🏆 已落地的第一刀：抽样记忆化（无损，−16.4%）

| | 耗时 |
|---|---|
| 官方忠实基线 | 57.9 / 56.7 s |
| **抽样记忆化** | **48.8 / 47.3 s** |
| 提升 | **−16.4%（1.20×）** |

**逐字节验证通过**：深度图 `1118179a…`、法线图 `60873f81…` 与基线完全相同
（`cmp` 无差异）。

### 原理
官方 Monte Carlo 循环抽 15 次 source，每次触发 5 个候选的 cost 计算。
官方注释自承：*"the same source image is likely to be sampled many times"*。
漏斗实测（真实 K/R/T + 真实深度图，4000 像素样本）：**15 次抽样平均只命中
7.95 个不同 source**，其余 7 次是重复抽中已算过的 ⇒ 28 次「121 采样 + exp」
的纯重复劳动。

### 无损的三个保证（改动时必须全部维持）
1. **累加顺序不变**——仍按 `sample_index` 顺序、仍按 candidate 0..4 顺序
   往 `candidate_costs[]` 累加。浮点加法不满足结合律，顺序一变结果就变。
2. **累加数值不变**——缓存里存的就是原本会算出的那个 float。
3. **RNG 序列不变**——`ColmapXorwowUniform` 仍每轮调用一次，
   `selected_source == -1` 的 `continue` 分支保持在同一位置（它同样消耗 RNG）。

### 预测 40% vs 实测 16.4% 的落差
漏斗预测的是**调用次数**省 40%，实测拿到的是**时间**省 16.4%。
说明 kernel 不是纯算术受限——缓存本身占寄存器（`memo_costs[10][5]`），
且未被跳过的 8 次仍要跑满 121 次采样。

---

## 四、已实测排除的方向（不要重走）

| 方向 | 判决 | 依据 |
|---|---|---|
| 寄存器 spill / `spvUnsafeArray` | **不存在** | Metal 驱动 API 实测 `maxTotalThreadsPerThreadgroup` = **1024 顶满**；有 spill 时驱动会压低此值 |
| threadgroup 内存 | 不是瓶颈 | `staticThreadgroupMemoryLength` = 4224 / 32768 |
| 权重为零的采样（可剪枝） | **零个** | 真实参考图 242 万个双边权重：p1=0.15、中位 0.669，**无一** < 2^-24。官方 `sigma_spatial = window_radius` 是精配的 |
| 候选去重 | 去重率 0 | 5 个候选的 `(depth, normal)` 两两不同 |
| view 维度并行 | **上限 1.15×** | 热点 86% 在 Monte Carlo 随机抽样循环里，它不是「对 10 个视图的循环」 |
| 并发 references | **1.49× 封顶** | N=2 与 N=3 加速比**相同**（77s vs 115s），GPU 已饱和 |
| circular buffer (PR #4124) | 变慢 | 61.9s |
| subgroup barrier | 无可辨识差异 | 56.7–57.9s 同档 |
| `THREADS_PER_BLOCK` 32→96 的「2.8×」 | **数字污染，作废** | 那 2.8× 测自 elementwise kernel 从未启动、normal_map 从未初始化的坏状态；同 issue 里报告者自己后来确认 "Number of fused points: 0" |
| 非归一化像素坐标采样 | **有损** | 4 路独立验源一致：normalized 路径 `(x/N)*N ≠ x` 可差 1 ulp，source image 用 `cudaFilterModeLinear`，会改变双线性权重量化 ⇒ 输出比特必变 |
| checkerboard propagation (ACMH/ACMM) | **有损，且非 COLMAP** | ACMH 论文自述比 COLMAP 快 6.03×，但它**改变传播顺序**、是竞争方法不是 COLMAP 优化 |

### 官方对并行度上限的定性（最高权重证据）
COLMAP 维护者 ahojnnes 在 issue #2536（引文逐字核对通过）：

> "The algorithm imposes that each row or column of an image uses one cuda
> thread. Depending on the size of your images, there will be many more cores
> than can be occupied by the image. You may be able to get more out of your
> GPU by simply listing the same GPU index of your a100 multiple times."
> 结帖：*"architectural limitation of patch match explained."*

源码交叉验证（`patch_match_cuda.cu:1515-1520`）：
`sweep_block_size_.x = 32`，`sweep_grid_size_.x = (width-1)/32+1`
⇒ 2000 宽的图只有 63 个 workgroup / 2016 个线程。

---

## 五、🔑 方法论修正（本日最重要的收获）

用户点破：稀疏点云能从 Mac 上几小时压到手机 30 秒内，为什么稠密不行？

翻稀疏侧账本，**没有一刀是「把同样的活干快」**：

| 刀 | 做法 | 收益 |
|---|---|---|
| probe-gate | 512 行子采样先探，AUC 0.95 认出必死配对，**整对不匹配** | 跳过 42.6% 配对 |
| DESC-ATOMIC | 私有数组 → 共享 atomic 黑板，**消灭 290 barrier/kp** | descriptor −76~79% |
| PACK-ZERO | 金字塔层出生就住 packed 缓冲，**零拷贝** | pack 62ms → 0ms，每帧少搬 380MB |
| B1 删描述子 | descriptors 重建根本不读 ⇒ **不存** | 5.18×，省 101MB |

而 08-30 上午我尝试的**全部是「干得更快」**（寄存器、barrier、threadgroup
布局、并发、view 并行），无一奏效。改用漏斗视角后，**第一刀「少做」就见了肉**。

> 用户 08-08 立的规矩：「提速=**减少总工作量**，削峰/摊平/重分布不算提速」
> 「提案前先自问：这个改动让机器**少做**了什么？答不上来就别做。」

**接手者请照此办理**：先做漏斗实测（像 probe-gate 当初测 160 万特征的生命
周期那样），拿到「多少工作是重复的/无效的」的实数，再动刀。不要先优化。

---

## 六、当前进度与剩余差距

- 单 ref：57.2s → **47.3s**
- 全量外推：4.20 小时 → **3.47 小时**
- 叠加并发 1.49×：**约 2.33 小时**
- 目标 30 分钟 ⇒ **仍差约 4.7 倍**

### 下一步候选（未验证，按漏斗视角排）
1. `GeometricCandidateCost` 的重复——几何一致性阶段是否有同类重复劳动
2. `cost_map` 的跨步访存——PR #4124 的 `cached_costs`（该 PR 唯一无损的一刀，
   约 6 行；但 PR 标题是 `[WIP]`，作者 ahojnnes 自己弃置，官方背书要打折）
3. 每像素每 sweep 的 `PhotoCandidateCost` 还剩 8 次（记忆化后），
   其中有多少是跨 sweep 重复的？（同一像素连续 sweep 间 depth/normal 若未变，
   cost 必然相同）

---

## 七、耐久存档位置（/tmp 会清空，勿用）

```
~/Developer/dense-bench-20260830/bench.sh        唯一合法 benchmark 入口
~/Developer/dense-bench-20260830/ledger.tsv      所有经校验的数字
~/Developer/dense-bench-20260830/funnel_*.py     漏斗实测脚本
~/Developer/dense-phase0-20260829/               Phase 0 存档（各版本 shader 原件 + 基线产物）
~/Developer/dense-regstats-20260830/regstats.mm  Metal 寄存器统计探针
~/Developer/dense-msl-dump-20260830/             MoltenVK 生成的 MSL
```

---

## 八、给接手者的一句话

不要再优化 kernel 的执行效率了——寄存器、threadgroup 内存、barrier、
并行度四条路今天都被实测堵死了。**唯一见效的是减少工作量本身**。
先做漏斗，拿实数，再动刀；每一刀都必须过 `bench.sh` 的逐字节对拍。


---

# 【第二部分】批处理战线：3.26× 已实测，A 方案进行中

> 本节记录 08-30 下半场。上半场的结论（一～八章）仍然有效，但第五章
> 「方法论修正」要补一条：**减少工作量之外，还有一条同等重要的路——
> 把已有的工作喂满 GPU**。

## 九、🏆 最重要的实测：真实 kernel 的批处理曲线

用**假 batch**（`RefIndex()` 恒返回 0，全部 workgroup 重复算同一 reference，
结果是错的，纯测速）在**真实 PatchMatch shader** 上量到：

| y (=grid.y) | workgroups | 耗时 | vs y=1 | **合并 N 个 vs 串行 N 个** |
|---|---|---|---|---|
| 1 | 63 | 48.1s | 1.00× | 1.00× |
| 2 | 126 | 54.5s | 1.13× | **1.76×** |
| 4 | 252 | 70.8s | 1.47× | **2.72×** |
| 8 | 504 | 118.0s | 2.45× | **3.26×** |

**读法**：y=8 时 8 个 reference 合并只要 118s，串行要 8×48.1=385s ⇒ 加速 3.26×。

⚠️ 这比合成微基准（`~/Developer/dense-regstats-20260830/dispatch_overlap.mm`
量到 1.66×）**好一倍**。真实 kernel 算术强度更高、访存更规整，GPU 更容易
靠多 workgroup 隐藏延迟。**不要用合成微基准的数字做决策**。

外推：
| | 单 ref 均摊 | 全量 264 阶段 |
|---|---|---|
| 现在（MEMOIZE-1） | 47.3s | 3.47 小时 |
| N=4 | 17.4s | 1.28 小时 |
| **N=8** | **14.7s** | **1.08 小时** |
| 目标 | 6.8s | 0.5 小时 |

## 十、🔴 MoltenVK 串行 encoder：多次小 dispatch 永远不会重叠

`MoltenVK/Commands/MVKCommandBuffer.mm` 逐字：

```objc
static MTLDispatchType getDispatchType(MVKCommandUse use) {
    switch (use) {
        case kMVKCommandUseAccumOcclusionQuery: return MTLDispatchTypeConcurrent;
        default:                                return MTLDispatchTypeSerial;
    }
}
```

**所有 compute 命令都进串行 encoder。** 这是「同一 command buffer 连发多个
dispatch 零收益」的确定性解释——不是驱动没优化，是写死的。

⇒ **提占用率的唯一合法路径是把 N 份工作合并进一次 dispatch**（grid.y = N）。

（可以 vendor 一份 MoltenVK 把它改成 Concurrent —— **不要做**，分叉上游、
跨端不可移植。）

## 十一、可逐字抄的范本：llama.cpp Vulkan 后端

`ggml/src/ggml-vulkan/vulkan-shaders/mul_mat_vec_base.glsl`：

```glsl
const uint batch_idx = gl_WorkGroupID.y + p.base_work_group_y;
```

主机侧 `ggml-vulkan.cpp` 配套：按 `maxComputeWorkGroupCount` 切块循环，
把已消费偏移写进 push constant，一份 descriptor set 覆盖全部 batch。
**生产级、跑在 iOS(MoltenVK)/Android/桌面全平台**，正合本产品的跨端约束。

**布局决策：连续大 buffer + 固定 stride，不用 descriptor array**
- cuBLAS 官方为 strided-batched **放弃指针数组**（指针数组要付四笔开销）
- Android descriptor indexing 支持度仅 **76.71%**，本产品必须跨端

## 十二、跨端硬限（决定 N 的上限，必须运行时检查）

| 限值 | iOS (MoltenVK) | Android 实测 | Vulkan 核心保底 |
|---|---|---|---|
| `maxImageArrayLayers` | 2048 | **495 份机型只有 256** | 256 |
| `minStorageBufferOffsetAlignment` | 16B | **587 份是 256B** | 256B |
| `maxPerStageDescriptorStorageBuffers` | 31 | Baseline Profile 保证 **4** | 4 |
| `maxComputeWorkGroupCount` 每维 | — | — | 65535 |

🔴 源图纹理数组需要 **N × num_sources 层**。Android 大量机型上限 256
⇒ **N ≤ 25**（num_sources=10 时）。必须运行时校验，不能写死。

## 十三、A 方案的已知卡点

**push constant 是全局 ABI，不是 sweep 私有**：
- 被 4 个 shader 共享（`compute_initial_cost` / `rotate_normal_f32` /
  `init_normal_unavailable` / `openmvs_pcg_initialization_layout`）
- `include/official_dense/patch_match_abi.h` 里有**逐字段偏移断言**，
  一路钉到 124 字节；加字段会撞 `static_assert`（fail-closed ABI 冻结）
- 还有 `abi_tests/patch_match_abi_test.cc` 在守

⇒ 加 `base_work_group_y` / `batch_count` 要五处同步。

## 十四、内存必须先压（从可选变必做）

N=8 需要 8 × 3.31GB = **26.5GB**，机器只有 18GB。
交接原文第九章早已指出的两处冗余，现在成了 N=8 的前置条件：
1. arena 给不少 map 保留了 **4 份 rotation 版本**，官方峰值更接近
   **current + destination 两缓冲**
2. photometric 阶段分配了该阶段用不到的 source-depth / mask / readback /
   graph / U32 gray 资源

目标：**压到 ~1.6GB/ref** ⇒ N=8 只需 12.8GB，安全。
这条对手机端同样是刚需（内存更紧张）。

## 十五、被否掉但值得记录的岔路

**ACMH/ACMM 红黑棋盘传播**：`grid = (W/32) × ((H/2)/16)` ≈ **2961 个
workgroup**，比现状多 47 倍，不需要任何 batching 就填满 GPU。
fixstars CUMVS（比 ACMM 快 5.7×）、OpenMVS CUDA 后端全是这个形态。
Fixstars 讲义原话：*顺序传播发挥不出 GPU 性能，解法是红黑棋盘*。

❌ **改变传播顺序 ⇒ 输出不同 ⇒ 违反逐字节铁律**。产品选择是
「长期工程维护成本优先，用 COLMAP」，所以这条只记录不采纳。
（质量排序：MapAnything > CasDiffMVS > COLMAP，选 COLMAP 是工程决策。）

## 十六、B 方案（plan 交错）的结局

已实现并通过 12/12 契约测试，`Validate()` 认可交错形态，N=2 产物
**逐字节相同**，submit 从 46 降到 25 —— **功能全对，但零加速**
（94.6s，每 ref 47.3s）。原因就是第十章的 MoltenVK 串行 encoder。

代码保留在树上：`dispatch_plan.cc` 的 `AppendImagesInterleaved` +
`validate_images_interleaved`。它不是白做——A 方案的 dispatch 维度改造
要用到同一套多 image plan 基础设施。

## 十七、当前工作树状态（A 方案进行中）

- ✅ `sweep_full_openmvs_pcg.comp`：`RefIndex()` / `SourceLayer()` 索引改造
  已完成，push constant 已加 `base_work_group_y` + `batch_count`
- ✅ `rng/colmap_xorwow.glsl`：RNG 状态平面加 ref 偏移（条件编译
  `PW_XORWOW_REF_BATCHED`，因该文件被多个一维 shader 共享）
- ✅ `dispatch_plan.cc`：交错 plan + 校验
- ✅ `frozen_scene_probe.cc`：`PrepareInputsMulti` + `ExecuteReferenceBatch`
  + `photo_batch` 模式（`PW_DENSE_PROBE_BATCH_SIZE`）
- ✅ ~~ABI 头 + 4 个共享 shader 的 push constant 同步~~ → **改为「不需要同步」**，
  见第十八节：两个新字段已删除，`PatchPC` 保持 128 字节不变
- ✅ **arena：rotation 4 份 → 2 份，3.31 GB → 2.04 GB/ref，逐字节相同**（第十九节）
- ⬜ **arena：N 份资源合并成连续 buffer + stride**
- ⬜ 纹理数组 N×10 层 + 运行时校验
- ⬜ `WritesFor()` descriptor 绑定
- ⬜ 主机侧切块循环（抄 llama.cpp `base_work_group_y`）

⚠️ 假 batch 测速版（`RefIndex()` 恒 0）**已撤销**，勿从
`~/Developer/dense-phase0-20260829/` 里误取那一版。


---

## 十八、push constant 不加字段（2026-08-30 定案）

A 方案原计划抄 llama.cpp，给 `PatchPC` 加 `base_work_group_y` + `batch_count`。
**推翻，两个字段都不加**，`RefIndex()` 直接写 `gl_WorkGroupID.y`。

三条理由，第一条是硬约束：

1. **128 字节是跨端红线。** `PatchPC` 现在正好 `sizeof == 128`，而 Vulkan 规范
   对 `maxPushConstantsSize` 的**强制下限就是 128**（Required Limits 表）。加
   8 字节会掉出保证区间，低端安卓/鸿蒙机可能直接 `vkCreatePipelineLayout`
   失败 —— 与用户的「100% 跨端」硬约束正面冲突。
   > ⚠️ 结构里 byte 28 那个 `reserved` **不是空槽**：
   > `vulkan_runtime.cc:1045` 往里写 NCC 归一化位，
   > `sweep_contract.h:50` 声明 sweep 会消费它。别再打它主意。
2. **`base_work_group_y` 是死代码。** 它只在需要按
   `maxComputeWorkGroupCount[1]` 切块时才非零，而该项规范下限 65535；
   本管线 N 被显存卡在 ≤6（2.04 GB/ref，14 GB 预算）。
3. **`batch_count` 本来就没被读过**（llama.cpp 里也只是声明）。

**收益**：`patch_match_abi.h` 的全部 byte-offset `static_assert`、
`abi_tests/patch_match_abi_test.cc`、以及共享该结构的 4 个 shader
（`compute_initial_cost.comp` / `rotate_normal_f32.comp` /
`init_normal_unavailable.comp` / `openmvs_pcg_initialization_layout.glsl`）
**一个字都不用改**。原交接文件里那条「ABI 同步」待办直接消失。

---

## 十九、rotation 4 → 2 压缩（2026-08-30 完成，逐字节相同）

### 结论

| 项 | 改前 | 改后 |
|---|---|---|
| 单 reference 显存（photometric） | 3.31 GB | **2.04 GB** |
| 去重后真实占用 | — | 1.884 GB（35 个唯一 alias group） |
| 18 GB 机器（留 4 GB 系统）可批 N | 4 | **6** |
| 产物 | — | 与基线**逐字节相同** |

### 官方依据

`patch_match_cuda.cu:1810 PatchMatchCuda::Rotate()` 每次只 `new`
**一个**临时目标，rotate 后 `swap`，旧的随 `unique_ptr` 立刻析构
⇒ **官方自己的活跃集也只有 {当前, 目标} 两份**，4 份是我们的实现冗余。

### 枚举证据（不靠推理）

`~/Developer/dense-regstats-20260830/rot_liveness.cc`
对官方 plan 全量枚举（`kPhotometricOnly` 273 步 / `kFull` 552 步）：

```
出现过的 (rotation_before → rotation_after) 组合只有
  (0→0)(0→1)(1→1)(1→2)(2→2)(2→3)(3→0)(3→3)
非相邻步骤数 = 0  ✅
```

即任何一步引用的 rotation 只可能是 `{r}` 或 `{r, r+1}`。
又因偶数轮是 W×H、奇数轮是 H×W（`resource_arena_plan.cc:234`），
**按 `rotation & 1` 分两组复用物理缓冲，尺寸自动对齐、且永不自我覆盖**：

```
rotate 0→1 读 slot0 写 slot1     2→3 读 slot0 写 slot1
rotate 1→2 读 slot1 写 slot0     3→0 读 slot1 写 slot0
```

### 改了哪三处

1. `vulkan_resource_arena/resource_arena_plan.cc`
   - 新增 `ParityAliasPool`（按 `(binding, rotation&1)` 发 alias group）
     + `DeviceBufferAliased()` 重载
   - rotation 循环里 10 处 `DeviceBuffer(..., &aliases)` →
     `DeviceBufferAliased(..., rot_pool.Take(binding, parity))`
2. `vulkan_runtime/vulkan_runtime.cc` — `ValidModeResources()` 里
   **两处** fail-closed 守卫从「4 个 rotation 两两不同」收紧为
   「**相邻两轮不同**」（`kRotatedBindings` 块 + `bindings[3]/[4]` 块）。
   > 这不是放松而是**校准**：它现在恰好断言真正的不变量，
   > 依然挡得住「把 rotate 的源和目标别名到同一块」这个真错误。
   > 同一轮内 `bindings[3] != bindings[4]` 一个字没动。
3. 备份：`~/Developer/dense-phase0-20260829/resource_arena_plan_BEFORE_rot2.cc`、
   `vulkan_runtime_BEFORE_rot2.cc`

### 验收

```
ledger: arena_rot2_N1_regression   47976 ms
        refidx_nopc_N1_regression  47159 ms
depth_maps/frame_000000.jpg.photometric.bin   ✅ sha256 与基线一致
normal_maps/frame_000000.jpg.photometric.bin  ✅ sha256 与基线一致
```

### 剩下的显存花在哪（去重后 1.884 GB 前 14 大）

扁平的 120 MB 级缓冲：`rot0/rot1` 各自的 `buf[2..5]`、`img[12]`、`buf[14]`、
`srcgraybuf_stage`、`mask_rb`。rot0 与 rot1 各一份是 parity 对的**必需**，
**没有再压的空间了** —— 2.04 GB/ref 是这条路的终点。

### 折算收益

| N | 显存 | 实测加速比 | 单 ref 耗时 | 132 帧全量 |
|---|---|---|---|---|
| 1 | 2.0 GB | 1.00× | 47.2 s | 3.46 h |
| 4 | 8.2 GB | 2.72× | 17.4 s | **1.28 h** |
| 6 | 12.2 GB | ~3.0×（待测） | ~15.7 s | **~1.15 h** |
| 8 | 16.3 GB ❌ 超预算 | 3.26× | 14.5 s | 1.06 h |

⇒ **N=6 是 18 GB Mac 上的上限**。手机端显存更小，N 会更小，
但 `RefIndex()` 路径与 parity 复用两项都是纯收益、不依赖 N。


---

## 二十、🔴 重新定位瓶颈：算法只占一半，另一半是 MoltenVK 绑定开销（2026-08-30）

### 先纠正我自己两个错误结论

1. **「N=8 批处理 3.26×」是错的。** 那是拿 `8×48.1/118.0` 算的，隐含假设
   整个 48.1s 都随批处理摊薄。但假 batch 实验只放大了 sweep 的工作量，
   非 sweep 部分只算了一遍。诚实的账见下表 —— 只批 sweep 的天花板是 **1.26×**。
2. **「把 dispatch 网格缩成 1 个 workgroup」不是有效的排除法。**
   缩到 1 个 workgroup 的 sweep 仍要**串行**跑完整列，本身就要 0.4–1.9s。
   我基于它做的第一版分解（sweep 21.0s / rotate 19.4s / 残留 21.8s，
   加起来 62.2s ≠ 47.3s）整个作废。**加法不成立时就是判据失效了，
   不要去解释残差，要去怀疑判据。**

### 正确的分解（用「跳过整类操作」而不是「缩网格」，加法成立）

| 部分 | 耗时 | 占比 |
|---|---|---|
| sweep | 26.7 s | 56% |
| **rotate（转置搬运）** | **20.4 s** | **43%** |
| 其余全部（上传/初始化/InitialCost/回读） | ~0.3 s | <1% |
| 合计 | 47.4 s | |

> `kInitialCost` 几乎免费（缩掉它 47.3 → 48.9，在噪声内）。
> 22 次 `vkQueueSubmit`+`vkQueueWaitIdle` 也**不是**成本：
> 把它们融合成 1 次（`PW_DENSE_FUSE_SUBMITS=1`）耗时纹丝不动（47.34 vs 47.14）。

### 真正的大头：MoltenVK 的 descriptor 绑定

| 配置 | 全量 | 跳过 rotate | ⇒ rotate 成本 |
|---|---|---|---|
| argument buffers **ON**（现役） | 47.9 s | 27.5 s | **20.4 s** |
| argument buffers **OFF** | 11.5 s | 7.3 s | **4.2 s** |

⇒ **47.9s 里有约 36.4s（76%）是 MoltenVK 的 per-dispatch descriptor 绑定开销**，
真正的 GPU 计算只有 ~11.5s。rotate 的 20.4s 里，16.2s 是绑定开销、4.2s 才是转置本身。

### ⚠️ `MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0` 不能用

它把 47.9s 压到 11.5s（4.17×），但**产物不逐字节相同**：
深度图 99.98% 的元素不同（中位差 0.008，最大 206.9），法线图 94.3% 不同。
量级正常、不像绑错缓冲，形态像**随机采样序列被改变**。
现役 argbuf=ON 才是对过官方的那条路 ⇒ 这条捷径不无损，**否决**。

另外两个配置试过、都无效：
`MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=2` → 47.4 s（逐字节同，但没提速）；
`MVK_CONFIG_PREFILL_METAL_COMMAND_BUFFERS=1/2` → 47.3 s（同上）。

### 下一刀（两把，都是「减少工作量」，都按构造逐字节无损）

**刀 1：融合 rotate 的逐层 dispatch。**
`vulkan_runtime.cc` 的 `RotateF32`/`RotateU32` 里是
`for (layer = 0; layer < source.array_layers; ++layer)`，
**每层一个 dispatch + 每层一次 `AllocateAndBindDescriptorSet`**。
10 个源 ⇒ 单个 rotate 步要 10 次。全程 705 个 dispatch 里约 680 个是 rotate。
改成一次 dispatch、用 `gl_WorkGroupID.z` 当 layer ⇒ **680 → 200**。
各层互相独立、数学与顺序都不变 ⇒ 按构造逐字节相同。
按 24 ms/次的绑定开销估算，省 ≈ 11.5 s。

> 🔴 这一刀对 A 方案是**前置条件**：批处理后 `layers_n = num_sources × N`，
> N=6 时逐层循环会变成 **60 次** dispatch，绑定开销直接翻 6 倍，
> 不先合并的话 A 方案会被它吃掉。

**刀 2：rotate 换成分块转置。**
`mat_ops/rotate_f32.comp` 现在是朴素逐元素转置：
```glsl
int output_x = input_y;
int output_y = pc.width - 1 - input_x;
output_data.values[output_index] = input_data.values[input_index];
```
`local_size = (32,1,1)`，读合并、**写完全散列**（跨 `output_pitch`）。
换成 32×32 共享内存分块转置可让写也合并。同一组 float 的同一个置换，
不做任何算术 ⇒ 按构造逐字节相同。目标：4.2 s → ~1 s。

### 折算

| 状态 | 单 ref | 132 帧 |
|---|---|---|
| 今日起点 | 56.7 s | 4.16 h |
| MEMOIZE-1 + ROT-2 后（现状） | 47.4 s | 3.48 h |
| 刀 1 + 刀 2 后（估算） | ~32 s | ~2.3 h |
| 再叠 A 方案 N=6（估算） | 待测 | 待测 |

### 遗留的测量脚手架（用完必须删）

`vulkan_runtime.cc` 里这些 env 开关**只服务测量，默认全关**，
逐字节回归在它们在位时已通过：
`PW_DENSE_SHRINK_SWEEP` / `PW_DENSE_SHRINK_ROTATE` / `PW_DENSE_SKIP_ROTATE` /
`PW_DENSE_SHRINK_INITIAL` / `PW_DENSE_FUSE_SUBMITS` / `PW_DENSE_TRACE_STEPS`，
以及 `SubmitWaitAndContinue` 里的 `submit_ms/begin_ms` 计时
（在 `PW_OFFICIAL_DENSE_VULKAN_DIAGNOSTIC` 里）。
另：`PW_DENSE_FAKE_BATCH_Y` 是旧的假 batch 开关，A 方案落地时换成真的 N。


---

## 二十一、🔴 第二十节的分解是错的：减法式测量被数据损坏污染

第二十节说「rotate 占 20.4 s / 43%」。**这个结论被两个独立的实验推翻。**

### 两把刀都落地了，都逐字节相同，都零收益

| 刀 | 改动 | dispatch | 耗时 | 逐字节 |
|---|---|---|---|---|
| 基线 | — | 705 | 47.1 s | — |
| 刀 1 层融合 | rotate 逐层 dispatch → 一次 dispatch,层号取 `gl_WorkGroupID.z` | **205**（−71%） | 47.2 s | ✅ |
| 刀 2 分块转置 | 朴素逐元素 → 32×32 共享内存分块,读写两端都合并 | 205 | 47.5 s | ✅ |

删掉 500 次 dispatch + 500 次 descriptor 分配 ⇒ 零变化。
把非合并的写变成合并的写 ⇒ 零变化。
**两条独立的路径都证明 rotate 不在关键路径上。**

### 错在哪

`PW_DENSE_SKIP_ROTATE` / `PW_DENSE_SHRINK_ROTATE` 让后续 sweep 读到
**未经旋转的数据**。PatchMatch 的代价、分支与收敛全都变了，sweep 自己
就跑得不一样快。于是「全量 − 跳过 rotate = rotate 的成本」这个减法
测的根本不是 rotate。

> 🔴 **规律（今天第三次被这条绊倒，前两次是「缩网格≠变便宜」和
> 「加法不成立时去解释残差」）：**
> 一个测量臂如果**改变了被测系统后续的计算内容**，它的差值就不是
> 被移除部分的成本。只有「不改变计算内容、只改变实现方式」的臂
> （层融合、分块转置）才是可信的——而它们的判据是**耗时变化**，
> 不是我的推理。

同理，第二十节里基于 `O = 26.2 s` 得出的「只批 sweep 天花板 1.26×」也不成立：
那个 26.2 s 里，被「缩成 1 个 workgroup」的 20 次 sweep 自己就占了约 22 s
（实测单次 372 ms / 1850 ms 交替）。

### 现在站得住的结论

- **sweep 占绝大部分**，与原交接文件「热点 86% 在随机采样循环」一致。
- `argbuf=OFF` 的 11.5 s **不是可达目标**：它产物不同 ⇒ 在算别的东西。
- rotate 的两把刀**仍然保留**：逐字节相同、dispatch −71%、kernel 质量更好，
  且**层融合是 A 方案的前置**（N=6 时逐层循环会变成 60 次 dispatch）。

### 不要再做的测量

- ❌ 缩网格 / 跳过整类 dispatch（污染后续计算）
- ❌ 改迭代次数（`PW_DENSE_ITERATIONS` 已加，但 plan 校验把 iterations
  钉死在官方的 5，非 5 一律 `ok:false`，这条路封死）
- ✅ **唯一可信的下一步：把 A 方案做到能真跑 N=2，直接量每-ref 耗时。**
  不需要任何分解。

---

## 二十二、A 方案剩余工作（已重新盘过，比原计划大）

已完成：
- ✅ shader `RefIndex()`（不加 push constant 字段，见第十八节）
- ✅ arena `batch_count`，线性验证：N=1/2/4/6/8 每 ref 恒为 2.04 GB
- ✅ **descriptor 无需改动**——`WritesFor` 里 sweep 绑的本来就是整块 buffer，
  N× 变大后同一份 descriptor 直接可用，shader 用 `RefIndex()` 自己寻址
- ✅ rotate 层融合（前置条件）

剩余：
1. ⬜ **arena：所有 `array_layers` 参数一并乘 batch。** 现在只有
   `num_sources` 那几个乘了（`layers_n`）。`binding[0]`（深度,`1U`）、
   `binding[1]`（法线,`3U`）、三个 readback 的层数还是 1/3，
   但 buffer 已经 N× 大 ⇒ rotate 的 `z = array_layers` 只会转 ref 0 那一份。
   改法：把这些 `1U`/`3U` 改成 `batch`/`3U*batch`，
   则 `plane_bytes = range / array_layers` 自动是「每 ref 每层」，
   rotate 的 z 维统一覆盖所有 ref × 所有层。
2. ⬜ **其余 kernel 也要有 ref 维**：`kInitializeRng`、`kInitializeRandomDepth`、
   `kInitializeRandomNormal`、`kInitializeSelectionAndWorkspace`、
   `kReferenceFilter`、`kInitialCost`、`kSelectCalibrationAndPose`。
   它们都是按整幅图的一维/二维网格，N 份数据需要各自跑到。
   （原计划漏了这一条——原以为只改 sweep 就够。）
3. ⬜ 主机侧 sweep dispatch 的 y 维换成真的 N（现在还是
   `kFakeBatchY`，读 `PW_DENSE_FAKE_BATCH_Y`）
4. ⬜ `batch_count` 从 probe 一路传到 executor / arena / runtime
5. ⬜ 运行时校验 `maxImageArrayLayers`（N=6 → 60 层，安卓下限 256，安全）
6. ⬜ 每个 ref 各自的上传（`PrepareInputsMulti` 已在 probe 里）
7. ⬜ 验收：每个 reference 的产物与单独跑逐字节相同

### 今日 ledger

```
arena_rot2_N1_regression   47976 ms  ✅逐字节
refidx_nopc_N1_regression  47159 ms  ✅逐字节
arena_batch_N1_regression  47142 ms  ✅逐字节
layerfuse_N1               47246 ms  ✅逐字节  dispatch 705→205
tiled_rotate_N1            47520 ms  ✅逐字节
```

### bench.sh 已通用化

第 2 步原来把 sweep 写死，改 `mat_ops/rotate_f32.comp` 时
`regenerate_frozen_bundle.py` 会报 `source identity changed`。
现在改成遍历 `frozen_manifest.json` 的全部 shader，
对任何 source/spirv 哈希变了的条目同时更新四处锁，并打印更新了哪些。
备份：`~/Developer/dense-bench-20260830/bench.sh.bak`。


---

## 二十三、🏆 A 方案落地：N=6 实测 2.56×，全部逐字节无损

### 实测曲线（每个 reference 的深度图与法线图都与单跑基线逐字节相同）

| N | 总耗时 | 每 reference | 加速比 | 显存 | 校验 |
|---|---|---|---|---|---|
| 1 | 47.1 s | 47.1 s | 1.00× | 2.0 GB | ✅ |
| 2 | 56.8 s | 28.4 s | **1.66×** | 4.1 GB | ✅ 2/2 |
| 4 | 82.3 s | 20.6 s | **2.29×** | 8.2 GB | ✅ 4/4 |
| 6 | 110.3 s | 18.4 s | **2.56×** | 12.2 GB | ✅ 6/6（12 个文件） |

N=8 需要 16.3 GB，超出 14 GB 预算，未测。

### 今日总账（photometric，单 reference）

| 阶段 | 每 ref | 132 帧 |
|---|---|---|
| 今晨起点 | 56.7 s | 2.08 h |
| MEMOIZE-1 | 47.4 s | 1.74 h |
| + ROT-2 / 层融合 / 分块转置（显存 3.31→2.04 GB，耗时持平） | 47.1 s | 1.73 h |
| **+ A 方案 N=6** | **18.4 s** | **0.67 h** |

⇒ **3.08×，全程逐字节无损。**

### 验收方法：批里放 N 份同一个 reference

不需要把 N 份不同输入的 plumbing 全接通，就能同时拿到**真实的加速比**
（工作量与访存形态与真跑 N 个 reference 完全一致）和**更强的正确性判据**：
N 个输出平面**每一个**都必须等于单跑基线。任何跨 reference 的越界、
stride 算错、RNG 串台都会立刻暴露 —— 事实上抓到了两个。

### 🔴 逐字节对比抓到的两个真 bug（静态推理全都放过了）

**bug 1：xorwow RNG 的 reference 步长写成 4，实际是 6。**
`rng/colmap_xorwow.glsl` 里 `RefIndex() * 4u * height * width`。
但 xorwow 状态是 `v0..v4` 加 `d` 共 **6** 个 uint32/像素
（binding 6 = `bytes_24p`，`array_layers = 6`）。
写成 4 会让 reference 1 的状态压在 reference 0 的第 4、5 分量上。

**bug 2：法线图套用了 `GpuMatIndex`（num_sources 层步长），实际只有 3 层。**
12 处 `normal_map.values[GpuMatIndex(...)]`。ref 步长成了 `num_sources*W*H`，
N=2 时 reference 1 的法线写落到 `10*W*H`，越出法线缓冲（`6*W*H`），
被 `robustBufferAccess` 夹回范围内 —— **正好砸在 reference 0 的数据上**。
症状是「`ok:true`、跑得通、连 reference 0 都算错」，99.95% 的深度值变化、
量级却完全正常（6.75 → 6.94）。已加 `NormalIndex()`。

> 两个 bug 的共同形态：**跑得通、不报错、数值看着正常**。
> 只有逐字节对比抓得住。这是今天第二次验证 MEMOIZE-2 那条教训。

### 改动清单

| 层 | 改动 |
|---|---|
| shader `sweep` | `RefIndex()=gl_WorkGroupID.y`；`NormalIndex()`；`ref_k/ref_inv_k` 改从位姿表尾部按 `RefIndex()` 读 |
| shader `compute_initial_cost` | 同样加 `RefIndex()`/`SourceLayer()`，dispatch 的 y 维改 N |
| shader `colmap_xorwow` | ref 步长 4→6 |
| arena | `batch_count`；所有字节量与 `array_layers` 乘 N；位姿区每 ref 加 8 个 float 的尾部 |
| runtime `WritesFor` | 新增 `reference/batch` 参数，把「整块 N 份」的 buffer 切成本 ref 那一份 |
| runtime `Dispatch` | 纯 buffer 的 kernel 按 reference 逐次 dispatch（**零 shader 改动**）；`kFullSweep`/`kInitialCost` 绑了纹理数组切不了，走 shader 内批处理 |
| runtime `ValidRequest` | 全部期望字节数与层数按 batch 放大（fail-closed 校验替我枚举出了 RNG 层数、workspace、法线层数等一串遗漏） |
| probe | `PW_DENSE_BATCH_N`；批处理时把 1..N-1 的平面也写盘（否则等于没验跨 reference） |

### 为什么 per-ref 参数放在位姿表尾部

实测冻结场景 132 帧：**内参 132 个不同组合、深度范围 132 个不同值**
（`depth_min ∈ [0.79, 3.78]`，`depth_max ∈ [4.61, 28.36]`）。
一次 dispatch 只有一份 push constant ⇒ 逐 reference 的参数必须按
`RefIndex()` 寻址。这就是 cuBLAS strided-batched / llama.cpp 的同一条原则，
只是对象从数据换成了参数块。

放位姿表尾部而不是新开 descriptor binding：descriptor 布局上挂着一整套
fail-closed 契约检查，动它的代价远大于把 stride 从 `num_sources*43`
改成 `num_sources*43 + 8`。sweep 只用 `ref_k`/`ref_inv_k` 两个 vec4，
`depth_min/max` 它根本不读 —— 那两个在按 reference 逐次 dispatch 的
kernel 里，各自带自己的 push constant。

### 剩余

- ⬜ 把「N 份同一个 reference」换成「N 份不同 reference」：需要 probe 侧
  按 shader 的 stride 约定拼接 N 份输入（参考图/源图/位姿/内参）。
  GPU 侧已经全部就绪，纯 host 端 plumbing。
- ⬜ 清掉测量脚手架：`PW_DENSE_SHRINK_*` / `PW_DENSE_SKIP_ROTATE` /
  `PW_DENSE_FUSE_SUBMITS` / `PW_DENSE_TRACE_STEPS` / `PW_DENSE_ITERATIONS` /
  `PW_VR_FAIL` / `submit_ms` 计时
- ⬜ geometric 阶段还没测（今天全部数字都是 photometric）
- ⬜ 运行时校验 `maxImageArrayLayers`（N=6 → 60 层，安卓下限 256，安全）


---

## 二十四、收尾三件事（2026-08-31）

### 1️⃣ 批处理的理论天花板：≈ 13–14 s/ref，已经吃掉 75%

对 N=1/2/4/6 的实测做最小二乘：

```
T(N) = 32.7 + 12.75·N   (总耗时,秒)
⇒ 每 ref = 32.7/N + 12.75
```

**边际成本在上升**（N=1→2 是 9.70 s，2→4 是 12.75 s，4→6 是 14.00 s），
说明 GPU 已接近吃满，批处理这条杠杆快到头了：

| N | 每 ref | 132 帧 | 显存 |
|---|---|---|---|
| 6（现状） | 18.4 s | 0.67 h | 12.2 GB |
| 8 | 16.8 s | 0.62 h | 16.3 GB ❌ 超预算 |
| 12 | 15.5 s | 0.57 h | 24.5 GB ❌ |
| N→∞ | **12.8 s** | 0.47 h | — |

⇒ **再加 N 已经不划算**。要往下走必须换「减少工作量」的刀。

### 2️⃣ N 份不同 reference：完成，每一个都与它自己单跑逐字节相同

新增 `PrepareFusedBatch()`：把 N 个 reference 拼成**一个** arena 输入
（区别于 B 方案的 N 个独立 arena）。拼接顺序逐字对应 shader 的 stride 约定：

```
reference_u32 : [ref0 的 W*H][ref1 的 W*H]...        ← PixelIndex()
source_gray_* : [ref0 的 S 个源][ref1 的 S 个源]...   ← SourceLayer()
batch_calib   : 每 ref 一份,arena 散布成 [rotation][ref] ← PoseIndex()
```
`num_sources` 仍是**每 reference** 的源数（它是 shader 的 stride），不乘 N。

**验收（最强形态）：批内第 i 个 reference 的产物 vs 它自己单跑的产物**

| N | 总耗时 | 每 ref | 加速比 | 逐字节 |
|---|---|---|---|---|
| 2 | 56.6 s | 28.3 s | 1.66× | ✅ 4/4 文件 |
| 4 | 82.4 s | 20.6 s | 2.28× | ✅ 8/8 文件 |
| 5 | 97.2 s | 19.4 s | 2.42× | ✅ 10/10 文件 |

> 与「N 份同一帧」量到的 20.6 s（N=4）完全一致 ⇒ 之前那个代理测量是诚实的。

顺带补齐的两处逐 reference 参数（实测 132 帧内参与深度范围**逐帧都不同**）：
- `compute_initial_cost.comp` 用了 16 处参考内参，而它是 shader 内批处理的
  ⇒ 改从位姿表尾部按 `RefIndex()` 读（与 sweep 同一套）。
- `init_depth_openmvs_pcg.comp`（用 `depth_min/max`）与
  `init_normal_openmvs_pcg.comp`（用 `ref_inv_*`）是按 reference 逐次
  dispatch 的 ⇒ 新增 `RotationCalibration::reference_patches`，
  每次 dispatch 换成该 reference 自己的 push constant。

### 3️⃣ 测量脚手架已全部清除

删掉：`PW_DENSE_SHRINK_SWEEP` / `PW_DENSE_SHRINK_ROTATE` /
`PW_DENSE_SKIP_ROTATE` / `PW_DENSE_SHRINK_INITIAL` / `PW_DENSE_FUSE_SUBMITS` /
`PW_DENSE_TRACE_STEPS` / `PW_DENSE_ITERATIONS` / `PW_DENSE_FAKE_BATCH_Y` /
`ShrinkEnabled()` / `PW_VR_FAIL` 宏与 15 个调用点 /
`SubmitWaitAndContinue` 里的 `submit_ms`·`begin_ms` 计时。

保留（生产开关，非脚手架）：`PW_DENSE_BATCH_N`、`PW_DENSE_BATCH_SAME`
（后者是回归专用：N 个槽装同一帧）。

清理后回归：12 个契约测试全过，N=1 47.0 s 逐字节相同。

### 4️⃣ geometric 首次实测：51.8 s/ref —— **它现在是大头**

`geo_ref` 模式，slot 0，前置是它自己加 10 个源的 photometric 产物：

```
"ok":true  "stage":"geometric_reference_complete"
"execution_ms":51844  "dispatch_count":204
```

dispatch 数 204（photometric 是 205），形态几乎一样 ⇒ 大概率同样吃批处理。

**全流程每帧的真实构成：**

| | 每帧 | 132 帧 |
|---|---|---|
| photometric（N=6 批处理后） | 18.4 s | 0.67 h |
| **geometric（未批处理）** | **51.8 s** | **1.90 h** |
| 合计 | 70.2 s | **2.57 h** |

⇒ **下一刀非常明确：把融合批扩到 geometric。** 若拿到同样的 2.5×，
geometric 降到 ~20 s，全流程每帧 ~38 s、132 帧 **~1.4 h**。

需要做的：`PrepareFusedBatch` 目前只走 `kPhotometricOnly`
（`ExecuteReference` 里的分支）。geometric 还要额外拼 N 份
`source_depth_f32` / `reference_depth_f32` / `reference_normal_f32`，
并让 `sources[]` 的 `image_slot`（geometric 走 `UINT32_MAX` 外部深度那条路）
与一致性图的容量按 N 处理。`ValidRequest` 的 geometric 分支已经按 batch
放大过，arena 与 runtime 都是 phase-agnostic 的。


---

## 二十五、🏆 融合批扩到 geometric（2026-08-31 完成）

### 验收：N=4 份**不同** reference，12 个文件全部逐字节相同

| ref | depth_maps | normal_maps | consistency_graphs |
|---|---|---|---|
| 0 | ✅ | ✅ | ✅ |
| 1 | ✅ | ✅ | ✅ |
| 2 | ✅ | ✅ | ✅ |
| 3 | ✅ | ✅ | ✅ |

对比基准是**每个 reference 自己单跑 `geo_ref` 的产物**。
一致性图也逐字节相同 —— 它是 StereoFusion 的输入，不能只验深度法线。

### 加速比

| N | 总耗时 | 每 ref | 加速比 | 显存 |
|---|---|---|---|---|
| 1 | 51.9 s | 51.9 s | 1.00× | 2.21 GB |
| 2 | 65.5 s | 32.7 s | 1.59× | 4.42 GB |
| 4 | 98.9 s | **24.7 s** | **2.10×** | 8.83 GB |
| 6 | 未测 | — | — | 13.25 GB（装得下） |

> N=6 显存没问题，但验收需要 slot 4/5 **各自的 10 个源**也有 photometric 产物，
> 当前前置只备到 slot 0–3 的源。这是前置数据的事，不是代码的事。

### 全流程账（132 帧）

| | 单帧 | 132 帧 |
|---|---|---|
| 今晨起点 | ~119 s | 4.37 h |
| 改造前（今天前面几刀之后） | 99.0 s | 3.63 h |
| **现在**（photometric N=6 + geometric N=4） | **43.1 s** | **1.58 h** |

⇒ 相对今晨 **2.77×**，全程逐字节无损。

### geometric 比 photometric 多改的几处

1. **一致性图逐 reference 序列化。**
   原来 `SerializeConsistencyGraph` 一次处理一整幅图。批处理后：
   掩码按 `r * W*H*num_sources` 取片、源索引按 `r * num_sources` 取片、
   输出写在 `values + r * (capacity/batch)` 各占独立一片、
   计数写 `value_count[r]`。
   `ConsistencyGraphReadback::value_count` 从「一个 size_t 指针」
   变成「指向 batch_count 个计数的数组」（N=1 时完全等价）。
2. **源清单变成 N 份。** 新增 `ResourceArenaImageInput::batch_sources`
   （长度 `num_sources * batch`）。它同时喂两处：一致性图的源索引表、
   以及 `kUploadSourceDepthMaps` 的逐层拷贝清单
   （层号 = `ref*num_sources + source`）。
   `source_count` 仍是**每 reference** 的源数（它是 shader 的 stride）。
   photometric 的占位 owner 是 `image_slot = 0`；
   geometric 走外部流入深度，owner 是 `UINT32_MAX`、
   `image_index` 是那个源自己的真实 index —— `ValidInput` 会核对这一对。
3. **流入的三份数据也按 N 拼接**（`geo_ref` 入口）：
   `source_depth` / `reference_depth` / `reference_normal`。
4. **`ValidRequest` 的 geometric 分支按 batch 放大**：
   `source_depth_layer_count`、`destination_layer` 上界、
   一致性图的 `source_image_count`、掩码字数、图值容量。
   `batch` 的定义前移到 `base` 之后（geometric 的校验在字节数计算之前）。

### 一个踩过的坑

逐 reference 导出时基准写成了 `readback` 而不是 `export_readback`。
geometric 导出里 photometric 的两份来自**流入的输入**
（`reference_depth_f32` / `reference_normal_f32`），不是回读缓冲；
用错基准会让 `WriteDiagnosticColmapMaps` 拿到空指针，
报 `incomplete diagnostic readback`。

### ⚠️ 机器磁盘已满

`/System/Volumes/Data` **896 GiB / 926 GiB，100%**。
本战役的全部产物只有 3 GB 出头，大头不在这里。
今天两次被 `ENOSPC` 打断（一次连 Bash 都跑不了，只能用 Write 工具
截断已知路径的大文件才挤出空间）。**下次开工前先 `df -h`。**


---

## 二十六、geometric 完整曲线与最优 N（2026-08-31）

补齐 slot 4/5 及其源的 photometric 前置后，拿到两阶段的完整曲线。
**每个点都做了「批内第 i 个 reference vs 它自己单跑」的逐字节验收。**

### geometric

| N | 每 ref | 加速比 | 显存 | 验收 |
|---|---|---|---|---|
| 1 | 51.9 s | 1.00× | 2.21 GB | — |
| 2 | 32.7 s | 1.59× | 4.42 GB | ✅ |
| 3 | 27.3 s | 1.90× | 6.62 GB | ✅ 9 文件 |
| 4 | 24.8 s | 2.09× | 8.83 GB | ✅ 12 文件 |
| **5** | **23.7 s** | **2.19×** | 11.04 GB | ✅ 15 文件 |
| 6 | 24.5 s | 2.12× | 13.25 GB | ✅ 18 文件 |

> N=6 第一次量到 26.0 s，复测两次是 24.3 / 24.8 s ⇒ 首测是噪声。
> N=4–6 基本持平，**N=5 是最优点**，再往上显存开始和系统争。

### photometric

| N | 每 ref | 加速比 | 显存 |
|---|---|---|---|
| 1 | 47.1 s | 1.00× | 2.04 GB |
| 2 | 28.4 s | 1.66× | 4.08 GB |
| 4 | 20.6 s | 2.29× | 8.16 GB |
| 5 | 19.3 s | 2.44× | 10.20 GB |
| **6** | **18.6 s** | **2.53×** | 12.24 GB |

### 🏁 最终配置与全流程账

**photometric N=6 + geometric N=5**（两阶段分开跑，峰值显存 12.2 GB）

| | 单帧 | 132 帧 |
|---|---|---|
| 今晨起点 | ~119 s | 4.37 h |
| 批处理前 | 99.0 s | 3.63 h |
| **现在** | **42.3 s** | **1.55 h** |

⇒ 相对今晨 **2.82×**，全程逐字节无损。

### 后续可能的方向（批处理这条杠杆已到头）

两阶段的边际成本都已上升到接近饱和，再加 N 只会被显存反噬。
要继续压必须换「减少工作量」的刀 —— 与 MEMOIZE-1 同一类。

---

## 二十七、磁盘清理（2026-08-31）

开工前 `/System/Volumes/Data` **896 GiB / 926 GiB，100% 满**，
今天两次被 `ENOSPC` 打断。清掉纯构建产物与缓存，**腾出 16.8 GB**
（3.3 GB → 20 GB）：

| 类别 | 释放 |
|---|---|
| `~/Library/Caches/`（com.openai.codex 4.2G、CocoaPods 975M、Homebrew 772M、Google 639M、Codex 261M、node-gyp 62M） | ~6.9 GB |
| `~/Library/Developer/Xcode/DerivedData` | 138 MB |
| `aether_cpp/build` + `build-ios-device-dawn/build` 等 | ~4.9 GB |
| `pocketworld/build` + `.dart_tool` + `ios/Pods` 等 | ~3.3 GB |
| `pocketworld_flutter/build` + `.dart_tool` + `ios/Pods` | ~2.0 GB |
| `xrslam/build-ios-b1/build` | 41 MB |

全部是 cmake / flutter / pod 重跑就能生成的，零信息损失。

### 🔴 故意**没有**动的大项（不是「可重复产生的数据」）

| 路径 | 大小 | 为什么不动 |
|---|---|---|
| `~/.codex/sessions` | 97 GB | 会话历史记录，删了不可恢复 |
| `~/Library/Containers` | 118 GB | 各 App 的容器数据 |
| `_host_fixtures.nosync`（`cap7_day`/`cap201_*`/`loop_cap37` 等） | 13 GB | **手机采集数据**，不可再生 |
| `_artifacts.nosync`（`batch*_install_*` 等） | 49 GB | 旧装机包与历史战役产物，理论上可重建但代价大，且不确定是否仍被引用 |
| `~/.config/superpowers/worktrees/*` | 23 GB | git worktree 可能有未提交改动 |
| `~/.codex/builds` | 978 MB | 本战役正在用的 probe 构建 |

⇒ 真正的大头（97 GB 会话 + 118 GB 容器 + 49 GB 旧产物）需要你自己拍板。
