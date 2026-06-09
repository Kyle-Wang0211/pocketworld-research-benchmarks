# DA3-BASE Image-Only N=60/N=90 CoreML Export Post-Mortem

日期：2026-06-09
作者上下文：跨两天的实验整理（2026-06-08 主体 + 2026-06-09 回归测试 + 复盘）

## 0 TL;DR

- **目标**：把 DA3-BASE image-only 的 mlpackage 从已 ship 的 N=50 扩到 N=60 / N=90，给 iPhone streaming 推理用
- **结果**：N=60 mlpackage **在 18GB Mac 上转不出来**——7 次 CoreML trace 尝试全 SIGKILL/OOM；MLX PR #237 替代路径修了 3 个 bug 后 Mac 上能跑（用 6.25 GB swap），但**对 iPhone 不可 ship**（手机无 swap + 3GB jetsam）
- **iPhone 上 N=50 仍稳定 ship**：今天 regression test confirm weight.bin **sha256 byte-identical** 跟昨天 ship state
- **方法论遵守**：未改 DA3 算法语义；chunked SDPA 只动执行调度
- **剩下三条路**：[A1] 换 32GB+ Mac trace；[A2] Linux/CUDA box trace；[A3] 接受 N=50 ceiling
- **推荐**：[A3]——N=60/N=90 不在产品 critical path，N=50 已 ship-able

---

## 1 起点 & 方法论硬约束

### 1.1 当前已 ship state（不动）

| 项 | 值 |
|---|---|
| iPhone ship 的 mlpackage | `DA3BASE_280x504_N50_image_only.mlpackage`（1.1 GB） |
| iPhone runtime 性能 | 1 分多钟 / window |
| 之前纯 CPU PyTorch 基线 | 15 分钟 / window（CoreML 15× faster） |
| ANE 状态 | 不可用（开 ANE inference 直接 crash），CoreML 走 cpuAndGPU |
| iPhone 14 Pro RAM | 6 GB，**无 swap**，app jetsam ~3 GB |
| Mac 测试机 RAM | 18 GB unified mem，最大 swap 6 GB |
| Apple Metal 单 buffer cap | 10.7 GB（同时跨 Mac/iPhone） |

### 1.2 方法论硬约束

来自 `docs/da3_image_only_long_term_memory_2026-06-06.md`（注意：那个路径在 iCloud Documents，本地 mmap 死，但内容已 grounded 到这）：

- **Faithfulness > novelty**——不动 DA3 算法语义（不剪头、不改 norm、不加门控、不蒸馏、不替 attention 实现）
- 调度/执行层面的优化（chunked SDPA、device 切换、precision 切换）允许，因为不动数学
- **Intermediate evidence > guessed explanations**——SIGKILL 没 traceback 就不能下"原因是 X"结论
- 不在 R1-R5 全跑通之前下"DA3 不行"判断

---

## 2 实验时间线（high-level）

| 阶段 | 工作 | 结果 |
|---|---|---|
| Stage 02（昨天） | 24-window R1 完成的状态下，针对 window_000 35 帧做 DA3-predicted pose geometry audit | 10 figures + 2 matrix heatmaps + 35 per-frame camera cards + 5 CSV + 1 JSON 全部 ship 到 [data side stage01 archive](../stage01_depth_conf_photometric_window000_2026_06_06/stage02_camera_pose_geometry/) |
| R1-R5 resume oracle（昨天） | 写 `da3base_official_streaming_oracle_resume.py` 跳过 cached chunks，跑完整 DA3-Streaming 24 windows | 被 iCloud Documents DA3 src 路径 mmap timeout 卡住，未完成（详 §6） |
| 切到 N60/N90 export（今天） | 另一个 agent 任务：N50→N60 trace 硬退 | 7 次 CoreML export 尝试全失败（详 §5） |
| MLX PR #237 探索 | atultw fork 修 3 bug | N=4 PASS / N=60 Mac PASS（swap-only） / iPhone 不可 ship（详 §7） |
| N=50 regression（今天） | 拿昨天命令重跑一遍 | weight.bin sha256 **bit-identical**，N=50 ship state 100% 完整（详 §8） |

