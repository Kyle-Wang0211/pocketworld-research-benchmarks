# Chronological Experiment Log: N=60/N=90 CoreML Export Investigation

日期：2026-06-08 → 2026-06-09
顺读这份 log = 复盘整个推演过程。每一条都 grounded 到实际 log file / 命令 / 失败信号。

---

## D1 起点：Stage 02 与 R1-R5 上下文

[Stage 02 已完成清单] window_000 35 帧 DA3 image-only camera geometry audit 全 ship：
- 10 序列级 figures
- 2 矩阵热力图
- 35 per-frame camera cards
- 5 CSV
- 1 JSON report
- 关键发现：cap-56 → cap-74 transition pose 跳变 0.558 距离 / 27.77° 旋转，是 window_000 内最大

[Stage 02 → data side stage01 folder 归档]
- 源：`experiments/da3_base_image_only_official_repro_2026_06_06/02_stage02_official_camera_pose_geometry/`
- 目：`data/.../diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/stage02_camera_pose_geometry/`
- `rsync -a --exclude='.DS_Store' --exclude='generate_*.py'` 完成

[R1-R5 framing]
- Memory `da3_image_only_long_term_memory_2026-06-06.md` 第一原则：Faithfulness > novelty
- 之前讨论的"Stage 02B 全 414 帧连续性诊断"+"A/B/C 改 windowing/pipeline"取消——是 jump to fix，违反方法论
- 正确动作：先把官方 DA3-Streaming 全 pipeline 跑完（R1-R5），再判断 cap-56→cap-74 是不是真问题
- R1 已经在 yesterday 完成（24 个 chunk_*.npy 在 `_tmp_results_unaligned/`），R2-R5 没跑

[R1-R5 resume 脚本写作]
- 原 oracle `da3base_official_streaming_oracle.py` 无 skip 逻辑，重启会重跑 30 分钟 R1
- 创建 `da3base_official_streaming_oracle_resume.py`：oracle 副本 + monkey-patch `DA3_Streaming.process_single_chunk` 让其在 cache 存在时 load 而不 inference

[Resume 启动撞 iCloud Documents]
- 启动后 `from da3_streaming import DA3_Streaming` 卡 124 秒 timeout
- 根因 grounded：`~/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/` 这条路径 mmap 死
  - `head -5 gs_renderer.py` 用 bash 直读秒回
  - Python `importlib.get_data` (line 1131) 124-188 秒 timeout（用 mmap 读 source）
  - `rsync` 也死：`mmap: Operation timed out` on `.flake8`（几百字节文件）
  - `xattr -l` 干净，但 `brctl status` 报 "Client zone not found"
- 怀疑 iCloud Drive file provider 那一层 zone 丢了（之前 user 截图 "403 Request not allowed" 跟此一致）

[DA3 src 迁出 iCloud]
- 尝试 1: rsync `~/Documents/...` → `.deps/Depth-Anything-3/src/` → mmap timeout
- 尝试 2: cp -R → 同样 timed out
- 尝试 3: cp Desktop `sap_test/depth-anything-3/src/` → `.deps/Depth-Anything-3/src/` → 成功（除 `dinov2/layers/__init__.py` 一文件 fcopyfile timeout）
- 单文件 cp -f 补上 `__init__.py`
- `install_da3_dinov2_layers_export_shim()` 在 export script 里自动兜空 `__init__.py`
- 验证 import：DepthAnything3 imported 1.78s ✅

[R1-R5 oracle resume **暂未恢复运行**]——优先级被 N=60 export 顶了，下次继续。

---

## D2 N=60 export 任务移交

[The other agent 的进展（screenshot 转述）]
- 之前 N40/N50 成功 ship mlpackage
- 同一套环境（.venv-da3, torch 2.12.0, DA3 repo .deps/, export 脚本）只改 `--window-size 60`
- N60 trace **第一阶段 torch.jit.trace 硬退**，无 Python exception
- 试过 `--no-trace-check`、`--trace-optimize-false`、`optimize=False` 都没救
- 正准备切 `torch.export`

[我的 grounded 检查]
- 找到 N60 attempt logs：`data/.../diagnostics/official_da3_image_only_coreml_n60_phone_gate_2026_06_08/*.log`
- 三份 log 都只 6 行，最后一行 `[export] torch.jit.trace begin check_trace=...` 后**无任何输出，无 Python traceback**
- 跟 N50 成功 log 对照：N50 conv 287s, output 1814 ops, MIL 95 passes
- N60 死在 trace 入口——SIGKILL（无 traceback = OS 杀，不是 Python 异常）

[初始假设 (后来被推翻)]
- DA3-BASE alt_start=4，blocks 4-11 做 cross-frame global attention
- K=60 时 global seq_len = 60 × 721 = 43260，attention matrix 90 GB fp32
- Mac 18GB unified mem 装不下 → jetsam SIGKILL
- N50 跑通是 PyTorch CPU SDPA dispatcher 在 36050 序列长度上选了 memory-efficient backend，K=60 切到 math backend 物化

