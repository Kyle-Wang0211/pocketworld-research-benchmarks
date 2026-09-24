# Official DA3 image-only K35 probe

日期：2026-06-04

## 当前结论

用户纠正是对的：如果目标是尽量贴合官方 DA3-Streaming 默认算法，DA3 inference 不应该吃 ARKit/VIO 相机输入。

官方 DA3 API 支持 optional pose-conditioned mode，但官方 DA3-Streaming 默认入口是 image-only：

- `da3_streaming.py` 调用 `model.inference(images, ref_view_strategy=ref_view_strategy)`。
- CLI 只收 `--image_dir` / `--config` / `--output_dir`。
- 当前 APP/CoreML 的 `DA3BASE_476x742_N35_pose.mlpackage` 必填 `image/extrinsics/intrinsics`，因此它是 pose-conditioned CoreML 派生路径，不是官方 streaming 默认 baseline。

## 新增 probe

新增 exporter 能力：

- `tools/python/official_pytorch_window_export.py --camera-mode image_only`
- `image_only` 不传 `extrinsics/intrinsics`，保留 DA3 自己预测的 pose/intrinsics。
- `pose_conditioned` 保持旧行为，用输入相机 + Umeyama 对齐。

已跑通：

```bash
python3.11 tools/python/official_pytorch_window_export.py \
  --frames-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \
  --manifest data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/strict_window_016_official_manifest.json \
  --model-path /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE \
  --official-src /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src \
  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_016/official_pytorch_image_only_k35_252 \
  --device mps \
  --process-res 252 \
  --process-res-method upper_bound_resize \
  --camera-mode image_only \
  --conf-threshold-coef 0.5
```

运行日志明确出现：

- `Selecting reference view using strategy: saddle_balanced`
- `Model Forward Pass Done`

这说明该 probe 走的是无外部 camera token 的官方分支。pose-conditioned 分支不会触发同样的 reference-view selection 条件，因为提供 `cam_token` 后官方代码跳过该选择。

## Low-res K35@252 comparison

这些数字只用于方向判断；它们不能关闭 full same-resolution gate。

| Case | Camera mode | Shape | bbox diag p01-p99 | valid before sampling | sampled points | pose center diag | conf median | depth median | Umeyama scale |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PyTorch fixed K35@252 | pose-conditioned legacy | `35 x 168 x 252` | `1.815001` | `813088` | `12174` | `1.364758` | `2.407397` | `1.047231` | `0.903520` |
| PyTorch fixed K35@252 | image-only official streaming default | `35 x 168 x 252` | `2.179986` | `963943` | `5767` | `1.335351` | `2.032193` | `0.922745` | n/a |
| PyTorch highres K35@252 | pose-conditioned legacy | `35 x 140 x 252` | `1.699973` | `654491` | `9801` | `1.364758` | `1.954635` | `1.030640` | `0.932102` |

## Interpretation

当前不能再说“只要把 APP 的 ARKit `cameraTransform` 转成 OpenCV w2c 就贴近官方”。更贴近官方 DA3-Streaming 的做法是：

1. DA3 official baseline 使用 image-only inference。
2. ARKit/VIO 数据保留为 capture metadata 或后续产品层 metric-scale/quality diagnostics。
3. 如果保留 pose-conditioned DA3 实验，必须单独标注，不要叫 official streaming baseline。
4. 对 pose-conditioned 实验而言，ARKit camera-to-world 不能原样作为 DA3 extrinsics；它需要转换成 OpenCV world-to-camera。

## Remaining gates

- 需要导出或获得 `DA3-BASE K35@476x742 image-only CoreML`，signature 不应要求 `extrinsics/intrinsics`。
- 需要用 image-only PyTorch/CoreML 重新跑 official core-frame downstream，再判断 K35 内部厚层是否仍是官方 upstream 几何限制。
- full same-resolution PyTorch K35 gate 仍未关闭；本报告只是低分辨率方向 probe。