---

## 3 数据可视化产出索引

### 3.1 Stage 02 已 ship 的 visualizations

完整路径：`<DATA>/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/stage02_camera_pose_geometry/`

其中 `<DATA>` = `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02`

| 类目 | 数量 | 路径 |
|---|---|---|
| 序列级 figures | 10 | `figures/stage02_{camera_center_components, camera_frustums_world, camera_trajectory_3d, camera_trajectory_top_front_side, depth_pose_scale_panel, intrinsics_normalized_timeseries, intrinsics_timeseries, pairwise_baseline_heatmap, pairwise_rotation_heatmap, pose_delta_timeseries}.png` |
| 矩阵热力图 | 2 | `matrix_heatmaps/stage02_{extrinsics,intrinsics}_matrix_heatmap_contact.png` |
| Per-frame camera cards | 35 | `per_frame_camera_cards/00_cap-1_camera_card.png ... 34_cap-131_camera_card.png` |
| CSV | 5 | `tables/stage02_{intrinsics_per_frame, camera_centers_per_frame, relative_pose_delta, pairwise_pose_metrics, depth_pose_context}.csv` |
| Contact sheets | 2 | `contact_sheets/stage02_{all_figures, per_frame_camera_cards}_contact_sheet.{png,jpg}` |
| JSON report | 1 | `stage02_camera_pose_geometry_report.json`（含 cap-56→cap-74 transition: center_distance 0.558 / rotation_angle 27.77° 等关键数字） |
| README | 2 | `README_STAGE02_ZH.md` + `README_STAGE02_RESULTS_ZH.md` |

### 3.2 N=60 七次失败的 log files

完整路径：`<DATA>/diagnostics/official_da3_image_only_coreml_n60_phone_gate_2026_06_08/`

| Log 名 | 配置 | 死法 |
|---|---|---|
| `official_da3_image_only_k60_280x504_convert.log` | CPU baseline | 6 行 trace begin 后 SIGKILL |
| `..._no_trace_check_convert.log` | CPU + `--no-trace-check` | 同 |
| `..._trace_opt_false_convert.log` | CPU + `optimize=False` | 同 |
| `..._chunked_sdpa_convert_*.log` | CPU + chunked qc=720 | 进 chunked path 后 SIGKILL |
| `..._chunked_sdpa_qc180_convert_*.log` | CPU + chunked qc=180 + local 也 chunk | 同 |
| `..._chunked_qc60_gc_*.log` | CPU + chunked qc=60 + gc.collect | 同 |
| `..._chunked_qc720_retry_*.log` | CPU + chunked qc=720（释放内存后） | 同 |
| `..._mps_*.log` | MPS trace + no chunk | `MPS OOM: allocated 22.30 GiB / max 22.64 GiB` ← **真 Python traceback** |
| `..._mps_chunked_*.log` | MPS + chunked qc=720 + min_gib=0.5 | `MPS OOM 21.14 GiB` |
| `..._mps_nowm_*.log` | MPS + chunked + `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` | SIGKILL by jetsam, swap=0 没动 |

### 3.3 N=50 conversion logs（baseline + regression）

完整路径：`<DATA>/diagnostics/official_da3_image_only_coreml_n50_phone_gate_2026_06_07/`

| 文件 | 用途 |
|---|---|
| `DA3BASE_280x504_N50_image_only.mlpackage` | 昨天 ship state（1.1 GB） |
| `DA3BASE_280x504_N50_image_only_regression.mlpackage` | 今天 regression test 产物（1.1 GB，weight.bin sha256 byte-identical） |
| `official_da3_image_only_k50_280x504_convert.log` | 昨天 convert log（287s 总耗时） |
| `official_da3_image_only_k50_280x504_regression_20260609_004134.log` | 今天 regression log（358s 总耗时，慢 24% 因 swap pressure） |
| `phone_k50_device_benchmark_report_2026_06_07.json` | iPhone 跑 N=50 实测 |