[Web research]
- ByteDance-Seed/Depth-Anything-3 issues / PRs grep
- PR #237 `Add MLX conversion` by atultw（WIP）
- Issue #49 `Streaming/Real-time, MPS, Benchmarking - PR incoming` by laubsauger (fork PR #1 add MPS support)
- Issue #63 `Running on mobile devices`：LSQzzx fork `Depth-Anything-3-for-CoreML` + Muna gist + ONNX 多个
- Issue #65 `PyTorch or ONNX version`：TillBeemelmanns ONNX + MSch8791 ONNX
- executorch #9506 `CoreML model works with torch.jit.trace, but not torch.export.export`——**反向死法**，torch.export 切换是死路
- Muna 报：CoreML DAv3-large 300-400ms vs ONNXRuntime 2000ms（5× faster）

[chunked SDPA 方案设计]
- 抄 oracle.py 的 `install_mps_chunked_sdpa`，改成 device-agnostic
- 关键：CPU PyTorch SDPA 在 K=50 走 memory-efficient（每 chunk softmax 累计），K=60 切回 math（一次性物化）
- 装 monkey-patch 强制 chunked，让 K=60 走 K=50 同样的 backend 行为
- 数学等价（chunked softmax 数值跟整体 softmax 输出一致）→ 不违反 Faithfulness

[改 export_da3_image_only_coreml.py]
- 加 4 个 CLI flag：
  - `--install-chunked-sdpa-for-trace`
  - `--chunked-sdpa-query-chunk` (default 720)
  - `--chunked-sdpa-min-gib` (default 2.0)
  - `--trace-device {cpu, mps}` (default cpu)
- 加 helper `install_chunked_sdpa_for_trace()` (~30 LOC)
- 在 main `run()` 函数里 wrapper 创建后注入 device move

---

## D3 N=60 七次失败 chronology

### Attempt #1: chunked CPU qc=720 + min_gib=2.0
- vm.free 286 MB / inactive 6 GB（初始）
- 进 `[chunked_sdpa]` 打印第一行：`query_shape=(1, 12, 43260, 64) score_buffer_gib=83.66 query_chunk=720` 后 **SIGKILL 137**
- 没跑到第一个 chunk iteration
- 假设：trace tape 引用住 4 个 local block scores（1.39 GB × 4 = 5.6 GB）+ FFN + 模型，process RSS 已经接近 jetsam 阈值

### Attempt #2: qc=180 + min_gib=0.5（local 也 chunk）
- 进 2 行 `[chunked_sdpa]` print（local 1.39 GB + global 83.66 GB 都触发）后 SIGKILL
- local chunked 反而让 tape 引用更多中间张量

### Attempt #3: qc=60 + min_gib=2.0 + gc.collect()
- 同 Attempt #1，1 行 print 后 SIGKILL
- gc.collect() 没救——trace tape 引用是 C++ 层不走 Python gc

### Attempt #4: qc=720 + min_gib=2.0 (重试 after free memory)
- 用户 kill 其他 app 释放内存，vm.free=2180 MB / inactive=4076 MB
- 同 Attempt #1 死法
- 证明：**chunk 大小不是关键变量**，local 累积 tape 才是

### Attempt #5: `--trace-device mps`（无 chunk）
- vm.free=4832 MB
- 24 秒后**真 Python traceback**：
  ```
  RuntimeError: MPS backend out of memory 
  (MPS allocated: 22.30 GiB, max allowed: 22.64 GiB). 
  Tried to allocate 356.95 MiB on shared pool.
  ```
- 比 CPU SIGKILL 信号清晰得多——证明 MPS PyTorch SDPA 也物化 K×K（不是 fused FlashAttention，我之前假设错了）

### Attempt #6: MPS + chunked qc=720 + min_gib=0.5
- vm.free=9522 MB
- 28 秒后死：`MPS OOM 21.14 GiB / 22.64 GiB max`
- 进了 local chunked print（1.39 GB score），global 还没到就死
- 4 local blocks × tape 内存累计 ≈ 20 GB

### Attempt #7: MPS + chunked + `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`
- 关掉 MPS 内置 watermark cap
- vm.free 81 MB / inactive 6 GB / swap 0 MB
- 进 local + global chunked print 后**SIGKILL by jetsam, swap 仍 0 MB**
- watermark=0 让 MPS 想用更多内存，但 OS jetsam 不让它走到 swap
- vm.swapusage 验证：`total=0 used=0 free=0`——OS 在 swap 之前就杀

---

## D4 Pivot：MLX PR #237

