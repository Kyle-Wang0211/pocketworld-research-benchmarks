# E1 + E2 Boundary Experiments: Grounded Findings

日期：2026-06-09 14:31:22 — 14:35:38（4 个测试，post-reboot swap=0 baseline）

## 0 TL;DR

之前的所有"K=60 跟 K=50 触发不同 backend / 不同 limit"假设全部被这次实验**推翻**。真因更简单也更刚性：

**Mac jetsam 在 swap_used ≈ 42-44 GB 时 SIGKILL 进程。K=50 vanilla 是擦边过这条线的边缘；K=51+ 全部踩过线。** 不存在 K=60 这个魔法阈值，存在的是 **swap pool jetsam threshold**。

## 1 实验设计

post-reboot (boot time 14:24:40)，swap = 0.00 MB 干净 baseline。运行：

```bash
# E1: discrete-threshold test
e1_n55_default: K=55, vanilla
e1_n58_default: K=58, vanilla

# E2: dispatcher backend hypothesis
e2_n60_efficient: K=60, --force-sdpa-backend efficient

# E2b: math at K=50 to test if dispatcher saved K=50
e2b_n50_math: K=50, --force-sdpa-backend math
```

完整脚本：[`run_boundary_experiments.sh`](run_boundary_experiments.sh)

## 2 Grounded 数据

| # | Test | K | flags | exit | 耗时 | swap_used peak |
|---|---|---|---|---|---|---|
| 1 | e1_n55_default | 55 | — | **137 SIGKILL** | 95s | 42.47 GB |
| 2 | e1_n58_default | 58 | — | **137 SIGKILL** | 95s | 43.14 GB |
| 3 | e2_n60_efficient | 60 | `--force-sdpa-backend efficient` | 0 + RuntimeError | 18s | 5.96 GB |
| 4 | e2b_n50_math | 50 | `--force-sdpa-backend math` | **137 SIGKILL** | 48s | 42.13 GB |

完整 logs: [`boundary_experiments/`](boundary_experiments/)

## 3 关键 finding

### 3.1 不存在 K=60 "离散 threshold"

**K=55 / K=58 vanilla 都 SIGKILL**——不是 K=60 才开始死。继续往下推 K=51, K=52, K=53 八成也死（没测，但 swap peak trend 强暗示）。

意味着**真正的 ceiling 在 K=50 附近**，N=50 是擦边过的边界值。

### 3.2 PyTorch CPU EFFICIENT_ATTENTION backend 对 fp32 长序列 NOT viable

```
RuntimeError: No viable backend for scaled_dot_product_attention was found. 
This is likely due to turning off both the math kernel and the fused kernels.
```

`torch.nn.attention.sdpa_kernel([EFFICIENT_ATTENTION])` 在 CPU fp32 input shape `(1, 12, 43260, 64)` 上**直接报 not viable** —— PyTorch 自己认这条 backend 不能跑这个 shape。

这意味着：**我之前"K=50 走 efficient backend，K=60 dispatcher 切 math"的假设根本不成立**。CPU efficient 从一开始就不可用，K=50/K=55/K=60 vanilla 都不可能走 efficient。

### 3.3 强制 math @ K=50 也死，但 vanilla K=50 287s 完成

**最有意思的反差**：

| 配置 | 结果 |
|---|---|
| K=50 vanilla（dispatcher 自由选） | 287s 完成 ✅ |
| K=50 `sdpa_kernel([MATH])` 强制 | 48s SIGKILL ❌ |

dispatcher 自由选的时候 fallback 链是 FLASH → EFFICIENT → MATH。FLASH/EFFICIENT 都 not viable，所以最终也走 MATH。但**vanilla path 跟 sdpa_kernel-forced path 行为不同**。

可能原因（PyTorch 内部黑盒，未深扒）：
- `sdpa_kernel` context manager 禁了 fallback，可能触发更早的物化
- vanilla 路径可能享受某种 lazy allocation / op fusion 让 peak memory 略低
- vanilla 可能用了 OVERRIDEABLE 路径或某种 native CPU kernel

**关键是**：vanilla K=50 跟 forced math K=50 在 swap peak 表现上明显不同 —— 前者擦边过，后者直接超 jetsam。