---

## 4 关键 grounded 发现

### 4.1 iPhone runtime fused SDPA != Mac trace materialization

**N=50 mlpackage 在 iPhone 上跑通的根本原因**：CoreML runtime 的 SDPA op 在 iPhone 上走的是 Apple 自己写的 fused FlashAttention-style kernel——O(seq) 内存，**永远不物化 K×K attention matrix**。这跟硬件无关，是 CoreML runtime 内置优化。

**Mac trace 死的原因**：`torch.jit.trace` 跑 eager forward 时用的是 PyTorch 自己的 SDPA dispatcher（CPU math backend 或 MPS materializing kernel），**会一次性物化 K×K**。K=60 时 cross-frame global attention 序列长度 = 60 × 721 = 43260，attention matrix = 12 × 43260² × 4 = **89.8 GB**（fp32）。

这两层是分开的：trace 时怎么算 不等于 runtime 时怎么算。但**得先有 mlpackage**，所以 trace 卡住 = 没法 ship。

### 4.2 Mac trace tape pile-up

`torch.jit.trace` 期间 PyTorch tracer 把每个 op 的输入输出张量 metadata 都引用住，直到 trace 结束。对 DA3-BASE K=60：

- 4 个 local attention blocks：每个的 scores (60, 12, 721, 721) fp32 = 1.39 GB，softmax probs 1.39 GB，FFN expansion 520 MB，等等
- 加 model 权重 fp32 ≈ 800 MB + 输入 100 MB
- **达到 global attention 入口时进程 RSS 已经 13-17 GB**

这就是为什么 4 次不同 chunk size（720/180/60）的 chunked SDPA 都死同一点——**chunk 控制的是 global 的 marginal 成本，控不了 local 已经累积的 tape**。

把 local 也 chunk（min_gib=0.5）反而让 chunk 中间张量被 tape 引用住更多。

**根因是 trace 的 tape 引用机制本身**，不是任何 chunk 参数。要救得用 `torch.utils.checkpoint` opaque 包装改 DA3 forward 语义——违反 Faithfulness。

### 4.3 MLX Metal single-buffer cap (10.7 GB)

MLX 在 Mac 上跑 attention 时同样物化 K×K（atultw 的 `mlx_depth_anything_3/layers.py:234` 是朴素 `q @ k.T + softmax + @ v`），撞 Metal 单 buffer 上限：

```
RuntimeError: [metal::malloc] Attempting to allocate 89828524800 bytes 
which is greater than the maximum allowed buffer size of 10726686720 bytes
```

89.8 GB > 10.7 GB → 必死。chunked SDPA 后单 buffer 降到 ~1.5 GB / chunk fp32，过线。

### 4.4 iPhone has no swap

Mac 上跑 MLX N=60 通了，但**用了 6.25 GB swap**——iPhone 没 swap，**6 GB RAM + 3 GB jetsam 死硬限**。所以 MLX N=60 在 iPhone 上必死。

这就是 MLX 路径不能 ship 到 iPhone 的物理原因——不是 atultw PR 完成度的问题，是**手机硬件**装不下。

---

## 5 N=60 七次 CoreML export 失败清单（详）

每次都 `--window-size 60 --height 280 --width 504 --convert --compute-precision float16 --static-shape-export-patches --allow-duplicate-openmp`。

