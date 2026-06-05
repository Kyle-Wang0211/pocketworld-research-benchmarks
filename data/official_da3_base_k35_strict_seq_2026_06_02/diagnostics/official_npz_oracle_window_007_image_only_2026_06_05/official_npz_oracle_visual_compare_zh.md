# Official NPZ Oracle: window_007 image-only visual compare

日期：2026-06-05

## 结论

- 不能说厚层/重叠已经完全解决。
- 桌面上原来的 `DA3_image_only_window_007_*_npz_rgb.ply` 和官方 `npz_output_process.py` 直接导出的 `official_npz_script_*.ply` 在点数、包围盒、PCA 厚度上几乎一致。
- 因此这次肉眼看到的形状很烂，不是 Dart/Research PLY sampling executor 额外改坏；问题已经存在于 `CoreML image-only depth + pred pose + official npz_output_process.py` 这条链路里。
- 单帧 `frame_119` 的 depth 数值和可视化是连续、有限、可解释的，不像 depth 本身完全坏掉；多帧从 `first10` 开始明显散，优先嫌疑是多帧 pose/scale 一致性，而不是单帧 depth。

## 桌面文件

- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_single_frame_identity_cap621.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_first10_baseline.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_official_downstream_core17.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_full35_diagnostic.ply`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_frame119_image_depth_conf.png`
- `/Users/kaidongwang/Desktop/DA3_image_only_window007_visual_check/official_npz_script_ply_projection_compare.png`

## Official Script Evidence

官方脚本：

`/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/npz_output_process.py`

运行时只在诊断目录临时 stub 了导出点云未使用的 import 依赖：`triton`、`numba`、`sklearn`、`LoopDetector`、`DepthAnything3`。这些 stub 没有被调用；真正执行的是官方 `depth_to_point_cloud_vectorized(...)` 和 `save_confident_pointcloud_batch(...)`。

## Single Frame Depth Check

`frame_119 / cap-621`:

| signal | min | max | mean | p2 | p50 | p98 |
|---|---:|---:|---:|---:|---:|---:|
| depth | 0.590332 | 1.324219 | 0.972402 | 0.614258 | 0.975586 | 1.277344 |
| confidence | 1.000000 | 1.437500 | 1.075903 | 1.000000 | 1.053711 | 1.269531 |

解释：单帧 depth 没有 NaN、负值、爆远值，也能在 `single_frame_identity` PLY 里形成主体和地板的基本 2.5D 结构。它不是当前形状崩坏的第一嫌疑。

## PLY Metric Compare

| PLY | points | extent xyz | PCA std xyz |
|---|---:|---|---|
| official single identity | 11289 | `[1.0445, 0.7539, 0.7261]` | `[0.144771, 0.184357, 0.332114]` |
| official first10 | 21168 | `[1.1820, 1.2531, 1.1175]` | `[0.178621, 0.213892, 0.315201]` |
| official core17 | 35985 | `[1.1713, 1.2474, 1.1632]` | `[0.182038, 0.207853, 0.310638]` |
| official full35 | 74088 | `[1.3743, 1.2997, 1.2295]` | `[0.201479, 0.236953, 0.309212]` |
| official core17 pred-as-c2w diagnostic | 35985 | `[1.3237, 1.1547, 1.1808]` | `[0.200244, 0.219323, 0.314223]` |
| official full35 pred-as-c2w diagnostic | 74088 | `[1.4434, 1.3903, 1.2155]` | `[0.199572, 0.251692, 0.307921]` |

`pred-as-c2w` 没有明显改善，所以不能把问题简单定性成 `w2c/c2w` 反了。下一步应继续对齐官方 streaming 的 pose/scale postprocess：尤其是 CoreML image-only 输出的 `pred_extrinsics` 是否已经完成官方同等的 scale restore / chunk alignment / save_camera_poses 语义。

