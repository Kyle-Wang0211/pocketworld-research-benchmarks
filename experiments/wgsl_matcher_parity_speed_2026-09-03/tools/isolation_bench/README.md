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