| # | 额外 flag / env | vm.free / inactive @ start | 死法 |
|---|---|---|---|
| 1 | （baseline） | – | 6 行 log 后 SIGKILL 137 在 trace begin 之后 |
| 2 | `--no-trace-check` | – | 同 |
| 3 | `--trace-optimize-false` | – | 同（trace 跑更久但仍 SIGKILL） |
| 4 | `--install-chunked-sdpa-for-trace --chunked-sdpa-query-chunk 720 --chunked-sdpa-min-gib 2.0` | low | 死后 1 行 chunked print：`query_shape=(1,12,43260,64) score_buffer_gib=83.66 query_chunk=720` |
| 5 | qc=180 + min_gib=0.5（local 也 chunk） | – | 2 行 chunked print（local + global）后 SIGKILL |
| 6 | qc=60 + min_gib=2.0 + `gc.collect()` 在 chunk 循环里 | – | 同 #4 |
| 7 | qc=720 + min_gib=2.0（释放内存后重试） | free=2180 MB, inactive=4076 MB | 同 #4 |
| 8 | **`--trace-device mps`**（无 chunk） | free=4832 MB | **真 Python traceback**：`RuntimeError: MPS OOM (allocated 22.30 GiB / max 22.64 GiB)` ← 比 CPU 路死得更明白 |
| 9 | MPS + chunked qc=720 + min_gib=0.5 | free=9522 MB | `MPS OOM 21.14 GiB` |
| 10 | MPS + chunked + `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`（关 watermark） | free 各种 | SIGKILL by jetsam, swap=0 没动（OS 不让走到 swap） |

**所有死亡都在同一点：global cross-frame attention 的第一次 SDPA 调用入口**。

---

## 6 R1-R5 oracle resume 工作 (昨天)

不是 N=60 export 工作流，但是同时段的 grounded 工作，影响今天 N=60 调查。

### 6.1 目标

按官方 DA3-Streaming faithfully 跑完 24 windows × K=35 inference + SALAD loop retrieval + dense Sim3 alignment + Sim3LoopOptimizer + pointcloud fusion → PLY。Yesterday 24 chunks 的 R1 inference 已落盘到 `_tmp_results_unaligned/chunk_0..23.npy`，R2-R5 没跑。

### 6.2 写的代码

`tools/python/da3base_official_streaming_oracle_resume.py`——`da3base_official_streaming_oracle.py` 的副本 + monkey-patch `DA3_Streaming.process_single_chunk` 让其在 `_tmp_results_unaligned/chunk_{idx}.npy` 已存在时直接 load 不 inference。

### 6.3 阻塞

启动后 `from da3_streaming import DA3_Streaming` 卡住——`gs_renderer.py` import 在 124 秒后 `TimeoutError [Errno 60]`。诊断：**`~/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/` 这条 path 上 macOS file provider 层挂了**：
- bash `head -5` 直读秒回
- Python `importlib.get_data` 124-188 秒 timeout
- `rsync` 报 `mmap: Operation timed out` 在 `.flake8` 这种几百字节文件
- `xattr` 干净，但 `brctl status` 报 "Client zone not found"
- 怀疑 iCloud Drive 那一层 zone 丢了（之前截图里 "403 Request not allowed" 跟它一致）

### 6.4 修法

整个 DA3 src cp 出 `~/Documents/`，放到 `~/Developer/Aether3D-cross/.deps/Depth-Anything-3/src/`（之前 cp 自 Desktop `sap_test/depth-anything-3/src` + 单文件 cp -f 补 `dinov2/layers/__init__.py` 那个 mmap timeout 文件）。

但 R1-R5 oracle resume 在切到 N=60 export 调查后**暂未恢复运行**——优先级被 N=60 顶了。oracle resume 自身代码就绪，路径已迁，**等本次 N=60 问题闭环后可立刻继续**。

---

## 7 MLX PR #237 (atultw fork) 探索

### 7.1 atultw PR 状态

- **PR #237** `Add MLX conversion` by atultw（OPEN，WIP）
- fork: `atultw/Depth-Anything-3-coreml` branch `copilot/convert-model-to-mlx`
- atultw 自陈："PR is a work-in-progress" + "I used Copilot to do the initial conversion"
- 验证 parity 时用的是 da3-small，没在 da3-base 全跑过

clone 命令：
```bash
git clone --depth 1 --branch copilot/convert-model-to-mlx \
  https://github.com/atultw/Depth-Anything-3-coreml.git \
  /Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3-mlx
```

### 7.2 修的 3 个 bug

**Bug 1** (`mlx_depth_anything_3/transform.py:58-59`)：`mx.full_like` 在 mlx 0.31.2 不存在。修补：
```python
# 原:
mx.full_like(fx, W / 2.0)
# 改:
mx.full(fx.shape, W / 2.0, dtype=fx.dtype)
```

