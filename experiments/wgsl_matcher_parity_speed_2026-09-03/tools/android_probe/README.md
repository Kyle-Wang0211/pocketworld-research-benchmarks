# PWMatchProbe(Android arm64)—— 跨端逐字节一致性的实证器

## 为什么
09-05 用户追问:"MMA 只有苹果能用,那我们在做什么跨端?" 查下来:
`VK_KHR_cooperative_matrix` 2023 年就随 Vulkan 1.3.255 批准(**Arm 是共同作者**),
Imagination 已在 Android DDK 出货,Qualcomm 说 Adreno GEN5 会有(+1.5–1.7×),
Snapdragon 8 Elite Gen 6(2026-09-03)带专用 Adreno Matrix 核 —— **不是苹果独占,是正在到货**。
但**存量覆盖率查不到**(vulkan.gpuinfo.org 覆盖页 403),而且我们的核为正确性写死 subgroup=32
(`@workgroup_size(512)` 配 16 个 subgroup、行映射 `sg*8`、蝶形 mask 1/2),
Mali/Adreno 不是 32 ⇒ 即使扩展就位,现在这份核也不会跑,只会静默回退 tiled。

**所以真正要先证的不是速度,是"同一份源码在第三个后端上输出逐字节相同"。**

## 判据(与速度无关)
夹具 `fx13` 在 Mac(M3 Pro/Metal)与 iPhone(A16/Metal)上的答案已冻结:
- 8192²  → `fcb72732ae098e0b…`
- 13312² → `a59db73512ce…`

安卓吐出同一个 sha ⇒ 一套源码三端逐字节一致,**哪怕它慢十倍**。

## 用法
```
./run_android.sh          # 找设备 → 推送 → 自报家门 → 8192² → 13312²
```
输出的 `BACKEND_INFO` 里:`kernel=` 是 mma 还是 tiled、`subgroup=[a,b]` 是这台机器的真实宽度、
`sgmatrix/f16_f32/mixed` 是驱动上报的能力。

## 构建
NDK(brew cask android-ndk)+ 为 Android arm64 单独编的 Dawn(`~/Developer/dawn-android-arm64`,
Vulkan ON / Metal OFF / Release)。🔴 Dawn 的代码生成器会被 brew python 3.14 的坏 pyexpat 打断,
必须 `-DPython3_EXECUTABLE=/usr/bin/python3`。
探针自带可移植 SHA-256 —— 不用 `fair_match_common.h`,那个头依赖 Apple 的 CommonCrypto,
为安卓去改它会动到 Apple 侧四道门在用的公共代码。

## 2026-09-05 首次实测:PAL-AL00(骁龙 888 / Adreno 660 / Android 12)
| 核 | 尺寸 | ms(p50) | sha | 判定 |
|---|---|---|---|---|
| 默认 → tiled(sgmatrix=0) | 8192² | 3202 | `fcb72732ae09` | ✓ 逐字节 |
| **blocked 8x4(通用核)** | 8192² | **430** | `fcb72732ae09` | ✓ 逐字节,快 7.4× |
| **blocked 8x4(通用核)** | 13312² | **485** | `a59db73512ce` | ✓ 逐字节 |

**同一份 WGSL 在第三个后端(Vulkan)上与 Mac(Metal/M3 Pro)、iPhone(Metal/A16)逐字节一致。**
指纹:`sgmatrix=0`(Adreno 660 无 cooperative matrix)、**`subgroup=[64,128]`**(MMA 核写死 32 在此不可能跑)、
`packed_dot=1`、storage 32768 / invocations 1024。完整日志 `run_2026-09-05_adreno660.log`。

