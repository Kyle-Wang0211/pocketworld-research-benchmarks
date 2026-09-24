# Official DA3 copy-paste parity ledger

- 日期：2026-06-05
- 状态：`copy_paste_parity_rows_closed`
- 结论：官方 image-only CoreML signature/artifact 已落地并通过 readiness gate；已验证的 C++ OpenCV/libjpeg preprocess kernel 已完成 macOS/JIT bundled native asset smoke，APP 测试也已强断言 native 可用时 manifest 必须走 native_cpp_opencv_libjpeg；hook fallback 已加 host os/arch 安全限制，prebuilt matrix 已对当前 macOS arm64 做 ABI probe pass，并已把 ohos_arm64/ohos_x64 纳入正式目标；但总体仍是 1/9 ready，iOS/Android/Harmony/Windows/Linux/macOS x64 的预编译库与平台打包矩阵还没闭环。Research/CLI/capture package 已证明 source_highres 到官方 PIL/OpenCV InputProcessor 的 pixel/tensor exact；APP Dart runner 默认 tryOpen 已接上，Dart package:image decode/resize 现在只是 fallback-only gap。
- 下一步：用 DA3BASE_280x504_N35_image_only 跑 same-capture APP image-only regression；同时补齐 C++ OpenCV/libjpeg kernel 的 iOS/Android/Harmony/Windows/Linux/macOS x64 预编译库与平台打包矩阵。

## 大白话

- 你说的“找不同”是对的：现在剩下的大差异不是很多。
- 允许不同：官方 120/60 被手机约束改成 K35/overlap18。
- 刚补掉的差异：官方 image-only CoreML artifact/signature 已落地，并被 Xcode Resources 引用。
- 已经复制的部分：DA3-BASE 商用模型、官方 image-only 输入合约、官方 preprocess 的尺寸/patch 合同、K-window sliding/save-frame ownership、RGB/NCHW/ImageNet normalization、results_output core-frame downstream 边界。
- 刚补掉的差异：source_highres JPEG 到 photos_depth/photos_depth_tensor 已能通过实际 C++ OpenCV/libjpeg kernel byte-exact 复刻官方 InputProcessor。
- 仍要标注但不再算产品 blocker 的差异：Dart package:image 解同一张 JPEG 在原图阶段不是 byte-exact；它只能做 fallback/compat。
- 刚确认的复刻路线：实际 C++ OpenCV/libjpeg kernel 已有 C ABI 和 Dart FFI runner；不用再继续硬翻成 Dart。
- 官方 Python/C++ 能直接作为 Research/desktop oracle 的地方不替换；Dart 只负责 APP 编排和移动端 replay。
- 刚补上的 APP 接口：LocalPipelineRunner 和后台 isolate 已默认 tryOpen native preprocess runner。
- 刚补上的打包路径：aether_capture_services hook/build.dart 已能把现有 macOS dylib 注册成 bundled native asset；不带 env 的 package smoke 已通过。
- 还没闭环的工程差异：iOS/Android/Harmony/Windows 的 C++ OpenCV/libjpeg 预编译库和平台打包矩阵还没补齐；Harmony/OHOS 现在已进入机器可检查矩阵。
- 连续性 quarantine 不是官方复制，是后续移动端产品候选；不能拿它冒充 DA3 parity。

## Rows

