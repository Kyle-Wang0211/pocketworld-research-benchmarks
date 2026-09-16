# Release Dawn：白赚 10%，以及一条被推翻的口径（2026-09-16）

回放通道（设备录像 849 帧，输入逐字节固定），臂 `gpufe_nothread`，1920×1440，全程 nominal，ABBA 轮转臂序。

| | Debug Dawn | **Release Dawn** | |
|---|---|---|---|
| base（split 关） | 31.31 / 31.53 | **34.67 / 34.31** | **+9.8%** |
| split 开 | 39.61 / 39.53 | **43.92 / 44.21** | **+11.3%** |
| base 空提交 | 0.61 / 0.62 | 0.59 / 0.58 | 不变 |
| **split 空提交** | 5.96 / 6.25 | **6.18 / 6.38** | **不变** |
| pre_gpu | 10.86 / 10.75 | 10.68 / 10.65 | 不变 |
| 引擎框架体积 | 39.9 MB | **13.1 MB** | |

判据：Debug 库内 `Validation` 字样 17 070 处，Release 76 处。
构建脚本改为 `PW_DAWN_FLAVOR`（默认 Release，可切回 Debug 做对照）。

## 结论
1. **Release Dawn 两条臂各白赚约 10%**，逐场稳定。纯工程欠账（09-11 已记录未执行）。
2. 🔴 **空提交延迟不是校验层**：Release 之后几乎不变。先前把它归给 Debug Dawn 是错的。
3. 🔴 **口径更正**：`empty_submit_ms` 此前被当成**可加的每帧成本**（"split 多付约 5.4 ms"）。
   证伪：**split 提交两次却更快**（44.06 vs 34.49，+27.7%）。
   [arXiv:2604.02344](https://arxiv.org/html/2604.02344v1) 原句："Single-operation measurements include GPU-CPU
   synchronization overhead. Sequential measurements … isolate the true per-dispatch cost"，单次测法高估 10–60×；
   我们的 `probe_latency()` 正是单次 dispatch + 同步。
   ⇒ **它是带同步的唤醒延迟诊断量，不是每帧可加成本**，凡用它做加减法的账作废。

## 待办
生产 iOS 框架据 09-11 记录也链 Debug Dawn ⇒ 生产的匹配器/提取器可能背着同一层，需另行核实并定价。