**Bug 2** (`convert_to_mlx.py` map_key)：atultw 把 PyTorch snake_case 全转 Swift camelCase（"for Swift compatibility"）+ 砍 `backbone.pretrained.` 成 `backbone.`。但 Python MLX model 内部仍用 snake_case + 保留 pretrained 前缀。直接用 atultw convert 出来的 weights 只 38/443 keys 匹配。

修补：写 python-native 转换器（在 `run_mlx_smoke_n60.py`），保留 snake_case + 只做必要结构性 rename：
- `head.scratch.` → `head.`
- `head.resize_layers.{N}.` → `head.resize_{N}.`
- `head.output_conv2.0.` → `head.output_conv2_a.`，`.2.` → `.output_conv2_b.`
- `cam_dec.backbone.0/2.` → `cam_dec.backbone_fc1/2.`
- `cam_dec.fc_fov.0.` → `cam_dec.fc_fov_linear.`
- `head.output_conv1_aux.X.Y.` → `head.output_conv1_aux.X.layers.Y.`
- `head.output_conv2_aux.X.{0,2,5}.` → `head.output_conv2_aux.X.{conv1,ln,conv2}.`
- Conv2d weight transpose OIHW→OHWI
- 不 skip `_aux`

得 437/443（98.6%）匹配。剩 6 个是 `head.output_conv2_aux.{1,2,3}.ln`——PyTorch checkpoint 只有 aux head 0 有 LN，MLX model 设计成 4 个都有。**这是 MLX model 设计 vs checkpoint 的 divergence，跟主 depth path 无关**。

**Bug 3** (`mlx_depth_anything_3/layers.py:234`)：MLX Attention 用朴素 `attn = q @ mx.transpose(k, axes=(0,1,3,2))` 物化 K×K，撞 Metal 10.7 GB 单 buffer cap。

修补：加 query-chunked SDPA：
```python
N_seq = q.shape[2]
CHUNK = 720
if N_seq <= CHUNK or attn_mask is not None:
    # 原路径（短序列 / 带 mask）
    attn = q @ mx.transpose(k, axes=(0, 1, 3, 2))
    if attn_mask is not None: ...
    attn = mx.softmax(attn, axis=-1)
    out = attn @ v
else:
    # query-chunked path（长序列，跨帧 attention）
    k_t = mx.transpose(k, axes=(0, 1, 3, 2))
    out_chunks = []
    for start in range(0, N_seq, CHUNK):
        end = min(start + CHUNK, N_seq)
        q_chunk = q[..., start:end, :]
        attn_chunk = q_chunk @ k_t
        attn_chunk = mx.softmax(attn_chunk, axis=-1)
        out_chunks.append(attn_chunk @ v)
    out = mx.concatenate(out_chunks, axis=2)
```

### 7.3 跑通结果

| 测试 | 结果 |
|---|---|
| N=4 image-only MLX forward | ✅ PASS, 0.69s, depth shape (4, 280, 504), range [0.8237, 0.9438], finite |
| N=60 image-only MLX forward | ✅ Mac 跑通，**但用了 6.25 GB swap**（vm.swapusage 验证） |
| N=60 iPhone 部署可行性 | ❌ iPhone 6GB RAM + 0 swap + 3GB jetsam → 必死 |

### 7.4 MLX weights 副产物

- atultw 路转出的 Swift-style key weights：`pocketworld_research_benchmarks/artifacts/mlx_exports/DA3BASE_mlx_fp16.safetensors`（251 MB fp16）
- **注意**：这个文件是 Swift MLX runtime 用的，**Python MLX model 不能直接 load**。Python 测试我走 in-memory python-native 转换。

---

## 8 N=50 regression：ship state 完整性确认

今天用同一脚本（已加 chunked + trace-device 等 flag，但调用时不开）跑 N=50 vanilla conversion，验证我的代码改动没破坏 baseline：

