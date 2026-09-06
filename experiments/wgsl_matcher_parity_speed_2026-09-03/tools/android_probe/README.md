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

### 算术梯子探针(`PW_PROBE_ALU=1`;TU `pwdawn_probe_alu_shape`,1024 组 × 256 线程 × 4096 迭代)
| 级 | M3 Pro | Mate 10(G72) |
|---|---|---|
| chain16(16 条独立 FMA 链,纯峰值) | 1761 GFMA/s = 100% | 105.7 = 100% |
| gemm44(4x4 内层,零访存) | 1533 = 87% | **72.0 = 68%** |
| gemm44ld(加回 L1 常驻载入) | 1372 = 78% | 72.2 = 68% |
| gemm84(8x4 内层,零访存) | 1707 = 97% | 84.3 = 80% |
| 真实核(13312²) | 1220 = 69% | 43.6 = 41%(NOLOAD 521)/ 36.9 = 35%(616) |
读法:**Bifrost 单发射,每条非 FMA 指令(载入/循环/地址)都占一个 FMA 槽** ⇒ 4x4 每 16 FMA 配 ~5 条杂指令 = 68%,8x4 80%;
Apple 上循环本身 87–97%,缺口在循环外(扫描 9%、tile、载入)。⇒ "所有机型共享"的两处肉:
① 每条指令的 FMA 占比(W128 放宽寄存器后重测展开)、② 循环外的扫描/tile 开销。A16 的梯子待 iPhone(台架 app 接入中)。

## 2026-09-05 夜 第十批(Mate 10,13312²;`run_2026-09-05_mate10_batch10.tsv`)
| 臂(均 W128+NOPB+TEX) | ms | 判读 |
|---|---|---|
| ref ×2 | 625 / 630 | |
| +fma | 617 | −1~2% |
| +unroll2 ×2 / +unroll4 / +fma+unroll2 | 660 / 665 / 748 / 657 | 展开在 W128 下仍赔:桌面(寄存器)还是不够 |
| noscan(探针) | 569 | 扫描 9% |
| noload(探针) | 523 | 载入 16% |
⇒ Mali 上"少记账"这条路到头;剩下共享的刀 = 并行扫描(PSCAN,第十一批)。

## 2026-09-05 深夜 A16 台架(iPhone 14 Pro,Wi-Fi devicectl,13312²,每臂 metal 原生 vs dawn 同进程交替 9 轮,sha 两边全 `a59db73512ce`)
| 臂 | 原生 ms | 通用核 ms | 比 |
|---|---|---|---|
| base84(现役:8x4 线程组暂存+PIPEB)×2 | 70.0 / 70.8 | **97.4 / 97.8** | 1.39 |
| direct84 | 69.9 | 103.9 | 1.49(DIRECT 在 Apple 赔 6.7%) |
| direct44 | 69.2 | 101.1 | 1.46 |
| w128 | 69.9 | 103.5 | 1.48 |
| w128+nopb | 68.6 | 99.9 | 1.46 |
| w128+nopb+tex ×2 / +texa | 70.4 / 71.1 | **131.9 / 131.9 / 139.5** | 1.87 / 1.96(纹理在 Apple 赔 32–40% ⇒ 淘汰) |
| w128+pscan / w128+nopb+tex+pscan | 70.3 / 71.1 | 103.8 / 133.4 | PSCAN 0% |
| direct84+tex | 68.6 | 151.6 | 2.21 |
A16 梯子:chain16 671 GFMA/s / gemm44 49% / gemm44ld **33%** / gemm84 31%;真实核 35%、原生 48%
⇒ A16 上每条 vec4 载入 = 32 lane × 16 B = 512 B,L1 64 B/拍 ⇒ 8 拍;**处方与 Mali 同:每次 FMA 少搬字节** ⇒ PACKED(u8 打包 + unpack4xU8)。
Mate 10 第十一批:PSCAN 655 vs 参照 613 ⇒ +7% 淘汰;w128+nopb **不带纹理 1320**(双 LSU 无预取延迟暴露)。
**规矩(用户 09-05)**:没有专属,一把刀任一端赔即淘汰。

## 2026-09-05 深夜 PACKED(u8 打包 + unpack4xU8)—— 淘汰
A16:pk_w128 139.9 / pk_44 140.4 / pk_84 120.4 vs w128 102.9、base84 97.3(+36~40%);M3 +35%。解包指令太多,把省下的载入带宽全吃光。
⇒ A16 上的处方必须是"字节减半且几乎不加指令":**F16 存储、f32 计算**(u8 在 f16 精确;M3 −15%:15.8 vs 18.7ms)。第十三批 + A16c 批同时上。

## 2026-09-05 深夜 🏆 F16 存储 / f32 计算(A16 台架,13312²,metal 原生 vs dawn 同进程交替 9 轮,sha 全 `a59db73512ce`)
| 臂 | 原生 ms | 通用核 ms | 比 |
|---|---|---|---|
| base84(现役)×2 | 70.4 / 70.5 | 97.7 / 97.7 | 1.39 |
| f16 + 8x4 直连 ×2 | 68.7 / 68.8 | **76.3 / 75.5** | 1.10 |
| f16 + 4x4 ×2 | 70.9 | 80.4 / 80.4 | 1.13 |
| f16 + 4x4 + W128 | 69.6 | 80.8 | 1.16 |
| **f16 + 4x4 + W128 + NOPB** | 70.9 | **68.0** | **0.960 —— 通用核首次超过苹果原生** |
| f16 + 8x4 + NOPB | 68.8 | **64.5** | **0.938** |
原理:A16 每条 vec4 载入 512 B 占 8 拍(梯子 gemm44ld 33%);u8 在 f16 精确,存 vec4<f16> 载入字节减半,寄存器里一条 vec4<f32>() 转换后
仍走 f32 FMA ⇒ 乘积/和逐位同。PACKED(u8+unpack)同样省字节却 +36%,差别就在"几乎不加指令"。
"一套核"候选 = f16 + 4x4 + W128 + NOPB(A16 0.96×;4x4/W128 是 Mali 64 寄存器线要求的形态)。Mate 10 第十三批待出。

## 2026-09-05 深夜 F16 在 Mate 10(第十三/十四批,13312²,sha 全同;探针 stderr 已并入输出,链路 applied 可见)
| 臂(均 f16 + 4x4 + W128) | Mate 10 | A16 |
|---|---|---|
| PIPEB(预取 B,参照)| **618 / 619 / 620** | 80.7 / 80.8(1.165) |
| NOPB | 822 / 825 | **68.3 / 68.9(0.96)** |
| "PIPEA"(实为 NOPB,锚点在 NOPB 后失效)| 842 / 854 | 68.6 / 71.4 |
| PIPEB + SCANMEM | 620 | 80.8 |
| NOPB + SCANMEM / + unroll2 / + fma | 825 / 938 / — | 68.3 / 68.3 / 71.3 |
| f16 + 4x4(256 线程)| 720 | 80.4 |
| f16 + 8x4 | 2747(溢出) | 76.3 / 75.5;+NOPB **64.5(0.938)** |
⇒ Mali 必须预取"每线程地址不同"的操作数(B,quad 内 A 是广播);A16 不接受预取 B 却接受少寄存器。
🔴 第三次同类坑:PIPEA 锚点只认带 B 预取的循环头,NOPB 之后静默 no-op ⇒ 上表"PIPEA"两端读数都是 NOPB。已修、链路日志照出。
下一刀 TMAP:线程映射转置让"地址各异"的操作数变成 A,配真 PIPEA(第十五批 / A16e)。

## 2026-09-05 深夜 A16f:UNROLLH(载入提前的展开)—— A16 不赔(sha 全同,链路 applied 亲核)
| 形态(f16 + 4x4 + W128 + NOPB) | A16 ms | vs 原生 |
|---|---|---|
| 零预取参照 | 70.0 | 1.005 |
| **UNROLLH2** | **68.5** | **0.930** |
| UNROLLH4 | 69.9 | 0.996 |
| UNROLLH2 + SCANMEM(SCANMEM 在 W128 上锚点未命中,= UNROLLH2)| 71.1 | 0.957 |
| UNROLLH2 + TMAP(iPhone 已热限频,两边同倍数变慢)| 158.8 vs 156.2 | 1.017 |
| 零预取再测(热限频中)| 138.9 vs 151.5 | 0.917 |
⇒ 体首发出两个 k 的载入、不跨迭代持寄存器的形态,A16 与零预取同档(0.93–1.0×)。**若 Mate 10 上 UNROLLH2 落在 PIPEB 的 610–630 档,
"一套核"即定:f16 + 4x4 + W128 + NOPB + UNROLLH2**(batch16.sh + APK 已就绪,等插线)。

## 2026-09-06 凌晨 第十六/十七批 + A16 g/h:预取形态的交集搜索(f16 + 4x4 + W128 + NOPB 基底,sha 全同,链路 applied 亲核)
| 形态 | Mate 10 | A16(vs 原生) | 判 |
|---|---|---|---|
| PIPEB(B 提前一拍,+4 寄存器,跨回边) | 612–644 | 80.5(1.15) | Mali ✓ A16 ✗ |
| NOPB(零预取) | 824–850 | 68.3–69.5(0.97–1.00) | Mali ✗ A16 ✓ |
| UNROLLH2 / 4(载入全提到体首,+8/+24 寄存器,不跨回边) | 944–974 / 1040 | 67.9–69.3(0.96–0.98) | Mali ✗ A16 ✓ |
| **TAILB**(FMA 后再装下一拍 B,寄存器 = 零预取,跨回边) | **624 / 623 / 616(tmap)** | 81.6 ×2(1.16) | Mali ✓ A16 ✗ |
| TAILB2(去 min、剥最后一拍) | — | M3 +70% | 淘汰 |
⇒ **A16 赔的不是寄存器,是"载入值跨过循环回边"**;Mali 需要预取但只容得下 +4 寄存器。交集猜想 = UNROLLHB2(展开 2 倍、只把两拍 B 提到体首:+4、不跨回边)—— 第十八批 / A16i。

## 2026-09-06 凌晨 第十八批 / A16i:UNROLLHB2(展开 2 倍只提前 B)—— 交集搜索收官
| 形态 | Mate 10 | A16(vs 原生) |
|---|---|---|
| TAILB(参照)| 639 / 617 | — |
| NOPB(参照)| 829 | 70.3 / 68.3(1.00 / 0.98) |
| **UNROLLHB2** | **966 / 966**(+TMAP 935) | **68.0 / 68.2(0.97 / 0.95)** |
⇒ 源码层能想到的交集形态全部试完:**Mali 只认一拍宽的旋转循环(PIPEB/TAILB),A16 不认任何旋转循环**。两家编译器的行为对撞。
裁决交用户:**A 零预取**(A16 0.97–1.00×、Mali 830 = 开工 7.8×,三端真正一套核且 iOS 不倒退)或 **B 预取**(A16 1.15×、Mali 615 = 10.5×,
iOS 仍需留原生核)。建议 A。Mali 剩下的 35% 属于占用率(寄存器压到 ≤32 让硬件藏延迟),需 Arm 离线编译器看真实寄存器数,下一轮。
台架:主核 WGSL 现可由 Mac 生成、验 sha 后 `gen_wgsl.sh` push 到设备(`OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE`),换核不必重装 .so。

