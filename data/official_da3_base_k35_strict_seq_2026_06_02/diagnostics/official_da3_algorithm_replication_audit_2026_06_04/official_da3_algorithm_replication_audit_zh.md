# Official DA3 algorithm replication audit

日期：2026-06-04

## 结论

- status: `incomplete_missing_target_image_only_coreml_model`
- can judge original thick layer: `False`
- highest priority gap: `DA3BASE_476x742_N35_image_only.mlpackage_or_mlmodelc_missing`
- fixed target: `DA3BASE_476x742_N35_image_only` / K35 / `476x742`
- AR/VIO: official baseline 禁用外部相机输入，AR 只可作为 metadata 或兼容路径对照。

当前不能把 `_pose` CoreML 的厚层直接归因给 DA3 官方算法。官方 Streaming 默认是 image-only，当前产品路径还缺目标 image-only CoreML 模型和同 capture 输出。

## 官方算法事实

- official repo HEAD: `41736238f5bced4debf3f2a12375d2466874866d`
- official remote main: `41736238f5bced4debf3f2a12375d2466874866d	refs/heads/main`
- DA3-BASE commercial license: `True`
- Streaming call has no external camera args: `True`
- Streaming call: `da3_streaming.py:273 predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)`
- default camera decoder evidence: `da3.py:216 pose_enc = self.cam_dec(feats[-1][1])`
- predicted w2c output evidence: `da3.py:225 output.extrinsics = affine_inverse(c2w)`
- GS head prefers predicted camera poses: `da3.py:247 # we instead use the predicted camera poses for better alignment.`

## Downstream 事实

- npz output process reads frame npz: `npz_output_process.py:27 npz_files = sorted(glob(os.path.join(npz_folder, "frame_*.npz")))`
- confidence threshold: `npz_output_process.py:77 conf_threshold = np.mean(confs_combined) * conf_threshold_coef`
- no in-window fusion/dedup detected: `True`

大白话：官方 downstream 负责跨 chunk 只保存 core-frame、按置信度筛点、采样；它不是把单个 K35 里同一墙面/桌面多次观测融合成一层的模块。单 window 厚层如果存在，首先要查 DA3 上游预测的 depth/pose/intrinsics 一致性。

## 当前项目状态

- image-only CoreML package exists: `False`
- image-only compiled model exists: `False`
- pose CoreML package exists: `True`
- image-only DA3 output dir exists: `False`
- overlap gate status: `blocked_missing_image_only_target_output`

## Research / APP 对齐

- Research PyTorch exporter image-only mode: `official_pytorch_window_export.py:41 choices=["pose_conditioned", "image_only"],`
- Research Mac exporter detects CoreML input contract: `da3_mac_window_export.py:286 def da3_input_contract(input_names: list[str]) -> str:`
- Research pose path converts ARKit camera to OpenCV w2c: `da3_mac_window_export.py:321 extrinsics.append(camera_transform_to_opencv_w2c(frame["cameraTransform"]))`
- APP Swift supports target image-only resource name: `Da3DepthPlugin.swift:30 "DA3BASE_476x742_N35_image_only",`
- APP `_pose` raw cameraTransform risk: `Da3DepthPlugin.swift:631 let values = doubleArray(frame["cameraTransform"])`
- policy blocks official baseline until image-only signature: `photo_bundle_pipeline_policy_service.dart:17 'blocked_until_image_only_coreml_signature',`

## 输入预处理

- current input: `476x742`
- resize mode: `direct_stretch`
- scale x/y: `0.17566287878787878` / `0.20033670033670034`
- aspect preserving: `False`

这说明当前 `photos_depth` 是固定输入同源 parity 路径，不等价于官方 highres API 的动态 `upper_bound_resize`。这个差异要被标注，但现在不改尺寸。

## 下一步

- Export or obtain DA3BASE_476x742_N35_image_only.mlpackage with CoreML input signature image only.
- Put the package in ios/Runner/Models/DA3-BASE-CoreML or pass it to the Mac exporter.
- Run da3_image_only_coreml_readiness_gate.py, then da3_mac_window_export.py on the same capture.