## 2026-09-05 傍晚:同一把刀在两台真机上方向相反(13312²,全部逐字节)
| 8x4 + 刀 | A16(两轮交替) | Adreno 660(5 轮 min) |
|---|---|---|
| 基线 | 94 / 99 | 359 |
| PIPE(线程组载入提前一拍) | **+12%** | **−13%** |
| GPF(全局预取到寄存器) | **+9%** | **−11%** |
| PIPE+GPF | — | −10% |
| 8x8 / RSCAN | 赔 | 赔 |
开销结构:A16 载入 8% / 暂存 8.5% / 扫描 9%(FMA 循环≈峰值 35%);Adreno 24% / 16% / 10%(≈18%)。
⇒ 「一套核不分叉」的硬边:同一把预取刀两边反相关,得选一边吃亏,或找两边都赚的形态。
🔴 探针纪律:PIPE / NOSTAGE 的锚点只认 4x4 文本,在 8x4 上静默 no-op,两台机器各读出一条假"零收益";
设备侧 stderr 不可见,靠指纹文件的 anchor_mismatch 才抓到。**每个探针对每种核形态都要验一次活性。**

## 2026-09-05 收官:通用核默认 8x4 + PIPEB;tiled 让位
PIPEB(只提前 B 的一个 vec4)A16 −1~5% / Adreno −5.9%,三平台逐字节。无 MMA 设备默认落 blocked(不再 tiled),
Adreno 默认路径复验 `BACKEND_INFO backend=blocked`。产品仓 commit 5a3138e。

## 2026-09-05 晚:真正的底板到了 —— Mate 10(麒麟 970 / Mali-G72 MP12 / Android 10,2017 年机)
| 核 | 尺寸 | ms | sha | 判定 |
|---|---|---|---|---|
| tiled(env 强制) | **13312²(生产尺寸)** | 38107 | `a59db73512ce` | ✓ 逐字节 |
| **blocked 8x4+PIPEB(默认)** | **13312²(生产尺寸)** | **7234** | `a59db73512ce` | ✓ 逐字节,比 tiled 快 **5.27×** |
| tiled(env 强制) | 8192² | 14258 | `fcb72732ae09` | ✓ 逐字节 |
| blocked 8x4+PIPEB(默认) | 8192² | 3063 | `fcb72732ae09` | ✓ 逐字节,4.65× |

指纹:**`subgroup=[0,0] subgroups=0`**(这块 GPU 连 subgroup 都没有)、sgmatrix=0、packed_dot=1、
storage 32768 / invocations 384 / sizeX 384。通用核不依赖任何这些特性,照跑。
**同一份 WGSL 现在在四个后端逐字节一致:Metal(M3 Pro)/ Metal(A16)/ Vulkan(Adreno 660)/ Vulkan(Mali-G72)。**
慢是慢(13312² 7.2s,是 Adreno 660 的 15×、A16 的 77×),但那是 2017 年中端 GPU 的算力,不是算法分叉。
🔴 比值一律按生产尺寸 13312² 报(用户 09-05:"为什么不用生产端的 13312²"),8192² 只留作跨端 sha 参照。

### 上机四个坑(都记在脚本里)
1. **麒麟 970 的 Vulkan ICD 对 adb shell(uid 2000)进程返回 0 个物理设备**(`vkinfo.c` 纯 Vulkan 枚举同样 0)
   ⇒ Dawn 只剩 Null 后端(TU 已拒)。必须以 app 身份跑 ⇒ `apk/`(aapt2→javac→d8→zip .so→zipalign→apksigner,无 Gradle,
   `build_apk.sh` 缺 keystore 自生成);夹具 `run-as` 拷进 `files/fixtures/fx13`,结果在 `files/probe_out.txt`。
2. EMUI **纯净模式·增强防护**拒装未经应用市场检测的 APK:`INSTALL_FAILED_ABORTED: User rejected permissions`,
   弹窗只有"查找类似应用/取消安装"。手机上 设置→系统和更新→纯净模式→退出增强防护 后直通。
3. `run_apk.sh`:`pidof <包名>` 在此机返回空(改 `ps -A` + `tr -d '\r'`);adb shell 吞空的 `""` 参数 ⇒
   `am start` 报 "Argument expected after extra"(非空才加 `--es`);灭屏时 Activity 不起(先 `KEYCODE_WAKEUP`)。
4. 指纹标签硬编码 `blocked(fma4x4,V3)` 而默认核早已是 8x4+PIPEB —— 指纹说了假话;产品仓 94621fe 改为
   `BlockedLabel()` 按选核 env 生成,Mac 阳性对照 `blocked(fma8x4+pipeb,V3)` + sha 不变。