## 2026-09-06 🏁 用户裁决:三端一套核默认 = 形态 A(DIRECT + 4x4 + W128 + 零预取 + f16 存储/f32 计算);产品仓已切默认
| | 旧默认(8x4 线程组暂存) | **形态 A(新默认)** | 形态 B(预取 B,env PIPEB) |
|---|---|---|---|
| iPhone 14 Pro(vs 原生 70) | 97.4(1.39×) | **68.3–70.3(0.97–1.00×)** | 80.5(1.15×) |
| Mate 10(Mali-G72,鸿蒙 2.2) | 6461 | **824–850(7.8×)** | 615(10.5×) |
| M3 Pro | 19.0 | 16.45 | 16.43 |
Mac 门:fx13 sha 同、db51 162/162、parity 绿、ABI 双绿。理由:A 让"三端同一份 WGSL、同一份输出、iOS 不倒退"今晚成立;Mali 的 35% 留给占用率一轮。

## 2026-09-06 形态 A 默认确认(无 env)+ 段账(第十九/二十批,A16 j/k)
| | Mate 10 | A16(vs 原生) |
|---|---|---|
| 无 env 默认 = A | 877 / 837 / 822 | **64.4 / 64.0 / 64.1 / 69.1(0.92–0.97×)** |
| LEGACY84(旧默认) | 7844(机身已热) | 93.0(1.34×) |
| 形态 B(PIPEB) | 626 | 77.9(1.12×) |
| 去扫描探针 | **534(35%)** | 63.2(2%) |
| 分块关 | 747(−10%) | 61.8(原生臂同掉,判不出) |
| 去载入探针 | 作废(f16 锚点未中,已修) | 作废 |
⇒ Mali 上"扫描 35%"与形态 B 时的 9% 矛盾 ⇒ 不是扫描本身,是扫描段与零预取 GEMM 的寄存器/占用率互动。第二十一批用行/列分拆探针定位。

## 2026-09-06 第二十一批 / A16l:形态 A 的扫描分拆(探针非逐字节)
| 探针 | Mate 10(参照 853–857) | A16(参照 64.0–64.5) |
|---|---|---|
| 去行扫描 | 752(−12%) | 61.9(−4%) |
| **去列扫描** | **591(−31%)** | 60.5(−6%) |
| 去两者 | 519(−39%) | 63.2 |
| 去载入(f16 锚点已修) | 518(−39%) | 86.9(反慢:提出循环的常驻寄存器压占用率,此探针在 A16 不能当地板) |
| SCANSEL(select 取分量,逐字节) | 880 / 892(不赚,淘汰) | 64.6 / 64.1(持平) |
读法:Mali 每核只驻一个 128 线程组,列扫描 64 线程各自串行 32 次取线程组内存、行扫描 16 次,**每次延迟暴露**;GEMM 段的零预取载入同理。
⇒ SCANU4:扫描段 4 路提前载入(比较顺序不变 ⇒ 逐字节),第二十二批 / A16m。

## 2026-09-06 第二十二/二十三批 + A16 m/n:扫描段的刀(形态 A,sha 全同)
| 刀 | Mate 10(参照 817–885) | A16(参照 63.8–71.1) | 判 |
|---|---|---|---|
| SCANU4(4 路提前载入) | 866 / 847(噪声) | 63.8 / 64.5(持平) | 淘汰:病不在载入延迟 |
| **PSCAN**(128 线程全上 + 精确合并) | **623 / 619(−26%)** | 67.3 / 77.2(+4.5~8%,多一次 barrier) | Mali ✓ A16 小赔 |
病根(对照 Arm 指南"让每个线程都忙"):列扫描 64 线程干活、64 线程在 barrier 等,一核只驻一个 workgroup ⇒ 整核 1/4 吞吐串行 32 步。
⇒ PSCAN2:局部结果写 S 扩展区(512→768 vec4),barrier 4→3,赌 A16 回到持平(第二十四批 / A16o)。
🔴 流程教训(用户质问"这不是联网查查就知道的吗"):规矩前一晚就读了,没逐段对照自己的核;探针该用来量违规的代价,不该用来找违规。

## 2026-09-06 第二十四批 / A16o:PSCAN2(局部结果写 S 扩展区,barrier 4→3,S 8→12 KiB)—— 两端判死
| | Mate 10(参照 834–849) | A16(参照 64.6–68.5) |
|---|---|---|
| PSCAN(覆写 S,4 barrier) | **618**(三测 623/619/618) | 67.3 / 77.2(+4.5~8%) |
| PSCAN2(S 扩到 768 vec4,3 barrier) | 706 / 696 | 77.7 / 71.4 / 75.9(+5~15%) |
读法:Apple 对线程组内存量敏感(8→12 KiB 每核可驻组数 4→2,比多一次 barrier 还伤);Mali 上扩 S 也赔(占用率/缓存)。
⇒ 下一形态 PSCAN3:只并行列扫描(Mali 的 31% 全在此),局部结果写 1.5 KiB 独立小区,S 不扩、barrier 不增;待六路调研回来再定。

## 2026-09-06 深夜:六路调研汇总(来源 × 思路 × 风险)+ KEYSCAN

