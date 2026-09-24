# Official DA3 parity decision matrix

日期：2026-06-04

## 当前结论

PocketWorld 当前应继续复刻官方 DA3-Streaming 的 `results_output/frame_*.npz + npz_output_process.py` core-frame downstream 路径，而不是默认 CLI 的 `pcd/combined_pcd.ply` full-chunk merge 路径。

单个 K35 window 内多帧看到同一表面产生厚层，当前更像 DA3/K35 上游多帧几何一致性限制，不像是 APP downstream 少做了官方隐藏去重。

工程策略：

1. 先保持官方 baseline 干净：不加 voxel、TSDF、surfel、statistical pruning、normal-based cleaning。
2. APP 只走商业安全的 DA3-BASE K35@476x742。
3. 等 full same-resolution PyTorch K35 gate 关闭后，再开始移动端产品层调参/清理。

注意：`89.01 GiB` 不是“实现官方算法必须 89GB 内存”。它是本机用官方 PyTorch + MPS 跑 K35 same-resolution hard parity 实验时，global attention 申请的临时 buffer。APP 的产品路径是 CoreML；这个数字只说明 PyTorch 官方硬对齐验证在这台机器上被内存门槛卡住。

## 官方状态快照

刷新时间：2026-06-04。

官方 GitHub：

- Repo：<https://github.com/ByteDance-Seed/Depth-Anything-3>
- `main` / `HEAD`：`41736238f5bced4debf3f2a12375d2466874866d`
- PR #256 `Real-time Streaming Support for DA3-Streaming`：open，head `641a8b7ef86dbdbcbe165299296f6687a201f4c0`
- Issue #254 `DA3-Streaming 在室内近距离宽视角视频中出现 chunk 内/跨 chunk 多重影和局部错位...`：open，0 comments
- Issue #12 `DA3-long`：open，4 comments

官方许可：

- Official README model table：
  - `DA3-BASE`：Apache 2.0
  - `DA3-SMALL`：Apache 2.0
  - `DA3-LARGE` / `DA3-GIANT` / `DA3NESTED-*`：CC BY-NC 4.0
  - `DA3-LARGE-1.1` / `DA3-GIANT-1.1` / `DA3NESTED-GIANT-LARGE-1.1`：README table 仍列为 CC BY-NC 4.0
  - `DA3METRIC-LARGE` / `DA3MONO-LARGE`：Apache 2.0, but these are task-specific depth models, not direct replacements for the current DA3-Streaming pose/depth baseline
- HF model card：
  - <https://huggingface.co/depth-anything/DA3-BASE>：Apache 2.0
  - <https://huggingface.co/depth-anything/DA3-LARGE>：CC BY-NC 4.0
  - <https://huggingface.co/depth-anything/DA3-LARGE-1.1>：HF card/API currently says Apache 2.0, which conflicts with the official README table
- Official repo `pyproject.toml` declares package license `Apache-2.0`, but product model checkpoint policy must follow each model card/table, and conflicting checkpoint metadata should be treated as unresolved. For PocketWorld commercial path, DA3-BASE remains the safe default.

## 官方 downstream 路径判定

| 路径 | 官方行为 | 是否去 overlap | 是否解决单 window 厚层 | PocketWorld 选择 |
|---|---|---:|---:|---|
| `pcd/combined_pcd.ply` | `da3_streaming.py` writes each aligned full chunk to `pcd/*_pcd.ply`; `merge_ply_files` concatenates vertex payloads | No | No | 不作为 baseline |
| `results_output/frame_*.npz + npz_output_process.py` | `save_depth_conf_result` 只保存 non-overlap/core slots；`npz_output_process.py` 全局 threshold + sample | Yes, by frame selection | No hidden per-surface dedupe | APP official baseline |

关键理解：

- 官方 core-frame downstream 只减少 chunk overlap 帧重复。
- 它不做 voxel/TSDF/surfel，也不把单 window 内同一表面多帧投影强行融合成薄面。
- 所以 K35 内部厚层如果存在，主要要回到上游 depth/pose/scale 一致性和 K/window/resolution 限制去看。

