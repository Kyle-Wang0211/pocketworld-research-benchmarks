# window_007 official confidence contract fix

日期：2026-06-05

## 结论

- 找到并修复一个明确的官方复刻差异：官方 DA3-Streaming 在写 `results_output/frame_*.npz` 前执行 `predictions.conf -= 1.0`。
- APP Swift image-only 分支已经按这个语义写 `confidencePath`。
- Research `da3_mac_window_export.py` 之前直接把 CoreML `depth_conf` 原样写出，导致官方 `npz_output_process.py` 默认 `conf_threshold_coef=0.5` 几乎放过所有点。
- 修复后，window_007 PLY 噪点/厚度有明显下降，但多帧 pose/scale 仍未根治。

## 代码修复

文件：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py`

修复：

`conf = depth_conf - 1.0`

这对齐官方：

`/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py`

其中 `process_single_chunk(...)` 在 inference 后执行 `predictions.conf -= 1.0`。

## 视觉文件

- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_first10_CONF_MINUS_ONE.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_core17_CONF_MINUS_ONE.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_full35_CONF_MINUS_ONE.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_conf_minus_one_before_after_projection.png`

## Metrics

| group | points before | points after | point ratio | PCA minor before | PCA minor after | minor ratio | Z extent before | Z extent after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| first10 | 21168 | 11614 | 0.5487 | 0.178621 | 0.168512 | 0.9434 | 1.1175 | 0.8391 |
| core17 | 35985 | 20438 | 0.5680 | 0.182038 | 0.166659 | 0.9155 | 1.1632 | 0.8183 |
| full35 | 74088 | 37820 | 0.5105 | 0.201479 | 0.175388 | 0.8705 | 1.2295 | 0.8659 |

## 判断

这次修复直接减少了低置信点融合，属于官方复刻必须修的 downstream confidence contract。它能减弱厚噪声，但仍不能解释所有多帧错位。下一步继续查 image-only CoreML `pred_extrinsics/pred_intrinsics` 与官方 PyTorch cam_dec 输出和 OutputProcessor 解码是否一致。

