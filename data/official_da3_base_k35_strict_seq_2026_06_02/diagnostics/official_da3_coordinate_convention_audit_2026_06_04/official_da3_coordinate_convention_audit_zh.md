# Official DA3 coordinate convention audit

日期：2026-06-04

## 结论

- 本地 official DA3 与 GitHub main 一致：`41736238f5bced4debf3f2a12375d2466874866d`。
- DA3 `prediction.extrinsics` 是 OpenCV/Colmap-style w2c。
- 官方 GLB 导出会额外做 first-camera 对齐、CV-to-glTF 的 Y/Z 翻转、median centering。
- 官方 DA3-Streaming NPZ/PLY 路径不做 GLB 对齐；它是在 DA3 world 坐标里 confidence filter + reservoir sample。
- Research 已经把 GLB-style 和 NPZ-streaming-style 分开；APP official baseline 应继续使用 NPZ streaming 语义。
- 当前 `_pose` APP 分支仍把 `cameraTransform` 原样喂 CoreML；它只能当兼容/对照，不是官方 image-only baseline。

## 坐标语义表

| Path | Coordinate frame | What it does |
|---|---|---|
| DA3 prediction | OpenCV/Colmap w2c | model outputs `pred_extrinsics/pred_intrinsics` |
| official GLB | glTF-aligned scene | w2c backproject -> first camera -> flip Y/Z -> center |
| official NPZ/PLY | DA3 world | w2c backproject -> confidence threshold -> sample |
| Blender/third-party PLY | tool-dependent | needs explicit conversion; do not assume DA3 PLY is Blender-ready |

## 官方证据

### GLB path

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/export/glb.py:237`: `c2w = np.linalg.inv(_as_homogeneous44(ext_w2c[i]))  # (4,4)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/export/glb.py:275`: `def _compute_alignment_transform_first_cam_glTF_center_by_points(`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/export/glb.py:302`: `M[1, 1] = -1.0  # flip Y`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/export/glb.py:303`: `M[2, 2] = -1.0  # flip Z`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/utils/export/glb.py:311`: `center = np.median(pts_tmp, axis=0)`

### Streaming NPZ/PLY path

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:273`: `predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:102`: `c2w = torch.inverse(extrinsics_4x4)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/npz_output_process.py:77`: `conf_threshold = np.mean(confs_combined) * conf_threshold_coef`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/loop_utils/sim3utils.py:237`: `def save_confident_pointcloud_batch(`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/loop_utils/sim3utils.py:233`: `trimesh.PointCloud(points, colors=colors).export(output_path)`

## Research 对齐状态

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:321`: `extrinsics.append(camera_transform_to_opencv_w2c(frame["cameraTransform"]))`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/da3_mac_window_export.py:345`: `def camera_transform_to_opencv_w2c(values: list[float]) -> np.ndarray:`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/strict_k35_window_official_filter_micro_audit.py:359`: `def official_glb_alignment_transform(ext_w2c0: np.ndarray, points_world: np.ndarray) -> np.ndarray:`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/strict_k35_window_official_filter_micro_audit.py:395`: `def depth_to_point_cloud_vectorized(`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/official_save_sequence_pointcloud_export.py:312`: `world_points = (c2w @ camera_points_h)[:3].T.astype(np.float32)`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/official_save_sequence_pointcloud_export.py:365`: `"note": "No cleanup, no Poisson, no mesh; only official confidence filter and reservoir sample.",`

## APP 风险点

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:30`: `"DA3BASE_476x742_N35_image_only",`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:237`: `"image": MLFeatureValue(multiArray: imageArray),`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:238`: `"extrinsics": MLFeatureValue(multiArray: extrinsics),`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:631`: `let values = doubleArray(frame["cameraTransform"])`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Da3DepthPlugin.swift:633`: `for i in 0..<16 { ptr[base + i] = Float(values[i]) }`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/lib/pipeline/local_pipeline_runner.dart:2597`: `id: 'official_streaming_image_only_coreml_contract',`
- `/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart:17`: `'blocked_until_image_only_coreml_signature',`

## 判读规则

Do not compare GLB-aligned views and NPZ world PLYs as if they used the same coordinate frame. For single-window thickness, use one fixed official style, preferably NPZ streaming for APP baseline.

## 下一步

After DA3BASE_476x742_N35_image_only exists, run the same window through image-only and compare first35/first10 thickness in NPZ streaming coordinates.