## APP 当前对齐点

APP repo：`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter`

关键文件：

- `ios/Runner/Da3DepthPlugin.swift`
  - CoreML confidence 写出前应用 `official_da3_streaming_conf_minus_one`
  - `confidenceOffsetApplied = -1.0`
- `packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart`
  - 默认 windowing mode：`officialStreamingSequential`
  - `officialCoreFrameIDs` / `officialSaveSlotIndices`
  - `officialSavedDuplicateFrameCount = 0`
  - preflight mode：`official_da3_streaming_npz_downstream_baseline`
  - product cleanup policy：disabled until official parity is proven
- `lib/pipeline/local_pipeline_runner.dart`
  - PointCloudStage consumes only official core frames
  - uses `relativeDepthPath_only`
  - ignores `metricDepthPath` in official baseline
  - blocks downstream if dense Sim3 / streaming alignment is incomplete
  - writes `camera_poses.txt`, `intrinsic.txt`, `camera_pose_depth_scales.json`
  - applies global `mean(conf) * 0.5`
  - `0.5` comes from `npz_output_process.py` CLI default; `0.75` is the DA3-Streaming `Pointcloud_Save` config used by the full-chunk PLY path
  - applies `sample_ratio = 0.015`
  - writes binary little-endian PLY

APP verification already run:

```bash
flutter analyze lib/pipeline/local_pipeline_runner.dart \
  packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart \
  test/local_pipeline_runner_test.dart

flutter test test/local_pipeline_runner_test.dart \
  test/geometry_verification_test.dart \
  test/depth_meta_test.dart

git diff --check
```

Status：passed.

## Research evidence matrix

