# Official PyTorch K35 full-res memory gate

日期：2026-06-04

## 结论

`window_016` 的官方 PyTorch full K35 同分辨率 A/B 目前在本机 MPS 上不可跑。这个 blocker 不是 PyTorch 2.8 的单点问题；PyTorch 2.12 也在同一 attention buffer 上失败。

这条 gate 仍未关闭，所以不能把“官方 PyTorch 同分辨率 K35 是否也厚”作为已证明事实。

## 官方代码检查

本地官方 DA3 source：

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/layers/attention.py`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/vision_transformer.py`

关键点：

- DINO attention 直接调用 `torch.nn.functional.scaled_dot_product_attention`。
- `block_chunks` 注释和代码语义是 FSDP wrap，不是推理时把 global attention 切块。
- 当前官方代码没有发现可直接启用的 xformers/memory-efficient attention fallback。
- `xformers` 在 requirements 中列出，但当前官方 DINO layer 实际 import path 没有使用 xformers attention 替代当前 SDPA 分支。

## 环境尝试

### Python 3.9 / torch 2.8.0

命令入口：

```bash
/usr/bin/python3 tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --device mps
```

结果：

- `process_res=742`
  - processed shape：`35 x 3 x 476 x 742`
  - failure：`RuntimeError: Invalid buffer size: 89.01 GiB`
- `process_res=476`
  - processed shape：`35 x 3 x 308 x 476`
  - failure：`RuntimeError: Invalid buffer size: 15.36 GiB`
- `process_res=252`
  - processed shape：`35 x 3 x 168 x 252`
  - success
  - output：`pytorch_vs_coreml_window_016/official_pytorch_k35_252/`

### Python 3.11 / torch 2.12.0

为了确认是不是 torch 2.8 的 MPS 实现问题，补齐官方 API import 所需的最小依赖：

- `omegaconf`
- `safetensors`
- `moviepy<2`
- `addict`
- `plyfile`
- `pycolmap`
- `trimesh`
- `evo`

`gsplat` 仍未安装；本实验不渲染 3DGS，官方 API 只打印 warning。

结果：

- `process_res=476`
  - torch：`2.12.0`
  - processed shape：`35 x 3 x 308 x 476`
  - failure：`RuntimeError: Invalid buffer size: 15.36 GiB`

因此，升级到 torch 2.12 没有解决 K35 full-ish resolution global attention buffer 问题。

## 当前可用证据

已经能跑的只是低分辨率趋势 gate：

- fixed `photos_depth` K35 `process_res=252`
- highres dynamic K35 `process_res=252`
- official npz-style CoreML/PyTorch downstream 对照

这些证据支持：

- CoreML 没有比 PyTorch 低分辨率参考成倍变厚。
- fixed mobile input 不是当前最强主因。
- 官方 downstream 没有隐藏的 voxel/TSDF/surfel 去重。

但它们不能替代 full same-resolution K35 PyTorch hard parity。

## 下一步

要关闭这个 gate，需要满足至少一个条件：

1. 在更大统一内存/更大显存环境上跑官方 PyTorch `window_016` K35 `process_res=742`。
2. 官方后续提供 streaming/memory-efficient global attention 或 DA3-Long/DA3-Streaming update，并且确认输出语义仍是官方可比口径。
3. 在不改变 DA3 数学语义的前提下，找到官方认可的 attention kernel 替代路径。

在 gate 未关闭之前，工程结论应保持：

- K35 厚层更偏上游几何一致性限制。
- 但“官方 PyTorch 同分辨率 K35 是否也厚”仍是未证明项。
