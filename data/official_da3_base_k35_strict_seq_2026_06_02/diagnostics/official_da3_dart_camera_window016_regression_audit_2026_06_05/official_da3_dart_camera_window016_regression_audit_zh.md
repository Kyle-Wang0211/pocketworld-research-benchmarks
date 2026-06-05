# Official DA3 Dart-camera window_016 regression audit

日期：2026-06-05

## 结论

- status: `thickness_persists_after_dart_camera_contract_pose_coreml`
- product path: `DA3BASE_476x742_N35_pose CoreML CPU rerun with Dart-owned camera tensors`
- goal complete: `False`

Single-window thickness still persists after Dart camera contract, current runnable CoreML rerun, and official postprocess.

Inspect DA3 upstream pose/depth/scale consistency inside window_016, especially later slots; do not route this back to A100/large-memory image-only export as product blocker.

## 大白话

- 当前能在 Mac/Apple 路线跑的 DA3-BASE pose CoreML 已经按 Dart camera contract 重跑了 window_016。
- 官方 postprocess 之后，npz downstream 风格下 first35 仍比 first10 明显变厚。
- 这说明厚层不是大内存导出问题，也不是官方 downstream 里有一个隐藏去厚步骤没跑。
- 下一步应该继续查 DA3 上游几何一致性：同一 K35 window 后段 slot 的 pose/depth/scale 是否互相打架。

## Metrics

- npz bbox k35/k10: `1.489`
- npz PCA minor k35/k10: `1.720`
- glb bbox k35/k10: `1.285`
- glb PCA minor k35/k10: `1.106`
- pose span k35/k10: `4.595`
- depth p95 k35/k10: `1.074`

## Checks

| check | status | evidence |
|---|---:|---|
| `dart_camera_fields_present` | `pass` | All 414 frames carry Dart-owned OpenCV w2c and 3x3 intrinsics. |
| `single_window_coreml_rerun_completed` | `pass` | window_016 CoreML CPU rerun wrote 35 frames. |
| `official_postprocess_completed` | `pass` | official postprocess poseScale=0.7230838815049764 |
| `npz_streaming_thickness_persists` | `fail` | npz k35/k10 bbox=1.489, minor=1.720 |
| `glb_style_thickness_persists` | `warning` | glb k35/k10 bbox=1.285, minor=1.106 |
| `pose_span_expands_more_than_depth` | `pass` | pose span=4.595x, depth p95=1.074x |