| Evidence | Artifact | Result | Interpretation |
|---|---|---|---|
| Official overlap/downstream audit | `diagnostics/official_da3_streaming_overlap_alignment_update_2026_06_04/official_overlap_pointcloud_alignment_update_zh.md` | No hidden voxel/TSDF/surfel dedupe found | Downstream cleanup is not official baseline |
| Upstream parity status | `diagnostics/official_da3_upstream_parity_status_2026_06_04/official_da3_upstream_parity_status_zh.md` | K35 thick layer is upstream geometry-related, full-res hard gate still open | Do not blame APP downstream first |
| CoreML vs PyTorch GLB-style K35-252 | `diagnostics/coreml_pytorch_official_filter_pointcloud_compare_window016_k35_res252/` | CoreML/PyTorch bbox ratio `1.080473`, PCA minor ratio `0.921668` | CoreML not catastrophically thicker than PyTorch low-res |
| PyTorch fixed vs highres K35-252 | `diagnostics/official_pytorch_fixed_vs_highres_window016_k35_res252/` | fixed/highres bbox ratio `1.067664` | fixed mobile input is a risk, but not strongest main cause |
| Official npz-style K35 compare | `diagnostics/official_npz_style_window016_k35_dataset_compare/` | CoreML/PyTorch fixed bbox ratio `0.959770`, PCA minor ratio `1.056783` | Official downstream path does not reveal CoreML-only thickening |
| Official npz threshold sensitivity | `diagnostics/official_npz_threshold_coef_sensitivity_2026_06_04/official_npz_threshold_coef_sensitivity_zh.md` | `coef=0.5` bbox ratios CoreML/PyTorch fixed/highres `1.011861 / 1.086782`; `coef=0.75` ratios `0.959770 / 0.992602` | APP should use npz CLI default `0.5`; threshold changes thickness but still does not reveal hidden downstream dedupe |
| Full-res memory gate | `diagnostics/official_pytorch_k35_fullres_memory_gate_2026_06_04/` | torch 2.8 and 2.12 both fail K35 `process_res=476` with `15.36 GiB`; `742` fails with `89.01 GiB` | Same-resolution PyTorch K35 hard parity requires bigger memory or official memory-efficient update |
| Full-res gate runbook | `diagnostics/official_pytorch_fullres_gate_runbook_2026_06_04/official_pytorch_fullres_gate_runbook_zh.md` | Provides CUDA/A100-H100 run commands and decision rules using canonical `conf_threshold_coef=0.5` | Big GPU is a one-time research reference gate, not a product hardware requirement |
| Remaining parity gaps ledger | `diagnostics/official_da3_remaining_parity_gaps_2026_06_04/official_da3_remaining_parity_gaps_zh.md` | Tracks 13 remaining official/research/product gaps | Prevents official baseline gaps from being confused with future product adaptation |
| Official PR #256 audit | `diagnostics/official_pr256_realtime_streaming_audit_2026_06_04/official_pr256_realtime_streaming_audit_zh.md` | Adds `da3_live.py`; no `save_depth_conf_result` / `npz_output_process.py` semantic change; no voxel/dedup | Real-time entry does not change downstream baseline or provide overlap pointcloud thinning |
| Official external refresh | `diagnostics/official_da3_external_refresh_2026_06_04/official_da3_external_refresh_zh.md` | PR/issues unchanged; `DA3-LARGE-1.1` has README-vs-HF license mismatch | Keep product checkpoint locked to DA3-BASE until upstream license conflicts are clarified |
| Official forum / issue watch | `diagnostics/official_da3_forum_watch_2026_06_04/official_da3_forum_watch_zh.md` | GitHub issue #254 directly reports DA3-Streaming indoor wide-FOV ghosting; #12/#132 mention double/multiple instances in chunk stitching; #204 explains huge OOM can come from BF16/FP32/backend mismatch; HF discussions provide no hidden cleanup path | A100/H100 is useful only as a one-time PyTorch reference gate; product viability must be judged on CoreML DA3-BASE mobile/laptop benchmarks |
| Mobile viability gate | `diagnostics/official_da3_mobile_viability_gate_2026_06_04/official_da3_mobile_viability_gate_zh.md`; `tools/python/da3_mobile_viability_gate.py` | Research sample reports `warning`: DA3-BASE K35@476x742 completed 414/414, but no real-device telemetry, no pointcloud report for that sample path, and no explicit product thresholds | Do not confuse Mac research completion with phone/tablet/laptop viability; DA3 product continuation must be proven by APP real-device audit + explicit latency/memory/thermal thresholds |
| Overlap vs K35 thickness attribution | `diagnostics/official_da3_overlap_vs_window_thickness_attribution_2026_06_04/official_da3_overlap_vs_window_thickness_attribution_zh.md`; `tools/python/da3_overlap_vs_window_thickness_attribution.py` | overlap18/overlap06 both select 414 unique frames with 0 duplicate saved frames; `window_016` still shows first35/first10 PCA minor growth about `1.465` under npz-style filtering | Official core-frame downstream removes overlap-frame duplicates, but single-window thick layers remain a within-window/upstream geometry consistency issue until full-res PyTorch gate says otherwise |
| Upstream geometry alignment audit | `diagnostics/official_da3_upstream_geometry_alignment_2026_06_04/official_da3_upstream_geometry_alignment_zh.md`; `tools/python/da3_upstream_geometry_alignment_audit.py` | Official DA3-Streaming default calls `model.inference(images, ref_view_strategy=...)` and CLI only accepts `--image_dir`; current `DA3BASE_476x742_N35_pose.mlpackage` requires `image/extrinsics/intrinsics`, so APP/Research are running pose-conditioned CoreML, not the official streaming image-only default. Camera conversion evidence still matters only for a separately labeled pose-conditioned experiment | Highest-priority upstream gate is now `app_pose_conditioned_coreml_vs_official_streaming_image_only_contract`: export/use image-only DA3-BASE CoreML or stop calling the current pose-conditioned path the official baseline |
| Image-only K35 PyTorch probe | `diagnostics/official_da3_image_only_probe_2026_06_04/official_da3_image_only_probe_zh.md`; `tools/python/official_pytorch_window_export.py --camera-mode image_only` | `window_016` K35@252 image-only PyTorch runs successfully on MPS and logs `Selecting reference view using strategy: saddle_balanced`; fixed pose-conditioned bbox diag `1.815001` vs image-only bbox diag `2.179986` under this low-res diagnostic | Confirms the official streaming default branch is runnable and materially different from the current pose-conditioned path; use it to rebaseline before judging cleanup or AR/VIO conditioning |
| Image-only CoreML readiness gate | `diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_04/official_da3_image_only_coreml_readiness_gate_zh.md`; `tools/python/da3_image_only_coreml_readiness_gate.py` | Gate status is `fail`: APP bundle has 1 DA3 CoreML model, `image_only_model_count=0`, `pose_conditioned_model_count=1`; current `DA3BASE_476x742_N35_pose` requires `image/extrinsics/intrinsics` | APP native/policy are prepared to label or accept a future image-only resource, but official baseline remains blocked until a CoreML model whose required inputs are exactly `image` exists and becomes selected policy |
| Image-only CoreML export feasibility | `diagnostics/official_da3_image_only_coreml_export_feasibility_2026_06_04/official_da3_image_only_coreml_export_feasibility_zh.md`; `tools/python/da3_image_only_coreml_export_feasibility.py` | Wrapper contract is known: expose only `image`, call official DA3 with `extrinsics=None/intrinsics=None`, keep `pred_extrinsics/pred_intrinsics` outputs; `DA3-BASE/config.json` has both `cam_enc` and `cam_dec`; local environment has `coremltools 9.0` but torch `2.12.0` is outside coremltools tested range | Next action is to write/recover the original CoreML export wrapper for image-only DA3; do not fake image-only by passing identity/ARKit cameras |
| Image-only CoreML raw export dry-run | `diagnostics/official_da3_image_only_coreml_export_dry_run_2026_06_04/official_da3_image_only_coreml_export_dry_run_zh.md`; `tools/python/export_da3_image_only_coreml.py` | Raw PyTorch wrapper dry-run passes at K35@28x28 and outputs `depth/depth_conf/pred_extrinsics/pred_intrinsics`; unpatched tiny K3@28x28 CoreML conversion failed in PyTorch frontend `int` op | The official image-only wrapper semantics are valid, but raw official PyTorch graph is not directly CoreML-exportable without fixed-shape export patches |
| Image-only CoreML static export probe | `diagnostics/official_da3_image_only_coreml_static_export_probe_2026_06_04/official_da3_image_only_coreml_static_export_probe_zh.md`; `tools/python/export_da3_image_only_coreml.py --static-shape-export-patches` | K3@28x28 float16/float32 and K35@28x28, 56x56, 112x112, 168x280, 252x392 float16 image-only CoreML conversion all pass; every K35 package signature is exactly `image -> depth/depth_conf/pred_extrinsics/pred_intrinsics`; K3 float32 CoreML predict vs PyTorch has depth max abs `1.4305e-6`, depth_conf `3.5763e-6`, extrinsics `7.5027e-6`, intrinsics max rel `5.3401e-4`; K35@252x392 package size is `673M`; K35@336x532 dry-run passes but conversion terminates abnormally at about `37.62GB` peak memory footprint | CoreML image-only export is engineering-feasible without AR/external cameras; remaining gate is target-resolution K35@476x742 export in a larger/more stable conversion environment + APP bundle/readiness/performance parity |