## 2026-09-05 夜:Mali 病根的一手证据 → DIRECT 形态(产品仓 f8b50ee / DIRECT-44 后续提交)
**为什么 Mate 10 是 7.2 s:** 13312² × 128 = 22.7 G FMA;G72 MP12 @ 746 MHz 每核每拍 12 FMA(3 EE × 4 lane)
⇒ 峰值 ≈107 G FMA/s ⇒ 地板 ≈212 ms。实测 7234 ms = **峰值的 3%**;A16 是 35%、Adreno 18%。
载入/FMA 配比在纸面上不缺(每线程每 k 3 次 vec4 载入喂 32 次 FMA;quad 内 al/ah 广播、b4 落同一 64 B 行)。
可疑项是**线程组暂存 + barrier**——而这正是 Arm 官方说不要在 Mali 上做的事:

- Arm® Immortalis™ and Mali™ GPU OpenCL Developer Guide 6.1(101574_0601_25_en),§3.7:
  "Immortalis and Mali GPUs use global memory backed with caches in place of local or private memories. …
   Moving data from global to local memory typically does not improve performance."
- 同上,"Use of local or private memory":"GPUs use caches instead of local memories. … There is therefore no
  performance advantage using local or private memories … Some code copies data into a local or private memory,
  processes it, then writes it out again. This code wastes both performance and power by performing these copies."
- 同上,"Barriers":"If you remove copy operations to or from these memories, also remove the associated barriers."
- 同上,"Avoid excessive register usage":"Every thread has 64 32-bit working registers. … If a thread requires
  more than 64 registers, the compiler might start storing register data in memory."
- chips&cheese《Arm's Bifrost Architecture and the Mali-G52》:">32 registers halve theoretical occupancy";
  "Each Shader Core can only have one workgroup with local memory allocated"(G52 实测;G72 未证,待矩阵)。
- Arm Compute Library `src/core/CL/cl_kernels/common/gemm.cl`:Mali GEMM **不用 __local**,RHS 预 reshape/转置,
  寄存器分块 M0×N0 + vload,可选 cl_image 读 RHS(纹理缓存加带宽)。
- Panfrost `pan_desc.h`:`pan_wls_instances = next_pow2(x)*next_pow2(y)*next_pow2(z)`——WLS(workgroup local
  storage)是驱动按 dispatch 分配的内存区,实例数由驱动定 ⇒ "每核一个"不是硬件铁律,是驱动策略。

**DIRECT 形态**(`OFFICIAL_AETHER_MATCH_DAWN_BLK_DIRECT=1`):A/B 各一次预转置到 f32 `[k][row/4]`(xpose 入口,
绑定 0/3/7),主核绑定 7/8 读 At/Bt,GEMM 段零 barrier 零暂存;S 只留给扫描。算术逐 FMA 同源。
`+BLK_44=1` 派生 4x4/256(寄存器减半)。
Mac 门:fx13 13312 pairs sha `a59db73512ce`(8x4 四轮交替 / 4x4 两轮)、ABI 门默认/DIRECT 双绿、parity 19 绿、
**db51 全量 162/162**。M3 Pro:DIRECT 8x4 18.6 vs 基线 18.7 ms(持平),DIRECT-44 20.7。
🔴 Dawn 自动布局只收实际用到的绑定:DIRECT 主核不读 A/B,bind group 里多给 0/1 直接报错(已处理)。
🔴 Mac 活性检查:`unroll/noload/xbar` 三探针在 8x4+PIPEB 上生成代码与基线逐字节同 = 死锚点;noload/xbar 已修
(先认 PIPEB 形态),unroll 仍只认 4x4。**每个探针对每种形态验活性**——第三次撞同一坑。
设备:Mate 10 拔 USB 后 adbd 重启回 USB 模式,Wi-Fi adb(tcpip 5555)不跨拔线;此机必须插线测。

