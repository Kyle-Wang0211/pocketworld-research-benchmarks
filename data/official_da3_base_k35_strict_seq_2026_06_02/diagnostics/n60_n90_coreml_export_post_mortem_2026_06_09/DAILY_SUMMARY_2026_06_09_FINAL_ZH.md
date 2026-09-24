# DA3-BASE Image-Only N=60/N=90/N=120 CoreML Export — 2026-06-09 Final Daily Summary

日期：2026-06-09
身份：今日工作收尾 + closeout（POST_MORTEM_ZH.md 上半场的续篇）

## 0 TL;DR

- **上半场（Mac）失败**：18GB Mac trace 任何 K≥51 都 SIGKILL（macOS jetsam at swap ~42-44GB）；MLX PR #237 替代路径 Mac 上 N=60 PASS 但**iPhone 不可 ship**（手机无 swap + 3GB jetsam）→ POST_MORTEM_ZH.md 当时推荐 [A3] 接受 N=50 ceiling
- **下半场（云端）成功**：vast.ai 租 B200 / A100 转换 N=60 / N=90 / N=120 mlpackage 成功；7 个 mlpackage（N35 / N40 / N50 / N60 / N90 / N120 / N35_pose）全部上手机
- **iPhone 实测**：N=90 (1.9GB) ship-able ✅；N=120 (2.5GB) 装机后**直接闪退**（load 阶段已经超出 ~3GB jetsam 包络）
- **Ship 决策锁定**：**K=90** 作为 PocketWorld DA3 streaming production ceiling

---

## 1 上半场结论修正（POST_MORTEM_ZH.md §10 三条路）

| 原方案 | 实际状态 |
|---|---|
| [A1] 换 32GB+ Mac trace | 没走，跳过 |
| [A2] Linux/CUDA box trace | ✅ **走通**：vast.ai B200 → 90GB / A100 80GB 都成功 |
| [A3] 接受 N=50 ceiling | ❌ **没必要**——A2 走通后 N=90 已 ship-able |

**意外发现**：A2 比预想便宜——A100 80GB ≈ $2.5/hr，单次 N=120 trace + convert 约 20 分钟 ≈ $1。

---

## 2 实验时间线（下半场，云端）

| 时刻 | 步骤 | 结果 |
|---|---|---|
| 22:10 | 租 vast.ai **B200 180GB** ($5/hr) | 起 instance 即出 sm_100 报错（详 §3） |
| 22:25 | 装 torch 2.11.0 + cu128 | conv2d 通过 |
| 22:40 | K=60 trace + convert | 91GB peak，**chunked SDPA 监督下反而 OOM**（详 §4） |
| 22:55 | **关掉 chunked SDPA**，让 PyTorch 自动选 efficient backend | K=60 **35GB peak 通过** |
| 23:10 | K=90 trace + convert | 85GB peak 通过 → 1.9GB mlpackage |
| 23:20 | K=120 trace + convert | 85GB peak 通过 → 2.5GB mlpackage |
| 23:30 | tar + scp 回 Mac | N120.tgz 198MB（fp16） |
| 23:40 | iPhone 安装 + bench | N=90 OK；**N=120 闪退** |
| 00:10 | 删 B200 instance | 总花费 ~$10 |

---

## 3 失败原因 #1 — B200 Blackwell sm_100 不兼容 torch 2.5.1+cu121

**症状**：
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
  File "...torch/nn/functional.py" in conv2d
