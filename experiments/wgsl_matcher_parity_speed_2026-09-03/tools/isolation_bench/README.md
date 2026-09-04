# 隔离台架(2026-09-04)

harness 的轮噪声常年 ±1ms 以上(iCloud 同步 / xcodebuild / devicectl 都会污染),
0.3ms 级的刀在它上面判不了。这个台架把**同一进程内交替**跑各变体,只读
`cb.GPUEndTime - cb.GPUStartTime`,实测噪声 **±0.02ms**。

- `k.metal` —— 手写 Metal 参照:复刻现役内层循环的形状(64 工作组 × 512 线程 ×
  256 块 × 4nt × 16 MMA + 预取 + 每块两次 barrier),`formA` 原地累加 /
  `formB` tint 那种独立 dst + 整块拷回。**两者实测完全一致**(3.87 vs 3.87)
  ⇒ Metal 编译器会合并那次拷贝,不是差距来源。
- `main6.mm` —— 多变体交替台架。把 `OFFICIAL_AETHER_MATCH_DAWN_DUMP=1` 导出的
  tint MSL 切出来(第一个 `#include <metal_stdlib>` 到第一个 `dawn_entry_point`
  的收尾 `}`),改名后即可与手写形态同台。
- `main10.mm` —— 加 `NB` 环境变量扫 numB,用来验分块是否会反转结论。

## 它得出的定量分解(这是整场战役最有信息量的一次测量)

| | p50 (ms) |
|---|---|
| tint 完整 | 7.485 |
| tint 仅 MMA(删掉两次 barrier 之间的全部内容) | 4.282 |
| tint MMA+预取 | 5.989 |
| tint MMA+扫描 | 7.050 |
| 手写 仅 MMA | 3.873 |

⇒ **MMA 段只慢 11%,扫描段值 2.77ms**。而 harness 里把扫描循环体截断到 1 次
只省 0.86ms ⇒ 剩下 1.9ms 是**脚手架**,不是迭代。这直接推翻了"压缩扫描迭代数"
那一族刀(COL-SCAN-4x 的零收益由此得到解释)。

## 配套的定价探针(都在生产 TU 里,env 开关,输出作废或不变)

- `NOSCAN` 把两个扫描循环截断到 1 次 → 扫描迭代 = 0.86ms
- `XBARRIER=n` 在 nt 循环里**多加** n 次 barrier(删 barrier 会产生竞态、被
  harness 的跨 rep 确定性闸拦下 —— 那道闸是对的)→ 单次 barrier ≈ 0.4µs,
  现役两次共 ~0.2ms。⚠️ 相邻同种 barrier 会被 Metal 编译器合并,必须放在被
  MMA 隔开的程序点上,否则量到零。
- `STAGE0` 预取恒读第 0 块(输出错但确定,能过确定性闸)→ 预取内存 ≈ 0
  (B 全矩阵才 2MB,64 个工作组全命中 SLC)。

## 🔴 safe_run.sh —— 跑手工改过的着色器必须经这里(2026-09-04 两次事故后加)

两次 GPU 挂死都是自己写的着色器,**都编译通过**:
① 切 MSL 变体时把列循环自增 `col0 += 32` 一起删掉 → 死循环
② python 替换写出 `threadgroup int* __restrict cip = &cip[0];` → 野指针
一次挂死烧掉 11 分钟,并让整机 GPU 进入 2× 慢的降级态。

三道闸:
1. **冒烟** —— 先用 NB=256 跑一次(20s 超时)。死循环/野指针 3 秒内暴露,不是 11 分钟。
2. **硬超时** —— macOS **没有 GNU `timeout`**,用 `perl -e 'alarm; setpgrp; exec'` 杀整个进程组。
3. **阳性对照** —— `pc.mm` 跑手写参照核,不在 3.87±0.15 就**拒绝出正式数**。

`pc.mm` 本身也是个有用的诊断:它把 K 次 dispatch 塞进同一个 command buffer/encoder、
用 `memoryBarrierWithScope` 串行化,**零 CPU 空隙**。K=64 时离散归零 —— 用它可以区分
「CPU 饥饿导致 GPU 不升频」(K 增大就恢复)与「频率被真正压住」(K 增大也不恢复)。

### 降级态的排查清单(2026-09-04 逐项做过)
| 项 | 结果 |
|---|---|
| 残留台架/僵尸进程 | 无 |
| 低电量模式(电池档 + 电源档各一份) | 两档都 0 |
| 热警告 `pmset -g therm` | 无;在充电,电池 100% |
| 驱动 GPU 重置 `ioreg` **`recoveryCount`** | **0 —— 从未发生**,"挂死弄坏驱动"没有支撑 |
| CPU 饥饿 / DVFS 空隙 | 用 `pc` K=64 饱和排除(仍 8.0ms) |
| ⚠️ `ioreg` 的 `"Device Utilization %"` | **坏探针**:加已知负载读数不变(恒 100),**不可用** |

⇒ 目前唯一已知有效的恢复手段是重启;但**根因是我的着色器 bug,不是日常使用会遇到的**,
上面三道闸把"挂死"的代价从 11 分钟 + 一次重启降到 3 秒。

## 09-04 晚新增:GEMM 形态四核(每对只差一个变量)

| 文件 | 常驻 A 块 | 每 k B 载入 | 每 k MMA | 用途 |
|---|---|---|---|---|
| `k.metal` | 16 | 1(提出循环) | 4(单链) | 原始形态,阳性对照 |
| `k_ilp4.metal` | 16 | 4 | 4(**4 条独立链**) | **现役**:循环交换,已上生产 |
| `k_r2b.metal` | 16 | **2** | 4 | 只砍载入(用 `aFrag[15-k]` 冒充第二行块)⇒ **−4.0%** |
| `k_r2.metal` | **32** | 2 | 4 | 真两行块 ⇒ **+20.1%**,R2 判死的直接证据 |
| `k_ilp4_noload.metal` | 16 | **0**(全提出) | 4 | **纯 MMA 地板** ⇒ 载入只值 14.6% |

台架 `tt5.mm`(k vs k_ilp4)/ `tt6.mm`(ilp4 vs r2)/ `tt6b.mm`(ilp4 vs r2b)/ `tt6c.mm`(ilp4 vs 地板)。
全部经 `safe_run.sh` 三道闸。🔴 `maxTotalThreadsPerThreadgroup` 两边恒 1024,**不是占用率探针**。