用户 09-06 要求"多 agent 多语言联网查学术/社交/代码库,任何有用的代码或参考思路都行"。六路并行:
R1 Apple GPU 微架构(metal-benchmarks/Rosenzweig/Apple Tech Talk)、R2 GPU 精确 top-2 归约代码(SiftGPU/OpenCV cuda/FAISS/ORT/tfjs)、
R3 学术+英文社交(Romou MobiCom'22、SIGMOD'18 top-k、Dr.Top-k SC'21、Li&Amenta SISAP'15、TFLite GPU、TMModel ICS'25、RadiK、Arm 论坛、Chips&Cheese、Qualcomm 指南)、
R4 中文社区(知乎/CSDN 全被墙 → 极术/博客园/阿里云 MNN/Arm 一手)、R5 Mali Bifrost 寄存器与占用率(Arm 文档三份 + Mesa panfrost 源码 + Hot Chips 28)、
R6 WebGPU/Vulkan GEMM 代码(tfjs/ORT/llama.cpp-webgpu/ncnn/ACL/MNN/Dawn toggles/LlamaWeb arXiv 2605.20706)。
所有引用在各 agent 报告原文(会话产物);下表只列决策级条目。

| # | 思路 | 来源(一手优先) | 三端风险 / 逐字节 | 状态 |
|---|---|---|---|---|
| 1 | **寄存器预归约 + 打包键**:每线程把 4x4 块在寄存器归约成 4 行 + 4 列局部 (best,second),键=(score<<6)\|(63-列)/(score<<5)\|(31-行),score 0→键 0;合并无分支 `s=max(max(s,s2),min(b,b2)); b=max(b,b2)` | R2:COLMAP SiftGPU `MultiplyDescriptorG`、OpenCV cuda knnMatch(k=2)、FAISS 同形;ORT/tfjs 复合键;R3-A2 SIGMOD'18 "每线程寄存器内局部 top-k 再合并";Arm 最佳实践 §9.3 "归约拆成短链" | barrier 仍 2 次、S 仍 8 KiB(A16 两条红线都不碰);串行链 64/32→16/8;忙线程 64→96;并列语义逐条对过(高键=小序号=先出现者胜;second 含重复 best;全零 idx=-1) | **KEYSCAN 已实装**(34ed156,env `…_BLK_DIRECT_KEYSCAN=1`)。Mac:fx13 sha a59db73512ce 同、parity 全案例 PASS(含 zeros/tie_xwg/eq_best2)、db51 全闸 162/162。A16:第 1 轮 ref 68.0 / keyscan 69.2 ms(sha 同),后两轮见下。Mate 10:离线,batch18 守候中 |
| 2 | **工作组 128→64**(8×8 线程,tile 32×32,仍 4x4/线程) | R6:tfjs/ORT/llama.cpp-webgpu/ncnn/MNN 移动端 GEMM **全部**用 64;Arm 最佳实践 r3.4 §9.2 "Do not use more than 64 threads per workgroup";R4-#3 Bifrost 每核 192 线程容量 ⇒ 64 线程组可驻 3 组;Qualcomm 无 barrier 核走 streaming mode | A16:每 WG 只 2 个 simdgroup、延迟隐藏靠更多 WG;A 复用减半、全局流量 +;Adreno 对 WG 尺寸敏感 5–7×(TFLite GPU 论文)。逐字节无影响 | 未测 → **下一刀候选 #1**(纯文本变换) |
| 3 | **扫描剥离成第二个 dispatch**:GEMM 核无 barrier、无 workgroup 内存,每 tile 写列局部结果到全局,小核归并 | R3-A3 Dr.Top-k;Arm §9.2/9.3 "有 barrier/共享内存的 WG 不能拆合调度"、"拆成多核更便宜";R5-#11 Chips&Cheese G52 实测"含 local memory 的 WG 每核只驻 1 个";Qualcomm 80-NB295 "无 barrier 核可最大 WG" | A16 多一次 dispatch(~1 ms 级)+ 中间流量 ≈ 2×44 MB;Mali 11 GB/s ≈ 8 ms ≪ 830。逐字节靠 (score,idx) 字典序。先做无 `var<workgroup>` 变体 A/B 验证 #11 | 未测 → **候选 #2**(要改主机侧 dispatch + 缓冲) |
| 4 | 撤软件预取,延迟由占用率隐藏 | R3-P4 Harris "Mali 无硬件预取";R5-#10 Hot Chips 28 clause 拆分只能靠其它 warp;R3-P11 A16(Family 8)按峰值寄存器静态分配 ⇒ 预取直接减 simdgroup | 依赖 #2/#3 先解除"每核 1 组" | 形态 A 已是 NOPB;PIPEB 只在 Mali 赚 → 按"没有专属"已淘汰 |
| 5 | 寄存器压到 ≤32 | **disputed**:Arm malioc 手册/Bifrost 文档说 32 是断点;但 Mesa `bi_ra.c` 只在 arch≥7 才试 32 寄存器分配、v6 genxml 无 register_allocation 字段、Harris 2016 "G71 64 寄存器仍满占用" ⇒ **G72(v6)大概率没有 32 档** | 若属实,追 ≤32 在 Mate 10 零收益;09-05 "寄存器溢出"定案指的是 8x4 的真 stack spill,不是占用率减半 | 降级为诊断:Tint SPIR-V → `malioc --vulkan --compute -c Mali-G72`(Arm Performance Studio 需登录,用户装) |
| 6 | K 维 2 路展开,先发两次载入再 FMA | R6 idea3;TVM Mali 博客 unroll 0.66→9.98 GFLOPS | A16 任何循环携带/提前载入都赔 | **已测死**(UNROLLH/UNROLLHB/TAILB 09-05/06) |
| 7 | quad 连续地址线程映射 | R5-#2 Bifrost 4 线程 lock-step 合并载入;R6 tfjs `sequentialAccessByThreads` | — | **已测死**(TMAP,A16 赔) |
| 8 | Dawn `disable_robustness` + `disable_workgroup_init` | R6-#8 Dawn Toggles.cpp;LlamaWeb 量出 bounds check 吃 14–23% | 索引由构造在界内;P 全部 2048 项先写后读 | **09-03 已默认开**(env `…_DAWN_ROBUST` 可关做 A/B) |
| 9 | 纹理路径 | Romou/姚定界:G76 之前纹理无增益 | 两端赔 35% | 已死 |
| 10 | subgroup / 基数选择 / OpenCL thread_limit_hint | ncnn #6457 G72 subgroupSize=0;RadiK 小 k 无优势;hint 仅 OpenCL | 不可用 | 排除 |
| 11 | 常量进 uniform 寄存器、禁动态私有数组索引、缩活跃区间 | R5-#14 Vulkan-Samples "Mali 寄存器映射 uniform 免费";Apple Tech Talk 10580 / Qualcomm §7.1.4 动态索引私有数组会溢出 | 零风险小刀;acc0..3 已是命名 vec4 | 可顺手查 tint 输出 |
| 12 | (佐证)Arm ACL 自家 Bifrost GEMM = 4x4×k0=4 直载、无 local memory;ncnn 集成 GPU 关 local memory | R5-#13、R6-#5/#6 | 形态 A 的形状是 Arm/腾讯验证过的 | 不是刀,是背书 |

裁决顺序:#1 KEYSCAN 两机数字 → #2 WG64 → #3 两段 dispatch(若 Mali 扫描段仍是大头)。#5 先诊断不动刀。

### 09-06 深夜 A16 结果(13312²,wall p50 ms,每臂 9 rep,交替)
| 臂 | 轮 1 | 轮 2 | 轮 3 | 中位 | vs ref | sha |
|---|---|---|---|---|---|---|
| A ref(默认形态 A) | 68.0 / 67.3 | 68.6 / 68.8 | 69.3 | ~68.4 | — | a59db73512ce |
| A + KEYSCAN | 69.2 | 69.1 | 69.4 | 69.2 | +1.1% | 同 |
| A + W64 | 68.6 | 69.0 | — | 68.8 | +0.6% | 同 |
| A + W64 + KEYSCAN | 68.2 | 68.6 | — | 68.4 | 0 | 同 |

ref 自身当晚散布 67.3–69.3(3%),三臂差都在散布内 ⇒ **A16 三臂持平**(与 Apple 报告一致:S ≤ 8 KiB、barrier 数不变则 A16 不赔)。裁决交 Mate 10(原始 json/err:a16_2026-09-06_keyscan.log、a16_2026-09-06_w64.log)。
W64 两臂 Mac 闸:parity PASS、db51 162/162(w64 / w64+keyscan)。

### 09-06 上午 Mate 10 batch18(13312²,ms,Wi-Fi adb,TU 3f38655808ba;原始 run_2026-09-06_batch18_keyscan_w64.tsv)
| 臂 | 各轮 | 稳态中位 | vs ref 816 |
|---|---|---|---|
| A ref | 1139.7(装完 app 首臂,冷态离群)/ 822.0 / 811.4 | 816 | — |
| A + KEYSCAN | 652.5 / 638.5 / 619.7 | 638 | **−22%** |
| A + W64 | 1125.3 / 1139.8 | 1133 | +39%(单独=淘汰:老扫描按 32 列一段做,串行列扫描总时长翻倍) |
| A + W64 + KEYSCAN | 604.5 / 602.9 | 604 | **−26%**(比 KEYSCAN 再 −5%:64 线程全忙 + 每核可驻 3 组) |
十臂 sha 全部 a59db73512ce。A16 同形态:KEYSCAN +1.1%、W64+KEYSCAN 0(见上表,均在 ref 3% 散布内),补测三轮见下。
**三端同赚结论:W64+KEYSCAN**(Mac 逐字节 + parity + db51 全绿;A16 持平;Mate 10 −26%)—— 形态候选 A′ = f16 + 4x4 + W64 + NOPB + KEYSCAN,是否切默认交用户裁决。

### 09-06 中午:A′ 段账(batch19)、KEYSCAN2、热降频事故(batch20)
- **A′ 段账(Mate 10,全走 WGSL_FILE 推文件、零重装;run_2026-09-06_batch19_aprime_segments.tsv)**:基线 600.8/606.2/599.6;
  合并链归零(nomerge)610.8 ⇒ 合并段 **0%**;GEMM 载入提出循环(noload)591.4 ⇒ 载入延迟 **−1.5%**(W64 每核 3 组已把延迟藏住);
  整段尾巴连两次 barrier 一起删(noscan)1118.8 ⇒ **反而慢 86%**:barrier 让同核 3 组步调一致、Bt 同一 k 行在 L1 共享,删了各组漂开 Bt 重复取 ⇒ 变成访存瓶颈。
  结论:A′ 在 Mali 上 600 ms **全在 GEMM 循环 ALU**(22.7 GFMA / 0.6 s = 37.8 GFMA/s = ALU 峰值 105.7 的 36%;f16→f32 转换 8 条 + 地址算术 + 循环开销与 16 FMA 抢发射)。
- **KEYSCAN2**(3d38d91,env `…_BLK_DIRECT_KEYSCAN2=1`):尾段向量化——4 个 vec4<u32> 转换 + 8 次向量移位/或得全部 32 键;行/列 top-2 各 7 步树形一次算 4 行/4 列;零分键不再逐键 select,保留列/行位(<64/<32,小于任何正分键)在解码时按 (key>>bits)==0 判无候选。
  Mac:sha 同、parity PASS(zeros/tie_xwg/eq_best2)、db51 162/162;M3 时间与 KEYSCAN 同(16.3)。A16 第 1 轮 65.4 vs w64ks 68.3 / ref 68.1(五轮 ABC/CBA 进行中)。
- **batch20 作废(run_2026-09-06_batch20_THROTTLED_invalid.log)**:连跑 18/19/20 三批 ~15 分钟后 ref 600 → 2100/1716/1709,电池 38 °C;这批相对值也不可信。
  规矩:Mate 10 每臂必须同时采样 `/sys/class/devfreq/gpufreq/cur_freq`(G72 满频 767 MHz)记 max/众数进表,臂间 ≥60 s;batch21 起照做。
- 台架:gen_wgsl.sh 头改 zsh(`${=var}` 只在 zsh 成立,bash 下 "bad substitution" 且文件不推——第二次同类坑,见 09-05 env 叠加事故);iOS 台架 WGSL_FILE 支持 `~/Documents/...`(容器 HOME 展开),以后 iPhone 也只推文件。

### 09-06 中午 A16 五轮 ABC/CBA(13312²,dawn wall p50 ms,每臂 9 rep;a16_2026-09-06_5round_ref_w64ks_w64ks2.log)
| 臂 | 5 轮 | 中位 | vs ref | vs 原生 Metal(~70.5) |
|---|---|---|---|---|
| A ref | 68.1 / 68.4 / 68.0 / 68.0 / 68.2 | 68.1 | — | 0.966× |
| A + W64 + KEYSCAN | 68.3 / 68.2 / 68.1 / 67.9 / 67.9 | 68.1 | 0 | 0.966× |
| A + W64 + KEYSCAN2 | 65.4 / 65.1 / 65.0 / 65.1 / 64.8 | **65.1** | **−4.4%** | **0.923×** |
十五臂 sha 全同。KEYSCAN2 的向量化尾段(去 16 个逐键 select、7 步树形)在 A16 上把 KEYSCAN 的 +1% 变成 −4.4%,五轮散布 0.6 ms、无重叠 ⇒ 不是噪声。
Mate 10 晾机后的 A′ vs KEYSCAN2(batch21,带频率采样)见下。

### 09-06 中午 A16 GEMM 循环三变体(在 A′+KEYSCAN2 上,WGSL 文件推送、零重装;a16_2026-09-06_gemmloop_variants.log)
| 臂 | 3 轮(轮内顺序轮换) | 中位 | vs ks2 |
|---|---|---|---|
| ks2(基线) | 60.7 / 64.6 / 64.7 | 64.6 | — |
| ks2 + u2(纯 2 路 K 展开,不动载入顺序) | 64.9 / 65.6 / 65.2 | 65.2 | +0.9% |
| ks2 + ptr(地址改指针递增) | 62.4 / 62.2 / 63.4 | **62.4** | **−3.4%** |
| ks2 + ptru2(两者) | 59.9 / 62.8 / 64.3 | 62.8 | −2.8%(散布大) |
十二臂 sha 全同。ptr 三轮全部低于 ks2 的两轮稳态(64.6/64.7);ks2 首轮 60.7 是休息 60 s 后的冷态离群。iOS WGSL_FILE `~/Documents/...` 路径展开成功(/private/var/mobile/Containers/...)。
待 Mate 10 batch22 同四臂对照。

### 09-06 午后:PTR 进 TU、设备状态事故(锁屏 / 热)
- **PTR**(7081932,env `…_BLK_DIRECT_PTR=1`,链尾):GEMM 循环地址改指针递增;TU 生成文本与手工 ptr 文件**逐字节相同**;完整候选形态 **W64+KEYSCAN2+PTR** Mac 三闸:sha 同、parity PASS(zeros/tie/eq_best2)、db51 162/162。
- **A16 ks2 vs ks2+ptr 五轮 ABBA(a16_2026-09-06_ks2_vs_ptr_5round_THROTTLED.log)**:ks2 136.8/134.4/139.0/136.4/139.7、ptr 131.3/130.7/130.3/130.2/132.2 ⇒ **−4.5%,五轮无重叠**。
  但整机在半速:原生 Metal 臂同批 150–159 ms(正常 70)—— iPhone 连跑 ~40 分钟后降频。比值成立、绝对值不入账;晾 15 分钟后单臂复测(a16v)。
- **Mate 10 batch21 作废(run_2026-09-06_batch21_LOCKED_invalid.log)**:晾 45 分钟、电池 37 °C、thermalservice GPU 45 °C/mStatus=0(未报节流)仍 1705–1877 ms;
  根因是**屏幕已灭 + 锁屏(Keyguard=true)**:`svc power stayon true` + WAKEUP 后同臂 1301,仍是 600 的 2×,剩余差额只能是锁屏态的 EMUI 调度(11:31 那批 600 是用户刚解锁时跑的)。
  gpufreq sysfs 对 shell 时而 Permission denied(11:46 读到 415 MHz 一次),采样臂全 0,不可靠;改用 dumpsys thermalservice 温度 + ref 夹臂比值。
  规矩补:Mate 10 跑批前必须**解锁并保持亮屏**(stayon 已设),批内 ref 夹每一臂看比值,ref 漂 >10% 整批作废。
- **batch23(锁屏态,只看比值;run_2026-09-06_batch23_LOCKED_ratios_only.tsv)**:ref 1161/1451/1330/1325/1353(漂 25%,thermalservice 数值全程冻结在 45/55 ⇒ 锁屏态连温度也不更新),
  ks2 1200/1206、ks2_ptr 1197/1197 ⇒ 相对相邻 ref 约 −8~−10%,ptr ≈ ks2。只证"不劣",不入裁决。batch24 等 Keyguard=false 自动开跑(解锁后)。

### 09-06 12:11 Mate 10 batch24(用户解锁、亮屏常亮、ref 夹每臂;run_2026-09-06_batch24_unlocked_ks2_ptr.tsv)
| 臂 | 各轮 ms | 中位 | vs A′ 611 | vs 形态 A 816 |
|---|---|---|---|---|
| A′ = A + W64 + KEYSCAN(ref ×5) | 625.2 / 600.8 / 613.3 / 611.3 / 598.4 | 611 | — | −25% |
| A′ + KEYSCAN2 | 581.3 / 573.4 | 577 | **−5.5%** | −29% |
| A′ + KEYSCAN2 + PTR | 570.8 / 575.9 | 573 | −6.2%(vs ks2 −0.7%,噪声内) | **−30%** |
九臂 sha 全同,isStatusBarKeyguard=false 全程(锁屏判据已从恒真的 `Keyguard=` 改为 `isStatusBarKeyguard`)。
⇒ **KEYSCAN2 两端都赚(Mate 10 −5.5%、A16 −4.4%)**;**PTR 在 Mate 10 中性、A16 −4.5%(半速态比值,正常态复测 a16w 进行中)**。
候选终形态 **A″ = f16 + 4x4 + W64 + NOPB + KEYSCAN2 + PTR**:Mate 10 816 → 573(−30%),Mac 三闸绿,A16 待正常态复测后定绝对值。

### 09-06 12:2x A16 正常态复测(晾 15 分钟后 ref 68.3 / Metal 68.7 已回正常;a16_2026-09-06_normal_A_ks2_ptr_3round.log)
| 臂 | 3 轮(轮换顺序)dawn ms | 中位 | vs 形态 A | vs 原生 Metal(~70.3) |
|---|---|---|---|---|
| 形态 A(当前默认) | 69.8 / 68.2 / 67.8 | 68.2 | — | 0.970× |
| A + W64 + KEYSCAN2 | 65.1 / 64.9 / 64.9 | 64.9 | −4.8% | 0.923× |
| **A″ = A + W64 + KEYSCAN2 + PTR** | 63.0 / 63.3 / 62.9 | **63.0** | **−7.6%** | **0.896×** |
九臂 sha 全同;原生 Metal 臂 68.4–70.7 证明整机在正常态。PTR 在正常态 −2.9%(vs ks2),与半速态的 −4.5% 同向。

## 🏁 09-06 三端总账:A″ = f16 + 4x4 + W64 + NOPB + KEYSCAN2 + PTR
| 端 | 形态 A(09-06 凌晨默认) | A″ | 增益 | 逐字节 |
|---|---|---|---|---|
| Mac M3(尺子=闸) | — | — | — | sha a59db73512ce、parity 全 PASS、db51 162/162 |
| iPhone 14 Pro A16 | 68.2 ms(0.97× 原生) | **63.0 ms(0.90× 原生)** | **−7.6%** | 9/9 臂 sha 同 |
| Mate 10 Mali-G72 | 816 ms | **573 ms** | **−30%** | 9/9 臂 sha 同 |
三把刀各自在两端都不赔(KEYSCAN2:A16 −4.8% / Mali −5.5%;W64 只与 KEYSCAN 同用;PTR:A16 −2.9% / Mali −0.7%)。
env:`OFFICIAL_AETHER_MATCH_DAWN_BLK_DIRECT_W64=1 …_KEYSCAN2=1 …_PTR=1`(TU 7081932)。切默认交用户裁决;生产机未动。

### 09-06 午后:FMA 形状探针(A″ 之上,WGSL 文件,两机;a16_2026-09-06_fma_shape_probes.log / run_…_batch25)
前提:Mali 段账里 noload(载入+转换全提出循环)只 −1.5% ⇒ "A 改 f32 免转换"在 Mali 天花板 1.5%、A16 还要付带宽 ⇒ 不做;剩下的全是 16 条 FMA 的发射效率(36–39% 峰值)。
| 探针(操作数 swizzle 轮转防提出循环) | A16(真核 63.0) | Mate 10(真核 587) | 读法 |
|---|---|---|---|
| fma_only:纯 FMA,每轮 1 k | 126.9 / 126.2(**污染**:Apple 上轮转变成跨迭代搬移链) | 548.8 / 548.5(−6.6%) | Mali:去掉全部载入/转换/地址只省 6.6% ⇒ 瓶颈是 FMA 循环本体 |
| fma_u4:纯 FMA,4 路展开 | **54.5 / 55.1(−13%)** | **420.5 / 415.6(−29%)** | 两端的 FMA 地板;Mali 549→418 = **循环开销(计数/比较/分支/clause 边界)占 FMA 循环近 1/3** |
| dot4:16 标量累加器 += dot(a_i,b_j) | 99.9 / 99.7(+58%) | 595.1(+1%) | **两端死** |
⇒ 真刀 = A″ 的真实 k 展开(载入自然顺序、无搬移、逐字节同):u2 / u4 / u8 已生成(Mac sha a59db73512ce),两机 batch26 / a16y 进行中。
注:09-05/06 判死的 UNROLLH 是"载入提前 + 展开"(A16 +17%),与这里的纯顺序展开不是同一刀;09-06 上午 u2 在 KEYSCAN(非 PTR)形态 A16 +0.9%。

### 09-06 12:3x 真刀 k 展开(A″ 之上,载入自然顺序、逐字节同;batch26 / a16_2026-09-06_real_unroll_u2u4.log)
| 臂 | Mate 10(解锁态,ref 575/576) | A16(ref 63.0/62.8/63.3) |
|---|---|---|
| A″ + u2 | 847 / 807(**+45%**) | 63.9 / 64.5 / 64.0(+1.5%) |
| A″ + u4 | 963 / 972(**+68%**) | 64.2 / 64.5 / 64.2(+2.1%) |
七/九臂 sha 全同。**两端都赔 ⇒ 顺序 k 展开淘汰,u8 批取消。**
机制:纯 FMA 的 u4 探针 −29%,带真实载入的 u4 反而 +68% ⇒ 展开后编译器把 2/4 组 vec4 载入(转 f32 后各 8 寄存器)提到段首,活跃寄存器叠加 ⇒ G72(只有 64 寄存器档,见 Mesa bi_ra.c)溢出到栈——与 8x4 的死法同源。
A16 +1.5–2%:与 09-06 上午 u2(+0.9%)同向,Apple 静态按峰值寄存器分配(Family 8),展开抬峰值就减 simdgroup。
验证寄存器假设的变体 u2dep/u4dep(后段地址人为依赖前段 FMA 结果,阻止提前载入;Mac 上 21.9/26.7 vs 16.4,代价=载入延迟暴露)两机 batch28 / a16aa 进行中——只为定机制,不指望成刀。

### 09-06 12:4x 收口:GEMM 循环体最后三组变体(A″ 之上,逐字节同;batch28/29,a16_…_unroll_dep / a16_…_fma_cnt)
| 变体 | Mate 10(ref 570–580) | A16(ref 62.7–63.0) | 判 |
|---|---|---|---|
| u2dep / u4dep(后段地址依赖前段 FMA,阻止载入提前) | 843 / 1001(+46% / +74%) | 79.7 / 117.4(+27% / +87%) | 死;u2dep ≈ u2(843 vs 847)⇒ Mali 的展开损失**不是**"载入提前叠寄存器"能解释的,机制未定,但判决不变 |
| 显式 `fma()` 内建 | 695 / 686(**+21%**) | 62.8 / 62.9(0) | 死(Arm 编译器对显式 fma 生成更差) |
| 倒计数循环 `k = KD; k != 0` | 573 / 578(0) | 62.8 / 62.9(0) | 中性,不入 |

## 🏁 09-06 GEMM 循环体战役结论
在"精确 f32 FMA(u8·u8 和 < 2^24)+ Bifrost 64 寄存器 + 无 subgroup/无 dp4a + 三端同一形态"的约束下,A″ 的 GEMM 循环体已到实用地板:
- Mali:去掉全部载入/转换/地址只省 6.6%(fma_only);纯 FMA 展开 4 路能到 −29%,但任何带真实载入的展开(u2/u4/u2dep/u4dep)都 +45~74%;dot4/显式 fma 更差。剩 ≈40% FMA 峰值是 Bifrost 寄存器端口 + clause 边界的结构税,WGSL 层无手可伸。
- A16:纯 FMA 地板 54.8 vs 真核 63.0(载入+转换+地址 13%),但每一种改动循环体的方式都 ≥0;A16 已是 0.90× 原生 Metal。
- 唯一还能让 Mali 再降的是软件流水(PIPEB,曾 −26%),A16 +15% ⇒ 按"没有专属"规矩不做。
- 未测且中等风险的一条:At/Bt 按 k 成对打包成 vec4<u32>(一次 16 B 载入带 2 个 k),载入 clause 数减半、寄存器占用与 u2 同(u2 已死 ⇒ 大概率也死),需改 xpose 布局(主机侧)才能量。
**今日三端总账不变:A″ = f16 + 4x4 + W64 + NOPB + KEYSCAN2 + PTR:Mate 10 816 → 573(−30%),A16 68.2 → 63.0(−7.6%,0.90× 原生),Mac 三闸绿。切默认待用户裁决。**

## 🏁 09-06 12:5x A″ 切三端默认(用户裁决)+ 两机 ref 对照
产品 TU de453a8:`ResolveDirectKnobs` 默认 w64/keyscan2/ptr 全开,标签 **V6** `blocked(fma4x4+direct+w64+nopb+f16+keyscan2+ptr,V6)`;退回形态 A:`…_DIRECT_NOW64=1 …_NOKEYSCAN=1 …_NOPTR=1` → `blocked(fma4x4+direct+w128+nopb+f16,V6)`。默认生成文本与两机验过的 aprime_ks2_ptr.wgsl 逐字节同。
Mac 四闸:fx13 sha a59db73512ce、parity 全 PASS、db51 162/162、abi_test PASS。
| 端(13312²,ABBA ×3,新装 app 的 TU 63443541bba1) | 默认 A″ | 形态 A(env 退回) | 增益 | sha |
|---|---|---|---|---|
| iPhone 14 Pro(原生 Metal 69.1–70.5) | 63.0 / 63.1 / 63.2 | 68.3 / 68.2 / 68.3 | **−7.6%**,0.90× 原生 | 6/6 同 |
| Mate 10(解锁亮屏) | 613.6(装后首臂)/ 571.5 / 573.5 | 826.7 / 849.8 / (见 tsv) | **−31%** | 全同 |
探针 APK / 台架 app 各装一次(主机侧默认改了,必须装);生产机未动。

## ⚠️ 09-06 13:0x 第三家 GPU 上机:华为 P50 Pocket(PAL-AL00,HarmonyOS 4.2 / 骁龙 888 / Adreno 660)—— A″ 在 Adreno 赔 18%
探针 APK(TU 63443541bba1)直接装成、fx13 推 files/fixtures/;13312² 逐字节 sha a59db73512ce **在 Adreno 660 也同**(Apple/Mali/Adreno 三家齐)。
| 臂(ABBA ×3;run_2026-09-06_p50pocket_batch31_default_vs_formA.tsv) | ms |
|---|---|
| 默认 A″(w64+keyscan2+ptr) | 639.3(装后首臂)/ 557.1 / 547.6 |
| 形态 A(NOW64+NOKEYSCAN+NOPTR) | 481.5 / 467.0 / 466.9 |
**A″ 比形态 A 慢 ~18% ⇒ 按"任一端赔=淘汰",A″ 作三端默认不成立**(上午切默认时只有 Apple+Mali 两端在手)。
另:2021 的 Adreno 660 跑形态 A 467 ms,比 2017 的 Mali-G72 的 816 快 1.75×,但比 A16 的 68 慢 6.9×。
分解批 batch32(default / NOW64 / NOPTR / NOKEYSCAN / formA)在 P50 上跑;Mate 10 batch33 与 A16 a16ad 同时补量 NOW64 形态(W128+KEYSCAN2+PTR)。
- **batch32/33 作废**(INVALID_…_declareA_all_formA.log):脚本用 `declare -A`,macOS bash 3.2 不支持 ⇒ 所有臂 env = 最后一项(formA);**标签列全是 w128 揪出来的**(P50 十臂 450–473、Mate 10 八臂 800–850 全是形态 A)。规矩:批脚本禁 declare -A,读表必须核标签与臂名一致。修正版 batch34(case 写法)两机重跑。
- **A16 a16ad(有效,case 写法;a16_2026-09-06_default_now64_formA.log)**:默认 A″ 63.3 / 63.0 / 62.9;**NOW64(W128+KEYSCAN2+PTR)63.4 / 64.2 / 64.7**;形态 A 67.7 / 67.8 / 70.3 ⇒ 去 W64 的 A″ 在 A16 −5.5%(A″ −7.5%)。

### 09-06 13:1x 修正版分解(case 写法,标签逐臂核对;run_…_p50pocket_batch34 / run_…_mate10_batch35)
| 形态(13312²,ms) | P50 Pocket / Adreno 660 | Mate 10 / Mali-G72 | A16(a16ad) |
|---|---|---|---|
| 默认 A″ = W64+KEYSCAN2+PTR | 525.6 / 530.5 / 538.8 | 573.4 / 569.6 / 574.2 | 63.3 / 63.0 / 62.9 |
| NOW64 = W128+KEYSCAN2+PTR | 547.0 / 538.2 | 570.8 / 578.9 / 579.3 | 63.4 / 64.2 / 64.7 |
| NOPTR = W64+KEYSCAN2 | 571.3 / 558.8 | — | — |
| NOKEYSCAN = W128+PTR | **458.4 / 465.4** | — | — |
| 形态 A | 488.3 / 473.7(batch31:481/467/467) | 829.1 / 831.0 | 67.7 / 67.8 / 70.3 |
读法:**Adreno 上赔的是 KEYSCAN2(+11~17%),PTR 赚 ~5%,W64 ≈ 0**;Mali 的 −31% 全来自 KEYSCAN2,W64 无贡献;A16 KEYSCAN2 −5.5%(W128)/−7.5%(W64)。
机制假设:Adreno 与 Apple Family 8 一样按峰值寄存器分 wave,KEYSCAN2 向量化尾段(u0..3/r0..3/c0..3/ra..rd 同时活)峰值 +~48 寄存器 ⇒ 整段 GEMM 的 wave 数掉;Mali 无此惩罚(64 寄存器档已到)。
⇒ 做 **KEYSCAN3**(w64_ks3_ptr.wgsl:v1 顺序折叠 + 去 32 个逐键 select,零分键靠 (key>>5)==0 判;峰值活寄存器 ≈ v1):Mac sha 同、parity PASS(zeros/tie);三机 batch36/37 + a16ae 对照 v1/v2/v3 进行中。
若 v3 在 Adreno 不劣于形态 A 且在 Mali/A16 保住增益 ⇒ 默认改 v3;否则退到 W128+PTR(三端都不赔但丢 Mali 的 30%)交用户裁决。

## 🏁 09-06 13:3x KEYSCAN 三版三机对照 ⇒ 三端不赔的形态 A‴ = f16 + 4x4 + W64 + NOPB + **KEYSCAN3** + PTR
(标签逐臂核对、WGSL_FILE 列核对 len=8665;run_…_p50pocket_batch36 / run_…_mate10_batch37 / a16_2026-09-06_keyscan_v123.log)
| 形态(13312²,ms) | P50 Pocket / Adreno 660 | Mate 10 / Mali-G72 | A16 |
|---|---|---|---|
| 形态 A(09-06 凌晨默认) | 467–488(三批) | 829–831 | 67.7–70.3 |
| A″ = W64+KEYSCAN2+PTR(de453a8 默认) | 533 / 555 / 563(**+13~17%**) | 573 / 574 / 580 | 63.0 / 63.0 / 62.9 |
| W64+KEYSCAN(v1)+PTR | 540 / 546(+13%) | 600 / 597 | 64.1 / 63.6 / 64.3 |
| **A‴ = W64+KEYSCAN3+PTR** | **473 / 488 / 477(≈ 形态 A,0%)** | **583 / 583(−30%)** | **63.9 / 63.7 / 63.8(−6%)** |
| W128+PTR(无 KEYSCAN) | 457 / 476(−3~5%,Adreno 最快) | ≈ 形态 A(PTR 在 Mali 中性) | ≈ −3% |
KEYSCAN3 = v1 的顺序折叠(峰值活寄存器最低)去掉 32 个逐键 select(零分键靠 (key>>5)==0 判);v1 与 v3 只差这 32 个 select,在 Adreno 差 13% ⇒ Adreno 对尾段每条指令/每个寄存器都敏感(按峰值寄存器分 wave)。
Mac:KEYSCAN3 文件 sha a59db73512ce、parity PASS(zeros/tie);TU 旋钮 `…_DIRECT_KEYSCAN3=1` 生成文本与文件逐字节同,标签 `blocked(fma4x4+direct+w64+nopb+f16+keyscan3+ptr,V6)`;parity/db51/ABI 全闸进行中。
**按"任一端赔=淘汰":A″ 出局,A‴ 是唯一三端不赔且保住 Mali −30%/A16 −6% 的形态;默认是否从 A″ 改 A‴ 交用户裁决。**
A‴ Mac 四闸(TU 旋钮 `…_DIRECT_KEYSCAN3=1`,8ecbf98):fx13 sha a59db73512ce、parity 全 PASS(zeros/tie_xwg/eq_best2)、db51 162/162、abi_test PASS。

## 🏁 09-06 13:4x A‴ 切三端默认(用户裁决;TU 1a790c1,标签 **V7** `blocked(fma4x4+direct+w64+nopb+f16+keyscan3+ptr,V7)`;KEYSCAN2 退 opt-in;形态 A = NOW64+NOKEYSCAN+NOPTR)
Mac 四闸:sha a59db73512ce、parity 全 PASS、db51 162/162、abi PASS;默认生成文本与三机跑过的 w64_ks3_ptr.wgsl 逐字节同。
三机 ref 对照(ABBA ×3,探针 TU d79942823044 / 台架同 TU;**此后不再有任何重装**,用户 13:2x 铁律):
| 端 | 默认 A‴ | 形态 A | 增益 | sha |
|---|---|---|---|---|
| iPhone 14 Pro(Metal 70.1–71.1) | 64.2 / 64.0 / 63.7 | 70.4 / 68.1 / 68.9 | **−7.5%** | 同 |
| Mate 10 | 738.6(装后首臂)/ 582.7 / 582.1 | 825.7 / 817.6 / 823.5 | **−29%** | 同 |
| P50 Pocket | 597.5(装后首臂)/ 478.5 / 487.7 | 451.0 / 461.8 / 451.0 | **+3~5%(偏赔)** | 同 |
P50 形态 A 跨批散布 451–488(8%),A‴/ks3 五臂 473–488 ⇒ Adreno 上 A‴ ≈ 形态 A 偏慢 ~3%,需稳态长序列定正负(batch39:default/formA/nokeyscan ×5 轮换,进行中)。"装后首臂"三机一致偏慢(shader 缓存/时钟爬坡),不入统计。
- **P50 batch39 稳态 15 臂(轮换,无重装;run_2026-09-06_p50pocket_batch39_steady15.tsv)**:默认 A‴ 484.7 / 485.4 / 509.5 / 494.3 / 470.9(中位 485);形态 A 464.6 / 473.2 / 460.3 / 458.5 / 446.8(中位 460);W128+PTR 485.8 / 459.8 / 472.2 / 482.0 / 462.2(中位 472)。
  ⇒ **Adreno 660 上 A‴ 比形态 A 慢 ~5%(485 vs 460),W128+PTR 慢 ~2.6%,形态 A 是 Adreno 最快形态**;KEYSCAN3 的尾段在 Adreno 是净成本。段账批 batch40(nomerge/noload/notail/KS3@W128)定它花在哪。
  三端现状:A‴ = Mali −29% / A16 −7.5% / Adreno +5%。按"任一端赔=淘汰"字面 A‴ 不成立;需要用户裁决"Adreno 赔 5% 换 Mali 29%"还是继续找 Adreno 中性的尾段。

### 09-06 14:0x Adreno 段账(P50,batch40;A‴ 基线 481–495)+ 三端"W128+PTR"权衡表 + 两路调研落地
| 探针 | ms | 读法 |
|---|---|---|
| nomerge(合并链 8→1 步) | 447.1 / 447.6 | 合并段 **−8%**(Mali 是 0%) |
| noload(GEMM 载入/转换/地址提出循环) | 349.1 | **−28%**:Adreno 的 GEMM 是载入受限(Mali 1.5%) |
| notail(整段尾巴+2 barrier 删掉) | 360.9 | 尾段合计 **−26%**;形态 A 自己的尾段也 ≈21%(460 vs 361) |
| KS3@W128(NOW64) | 533.4 / 529.0 | +10%:KS3 的 16 步行合并链 + 96/128 忙在 Adreno 更差 |
| W128+PTR(老扫描) | 456.8 | −6% |
三端 "W128+PTR"(不带 KEYSCAN):A16 66.4(−2.6% vs A)、Mate 10 821–836(0)、Adreno 457–472(−2%)⇒ 三端都不赔但几乎没肉;A‴ = Mali −29% / A16 −7.5% / Adreno +5%。
**调研落地(Adreno 成本模型,一手:Qualcomm 80-NB295-11 §3.2.2/§6/§7/§8 + Mesa ir3/turnip 源码 + Romou)**:Adreno 按核**峰值**寄存器静态分 wave(A660 `reg_size_vec4=64`,wave64 时 ≤32 regs→16 waves、33–48→8、49–64→6…;wave 成对发射,粒度 128/256);KEYSCAN2 的 +64 活寄存器把 GEMM 段 wave 数砍 2–4 倍 = +13~17% 的机制;"只用一次的 local memory + barrier"是官方点名坏模式("Using global memory directly to avoid barriers may be a better option");载入事务 128 位而 vec4<f16> 只用一半(合并 2 个 k 一次 128 位载入 = 改 xpose 布局 = 主机侧 ⇒ 需用户批准装);kgsl sysfs 在 P50 上只有 gpubusy 可读(cur_freq/gpuclk Permission denied);AOC(Adreno Offline Compiler,Qualcomm Software Center)可离线读 SPIR-V 的 footprint/wave 数——需用户下载。
**调研落地(精确剪枝)**:文献(LEMP/FEXIPRO/Maximus/GPU-IPRO/SiftGPU/OpenCV)一致:归一化 SIFT 无范数偏斜、未旋转前缀只拿 ~50% 内积、GPU 生产匹配器全是暴力;**真实 fx13 探针(prune_probe.py,只计数)**:零值 0.4–1%(无稀疏);identity K=32 逐对双侧可剪 23.8% 但 4×4 块全剪 0.75%、512 对组全剪 **0.00%**;能量排序 K=32:36.5% / 1.93% / 0.00%(K=64/96 与 PCA 见 prune_probe.log)⇒ **SIMT 粒度剪枝率 ≈ 0,精确剪枝路线判死**。
**PDB**(w64_ks3_ptr_pdb.wgsl:P 双缓冲 8 KiB、每 tile 一次 barrier;Mac sha 同、parity PASS)三机对照进行中——针对 Adreno 尾段 26% 与 A16 "barrier=drain"。
- **PDB 三机全死**(P 双缓冲 8 KiB、每 tile 一次 barrier):P50 670–703(+40%)、Mate 10 656–673(+15%)、A16 67.6–68.0(+6.5%);sha 同。少一次 barrier 抵不过 workgroup 内存翻倍带来的占用下降(A16 S≤8 KiB 红线、Adreno LDS/WG 限并发、Mali 同向)。
- 剪枝探针全量(prune_probe_2026-09-06_fx13.log):见文件;结论不变(SIMT 组级可剪 ≈ 0)。

### 🔍 09-06 14:2x 精确剪枝探针全量(fx13 真实描述子,prune_probe.py;oracle 阈值 = 真 second)
| 前缀 | 逐对双侧可剪 | 4×4 块全剪 | 512 对组全剪 |
|---|---|---|---|
| identity K=32 / 64 / 96 | 23.8% / 77.4% / 98.5% | 0.75% / 12.3% / 81.5% | 0.00% / 0.02% / 4.17% |
| 能量排序 K=32 / 64 / 96 | 36.5% / 84.2% / 99.0% | 1.9% / 22.2% / 86.4% | 0.00% / 0.06% / 8.92% |
| **PCA 旋转 K=32 / 64** | 98.9% / **99.88%** | — | **10.5% / 63.9%** |
PCA 前 32/64/96 维累计能量 0.890 / 0.965 / 0.990。未旋转的前缀在 SIMT 粒度剪不动(与 FEXIPRO 附录 B"未旋转时内积均匀分布在各维"一致);**旋转后 64 维前缀 + Cauchy–Schwarz 剩余界能整组剪掉 64% 的 512 对组**(oracle 阈值)。
设计草案(单核、逐字节精确):每 WG 对本 tile 先算旋转前 64 维(f16 存、f32 算)的近似点积 + 严格上界(旋转/f16 量化/累加舍入误差全部向上取整),按 SIMD 组判 `UB < T_row(32 行) && UB < T_col(16 列)`,整组成立则跳过,否则对该组算原始 u8 的精确 128 维点积(现役 A‴ 路径);top-2 与并列语义只用精确值。理论成本 = 0.5(前缀)+ (1−g512)×1.0 ⇒ oracle 下 0.86(−14%);阈值真核里不可得 oracle,prune_probe2.py 模拟子集预扫(5%/10%)与顺序累积阈值 + f16 量化误差项,结果见下。
**阈值现实性模拟(prune_probe2.py / prune_probe2_2026-09-06_fx13.log)⇒ 精确剪枝判死**:
| 阈值来源 | K=32 g512 | K=64 g512 | 估算成本(=K/128 + 幸存) |
|---|---|---|---|
| oracle(真 second) | 10.5% | 63.8%(f16 存 63.6%) | 0.86 |
| 5% 子集预扫(阈值仅低 1.2%) | 0.35% | 5.2% | 1.45 |
| 10% 子集预扫(低 0.9%) | 0.86% | 13.8% | 1.36 |
| 顺序累积(行阈值按 tile 累积,列阈值 0) | — | 0.00% | — |
界离阈值只有 <0.125·N² 的薄边(直方图),阈值低 1% 就把组级剪枝率从 64% 打到 5–14%;而拿到接近 oracle 的阈值需要先算接近全量的精确结果——循环论证。**结论:在逐字节精确 + SIMT 组级跳过的约束下,剪枝路线关闭。**

### 09-06 14:4x 调研:三端整数点积路线(一手:Dawn/Tint 源码、gpuinfo 设备报告、MSL 4.1 规范、Mesa asahi/turnip/bifrost、Qualcomm 指南、philipturner metal-benchmarks)⇒ 判死
- Tint 的 `packed_4x8_integer_dot_product` 是 kShipped 语言特性,**三端都报 true 但与硬件无关**;Metal 后端无条件 polyfill(MSL `dot` 只收浮点),A16 上每 4 MAC ≈ 21 条整数指令且 shift/imul 四分之一速率 ⇒ ≥10× 慢。
- Vulkan 后端只看 `VK_KHR_shader_integer_dot_product` 是否存在:**P50 Pocket 本机型(BAL-AL00,驱动 512.530.0,Vulkan 1.1.128)与 Adreno 660 全部 232 份报告都没有该扩展**;Mate 10 的 Kirin 970 驱动线止于 r18p0,同样没有;G72 即便新驱动暴露也 `*Accelerated` 全 false。Adreno 660 硅片有 dp4acc 但只有 Turnip 才发(HarmonyOS 装不了)。
- 精确替代表示不存在:u8×u8 需 16 位有效位(f16 只有 11);i32 IMAD Apple 四分之一速率;"u8 打包存储 + unpack4xU8 + f32 FMA"(TU 里的 PACKED)M3 实测 +67%。**f32 FMA 是三端全速且逐字节精确的下限,现役 f16 存 f32 算就是它。**
- 开源跨厂商 int8 GEMM 数字只有桌面(llama.cpp DP4A、Chrome dp4a、ORT),移动三端零命中;llama.cpp 作者原话:没有加速硬件不值得用。

## 🏁 09-06 下午总结:三路调研 + 两条实验路线全部关闭,A‴ 是 WGSL-only 的终点
| 路线 | 结论 | 证据 |
|---|---|---|
| 精确剪枝(PCA 旋转前缀 + CS 界 + 组级跳过) | 死:oracle 阈值 −14%,现实阈值成本 1.36–1.45 | prune_probe/prune_probe2(fx13) |
| 整数点积 / 打包存储 | 死:三端全 polyfill,PACKED M3 +67% | 调研 B + Mac 实测 |
| 尾段结构(KEYSCAN1/2/3、PDB) | KS3 = 三端唯一不赔 Mali/A16 的;PDB 三机全死 | batch36–42 |
| GEMM 体(展开/dep/fma/cnt/dot4) | 全死或中性 | batch25–29 |
唯一未测且有依据的刀 = **k 成对打包成一次 128 位载入**(Qualcomm §6.3:每事务 128 位,vec4<f16> 只用一半;Adreno noload 探针 −28%);**要改 xpose 布局 = 主机侧 = 必须重装探针/台架**,按用户铁律只能等用户批准;A16/Mali 方向未知(多 8 个活寄存器,Adreno 可能掉档)。

## 🔪 09-06 14:5x KP(k 成对 128 位载入;用户裁决:默认留 A‴,并**批准为 KP 装机一次**)
实现(010f858,env `…_DIRECT_KP=1`):At/Bt 布局 [k/2][row/4] 的 vec4<u32>(每元素 8 个 f16:k=2kp 的 4 行 | k=2kp+1 的 4 行),转置核用 pack2x16float(0..255 精确),主核每 2 个 k 各做一次 128 位载入 + unpack2x16float,FMA 顺序不变。Mac:sha 同、parity PASS、db51 162/162、ABI PASS。三机装 TU 66f15d123218(探针)/同 TU(台架)。
| 端(ABBA ×3,13312²,ms) | 默认 A‴ | A‴ + KP | 增益 | sha |
|---|---|---|---|---|
| iPhone 14 Pro | 63.5 / 63.4 / 63.8 | **60.2 / 61.0 / 60.3** | **−5%**(0.86× 原生) | 同 |
| Mate 10 | 718(装后首臂)/ 583.4 / 584.1 | **542.9 / 534.3 / 534.7** | **−8%** | 同 |
| P50 Pocket | 577(装后首臂)/ 493.4 / 466.8 | 481.3 / 480.3 / 469.8 | ≈0(噪声内) | 同 |
Adreno 没拿到 noload 探针暗示的 28%(合并载入后仍是同样的等待/占用结构),但不赔;Wi-Fi 长序列 batch44(×6 交替)定 Adreno 正负。
连接:三机改 Wi-Fi(Mate 10 192.168.1.11、P50 192.168.1.6 `adb tcpip 5555`、iPhone devicectl 配对 Wi-Fi)。
- **P50 Wi-Fi 长序列(batch44,拔 USB 前 9 臂)**:默认 473.4 / 480.1 / 487.2 / 482.2 / 480.6(中位 481)vs KP 467.2 / 453.1 / 482.1 / 481.0(中位 474)⇒ Adreno **≈ −1%,不赔**。
## 🏁 09-06 15:1x KP 进三端默认(产品 TU 标签 **V8** `blocked(fma4x4+direct+w64+nopb+f16+keyscan3+ptr+kp,V8)`,退回 `…_NOKP=1`;Mac abi/parity/db51 全绿;默认文本与三机跑过的 KP=1 文本逐字节同,**探针/台架无需再装**)
三端相对 09-06 凌晨形态 A:**A16 68.2 → 60.3(−12%,0.86× 原生 Metal)、Mate 10 816 → 534(−35%)、Adreno 660 467–488 → 470–481(≈0)**;全部逐字节同。
连接:P50 拔 USB 后 adbd 复位,tcpip 5555 关闭(Connection refused)——需要用户在开发者选项开"无线调试"并配对,或短暂插回 USB 再 `adb tcpip`。

## 🏁 09-06 15:13 生产上机:build 102(= build 100 原样换 PWOfficialSfm,A‴+KP 默认,V8)装上 iPhone 14 Pro
装机:装前备份 1400/1400 + 45/45 对账全绿;app 空闲 4 分钟后原地覆盖(用户明令);装后清单缺失 0。**首场 未命名(4)(15:32,30 张)**:`matcher_backend.jsonl` = `blocked(fma4x4+direct+w64+nopb+f16+keyscan3+ptr+kp,V8)`;cpuM=0、raw-fallback=0、rc=ok ×30、0 error;registered 30/30、points 23211。
| 场次(同机,13312 预算) | 匹配核 | 张数 | 单张中位 | 提取中位 | 匹配中位 | 候选中位 | 热状态 |
|---|---|---|---|---|---|---|---|
| 09-03 11:31 / 18:39(原生 Metal) | metal | 20 / 20 | 2012 / 1610 | 719 / 600 | 1106 / 901 | 10 / 10 | nominal |
| 09-04 23:13 / 23:30(build 100 Dawn) | mma V0 / tiled | 20 / 20 | 2593 / 2657 | 478 / 516 | 2042 / 2080 | 10 / 10 | nominal/fair |
| 09-06 15:07 未命名(2)(build 100,我台架烤热) | mma V0 | 33 | 2802 | 970 | 1763 | 12 | serious ×33 |
| **09-06 15:32 未命名(4)(build 102)** | **blocked V8** | 30 | **1472** | 614 | **803** | 12 | fair 16 / serious 14 |
每候选匹配:build 102 ≈ 67 ms vs 原生 Metal 90–111 ms vs build 100 Dawn 204–208 ms。用户体感:"这次就快多了"。

### 09-06 15:5x KP 之上的收尾变体(KP+2 路展开 / KP+倒计数;文件推送)
Mate 10:kp 534–535(首臂 676 冷态)、kp_u2 541–542(+1.3%)、kp_cnt 535–539(0);A16(整机半速态,只看比值):kp 125、u2 127(+1%)、cnt 125(0)⇒ 两根都不赚,**KP 是核的终点**。
### 生产每张预算(build 102,未命名(4),30 张,来自设备日志)
add_frame 平均 1556 ms = 提取 625(40%)+ 匹配 853(55%,候选均 9.6 ⇒ 每候选 89 ms)+ 其它 78;拍完 refine 9.0 s + colorize 2.4 s。
台架同对 13312²:GPU 50.9 ms / 墙钟 60.3 / 4 块提交 ⇒ 主机侧分块+同步 ≈ 16%;生产每候选 89 vs 台架 60 的差 = 热态 + 分块 + 采集期让路策略(ThermalGap/FPS30)。
下一刀候选:① 分块策略(CHUNK_TARGET_MS 默认 vs 0 vs 32,逐字节无关,两机测中);② 提取器(WGSL,08-10 九段趋平 orient/pyramid/detect/affine/desc 各 ~100 ms,收益递减);③ 拍完 refine 9 s(Ceres BA)。

### 09-06 16:0x 分块/热隙策略(主机侧,逐字节无关)
| 端 | CHUNK_TARGET_MS=16(默认,4 块) | 32(2 块) | 0(单次提交) |
|---|---|---|---|
| A16(此时 thermal=serious,台架带 capture_active) | 125.2 / 126.0(GPU 51.5) | 114.3 / 116.7(GPU 48.8) | **54.7 / 54.5** |
| A16 原生 Metal 臂(同状态) | 149.9 / 151.2 | 136.7 / 132.4 | 58.6 / 58.6 |
| Mate 10(nominal) | 551 / 538 | 530 / 531 | 551 |
**重新定性"A16 半速态"**:不是时钟降频——同一时刻单次提交的 dawn 54.7 / metal 58.6 都是正常速,慢的只有分块臂 ⇒ 是 **ThermalGapPct(serious=100%)在每块后插入等长空隙**,台架带 capture_active 所以和生产一样触发。生产 serious 时每候选 ≈ 2× 就是这条策略(热稳定硬约束,用户所定),不是核。
Mali 上分块 ≈ 0 成本;A16 nominal 下分块成本以 09-05 的 monolithic 59.3 vs 5 块 69.6(15%)为准(colchunk 已去掉尾部空转)。
⇒ 匹配段在生产里剩下的三块:热隙策略(产品决策)、分块次数(FPS30 时 24 ms 档,产品决策)、每候选 ~40 ms 的非核开销(上传/合并/回读/CPU 几何验证,待拆)。

## 09-06 16:3x 三块并行 · 第 1 块:让路/热隙策略调研落地(一手:Apple 文档/WWDC19-422/WWDC20-10632、Asahi 逆向、Khronos VK_EXT/KHR_global_priority、AOSP、Arm 异步计算博客、Linux msm a6xx_preempt.c、Qualcomm 专利、Computational Sprinting)
- **业界没有一家用"睡眠空隙"控热**:Apple 对 fair/serious/critical 的处方全是减工作/降帧率(critical=停相机),ARCore/Snap/Unity Adaptive Performance 同;我们 GAP 100%/300% 零外部背书。
- **物理**:温升由热时间常数窗口内的平均功率决定;空隙只在匹配队列背靠背排队(深度≥2)时才降平均功率,拍摄节奏慢于 GPU 忙时的话空隙只是把空闲挪位——温度收益≈0、墙钟 +50% 以上是确定的。
- **iOS**:Metal 无 GPU 优先级 API(MTLIO 的 priority 是 I/O),固件有抢占但不暴露;Apple 唯一指导是"command buffer 越少越好",16 ms 分块是自研策略非 Apple 推荐;预览若走 AVCaptureVideoPreviewLayer 由系统合成器承担,自绘(ARSCNView/Metal)才与 compute 同权。
- **Android**:`VK_EXT/KHR_global_priority` 在 Adreno/Mali 驱动广泛声明,正确姿势=把 compute 队列建成 LOW(永远被允许);Arm 明文高优先级队列可抢占;Adreno 老代长 compute 会冻屏 ⇒ 保留粗分块保底;Camera2→SurfaceView 预览不经 app GPU。
- **推荐**:让路与控热解耦——默认单次提交,预览/UI 帧时序超阈值才切块(滞回);热隙只在"队列深度≥2 且 serious"时启用,长度按 kernel 耗时膨胀率(iOS)/getThermalHeadroom(Android)连续调;承认逐字节不变约束下热隙对温度的贡献上限很小,由用户裁决用拍摄节奏买热稳定值不值。
- **零构建 A/B 路径**:official_env.json 推 `OFFICIAL_AETHER_MATCH_GAP_SERIOUS_PCT`(0/50)与 `OFFICIAL_AETHER_MATCH_CHUNK_TARGET_MS(_FPS30)`,重启 app 后拍同类场,对比每张 match ms 与 thermal 轨迹。

## 09-06 16:4x 第 3 块 · 安卓提取器探针可行性(只读考古)
- 提取器 = 纯 C++20 + Dawn(`tools/sift_extract_dawn.cc`、`sift_pyramid_dawn.cc`、`dawn_kernel_harness.cpp`、`bench/dsp_sift_gpu_c.cc`、`src/sfm/canonical_feature_selector_v1.cc` + `official_preclamp_instr_v1.cc` + `sha256.cpp`),无 Eigen/glog/Apple 依赖;宏 `AETHER_FEATURE_SELECTION_ENV_OFFICIAL=1 AETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1` + 两个字符串宏。CPU 回退符号 stub 掉即可。
- 契约:输入 8-bit 灰度紧凑 w*h(4032×3024),`aether_dsp_sift_extract_gpu_v2(gray,w,h,8192,…)` → xy(+0.5)+128 u8 描述子(与 fx13 a.u8 同格式,可直接喂匹配探针);内部 6 层/octave 全部常驻一个 f32 缓冲 ≈390 MB。
- 九段钩子已在:`aether_sed_last_stages(double[9])`(主机墙钟)/`aether_sed_last_stages_gpu`(GPU 时间戳,需 `OFFICIAL_AETHER_GPU_TIMESTAMPS=1` 且 adapter 有 TimestampQuery:P50 有、**Mate 10 无**(timestampComputeAndGraphics=false)⇒ Mate 10 只有主机九段)。
- WGSL 烘进二进制;探针用 `-DAETHER_WGSL_DIR=/data/data/com.kyle.pwprobe/files/wgsl` 编 ⇒ 之后 14 个 sift_*.wgsl 推文件迭代(**一次装机**);iOS 台架要推文件需 load_wgsl 加运行期 env(小补丁)。
- Mate 10 三个未知量:harness 无条件要 Subgroups 特性(Mate 10 subgroups=0 ⇒ RequestDevice 失败)、要求 1 GB 缓冲上限、Null adapter 静默回退——各需 1–3 行 harness 补丁 + 先打印 GetLimits。
- 夹具:12MP 图在 `~/Documents/progecttwo/.fixtures_12mp.nosync/frames/f_01..17.png`;三端逐字节闸要统一 `frame1.gray`(Mac 转一次,三端 fread)。f16 描述子核在有 ShaderF16 时自动启用 ⇒ 跨端比对要带 `SED_FORCE_F32=1` 臂。
- 工作量:小时级的确定工作 + Mate 10 三个未知量;**需要一次探针装机(待用户批)**。生产 A16 的九段可先由 env 诊断零构建拿到(sfm_match_fail.jsonl 的 gpu_timestamp_frame_v1)。

## 09-06 17:0x 第 2 块 · 生产"match=853ms"真相(核心自带 frame_split,零构建;prod_splits/*.jsonl)
代码地图(agent):`match_ms` 从 `official_aether_sfm_c.cc:9233` 到 `:10241`,含候选循环 + **每帧局部 BA**(`IterativeLocalRefinement`)+ 三角化 + tail-cache + 预览快照 + 诊断;每候选 GPU 路径 ≈ 7 次 host↔GPU 同步(DIRECT 预转置 SubmitAndWait + N 块 + finish + map),**A/B 预转置每候选重做**(B 一帧被转 12 次);驻留已开(Swift 插件 setenv);probe_batch 是死路径;overlap 生产者线程的 gpu_ms 未计时(恒 0),但 `m_gpu`(每块 submit→done 之和)可用。
| 场次(每帧中位) | cand | m_gpu(GPU 匹配) | m_chunks | m_sleep | tvg | tri | **lba** | tail(=等 GPU+cache+预览+诊断) |
|---|---|---|---|---|---|---|---|---|
| 09-03 10:40 原生 Metal | 9.5 | 697 | 52 | 0 | 65 | 3 | 135 | 675 |
| 09-03 11:15 原生 Metal | 5 | 121 | 10 | 9.5 | 16 | 1 | 32 | 143 |
| 09-04 15:14 / 15:31 build 100 | 9.5 | **1961 / 1965** | 133 / 120 | 0 | 26 / 41 | 1 / 1.5 | 46 / 82 | 1968 / 1938 |
| 09-06 15:07 build 100 未命名(2) | 12 | 1116 | 51 | 17 | 62 | 7 | 458 | 1200 |
| **09-06 15:32 build 102 未命名(4)** | 12 | **419.5** | 27 | 0 | 22.5 | 3 | **263.5** | 466.5 |
读法:build 102 把 GPU 匹配从 build 100 的 ~1960 压到 **420 ms/帧(每候选 35 ms,4.7×)**;"match=853" 里剩下的大头是 **每帧局部 BA 264 ms(31%)** 与等待/杂项 ~140;TVG 只有 22。
无损刀清单(第 2 块):(a) 预转置布局驻留(与 ResidentBuffer 同键,省每候选 2 次 xpose+同步);(b) 每候选同步次数 7→2(转置驻留后:N 块+finish 合并、map);(c) 生产者线程 gpu_ms 计时补上(15 行);(d) 每帧 LBA 264 ms 是下一座山(Ceres,另立战役)。(a)(b)(c) 都在 Dawn TU/核心 = build 103(PIPELINE_ONLY)。
第 1 块结合:fair 热态下分块本身只 ~3 ms/候选(27 块/帧 ≈ 2.25/候选),真正翻倍的是 serious 热隙 ⇒ A/B 只需动 GAP_SERIOUS_PCT。

## 09-06 16:4x 第 2 块 · XRES 台架实测(生产同款驻留回路:每帧 1 新图 × 12 驻留候选 × 4 帧;用户令:台架测,不上生产)
| 端 | 臂 | 每候选 p50(稳态,ms) | 每帧 ms(4 帧) | 逐字节 |
|---|---|---|---|---|
| A16(台架 TU 3c2a96fd5d3c) | XRES(默认) | **57.8 / 57.4** | 661–711 / 690–727 | 与非驻留 sha 同 |
| A16 | NOXRES=1 | 60.9 / 59.8 | 711–738 / 716–727 | 同 |
⇒ A16 每候选 **−4.5%**(≈ 跳过的两次转置 + 一次同步),12 候选/帧省 ~30 ms。分块 48/帧(每候选 4 块)。Mate 10 batch47 进行中。
- **Mate 10 驻留回路 XRES**(batch47,12 候选 × 4 帧):xres 322.6–329.3 vs NOXRES 327.0–329.2 每候选 ⇒ ≈ −1%(噪声内,不赔);sha 同。
- **🔴 尺子更正(09-06 16:2x)**:探针批一直用 reps=1 ⇒ RESULT p50 = 首次调用,**含管线编译与首次上传**。Mate 10 暖态复测(reps=3):p50 306.3 / min 304.5 ms,而单臂数字是 5xx。**所有 Mate 10 / P50 的单臂绝对值都含 ~200+ ms 一次性开销;相对比较不受影响(同一常数),但 README 里"Mate 10 573 ms"这类绝对值以暖态复测(batch49)为准。** A16 台架自带预热,不受影响。
- **FINISHFOLD**(aeb9eb3):finish(合并核+两次拷贝)折进最后一个列分块的命令缓冲(每候选 −1 次同步);**XFOLD**(5f4a70d):DIRECT 预转置折进第一个分块(需要转置时 −1 次同步)。两刀 Mac:sha 同、parity PASS、db51 162/162、ABI PASS;env NOFINISHFOLD/NOXFOLD 关。三刀合并(XRES+FINISHFOLD+XFOLD)在两台台架的驻留回路上 all-on vs all-off 对照中。
- **A16 台架驻留回路,三刀合并(XRES+FINISHFOLD+XFOLD)vs 全关**:每候选稳态 **56.4 / 56.4 vs 60.3 / 59.7(−6%)**,每帧 672–700 vs 714–730 ms;逐字节同。(XRES 单独 −4.5%,两次折叠再 −1.5%。)
- **Mate 10 台架驻留回路,三刀合并 vs 全关**(batch48):allon 322.6 / 325.8 vs alloff 324.8 / 326.9 / 330.5 每候选(稳态)⇒ ≈ −1%(噪声内,不赔);后两臂设备漂移(帧 6–9 s,锁屏/热)不入。sha 同。
**三刀(XRES+FINISHFOLD+XFOLD)三端结论**:A16 −6% / Mali −1% / Adreno 未测(P50 不在手);逐字节同;已在 Runner-103-xres.app 里备好,不装。

### 🏁 09-06 16:4x Mate 10 暖态复测(reps=3,p50 / min;batch49)—— README 里 Mate 10 的绝对值以此为准
| 形态 | p50 ms | min ms |
|---|---|---|
| 形态 A(09-06 凌晨默认) | 602.3 / 597.3 | 554.7 / 544.8 |
| **默认 A‴+KP(V8)** | **302.7 / 303.0** | **297.8 / 300.0** |
⇒ Mate 10 暖态 **−50%(2.0×)**;此前单臂(reps=1)数字含 ~200–270 ms 首次调用开销,稀释了比值(报成 −35%)。sha 同。

## 提取器无损刀(09-06 下午,Mac M3 宿主 CLI;设备段账待 iPhone 隧道恢复)

逐位闸定案:max_features 截断时(8192/32768)同一二进制两次运行的集合摘要都不同——42418 个候选里挑 8192 的选择器按 GPU 原子追加序破并列,**生产今天就不是跨运行确定的**;cap 65536(不截断)两次运行四摘要全同 ⇒ 提取器刀的逐位闸 = cap 65536 下 desc/xy/scale/ori 四摘要全同。下表所有刀都过了这道闸。

| 刀 | 改动 | Mac M3 12MP 段 GPU ms(cap 65536) | 逐位 |
|---|---|---|---|
| K1a | DoG 26 邻域早退(`sift_dog_detect.wgsl`) | detect 15.4→9.3 | ✓ |
| K2a | fused blur 源段+taps 进共享内存 | pyramid 25.7→25.3 | ✓ |
| K2b | K2a + 环形缓冲 64 行按位与(去 `% 40`) | pyramid →23.1 | ✓ |
| K2d32 | K2b + 每块 32 行(256 线程) | pyramid →20.4(2-pass 基线 19.9) | ✓ |
| K2d16 / K2e | 16 行 / 16 列×16 行 | 21.2 / 21.5 | ✓ |
| K5a | 仿射三路归约合一(21→7 barrier/迭代) | affine 24.0→24.5(无收益) | ✓ |
| **K7** | 网格分桶非极值抑制(host 四 pass,`OFFICIAL_AETHER_SUPPRESS_GRID=0` 关) | **suppress 20.4→0.5** | ✓ |

合刀(K1a+K2d32+K5a+K7)cap 8192:p50 134.0→105.6~108.8 ms(−21%),GPU 段和 103.8→72.4(−30%)。Mac 上 2-pass blur(19.9)本就比 08-10 的 fused(25.7)快,fused 的胜负要在设备上重判。K7 已在 aether_cpp 暂存(commit 因 iCloud .git 写超时未落,补丁在 ~/Developer/pw_extract_knives/k7_suppress_grid.patch);WGSL 变体持久副本 ~/Developer/pw_extract_knives/。

### 补充(09-06 傍晚,Mac M3)

| 刀 | 改动 | 结果 | 判决 |
|---|---|---|---|
| **K8** | 金字塔 packed/scratch/tmp 三缓冲按 (device,size) 跨帧常驻,省掉 Dawn lazy-clear 每帧 ≈490 MB 清零(host,`OFFICIAL_AETHER_PYR_PERSIST=0` 关) | pyramid host 50.9→23.8 ms(wait 49.1→21.8),逐位同 | ✓ 但 +490 MB 常驻,产品侧要空闲释放钩子(待用户) |
| K2f | 2-pass blur 8×8 tile+halo 进共享内存 | pyramid 19.5→25.4 | ✗ |
| K4a | 方向核 imsmooth 三段同序循环去 clamp | orient 19.4→23.5(逐位同) | ✗ 三段不等长 ⇒ lane 分歧 |
| K4b | imsmooth 静态 15 步 + 统一谓词、taps 常量索引 | orient 19.5→21.0(逐位同) | ✗ |
| 诊断 | 方向核去 imsmooth 两趟 | orient 19.5→5.8 | imsmooth 占方向段 70%(非刀) |

**Mac 全刀(K1a+K2d32+K5a+K7+K8)cap 8192:134.0→85.4 ms(−36%)**;剩余 GPU 段:pyramid 20 / orient 19.4 / affine 14.6 / detect 9.2 / desc 8.4 / suppress 0.5。设备验证链 `/private/tmp/ext_k78_chain.sh`(归档+bench 已编好,等 iPhone available 后一次安装,9 臂:old/new/kall × 65536 逐位闸 + 8192 计时 + 2-pass)。

### A16 设备实测(09-06 21:0x,PWMatchBench 一次安装,frame1.gray 12MP,reps 3)

| 臂 | cap | p50 ms | GPU 段 ms(pyr/det/sup/aff/ori/desc) | 摘要 |
|---|---|---|---|---|
| old(GRID=0,PERSIST=0,烘焙 WGSL) | 65536 | 1043 / 1031 | 95/107/79/146/217/232 | 3307182d4163 两次同 |
| new(K7+K8) | 65536 | 922 | 93/107/**0.9**/146/217/232 | 同 |
| kall(+K1a+K2d32+K5a) | 65536 | 867 | 86/**71**/1.0/**136**/216/232 | 同 |
| old | 8192 | 672 / 667 | 96/107/79/87/129/48 | (截断非确定) |
| new | 8192 | 557 | 93/107/0.9/87/129/47 | |
| **kall** | 8192 | **510(−24%)** | 86/71/1.0/82/129/47 | |
| kall + GSS_FUSED=0(2-pass) | 8192 | 514(min 484) | **78**/71/1.0/82/130/47 | |

要点:① 逐位闸在设备上成立(cap 65536 三臂同、老路径两次同);② K5a 在 A16 −6%(Mac 零收益)⇒ barrier 在 A16 更贵;③ **2-pass blur 在 A16 GPU 77.8 < fused 85.9 < 老 fused 96 ⇒ 08-10 的 GSS-FUSED 在 A16 是赔的**(交替 3 轮复验 R2 链跑中);④ 方向段 129 ms 成为最大段(31%)。老路径首尾两臂 672/667 ⇒ 无热漂移。

### A16 复验 R2/R3(09-06 21:3x–22:0x,env-only,无重装)

| 臂 | pyramid GPU ms | orient GPU ms | 判决 |
|---|---|---|---|
| fused(K2d32)×3 | 86.3 / 86.1 / 86.0 | 129 | |
| 2-pass ×3(+R3 两次) | 78.1 / 77.9 / 77.8 / 77.8 / 78.0 | 129 | **2-pass 在 A16 稳定 −8.3 ms**,Mac 也 19.0 vs 19.9 |
| K2f(2-pass tile 分段) | 112 | | ✗(逐位同但 +34) |
| K4a / K4b(方向核循环重排) | | 156 / 136 | ✗(逐位同但更慢),原版循环两端最优 |
| 诊断:去 imsmooth | | 42 | imsmooth = 方向段 67%(A16)/70%(Mac) |

K8b:2-pass 路径的 octave scratch 也常驻(按 slot+size 缓存),Mac 上 2-pass pyramid host 50→24 ms、与 fused 持平;cap 65536 逐位同。2-pass 路径的 wall 收益要 K8b 进归档后才在设备上兑现(本轮 bench 归档只有 K8)。

**定案(A16 + Mac,Mali/Adreno 提取器未测——无 APK):** WGSL 默认切成 K1a+K2d32+K5a(已写进 shaders/wgsl 工作树,补丁 wgsl_defaults_k1a_k2d32_k5a.patch);host 默认 K7+K8(b);GSS_FUSED 默认是否翻成 2-pass 待用户裁决(两端都赢但缺 Android 数据)。

### ⚠️ 操作点更正:生产 cap = 13312(09-06 22:2x,A16 重跑,env-only)

上两节的 8192 计时是错的操作点(用户:"有用也不会上生产")。以下为生产参数(12MP,max_features 13312,reps 3):

| 臂 | p50 ms | GPU 段 ms(pyr/det/sup/aff/ori/desc) | GPU 和 |
|---|---|---|---|
| old ×3 | 842 / 853 / 832 | 95/107/79/142/211/81 | 715 |
| K7+K8 | 737 | 94/107/0.9/142/212/81 | 637 |
| 全刀 fused ×2 | 689 / 690 | 86/71/1.0/133/212/81 | 584 |
| 全刀 2-pass ×2 | 691 / 690(min 663/672) | **78**/71/0.9/133/212/81 | 576 |

**A16 生产操作点:842 → 690 ms(−18%);GPU 段 715 → 576(−19%)。** 13312 下 (o,s) 前置剪枝几乎不剪 ⇒ orient 212 + affine 133 = GPU 60%,都是未动的段(K5a 仅 −9)。2-pass 仍稳定比 fused 少 8.5 ms GPU,wall 持平(K8b 未进本归档)。Mac 13312:167 → 114(−31%)。

### 09-06 深夜 · orient/affine 无损刀(A16,cap 13312,env-only)

| 刀 | 改动 | A16 段 GPU ms | 判决 |
|---|---|---|---|
| **K9o** | 方向核 workgroup 64→256 lane(逐像素独立、直方图整数原子、max 顺序无关;host 零改动) | **orient 212→120,总 690→600(601/598)**;128 lane=147 | ✓ 逐位同(65536) |
| K9d | 描述子核 64→256 lane | descriptor 81→127 | ✗(8 次原子加/像素撞地址) |
| K9(仿射直接 256) | Mac affine 23.6→46 | — | ✗ 二阶矩求和顺序绑 64 lane,其余 lane 空转 |
| K4c-v | imsmooth 边缘复制去 clamp | orient 212→217 | ✗ |
| K6a | 双线性 4 采样索引提升 | affine 132.8 / orient 213(持平) | 零收益 |
| K10 | 仿射 128-lane 装两个 keypoint(各 64 lane 原序) | Mac affine 23.7→31.8(赔);A16 跑中 | 待定 |

根因(K9o):方向核共享内存 13.4 KB ⇒ 每核驻留 workgroup 少,64 lane 只有 4 个 SIMD 组藏不住共享内存/barrier 延迟;扩 lane 不改任何求和顺序。

调研台账(agent,09-06,原文抓在 scratchpad):Apple 每 threadgroup 上限 32 KB、每核容量未公布(32 vs ~60 KB 二手源矛盾);**Mali 没有专用共享内存,shared=L1/L2 背书**(Arm BP 3.4 §9.3),Bifrost 每核 L1 16 KB;Adreno local 片上、"maximal waves<4 要减复杂度"(Qualcomm 80-NB295-11);WGSL textureGather = 线性采样会用的 4 纹素、Vulkan 按 LINEAR 规则 i0=⌊u−0.5⌋、Metal = ±半像素 nearest,喂 u=⌊x⌋+1.0 三端脚印一致,但 r32float 非可过滤时 gather 的 WebGPU 校验**未证**;Apple IMUL32 4 拍 / IMULHI 8 拍(metal-benchmarks),Adreno 整除极贵;VLFeat covdet 仿射每迭代重 warp,无精确捷径;PopSift/CudaSift 都不做位相同;Dawn lazy-clear 可按 device 关但实测无收益(成本是 OS 新页清零)。

**K10 判决(A16 13312 ×2):affine 133→174/174,赔 ⇒ 淘汰**(两个 keypoint 迭代次数不同要互等)。

### 🏁 09-06 提取器收官(A16,12MP,cap 13312,reps 3)

| 臂 | p50 ms | GPU 段(pyr/det/sup/aff/ori/desc) | GPU 和 |
|---|---|---|---|
| 老路径(现役 Dawn 提取器)×3 | 842 / 853 / 832 | 95/107/79/142/211/81 | 715 |
| **全刀 = K1a+K2d32+K5a+K9o(WGSL)+K7+K8(host)** ×3 | **601 / 598 / 598** | 86/71/1/133/119/81 | 491–499 |
| 全刀 + 2-pass blur | 600(min 577) | 78/71/1/133/119/81 | 484 |

**842 → 600 ms(−29%)**,cap 65536 四摘要全同。仍未动:affine 133(64-lane 求和顺序封死占用率路)、descriptor 81(原子撞地址)、detect 71、pyramid 78–86。K8 常驻已被用户否决,去掉 K8 约 +45 ms。WGSL 默认已切 K1a+K2d32+K5a+K9o(工作树,补丁 wgsl_defaults_k1a_k2d32_k5a_k9o.patch)。Mali/Adreno 提取器未测(无 APK);Mali 没有专用共享内存,K9o 在 Mate 10 必须单独验。
