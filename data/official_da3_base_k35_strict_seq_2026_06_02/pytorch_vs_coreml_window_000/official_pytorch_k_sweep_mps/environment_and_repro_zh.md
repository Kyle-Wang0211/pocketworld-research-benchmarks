# Official PyTorch K Sweep 环境与复现

## 目标

尝试跑通官方 DA3 PyTorch 在同分辨率 476 / 742 下的 reference。先从小 K 开始，作为 CoreML strict / official-filter 的对照线。此步骤不做自研 graph patch、不做自研融合，只调用官方 DA3 API 内部 forward、pose normalize、Umeyama align 相关逻辑。

## 官方来源

- 官方源码路径：`/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`
- 官方源码 commit：`41736238f5bced4debf3f2a12375d2466874866d`
- 官方 requirements 来源：
  - `requirements.txt`
  - `da3_streaming/requirements.txt`
  - `pyproject.toml`

## 模型

- 模型路径：`/Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE`
- 模型大小：516M
- `config.json` SHA256：`5e34115ebc17bd2d8d43033c5f72e9446ac8833fd61d3fa160b7e67e0bb5b7b5`
- `model.safetensors` SHA256：`e01067dc1659613083d9145a9a2547ccdbe6ccbbf83c4fe7b3e8a4e2bdae78b5`

## 本机运行环境

- macOS：26.1，Build 25B78
- Python：3.11.15
- Python executable：`/Users/kaidongwang/Developer/Aether3D-cross/.venv-da3/bin/python`
- 物理内存：19327352832 bytes
- Torch：2.12.0
- TorchVision：0.27.0
- MPS：available
- CUDA：not available
- NumPy：1.26.4
- Pillow：12.2.0
- OpenCV：4.11.0.86
- SciPy：1.17.1
- Einops：0.8.2
- HuggingFace Hub：1.15.0
- Safetensors：0.7.0
- CoreMLTools：9.0
- Open3D：0.19.0
- Trimesh：4.12.2

## 运行命令

```bash
/Users/kaidongwang/Developer/Aether3D-cross/.venv-da3/bin/python \
  tools/python/official_pytorch_k_sweep.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/strict_window_000_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/pocketworld/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k_sweep_mps \
  --device mps \
  --process-res 476 742 \
  --k-values 1 2 3 5 10 35 \
  --save-arrays
```

## 结果摘要

| K | process_res | 状态 | 说明 |
|---:|---:|---|---|
| 1 | 476 | failed | forward 后 Umeyama alignment 退化 |
| 2 | 476 | failed | forward 后 Umeyama alignment 退化 |
| 3 | 476 | success | 输出 `3x3x308x476` |
| 5 | 476 | success | 输出 `5x3x308x476` |
| 10 | 476 | success | 输出 `10x3x308x476` |
| 35 | 476 | failed | MPS buffer 15.36 GiB |
| 1 | 742 | failed | forward 后 Umeyama alignment 退化 |
| 2 | 742 | failed | forward 后 Umeyama alignment 退化 |
| 3 | 742 | success | 输出 `3x3x476x742` |
| 5 | 742 | success | 输出 `5x3x476x742` |
| 10 | 742 | aborted | MPS native abort，约 15.6 GB private buffer |

## 判断

这一步证明官方 PyTorch 同分辨率 reference 在小 K 下可以跑通，且 K=1/2 的异常不是 depth forward 崩坏，而是官方 Umeyama 在极少帧时不可解。它还没有证明完整 K35@476/742 的 PyTorch reference 已在本机跑通；完整 K35 reference 需要更大内存的 CUDA 机器，或在大内存机器上做受控 CPU 复跑。