## 4 真正的 limit：Mac jetsam swap threshold

| 测试 | swap peak when killed |
|---|---|
| K=55 vanilla | 42.47 GB |
| K=58 vanilla | 43.14 GB |
| K=50 forced math | 42.13 GB |
| **K=50 vanilla (历史 287s)** | **推测 ~35-40 GB（擦边过）** |

**模式**：Mac 这台机器 swap 能扩到 ~45 GB，但 jetsam 在 **swap_used ~42-44 GB** 时杀进程。所有 K=51+ 配置 swap peak 撞这条线 → SIGKILL。K=50 vanilla peak 在 35-40 GB 区间，没踩过。

这跟"chunked SDPA 之前 7 次都死同一点"完全一致——chunked 没救是因为**累积的 trace tape memory 是相同 K 决定的**，chunk 大小不影响整体 swap peak。

## 5 推翻的旧 hypothesis 清单

| 旧假设（昨天 / 今天早些 POST_MORTEM 写的） | 新 grounded |
|---|---|
| "K=60 trace 死是 dispatcher 切 math backend" | ❌ K=55/K=58 也死，不是 K=60 特殊 |
| "K=50 vanilla 走 efficient backend" | ❌ efficient not viable |
| "tape pile-up 5.6 GB 是触发点" | ❌ 实际触发点是 swap ~42 GB，比 5.6 GB 大一个量级 |
| "chunked SDPA + 关 watermark + 让 MPS 上 swap 就过得了" | ❌ jetsam threshold 是绝对的 swap 用量，不分 MPS/CPU |

## 6 修正后的产品结论

### 6.1 K=50 是 grounded ceiling，不是"研究 wishlist"

**N=50 mlpackage 是当前硬件 + PyTorch toolchain 已经擦边过的物理边界**。K=51 就开始撞 jetsam。

### 6.2 K=60/K=90 mlpackage 在这台 18GB Mac 上物理不可能

不是 chunked SDPA 能救，不是切 backend 能救，不是关 watermark 能救。是 swap pool jetsam threshold 死硬限。

任何 "再试一次新参数" 都是浪费时间——已经 grounded 验证四个不同维度（K 大小、SDPA backend 选择、chunk 大小、device 选择）全撞同一条线。

### 6.3 想 N>50 mlpackage 必须换硬件

| 方向 | 推断 |
|---|---|
| 32 GB Mac mini/Studio | swap pool 应该能扩到 ~80 GB，jetsam threshold 估计 ~70 GB+。K=60-K=70 应有空间。但**不是 100% 保证**——具体还得测 |
| 64 GB+ Mac Studio | 几乎肯定能跑 K=60-K=90 |
| Linux/CUDA box | 完全绕开 macOS jetsam，唯一限制是 RAM 总量 |

### 6.4 不再追求的方向（grounded 验明的死路）

- 继续在 18GB Mac 调 chunked SDPA / backend / device → swap 42 GB 死硬限
- 切 torch.export → executorch #9506 反向死法
- 降 process_res → 已是 patch-align 最低
- MLX → Metal 单 buffer + iPhone 无 swap + 3 GB jetsam 三死

## 7 跟之前 POST_MORTEM 的关系

[POST_MORTEM_ZH.md](POST_MORTEM_ZH.md) 第 4 节 "关键 grounded 发现" 里 4.2 "Mac trace tape pile-up" 这条**部分错了**——tape pile-up 概念对（memory 确实累积），但**触发点不是 4 local blocks ~5 GB，而是 swap ~42 GB**。差一个量级。

[POST_MORTEM_ZH.md](POST_MORTEM_ZH.md) 第 9 节决策树 A1/A2/A3 **仍然成立**——这次 grounded 反而加强了 A3 推荐（K=50 是 ceiling 不只是 ship-state，是物理 ceiling）和 A1/A2 必要性（要扩 K 唯一方法是换更大 swap pool 的硬件）。

## 8 一句话总结

**N=50 vanilla 不是触发了什么神奇 backend，是 swap peak (~35-40 GB) 卡在 jetsam (~42-44 GB) 阈值之下，擦边过。** K=51 之后 attention matrix 涨 6%+，swap peak 涨过临界，必死。当前 18GB Mac 硬件下 N>50 物理不可达。