### Adreno 官方口径(Qualcomm OnQ 博客《Matrix multiply on Adreno GPUs – Part 1》,2016-10-10,作者 Vladislav Shimanskiy,Adreno GPU Compute 团队)
- 微块:"A typical micro-tile has 4 x 8 = 32 components" —— 每个 work-item 算 4×8(= 我们的 8x4 寄存器块)。
- 向量读:"our kernels are written to use vectors of float4 type instead of just float … saturate the bandwidth to memory".
- **纹理管线**:"The trick we use to increase the bandwidth is to load one matrix through TP and the other through the
  direct load/store pipe … The TP has its own L1 cache and an independent connection to the L2 cache … We spend nearly
  as much time on the ALU operation as we spend waiting for data to come back from caches, and we can pipeline them".
- 通篇没有 local memory。⇒ Adreno 官方配方 = **DIRECT-TEX**(A 走缓冲、B 走纹理、寄存器 8x4、无 __local)。
- 与 ACL 的 Mali 配方(export_to_cl_image)同形 ⇒ 纹理臂在两家安卓 GPU 上都有一手背书;Apple 侧 M3 实测 +2 ms(需 A16 定夺)。
- Part 2(2016-10-17)内核清单核实:`float4 a[8]; float4 b[4]; float4 c[8];`,`b[i] = read_imagef(Bi, (int2)(gx, pos + i))`
  (x = 列四元组、y = k —— 与我们 DIRECT-TEX 的纹理布局逐字段相同),`a[i] = vload4(0, A + A_off)` 直读全局,
  `c[i] += a[i].x*b[0] + … + a[i].w*b[3]`;**全文无 `__local`**,建议 `-cl-fast-relaxed-math`(我们不用:要逐字节)。
  差异:高通每步 4 k 成批载入(a[8]+b[4]+c[8] ≈ 80 寄存器,Adreno 寄存器多),我们逐 k 载入 + 只预取 B(≈48 寄存器,
  给 Mali 的 64 上限留余量)。
- Mac 门齐:DIRECT / DIRECT-44 / DIRECT-G / DIRECT-TEX **db51 全量各 162/162**,ABI 门四臂绿,fx13 13312 sha 四臂 `a59db73512ce`。
  M3 Pro 13312²:基线 18.7 / DIRECT 18.6 / 44 20.7 / G 19.5 / TEX 20.7 ms。设备侧待 Mate 10 插回 USB(batch2.sh)与 A16。

## 2026-09-05 夜 第二批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch2.tsv`)
| 臂 | ms | vs 基线 | 判读 |
|---|---|---|---|
| base(8x4+PIPEB,LDS) | 6461 / 6083(再测) | 1.00 | |
| DIRECT 8x4 | 6278 / 6270 | 0.97 | 去暂存+barrier 只赚 3% —— 不是病根 |
| DIRECT 8x4 + chunk_off | 6084 | 0.94 | 分块提交间隙 ~3% |
| DIRECT-G 8x4 | 4400 | 0.68 | 核内零线程组内存 −30%:"带 local memory 每核只驻一个 WG" 在 G72 上成立 |
| DIRECT-G 8x4 + chunk_off | 4114 | 0.64 | |
| DIRECT-TEX 8x4 | **2555** | **0.40** | B 走纹理 −60%:高通/ACL 的 image 路径在 Mali 上同样是真金 |
| DIRECT-G+TEX 8x4 | 5215 | 0.81 | G 与 TEX 在 8x4 上反而互相拖累(占用率变了,纹理缓存命中随之变) |
| **DIRECT-44(4x4/256)** | **849** | **0.13** | **病根 = 寄存器溢出**:8 个 vec4 累加器 + 载入超过 Bifrost 每线程 64 寄存器,内层 spill |
| DIRECT-44+G / +TEX / +G+TEX | (失败,无 sha) | | G 锚点照 8x4 文本写,44 之后未命中 → 退回无 G 核但 C++ 仍绑 Scr → 管线失败;已修(第三批补测) |
🔴 Mac 侧"叠加形态 sha 全对"当时是假的:Bash 工具是 zsh,未加引号的 `$e` 不分词,`env "A=1 B=1"` 只设 A。
   已加 `OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1` 打印最终 WGSL 与 `[direct-chain]` 逐步日志,四种叠加形态重验真实生效。