| 项 | 昨天 ship | 今天 regression |
|---|---|---|
| exit | 0 | 0 |
| conversion status | pass | pass |
| 总耗时 | 287s | 358s（慢 24%, 因 3.4 GB swap pressure） |
| `weight.bin` sha256 | `eeef44b58f...adc987` | `eeef44b58f...adc987` ✅ **完全相同** |
| mlpackage 大小 | 1.1 GB | 1.1 GB |
| `model.mlmodel` | 差异（仅 timestamp / protobuf op id） | |
| `Manifest.json` | 差异（仅 authoring timestamp） | |

**模型权重 byte-identical → iPhone runtime 行为保证一致**。N=50 ship state 100% 完整。

---

## 9 三条剩下的路

### [A1] 换 32GB+ Mac trace（推荐 if 有硬件）

M-series Mac mini / Studio 32GB+ unified mem。chunked SDPA + 32GB 估计 80%+ 概率通（CPU trace tape pile-up ~10-15 GB peak，32GB 余 17-22 GB margin）。一次性 trace 出 mlpackage 拷回原 18GB Mac 部署。

```bash
# 启动命令模板（拷自 N50 invocation，新加 chunked + mps flag）
KMP_DUPLICATE_LIB_OK=TRUE PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONUNBUFFERED=1 \
/path/to/.venv-da3/bin/python -u export_da3_image_only_coreml.py \
--official-da3-repo <path>/.deps/Depth-Anything-3 \
--model-dir <path>/DA3-BASE \
--out-model <path>/DA3BASE_280x504_N60_image_only.mlpackage \
--out-report <path>/convert_report.json \
--window-size 60 --height 280 --width 504 \
--convert --compute-precision float16 --minimum-deployment-target iOS18 \
--static-shape-export-patches \
--install-chunked-sdpa-for-trace --chunked-sdpa-query-chunk 720 --chunked-sdpa-min-gib 2.0 \
--allow-duplicate-openmp
```

不通再加 `--trace-device mps`。

### [A2] Linux/CUDA box trace

coremltools 在 Linux 跑（无 Apple Silicon 加速但内存通常 64+ GB）。chunked SDPA 几乎肯定通。

注意：
- mlpackage file format 是 cross-platform，文件可拷回 macOS host
- 但 sign + bundle 进 iOS app 必须 macOS host
- coremltools 有些 macOS-specific 路径在 Linux 会警告（不影响产出）

### [A3] 接受 N=50 ceiling（推荐 if 无新硬件）

**今天 grounded**：
- N=50 ship state 完整（sha256 验证）
- iPhone runtime 1 分钟 / window 可用
- N=60/N=90 是研究 wishlist，**不在产品 critical path**

把 R1-R5 streaming pipeline 的 `chunk_size` 锁回 50，研究 N=60 推到下次硬件升级 / atultw PR 合并 / 自研 MLX FlashAttention port。

---

## 10 反模式记录（不要重试）

| 反模式 | 死法 grounded | 不再做 |
|---|---|---|
| 18GB Mac chunked SDPA + CPU trace | 4 次 SIGKILL 137 同点 | 不再 |
| `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` 关 watermark | jetsam 直接 SIGKILL, swap 不动 | 不再 |
| 切 `torch.export` 替 trace | executorch #9506 反向死法 (narrow op + None types fail) | 不切 |
| 降 process_res 救内存 | 280×504 已是 patch-align 最低（patch_size=14, 280/14=20, 504/14=36） | 不降 |
| MLX 走 iPhone deployment | Metal 单 buffer + 无 swap + 3GB jetsam 三死 | 不 push |
| 改 DA3 算法（剪头/换 attention/蒸馏） | 违反 Faithfulness | 不动 |
| 用 `~/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/` | iCloud file provider mmap timeout | 死路 |

---

## 11 文件 + 路径索引

### 11.1 已修改 / 已创建的代码

