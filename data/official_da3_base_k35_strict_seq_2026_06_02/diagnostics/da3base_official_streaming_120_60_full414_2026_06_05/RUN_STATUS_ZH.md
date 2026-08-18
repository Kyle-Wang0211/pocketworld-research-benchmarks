# DA3-BASE 官方 Streaming 120/60 Oracle 运行状态

日期: 2026-06-05

## 目标

- 模型: DA3-BASE
- Streaming: 官方 DA3-Streaming
- 窗口: chunk_size=120, overlap=60
- 输入: 414 帧，按 manifest 顺序重命名/软链为 000000.jpg ...
- loop closure: 开启
- alignment: 官方 dense Sim3。runner 默认 `--align-lib auto`，在 CUDA+Triton 环境保持官方默认 Triton backend；当前 Mac 因无 CUDA/Triton，自动降到官方支持的 numpy backend。此次失败发生在 DA3 前向，尚未进入 alignment。
- 输出目标: combined PLY + unique-frame NPZ fusion PLY

## 已完成

- DA3-BASE 权重已下载并指向:
  `/Users/kaidongwang/.cache/huggingface/hub/models--depth-anything--DA3-BASE/snapshots/f4a6c9b3c95e41c82048423d3493a81ec3fa810e`
- SALAD loop closure 权重已下载:
  `weights/dino_salad.ckpt`
- 414 帧 manifest 顺序输入已生成:
  `input_manifest_ordered_414/`
- effective config 已生成:
  `effective_config.yaml`
- oracle runner 已生成，并已做 CUDA 优先设备选择与 `--align-lib auto`:
  `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3base_official_streaming_oracle.py`

## 阻塞点

正式 120/60 运行在第一个 chunk 的 DA3-BASE 前向推理阶段失败，尚未进入 adjacent alignment、loop closure 或 PLY/NPZ 写出阶段。

错误核心:

```text
RuntimeError: Invalid buffer size: 167.32 GiB
```

触发位置是 DA3 的 DINOv2 attention:

- `depth_anything_3/model/dinov2/layers/attention.py`
- `F.scaled_dot_product_attention(...)`

原因不是本次 wrapper 的排序、权重或 Sim3 alignment 配置，而是本机 MPS 后端无法执行官方 120 帧 global attention。因为第一个 chunk 的推理没有完成，Sim3 alignment backend 实际没有被调用。

DA3-BASE 是 ViT-B，patch_size=14，num_heads=12。官方默认 process_res=504 时，本序列预处理为 280x504，每帧 token 数约:

```text
(280 / 14) * (504 / 14) + cls = 20 * 36 + 1 = 721
```

120 帧 global attention token 数:

```text
120 * 721 = 86,520
```

如果后端 materialize attention matrix，buffer 约:

```text
12 heads * 86520^2 * 2 bytes = 167.3187 GiB
```

这与实际报错的 `167.32 GiB` 完全一致。

## 当前本机环境

- 系统: Darwin arm64
- 统一内存: 19,327,352,832 bytes，约 18 GiB
- torch: 2.12.0
- CUDA: unavailable
- MPS: available
- `nvidia-smi`: unavailable

## 当前输出状态

因为失败发生在第一个 chunk 推理阶段之前的结果落盘点，所以当前没有:

- `_tmp_results_unaligned/chunk_*.npy`
- `pcd/*.ply`
- `pcd/combined_pcd.ply`
- unique-frame NPZ fusion PLY

我没有把窗口改小、没有降低分辨率、也没有用额外滤波/清理/修补算法来伪造结果。

## CUDA 复跑命令

在有 CUDA + Triton + memory-efficient SDPA/FlashAttention 的官方环境中，直接复跑；`--align-lib auto` 会选择官方默认 Triton backend:

```bash
KMP_DUPLICATE_LIB_OK=TRUE PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONUNBUFFERED=1 \
/Users/kaidongwang/.cache/codex-da3base-streaming-venv/bin/python -u \
/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3base_official_streaming_oracle.py \
--capture-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
--manifest /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_input_manifest.json \
--output-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/da3base_official_streaming_120_60_full414_2026_06_05 \
--vendor-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming \
--da3-src-dir /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
--da3-base-snapshot /Users/kaidongwang/.cache/huggingface/hub/models--depth-anything--DA3-BASE/snapshots/f4a6c9b3c95e41c82048423d3493a81ec3fa810e \
--salad-ckpt /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/da3base_official_streaming_120_60_full414_2026_06_05/weights/dino_salad.ckpt \
--align-lib auto \
--force-refresh-input
```