## 2026-09-05 夜 第三批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch3b.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| **44_lds(原线程组暂存版 4x4/256)** | **829** | 老核本身就 7.8×:寄存器是全部,DIRECT/G 在 44 上不再有用 |
| DIRECT-44 | 844 / 849 | ≈ 44_lds |
| DIRECT-44-G | 874 / 866 | G 在 44 上反而 −3% |
| **DIRECT-44-TEX** | **766 / 767** | TEX +9%,当前 Mali 最优 |
| DIRECT-44-G-TEX | 783 / 776 | |
| +chunk_off | 796 / 886 | 分块间隙在 44 形态上不再是钱 |
| base | 6507 | |
🔴 事故:第三批第一次跑在**旧 .so** 上(新 APK 只编未装),44+G 又"失败"了一遍。现在 .so 编进 TU sha(`BUILD_ID` 行),
`run_apk.sh` 对照 `out_build_id.txt` 不一致直接 exit 4——装机≠生效,判据必须从进程里读出来。
🔴 `am start` 对仍在前台的实例只投递 intent 不重跑 onCreate(runner 先 force-stop);新装包首启有 dexopt,进程判失改为连续两次未见。

## 2026-09-05 夜 第四批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch4.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| nopb84(DIRECT 8x4 去 B 预取) | 3138 / 3878(再测,机身升温) | 少 4 寄存器把溢出减半,但 8x4 在 64 寄存器线之上过不去 |
| nopb84tex | 2526 | |
| nopipeb_lds84(老核去预取) | 5308 | 同一条寄存器故事 |
| pipea44(A 也提前一拍) | 787 | −7%:延迟隐藏有效但不是大头 |
| pipea44tex | 702 | |
| **nopb44(去 B 预取)** | **749** | **−11%:少 4 寄存器比多 4 寄存器的 PIPEA 更赚 ⇒ 占用率 > 延迟隐藏** |
| **nopb44tex** | **681** | **当前 Mali 最优:基线 6461 → 9.5×** |
| direct44tex_ref | 769 | 与第三批 766/767 一致(尺子稳) |
| base_ref | 7045 | 长臂连跑后机身 33℃,基线漂到 7045;批内交替对照才作数 |
方向:44 形态目标是把每线程寄存器压到 ≤32(Bifrost 满占用率线)。下一批 TEXA(A 也走纹理,寄存器不变,赌两条载入通路并行)。

## 2026-09-05 夜 第五批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch5.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| nopb44tex(参照) | 692 / 679 | |
| texa44(A 走纹理) | 760 | 与 tex44(B 走纹理)的 766 等价:单边纹理 ≈ −10% |
| **nopb44texa** | **671** | **当前最优(9.6×)** |
| nopb44texa_tex(两边纹理) | 921 / 916 | **赔 35%** |
| texa44tex | 957 | 赔 |
| pipea44texa_tex | 935 | 赔 |
| nopb44_ref | 747 | 稳 |
⇒ 高通"一条走纹理管线、一条走直连"的平衡原则在 Mali 同样成立:纹理管线被两矩阵同时压满就翻车。

## 2026-09-05 夜 第六批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch6.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| nopb44texa_ref / again | 688 / 687 | |
| **sm44nopbtexa** | **671 / 663** | SCANMEM(行扫描状态落 RowP)+2–3%,当前最低 |
| sm44nopbtex | 673 | |
| sm44nopb | 734(vs nopb44 747) | |
| sm44 | 847(vs direct44 844) | 单独没用,只在寄存器紧的组合里显效 |
⇒ 寄存器这条线上能挤的已不多;44 形态离 LSU 地板(≈300ms)仍 2 倍,下一步先用探针量纯 FMA 地板与扫描段的价。