| row | status | conclusion | missing evidence |
| --- | --- | --- | --- |
| `commercial_checkpoint` | `copied` | 本地产品路径锁 DA3-BASE / Apache-2.0；未复制 LARGE/GIANT/NESTED。 |  |
| `streaming_k_window_size` | `mobile_override_allowed` | 这是用户允许的核心差异：官方 120/60 无法作为手机主线，Dart 复制 sliding-window 公式但缩到 K35。 |  |
| `streaming_image_only_forward` | `copied_image_only_coreml_artifact_signature_and_bundle_gate` | DA3BASE_280x504_N35_image_only CoreML is now exported, has an image-only signature, is referenced by Xcode resources, and Swift still refuses pose fallback for the official image-only path. |  |
| `api_preprocess_resize` | `copied_shape_contract_only` | Dart photos_depth/photos_depth_tensor 默认路径已复制官方 process_res=504、upper_bound_resize、nearest patch-size shape contract，并把官方预处理终点推进到 normalized float tensor。 |  |
| `opencv_preprocess_pixel_parity` | `copied_via_native_kernel_verified` | Research/CLI/capture package 已接 C++ OpenCV/libjpeg kernel；从 source_highres 到 photos_depth/photos_depth_tensor 的 sampled gate 已 pixel/tensor exact。Dart 手写 resize 只保留 fallback/compat，不再是 official product preprocess。 |  |
| `opencv_native_preprocess_path` | `copied_native_path_verified_in_research` | Research audit 已证明 source_highres 抽样 32 帧里，实际 C++ OpenCV/libjpeg kernel 对官方 InputProcessor pixel/tensor exact；C ABI 已暴露给 Dart/平台插件调用。产品方向应接这个 native kernel，而不是继续手写 Dart resize/decode。 |  |
| `app_native_preprocess_runner_hook` | `macos_bundled_native_asset_hook_verified_cross_platform_prebuilts_pending` | APP LocalPipelineRunner 和后台 isolate 已默认尝试打开 native preprocess runner；aether_capture_services hook/build.dart 已能把现有 dylib 注册成 bundled CodeAsset，并已限制 monorepo fallback 只能用于 host os/arch，避免把 macOS dylib 误塞进 iOS/Android/HarmonyOS 包。package smoke 不带 env 已通过；prebuilt matrix 现在对 host 库做 ABI probe，当前 macOS arm64 为 pass，并已把 ohos_arm64/ohos_x64 纳入正式跨端目标；但总体仍是 1/9 ready。APP local_pipeline_runner_test 也强断言 native 可用时 da3_input_manifest execution.owner 必须是 native_cpp_opencv_libjpeg。剩余工程差异是补齐 iOS/Android/Harmony/Windows/Linux/macOS x64 的预编译库与平台打包矩阵。 | `Da3NativePreprocessRunner.tryOpen` |
| `source_jpeg_decode_parity` | `fallback_only_gap_not_product_official_path` | cap-1 source decode audit 仍证明 Dart package:image 与 PIL/libjpeg 不 byte-exact；但 official product preprocess 现在应走 C++ OpenCV/libjpeg kernel，这个 gap 只约束 fallback，不能再算产品 official preprocess blocker。 |  |
| `image_tensor_normalization` | `copied` | Dart tensor layout/normalization now copies official ImageNet semantics before native; Swift only loads pre-normalized float32 CHW into CoreML. Runtime tensor boundary audit is exact on sampled frames. |  |
| `official_save_depth_conf_result` | `copied` | Dart/APP 已复制官方 results_output/core-frame ownership，不再把 full-K withheld tail 当 downstream。 |  |
| `confidence_minus_one` | `copied_in_native_and_downstream_executor_smoke_passed` | Research NPZ 路径已按 confidence-minus-one 做对照；Swift native 写 confidencePath 前现在显式执行 conf -= 1.0；APP depth_index/PointCloudStage contract 禁止 raw depth_conf，Dart 点云 executor smoke 已跑通。 |  |
| `npz_output_process_pointcloud_filter` | `official_python_oracle_with_mobile_replay_smoke` | Research/desktop 权威路径现在有 bridge 直接生成官方 Python npz_output_process.py 所需的 results_output/frame_*.npz + camera_poses.txt；APP PointCloudStage 只是移动端 replay。bridge 不重写点云过滤算法，只做格式转换；Dart smoke 仅证明移动端 replay 边界。full-chunk pcd/combined_pcd.ply 仍不是产品 baseline。 |  |
| `combined_pcd_merge` | `copied_as_boundary_not_product_solution` | 官方 full-chunk PLY merge 没有 hidden 单窗去厚；产品点云不能把这条路误当厚层修复。 |  |
| `continuity_rejection` | `not_official_do_not_call_parity` | 连续性风险字段和 quarantine 是产品/研究候选，不是官方复制内容。它解释 window_016，但不能标成官方算法。 |  |