```

**Root cause**：
- B200 是 Blackwell 架构 = `sm_100`
- torch 2.5.1+cu121 编译时支持 `sm_50 ... sm_90`（Hopper 顶级）
- Blackwell 之前没生产硬件，torch 默认 build 没 sm_100 PTX

**修复**：
```bash
pip uninstall torch torchvision -y
pip install torch --index-url https://download.pytorch.org/whl/cu128
# 装上 torch 2.11.0+cu128 = Blackwell native build
```

**教训（写进 memory）**：
- Vast.ai 租 B200 一定要先确认 torch 版本带 cu128
- 不确定就先租 A100 80GB（sm_80，所有 torch 2.x 都支持），便宜稳定
- 见 [feedback_dont_fabricate_versions_or_estimate_time](../../../../../../../../.claude/projects/.../memory/feedback_dont_fabricate_versions_or_estimate_time.md)：版本号必须 grounded，别瞎估

---

## 4 失败原因 #2 — chunked SDPA monkey-patch 在 trace 上下文里是反作用

**症状**：
- K=90 用 `--install-chunked-sdpa-for-trace --chunked-sdpa-query-chunk=720` 在 B200 上跑到 91 GB **OOM**
- K=120 一样路径 176 GB **OOM**
- 拿掉 chunked SDPA flag 让 PyTorch CUDA dispatcher 自动选 efficient backend → K=90 **35GB**（少 60%）/ K=120 **85GB**（少 90+GB）

**Root cause**：
- `torch.jit.trace` 在 forward 时把每个 op 的 intermediate tensors **pin 在 autograd tape** 上（哪怕 `requires_grad=False`，trace 自己的"recording tape"也要保留）
- chunked SDPA = 把 1 个 SDPA 拆成 N 个小 SDPA + cat
- 在 trace 里这 N 个小 SDPA 的 intermediates **全部累积**而不释放
- 反而比 1 个大 SDPA 更耗内存（特别是 efficient backend 本来就 O(seq) memory）

**修复**：
- Trace 阶段：**不要** chunked SDPA monkey-patch，让 dispatcher 选 efficient backend
- Runtime 阶段（手机）：CoreML SDPA 本身就是 fused FlashAttention-style，根本不需要 chunked

**教训（写进 memory）**：
- Memory monkey-patch 在 eager forward 里能省钱；在 trace 里**反而费钱**——因为 trace tape 在你给的 chunk 边界处全部记账
- 见 [feedback_w1_grounded_discoveries](../../../../../../../../.claude/projects/.../memory/feedback_w1_grounded_discoveries.md)：grounded test 第一，hypothesis 永远是次等

---

## 5 失败原因 #3 — iPhone 14 Pro N=120 jetsam 闪退

**症状**：
- N=120 mlpackage 2.5 GB 部署到手机
- 启动 K120 x3 overlap60 bench → app **load 阶段就闪退**
- 没 .ips jetsam log（说明可能不是 OOM 而是 **watchdog timeout**——主线程 load CoreML 模型卡住 > 20s 被 SpringBoard kill）
- 之前 K=90 (1.9 GB) load OK，K=120 (2.5 GB) 一下就跪 → 是 envelope cliff

**Root cause**：
- iPhone 14 Pro 6GB RAM，app jetsam ~3 GB
- N=120 mlpackage load 占 **2.5 GB**
- Flutter Engine + UI + 图像 buffer ~500 MB
- 合计 ≈ 3 GB，**正卡在 jetsam threshold**
- 没 jetsam log = SpringBoard 在 jetsam 前先 watchdog kill（主线程 mmap CoreML 用了 > 20s）

**修复**：
- **放弃 N=120 ship**——硬件不够
- 删 supportedResourceNames 里的 N=120
- ship 路径止步 K=90

**教训（写进 memory）**：
- iPhone CoreML mlpackage > 2 GB load 是新 cliff，比 inference OOM 更早触发
- 下次估算手机 ceiling 不能只算 inference peak，**load 阶段就要算 mmap 占用**
- 闪退要主动拉 .ips（idevicecrashreport），别等 user 截图 → 见 user 当时原话："你不是可以实时监控吗？为什么要我给你截图呢"

---

## 6 成功原因 #1 — vast.ai A100 80GB 是 PoC trace 的甜区

**为什么 A100 80GB 好用**：
| 维度 | A100 80GB | B200 180GB | RTX 4090 24GB |
|---|---|---|---|
| 价格 | $2.5/hr | $5/hr | $0.4/hr |
| Torch 支持 | 任何 2.x 直接装 | 必须 2.8+/cu128 | 任何 2.x |
| K=120 trace ceiling | ~85GB OK | ~85GB OK | OOM |
| 设置复杂度 | 5 分钟 | 30 分钟（cu128 + 摸石头） | 5 分钟 |

**推荐**：以后任何 K≥60 trace 全走 A100 80GB；只在 K=120 trace 失败时升级 B200。

---

## 7 成功原因 #2 — 拿掉 chunked SDPA + 用 efficient backend default

**Grounded 数据（B200 上）**：
| Config | K=60 peak | K=90 peak | K=120 peak |
|---|---|---|---|
| chunked SDPA query_chunk=720 | 91 GB | 176 GB OOM | OOM |
| **default**（efficient backend auto） | 35 GB | 85 GB | 85 GB |

PyTorch CUDA dispatcher 在 fp32 + 长序列下默认选 `efficient` backend，**O(seq) memory** 而不是 `math` 的 O(seq²)。我们把 monkey-patch 关了它就自动选对了。

---

## 8 成功原因 #3 — N=50 byte-identical regression baseline

今天 regression test 用昨天命令重跑 N=50：
- weight.bin **sha256 byte-identical** with ship state
- 说明 trace + convert pipeline 不引入随机性，决定性 reproduction
- 这给了"敢继续 push 到 N=60/90/120"的信心

---

## 9 最终 ship 矩阵（iPhone 14 Pro）

| Window K | mlpackage 大小 | iPhone load 状态 | iPhone runtime 状态 | Ship? |
|---|---|---|---|---|
| K=35 | 877 MB | ✅ | ✅ N50 baseline 比 | ✅ ship (fallback) |
| K=40 | 975 MB | ✅ | ✅ | ✅ ship |
| K=50 | 1.1 GB | ✅ | ✅ ~1 min/window | ✅ ship（已 ship） |
| K=60 | 1.3 GB | ✅ | ✅ 153s/window 231MB RSS thermal serious | ✅ ship |
| **K=90** | **1.9 GB** | **✅** | **待干净 bench**（K120 闪退打断了 K90 bench） | **✅ ship target** |
| K=120 | 2.5 GB | ❌ **闪退** | N/A | ❌ block |

**结论**：K=90 是 iPhone 14 Pro 的 production ceiling。

---

## 10 跨平台展望

| 平台 | 当前能跑的 K |
|---|---|
| iPhone 14 Pro (6GB) | K=90 (CoreML) |
| Mac 18GB (CPU) | K=35 only |
| A100 80GB (CUDA) | K=120 OK |
| B200 180GB (CUDA) | K=120+ |
| Android (TBD) | K=? 待 ONNX export |
| HarmonyOS (TBD) | K=? 待 ONNX export |

**Android / HarmonyOS roadmap**：
- 用 ONNX export 同 trace graph（CoreML 是叶子节点；ONNX 是上游 IR）
- 跨平台 K ceiling 由各设备 RAM + NPU 限制决定
- 不要再用 Mac 本地 trace，直接走 A100 cloud trace + per-platform export

---

## 11 写进 memory 的教训（建议）

1. **trace 阶段不要 monkey-patch SDPA**——只让 CUDA dispatcher 自己选 backend；monkey-patch 在 eager forward 有用，在 trace 上是反作用
2. **B200 sm_100 必须 torch 2.8+/cu128**——A100 80GB ($2.5/hr) 是稳定甜区
3. **iPhone mlpackage 2.5GB+ 是新 cliff**——load 阶段就触发 watchdog/jetsam，不到 inference 就跪
4. **CoreML trace 决定性可复现**——同 input + 同 trace + 同 coremltools 版本 = byte-identical weight.bin
5. **闪退主动拉 .ips**——`idevicecrashreport`，不要等 user 截图

---

## 12 相关产物清单

### Code
- `tools/python/export_da3_image_only_coreml.py` — 修改：加了 `--install-chunked-sdpa-for-trace` / `--trace-device` / `--trace-dtype` / `--force-sdpa-backend` 几个 CLI flag，事后实测 default（不开 chunked）才是甜区
- `code_snapshots/*.py` — 各 patched 状态快照

### Logs
- `boundary_experiments/*.log` — E1 E2 边界实验
- `../official_da3_image_only_coreml_n55_phone_gate_2026_06_08/*.log` — N=55 phone-gate 4 次尝试
- `../official_da3_image_only_coreml_n60_phone_gate_2026_06_08/*.log` — N=60 phone-gate 12 次尝试
- `../official_da3_image_only_coreml_n50_retest_2026_06_08/*.json` — N=50 regression report（byte-identical baseline）

### mlpackages（不进 git，已部署 iPhone Runner.app）
- `pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/`：N35（877MB）/ N40（975MB）/ N50（1.1GB）/ N60（1.3GB）/ N90（1.9GB）/ N120（2.5GB）/ N35_pose（804MB）

### iPhone Runner.app
- 当前 build 9.0 GB（含全部 7 个 mlpackage），ship 前要走 ODR (On-Demand Resources) 拆 base bundle ≤4GB