## 2026-09-05 夜 第七批 + 段账探针(Mate 10,13312²;`run_2026-09-05_mate10_batch7.tsv` / `_probes.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| sm84nopb / +tex / +texa | 3419 / 3162 / 3035(再测 3546) | **8x4 判死**:SCANMEM+NOPB 也挤不进 64 寄存器线 |
| best44_ref(×3) | 685 / 686 / 679 | 尺子稳 |
| best44 + chunk_off / chunk64 | 684 / 670 | 分块在 44 形态上零成本,不动分块策略 |
| **best44_noload(探针,非逐字节)** | **574** | 载入只占 16% |
| **best44_noscan(探针)** | **612** | 扫描段 11% |
| d44_noload / d44_noscan | 594 / 770(d44 844) | 无纹理形态载入占 30% ⇒ TEXA 的钱正是从这里来 |
⇒ 剩下 ≈500ms 全在 FMA 循环本身(峰值地板 212):**发射效率 ~40%**。两个逐字节的刀:显式 `fma()`(怀疑未融合)、k 循环展开(每 16 FMA 配 5–6 条循环/地址指令)。

## 2026-09-05 夜 第八批 + 算术峰值探针(Mate 10,13312²;`run_2026-09-05_mate10_batch8.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| best_ref / again | 710 / 681 | |
| fma(显式 fma()) | 684 / 684 | −4%:编译器本来大体已融合 |
| unroll2 / unroll4 / unroll8 | 699 / 770 / **9858** | 展开把载入提前、活寄存器变多 ⇒ 占用率掉、8 倍直接炸 |
| sm_fma_unroll4 | 706 | |
**ALU 峰值探针**(`PW_PROBE_ALU=1`,16 条独立 FMA 链零访存,1024×256×4096×32):Mate 10 **冷态 105.70 / 热态 105.71 GFMA/s**
= 12 核 × 12 lane × 746 MHz 的名义峰值 107,**没有降频**;M3 Pro 同探针 1719 GFMA/s(尺子对)。
⇒ 纯 FMA 循环 574ms vs 地板 215ms:2.7× **全是代码差距**。最可疑:Bifrost 满占用率(384 线程/核)要求 ≤32 寄存器,
>32 减半到 192,而 44 形态一组 256 线程比 192 还大 ⇒ 编译器只能压寄存器(spill)或一核挂半个组;
NOPB/SCANMEM 这些"少几个寄存器"的刀都赚正是这个症状。下一刀:44 改 128 线程一组(tile 32×64,W128)。

## 2026-09-05 夜 第九批(Mate 10,13312²,全部 sha `a59db73512ce`;`run_2026-09-05_mate10_batch9.tsv`)
| 臂 | ms | 判读 |
|---|---|---|
| best_ref(256 线程,nopb+texa)×2 | 700 / 672 | |
| w128 单独(4x4,128 线程,tile 32×64) | 682(vs direct44 844) | **−19%**:占用率假设坐实(Bifrost >32 寄存器 ⇒ 192 线程/核 < 256 的组) |
| **w128 + nopb + tex(B 走纹理)** | **616** | **今晚最优:基线 6461 → 10.5×** |
| w128 + nopb + texa ×2 | 635 / 635 | |
| w128 + fma / + pipea | 642 / 650 | |
| w128_noload(探针) | 521 | 载入 18%;FMA 循环仍是算术地板 215 的 2.4× |

### 今晚收官账(Mate 10 vs iPhone 14 Pro,同夹具 13312² 同一对,逐字节同)
| 机器 | ms | vs 14 Pro 通用核 93.5 | vs 14 Pro 原生 70 |
|---|---|---|---|
| Mate 10 开工时(8x4+PIPEB) | 6461 | 慢 69× | 慢 92× |
| **Mate 10 收官(w128+nopb+tex)** | **616** | **慢 6.6×** | **慢 8.8×** |
两块 GPU 的 FMA 峰值比 ≈105 : ~900 ≈ 8.6× ⇒ Mate 10 已在算力该有的位置。剩下的共享杠杆 = FMA 循环发射效率(两边都只有峰值的 ~35–45%);
算术梯子探针(chain16 → gemm44 → gemm44ld → gemm84)已就位,下一轮逐级定位。A16 一票未测(DIRECT 家族 + W128 全部待 iPhone)。
