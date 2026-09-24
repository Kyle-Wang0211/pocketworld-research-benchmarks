# Official DA3 image-only geometry path audit

日期：2026-06-04

## 结论

- 官方 DA3-Streaming 默认路径是 image-only：不喂 AR/VIO，不喂外部 `extrinsics/intrinsics`。
- image-only 位姿来自 DA3 网络内部的 camera decoder：多视角特征 -> `cam_dec` -> 平移/旋转/FOV -> `pred_extrinsics/pred_intrinsics`。
- 官方 downstream 的 npz/pointcloud 路径做置信度阈值、采样、chunk 对齐和 core-frame 保存；没有看到单个 K35 window 内同表面点云融合/去重步骤。
- 因此，单 window 厚层如果被官方复刻消掉，应该主要来自上游 image-only depth/pose/scale 一致性，而不是 downstream 隐藏清理。
- 当前阻塞：`missing_DA3BASE_476x742_N35_image_only_coreml_and_outputs`。

## 固定目标

- model: `DA3-BASE`
- resource: `DA3BASE_476x742_N35_image_only`
- shape: `35 x 476 x 742`
- dimension sweep: `disabled`
- official camera input: `image_only`

## 官方代码证据

### Image-only entry

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:273`: `predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/docs/API.md:34`: `prediction = model.inference(["image1.jpg", "image2.jpg"])`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/README.md:21`: `arbitrary visual inputs, with or without known camera poses.`

### Camera generation

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/da3.py:126`: `if extrinsics is not None:`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/da3.py:216`: `pose_enc = self.cam_dec(feats[-1][1])`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/da3.py:224`: `c2w, ixt = pose_encoding_to_extri_intri(pose_enc, (H, W))`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/cam_dec.py:29`: `self.fc_t = nn.Linear(output_dim, 3)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/cam_dec.py:30`: `self.fc_qvec = nn.Linear(output_dim, 4)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/cam_dec.py:31`: `self.fc_fov = nn.Sequential(nn.Linear(output_dim, 2), nn.ReLU())`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/utils/transform.py:59`: `intrinsics[..., 0, 0] = fx`

### Reference view

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/docs/funcs/ref_view_strategy.md:12`: `DA3 provides a simple approach to address this through **automatic reference view selection** based on **class tokens**. Instead of relying on heuristics or manual selection, the model analyzes the class token features from all input views and intelligently selects the most suitable reference frame.`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/vision_transformer.py:318`: `b_idx = select_reference_view(x, strategy=strategy)`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src/depth_anything_3/model/dinov2/vision_transformer.py:328`: `ref_token = self.camera_token[:, :1].expand(B, -1, -1)`

### Downstream

- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/npz_output_process.py:77`: `conf_threshold = np.mean(confs_combined) * conf_threshold_coef`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/npz_output_process.py:120`: `sample_ratio = args.sample_ratio`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/da3_streaming.py:665`: `save_confident_pointcloud_batch(`

## 商用约束

- DA3-BASE 在官方 model card 表里是 `Apache 2.0`；DA3-LARGE/DA3-LARGE-1.1 是 `CC BY-NC 4.0`。
- 所以 APP 商用 baseline 继续锁 `DA3-BASE` 是合理的；不要为了质量直接换 Large，除非拿到额外授权。
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/README.md:223`: `| [DA3-BASE](https://huggingface.co/depth-anything/DA3-BASE)                     | 0.12B     | ✅             | ✅            | ✅             |       |               |           | Apache 2.0     |`
- `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/README.md:221`: `| [DA3-LARGE-1.1](https://huggingface.co/depth-anything/DA3-LARGE-1.1)                     | 0.35B     | ✅             | ✅            | ✅             |       |               |           | CC BY-NC 4.0     |`

## 当前项目状态

- APP CoreML packages: `DA3BASE_476x742_N35_pose.mlpackage`
- has target image-only package: `False`
- readiness gate: `{"status": "fail", "official_baseline_ready": false, "has_image_only_coreml_signature": false, "current_bundle_is_pose_conditioned_only": true, "app_contract_ready_for_future_image_only_model": true, "policy_blocks_current_pose_model_from_official_baseline": true, "selected_policy_resource": "DA3BASE_476x742_N35_pose", "highest_priority_gap": "missing_image_only_da3_base_coreml_signature", "do_not_use_arkit_vio_as_da3_input_for_official_baseline": true, "do_not_add_downstream_cleanup_to_hide_this_gap": true}`
- overlap regression gate: `{"status": "blocked_missing_image_only_target_output", "can_judge_original_thick_layer": false, "reason": "Need DA3BASE_476x742_N35 image-only CoreML output for the same capture/window before testing whether overlap thickness is removed.", "highest_priority_gap": "da3_output_dir_missing", "do_not_change_dimension": true, "do_not_use_arkit_vio_as_da3_input": true, "do_not_claim_downstream_cleanup_fixed_upstream_overlap": true}`
- prior overlap/thickness finding: `{"overlap_frame_duplicate_saved_to_downstream": false, "official_core_frame_selection_removed_overlap_duplicates": true, "single_window_thickness_remains_after_official_filter": true, "confidence_or_valid_fraction_is_sufficient_explanation": false, "pose_span_is_strongest_current_clue": true, "most_likely_current_cause": "within_window_upstream_geometry_consistency", "plain_language": ["Official core-frame downstream removes repeated overlap frames from the final sequence-level pointcloud.", "That does not fuse multiple K35 views of the same surface into one thin surface.", "Current evidence says the remaining thick layer is already present inside individual K35 windows, before cross-window loop or full-chunk merge can explain it."]}`

## 外部状态

- official repo: https://github.com/ByteDance-Seed/Depth-Anything-3
- issue #254: https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254
- issue #254 state: `open`
- issue #254 comments: `0`

## 下一步

1. Export or obtain DA3BASE_476x742_N35_image_only.mlpackage.
2. Run da3_mac_window_export.py against the same capture/window_016 with the image-only package.
3. Rerun da3_image_only_overlap_regression_gate.py; judge PCA minor first35/first10 against old _pose.
4. Only after that result, decide whether remaining cleanup is official parity or product adaptation.
