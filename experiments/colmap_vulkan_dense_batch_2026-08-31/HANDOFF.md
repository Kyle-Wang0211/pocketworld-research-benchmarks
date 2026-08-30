# COLMAP PatchMatch MVS → Vulkan 批处理:2.82× 无损提速(2026-08-30/31)

## 一句话

把官方 COLMAP 4.1.1 的 PatchMatch 稠密重建移植到 Vulkan/SPIR-V/MoltenVK 之后,
用「一次 dispatch 覆盖 N 个 reference」把单帧从 ~119 s 压到 **42.3 s**,
132 帧从 **4.37 h → 1.55 h**,**全程逐字节无损**。

## 结果

| | 单帧 | 132 帧 |
|---|---|---|
| 起点(2026-08-30 晨) | ~119 s | 4.37 h |
| **现在** | **42.3 s** | **1.55 h** |

最优配置:**photometric N=6 + geometric N=5**,峰值显存 12.2 GB。

| N | photometric 每 ref | geometric 每 ref |
|---|---|---|
| 1 | 47.1 s | 51.9 s |
| 2 | 28.4 s | 32.7 s |
| 4 | 20.6 s | 24.8 s |
| 5 | 19.3 s | **23.7 s** ← 最优 |
| 6 | **18.6 s** ← 最优 | 24.5 s |

## 验收判据(唯一可信的那个)

**批内第 i 个 reference 的产物 vs 它自己单独跑出来的产物,逐字节相同。**

- photometric:深度图 + 法线图,N=2/4/5 共 22 个文件全绿
- geometric:深度图 + 法线图 + **一致性图**,N=3/4/5/6 共 54 个文件全绿
  (一致性图是 StereoFusion 的输入,只验深度法线等于没验)

`bench/bench.sh` 是唯一合法的测速入口:编译 shader → 更新四处哈希锁 →
**显式重建 probe**(`EXCLUDE_FROM_ALL`,`make` 不会自动建)→ 12 个契约测试 →
**dump MSL 并校验运行时加载的 SPIR-V 与 bundle 逐字节一致** → 不一致就拒绝输出耗时。
这套强制校验是因为 08-30 上午出过「在旧二进制上测了三组数」的事故。

## 三条主要的刀

1. **MEMOIZE-1**(−16.4%):随机采样循环里同一个 source 被重复抽中时,
   5 个候选的代价只算一次。累加顺序、累加值、RNG 序列三者都不变。
2. **rotation 4 份 → 2 份**(显存 3.31 → 2.04 GB/ref):
   官方 `PatchMatchCuda::Rotate()` 每次只 new 一个临时目标、rotate 后 swap,
   活跃集本来就只有 {当前, 目标} 两份。用 `rot_liveness.cc` 对官方 plan
   全量枚举(273/552 步)证明「任何一步引用的 rotation 只可能是 {r} 或 {r,r+1}」。
3. **A 方案批处理**(2.5×):`RefIndex() = gl_WorkGroupID.y`,
   连续大 buffer + stride(抄 cuBLAS strided-batched / llama.cpp Vulkan 后端,
   不用 descriptor indexing —— 安卓支持度只有 76.71%,与「100% 跨端」冲突)。

## 逐字节对比抓到的三个真 bug(静态推理全都放过了)

都是「跑得通、`ok:true`、数值量级正常」的静默错误:

1. **xorwow RNG 的 reference 步长写成 4,实际是 6**
   (状态是 v0..v4 加 d 共 6 个 uint32/像素)。
2. **法线图套用了 `GpuMatIndex`(num_sources 层步长),实际只有 3 层**。
   N=2 时 reference 1 的法线写落到 `10*W*H`,越出缓冲后被
   `robustBufferAccess` 夹回来,**正好砸在 reference 0 的数据上** ——
   连 reference 0 都算错,99.95% 的深度值变化,但 6.75 → 6.94 肉眼无感。
3. **逐 ref 导出的基准写成 `readback` 而非 `export_readback`** ——
   geometric 导出里 photometric 那两份来自流入的输入而非回读缓冲。

## 被否决的路

- `MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0`:47.9 → 11.5 s(4.17×),
  但**产物不逐字节相同**(深度图 99.98% 的元素不同)⇒ 它在算别的东西,否决。
- 融合 22 次 `vkQueueSubmit`:耗时纹丝不动(47.34 vs 47.14),无效。
- rotate 层融合(dispatch 705 → 205)与 32×32 分块转置:逐字节相同但**零加速**,
  仍然保留(kernel 质量更好,且层融合是批处理的前置)。

## 🔴 方法论:三次被同一类错误绊倒

1. 「把 dispatch 网格缩成 1 个 workgroup」≠ 让它变便宜 ——
   1 个 workgroup 仍要**串行**跑完整列。
2. 分解出来的各项加起来 62.2 s ≠ 实测 47.3 s 时,
   **该怀疑的是判据,不是去解释残差**。
3. 「跳过 rotate」会让后续 sweep 读到未旋转的数据,分支与收敛全变 ——
   **一个测量臂如果改变了被测系统后续要算的内容,它的差值就没有意义**。

⇒ 只有「不改变计算内容、只改变实现方式」的臂可信,判据是耗时变化,不是推理。

## 目录

- `src/` —— Vulkan 稠密移植的全部源码(149 个文件)。
  产品端的最终归宿是 `pocketworld` 仓库的 `vendor/official_dense/`。
- `src/third_party/` **未包含**(52 MB 上游源码),pin 见 `docs/THIRD_PARTY_PINS.txt`:
  COLMAP 4.1.1、MoltenVK 1.4.2(commit `db66022459ffb663aa2b50f6b018bc2e124f5edf`)。
- `bench/` —— `bench.sh`(唯一合法测速入口)、`ledger.tsv`(全部实测记录)、
  各测量小程序(`rot_liveness.cc` 枚举证据、`batch_scale.cc`/`geo_scale.cc` 显存线性、
  `op_census.cc` 操作统计、`scene_params.cc` 逐帧内参/深度范围)。
- `docs/` —— 两份完整交接文件(1000 行,含全部错误结论的纠正过程)。

## 下一步

批处理这条杠杆两个阶段都已接近饱和(边际成本上升,再加 N 被显存反噬)。
继续压必须换「减少工作量」的刀 —— 与 MEMOIZE-1 同一类。
