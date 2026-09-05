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