## Decision table

| Question | Current answer | Confidence | Why |
|---|---|---:|---|
| 官方是否有隐藏的 per-surface pointcloud dedupe? | No evidence found | High | Official code paths only core-frame selection, threshold, sample, PLY concat |
| APP 是否应该走 `combined_pcd.ply`? | No | High | That path retains overlap slots; it is worse for duplicate overlap frames |
| APP 是否应走 `results_output + npz_output_process.py`? | Yes | High | This is official core-frame downstream; APP now follows its CLI default `conf_threshold_coef=0.5` |
| K35 单 window 厚层是否 downstream 造成? | Unlikely | Medium-high | npz-style compare shows no CoreML-only blow-up |
| K35 单 window 厚层是否 upstream geometry limitation? | Most likely | Medium | Pose/depth/scale span evidence + low-res PyTorch/CoreML compare support this |
| 是否已证明官方 PyTorch same-res K35 也厚? | No | Low/blocked | MPS memory gate prevents full same-resolution K35 PyTorch run |
| 是否可以开始加移动端 voxel/TSDF/surfel 清理? | Not yet for official baseline | High | Product cleanup belongs after official parity gate |
| 商用模型选择是否安全? | DA3-BASE remains the safe path | High | DA3-BASE Apache 2.0; LARGE/GIANT/NESTED have non-commercial or conflicting metadata; task-specific Apache depth models need separate study |
| 当前 APP CoreML 是否已经能称为官方 DA3-Streaming baseline? | No | High | New readiness gate proves current bundle is pose-conditioned only; image-only CoreML is missing |
| image-only CoreML 的位姿从哪里来? | DA3 internal camera decoder | High | Official model uses `cam_dec` to predict pose from image features when `extrinsics=None`; external cameras only activate the `cam_enc` conditioning path |
| image-only PyTorch wrapper 是否能本地前向? | Yes at diagnostic resolution | High | K35@28x28 dry-run passes, finite outputs have official four-output contract; the wrapper uses `extrinsics=None/intrinsics=None` |
| image-only CoreML conversion 是否完成? | Partially | High | K35 image-only CoreML conversion now passes up to `252x392` and has only `image` input; K35@336x532 dry-run passes but local conversion hits a resource gate; target `DA3BASE_476x742_N35_image_only.mlpackage` still does not exist and APP readiness gate remains fail |