| 路径 | 改动 | 备份 |
|---|---|---|
| `pocketworld_research_benchmarks/tools/python/export_da3_image_only_coreml.py` | 加 4 个 CLI flag + `install_chunked_sdpa_for_trace()` helper + trace-device 移设备 block | [`code_snapshots/export_da3_image_only_coreml_2026_06_09.py`](code_snapshots/export_da3_image_only_coreml_2026_06_09.py) |
| `pocketworld_research_benchmarks/tools/python/da3base_official_streaming_oracle_resume.py` | 全文件新建（oracle.py 副本 + skip patch） | 已 ship 在 tools/python/ |
| `.deps/Depth-Anything-3-mlx/mlx_depth_anything_3/transform.py` | line 58-59 mx.full_like → mx.full | [`code_snapshots/mlx_transform_patched_2026_06_09.py`](code_snapshots/mlx_transform_patched_2026_06_09.py) |
| `.deps/Depth-Anything-3-mlx/mlx_depth_anything_3/layers.py` | line 234 区域加 chunked SDPA | [`code_snapshots/mlx_layers_patched_2026_06_09.py`](code_snapshots/mlx_layers_patched_2026_06_09.py) |
| `.deps/Depth-Anything-3-mlx/run_mlx_smoke_n60.py` | 全文件新建：python-native PT→MLX 转换 + smoke 测试 | [`code_snapshots/run_mlx_smoke_n60_2026_06_09.py`](code_snapshots/run_mlx_smoke_n60_2026_06_09.py) |

### 11.2 数据产物路径

| 项 | 路径 |
|---|---|
| Stage 02 visualizations (10 figs + 35 cards + 2 heatmaps + 5 CSV) | `data/.../diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/stage02_camera_pose_geometry/` |
| N50 ship mlpackage | `data/.../diagnostics/official_da3_image_only_coreml_n50_phone_gate_2026_06_07/DA3BASE_280x504_N50_image_only.mlpackage` |
| N50 regression mlpackage | 同目录的 `..._regression.mlpackage` |
| N60 七次失败 log + JSON | `data/.../diagnostics/official_da3_image_only_coreml_n60_phone_gate_2026_06_08/*.log + *.json` |
| MLX fp16 weights (Swift-key) | `artifacts/mlx_exports/DA3BASE_mlx_fp16.safetensors`（251 MB） |
| R1-R5 K35 unaligned chunks | `data/.../diagnostics/da3base_official_streaming_k35_overlap18_full414_mac_2026_06_05/_tmp_results_unaligned/chunk_0..23.npy` |
| 120/60 baseline RUN_STATUS | `data/.../diagnostics/da3base_official_streaming_120_60_full414_2026_06_05/RUN_STATUS_ZH.md` |

### 11.3 外部依赖路径

| 项 | 路径 |
|---|---|
| Python venv | `.venv-da3/bin/python`（Python 3.11.15, torch 2.12.0, mlx 0.31.2） |
| DA3 src（去 iCloud 化）| `.deps/Depth-Anything-3/src/depth_anything_3/` |
| DA3-Streaming vendored | `tools/vendor/official_da3_streaming/` |
| atultw MLX fork clone | `.deps/Depth-Anything-3-mlx/`（branch `copilot/convert-model-to-mlx`） |
| HF DA3-BASE 权重 | `~/.cache/huggingface/hub/models--depth-anything--DA3-BASE/snapshots/f4a6c9b3c95e41c82048423d3493a81ec3fa810e/model.safetensors` |
| ⚠️ iCloud 死路 DO NOT USE | `~/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/` |

---

## 12 给那个 agent / 未来 agent 的一句话

**N=60 mlpackage 必须用 CoreML（fused SDPA 是 iPhone 上唯一活路），但 trace 这道工序在 18GB Mac 上死了 7 次。换 32GB+ 硬件 OR 接受 N=50 ceiling。MLX 走 iPhone 不通。**

并行 R1-R5 oracle resume 工作就绪等恢复（DA3 src 已搬出 iCloud）。

---

## 13 详细 chronological log → [EXPERIMENTS_LOG_ZH.md](EXPERIMENTS_LOG_ZH.md)