[决策点]
- 7 次 CoreML export 都死同一类机制（trace tape pile-up），降参数救不了
- 用户认可 MLX 路径探索（之前 prompt 里 [2] 选项）

[atultw fork clone]
```bash
git clone --depth 1 --branch copilot/convert-model-to-mlx \
  https://github.com/atultw/Depth-Anything-3-coreml.git \
  /Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3-mlx
```

[Bug 1: mx.full_like 不存在]
- `mlx.core` 没有 `full_like` attribute（在 mlx 0.31.2）
- 用 `mx.full(shape, value, dtype=...)` 替换
- 改 `transform.py:58-59` 两行

[Bug 2: convert_to_mlx Swift-key 与 Python MLX model snake_case 不匹配]
- atultw `map_key`：`backbone.pretrained.` → `backbone.`，`.mlp.` → `.mlpLayer.`，`q_norm` → `qNorm` 等
- 直接 load 只 38/443 match
- 写 python-native 转换器在 `run_mlx_smoke_n60.py`：
  - 保留 PT snake_case + `backbone.pretrained.` 前缀
  - 只做结构性 rename（8 类）
  - Conv2d weight transpose OIHW→OHWI
  - 不 skip `_aux`（MLX model 设计有）
- 迭代：38 → 285 → 379 → 437/443（98.6%）

[Bug 3: 朴素 K×K attention 撞 Metal 10.7 GB 单 buffer]
- `layers.py:234` `attn = q @ mx.transpose(k, axes=(0,1,3,2))`
- N=60 global attention `(1, 12, 43260, 43260) × 4 bytes = 89.8 GB`
- 报错 `[metal::malloc] Attempting to allocate 89828524800 bytes which is greater than 10726686720`
- 加 query-chunked SDPA（同 oracle.py CPU 实现思路）

[N=4 PASS]
- forward 0.69s
- depth shape (4, 280, 504)
- depth range [0.8237, 0.9438]
- finite ✅

[N=60 PASS but swap]
- Mac 跑通了
- vm.swapusage：6.25 GB swap used
- **iPhone 6GB RAM + 0 swap → 不可 ship**
- 这条路对 iPhone deployment 无效

---

## D5 N=50 regression 确认

[动机]
- 我加了一堆 flag 到 export 脚本，需要回归测试昨天的 N=50 ship state 没坏

[执行]
- 拿昨天 N=50 命令 vanilla 跑（不开 chunked / mps flag）
- 输出到 `_regression.mlpackage` 避免覆盖原 ship

[结果]
- exit 0, conversion status pass
- 358s (vs 昨天 287s，慢 24% 因 3.4 GB swap pressure)
- weight.bin sha256：`eeef44b58f...adc987` ↔ 昨天同样 ↔ **byte-identical**
- model.mlmodel / Manifest.json 差异：仅 timestamp / protobuf 内部 op id（不影响 inference）

[结论]
- N=50 ship state 100% 完整
- 我的代码改动 0 影响 baseline
- iPhone 端 N=50 不需要重测（CoreML 跑的是 weight.bin，bit-equal weights → bit-equal inference）

---

## D6 swap 状态遗留 + 285s baseline 恢复

[用户问]：怎么回到 287s baseline?

[grounded]
- 现在 vm.swap.used = 4.99 GB，inactive 6.36 GB（可回收）
- 无遗留 python/da3 进程（之前都 SIGKILL/exit 0 清干净）
- swap 是之前 MLX N=60 + 7 次 CoreML 尝试**已死进程留下的 paged-out 状态**

[macOS swap 不动态缩小]
- 一旦 paged out 就在 swap 文件里，直到 reboot
- `sudo purge` 清 inactive cache 但不清 swap
- 无 user-level 命令清 swap

[options]
1. Reboot Mac — 唯一彻底回 287s
2. 不 reboot, 接受 358s — byte-identical 结果
3. kill 非必要 app — 释放 RAM 但不缩 swap

---

## D7 最终决策点

[grounded 三选一]
- [A1] 换 32GB+ Mac trace — 推荐 if 有硬件
- [A2] Linux/CUDA box trace — 工程量更大
- [A3] 接受 N=50 ceiling — 推荐 if 无新硬件

[未完成的工作]
- R1-R5 oracle resume 已就绪等恢复运行（DA3 src 已搬出 iCloud，oracle resume 脚本已写）
- R6 (查 cap-56→cap-74 在 final PLY 是否仍黑块) 等 R1-R5 跑完才能开始

[反模式记录]
- 不再用 18GB Mac chunked CPU trace
- 不切 torch.export
- 不 push MLX 到 iPhone
- 不动 DA3 算法
- 不碰 ~/Documents/progecttwo iCloud 路径

---

[末了]：本 log 配合 [POST_MORTEM_ZH.md](POST_MORTEM_ZH.md) 看。POST_MORTEM 是结构化总结，本 log 是 chronological 推演细节。