## Remaining gates

### Gate A：full same-resolution PyTorch K35

Required to fully prove upstream limitation:

- `window_016`
- K35
- same frame set
- official PyTorch DA3-BASE
- same fixed `742x476` input or official highres dynamic reference
- official postprocess
- official npz-style downstream

Current blocker:

- `process_res=742`: `Invalid buffer size: 89.01 GiB`
- `process_res=476`: `Invalid buffer size: 15.36 GiB`
- reproduced under torch `2.8.0` and torch `2.12.0`

Runbook:

- `diagnostics/official_pytorch_fullres_gate_runbook_2026_06_04/official_pytorch_fullres_gate_runbook_zh.md`
- A100/H100-class GPU is only for closing the research reference gate; it is not a PocketWorld product hardware target.

### Gate B：official memory-efficient route

Watch upstream:

- PR #256：audited on 2026-06-04; it adds DA3-Live style real-time streaming entry, but does not add memory-efficient attention, voxel/TSDF/surfel dedupe, or core-frame downstream changes
- issue #254
- DA3-Long / VGGT-Long / future streaming updates

Do not adopt a custom attention/chunking patch as "official parity" unless the output semantics are clearly official or separately labeled as product adaptation.

### Gate C：product cleanup after parity

Only after official baseline is frozen:

- voxel/TSDF/surfel thinning
- normal-consistency pruning
- multi-view surface fusion
- metric-depth anchored cleanup
- mobile-specific K/resolution/window tuning

These must be reported as product layers, not as DA3 official replication.

## Plain-language answer

官方 DA3 能减少一类重复：chunk 与 chunk 之间 overlap frame 的重复保存。它不是在 downstream 里把单个 K35 window 内同一面墙的多帧点云“融合成一张薄面”。

所以我们现在走官方 `results_output/frame_*.npz + npz_output_process.py` 是对的，因为它是官方里面更干净的 core-frame 路径；但它不能魔法般解决 K35 内部厚层。

当前最稳妥的判断是：

- Downstream：APP 已经越来越接近官方路径，隐藏去重方向基本不成立。
- Upstream：K35 内部厚层更像 DA3/K35 上游几何一致性限制。
- Remaining proof：还缺 full same-resolution PyTorch K35 hard parity，原因是本机官方 PyTorch global attention 验证路径内存不够；这不是 APP/CoreML 产品实现必须 89GB。
- PR #256：它是“实时跑起来”的入口，不是“把重叠点云清薄”的入口。
