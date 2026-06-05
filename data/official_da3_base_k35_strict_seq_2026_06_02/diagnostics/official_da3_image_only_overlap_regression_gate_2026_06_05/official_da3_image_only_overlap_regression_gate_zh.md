# Official DA3 image-only overlap regression gate

日期：2026-06-05

## 结论

- status: `pass_image_only_within_single_window_thickness_threshold`
- can judge original thick layer: `True`
- highest priority gap: `None`

这个 gate 只回答原始问题：固定 `DA3BASE_280x504_N35_image_only` 后，官方 image-only 路径是否控制住单个 K35 window 内多帧看到同一表面造成的厚层。

## 固定前提

- resource: `DA3BASE_280x504_N35_image_only`
- window size: `35`
- input: `280x504`
- camera policy: `official_image_only_no_arkit_vio_inputs`
- preprocess baseline: `photos_depth_same_input`
- old `_pose` role: `old_pose_conditioned_is_reference_only`
- dimension sweep: `disabled`

## 输入预处理基线

- baseline: `photos_depth_same_input`
- ready for this gate: `True`
- expected tensor source: `photos_depth official process_res=504 upper_bound_resize patch-aligned images`
- official API preprocess equivalent: `True`
- CoreML same-input parity: `True`
- shape matches fixed target: `True`
- resize mode: `upper_bound_resize_patch_align`
- scale x/y: `0.119318` / `0.117845`
- aspect preserving: `False`
- blocking reasons: ``

`photos_depth_same_input` 现在来自官方 process_res=504 upper_bound_resize + patch-align 的缓存；厚层回归比较不能把它和旧 742x476/direct_stretch 输入路径混用。

## 官方 downstream 参数

- path: `results_output/frame_*.npz + npz_output_process.py`
- conf threshold coef: `0.5`
- sample ratio: `0.015`
- cleanup: `none`

## 输出检查

| dataset | ready | contract | resource | shape ok | window frames | reasons |
|---|---:|---|---|---:|---:|---|
| pose_conditioned_reference | False | pose_conditioned_coreml_requires_image_extrinsics_intrinsics | DA3BASE_476x742_N35_pose | False | 35 | shape_not_fixed_target |
| image_only_candidate | True | image_only | DA3BASE_280x504_N35_image_only | True | 35 |  |

## 当前为什么不能判断厚层是否消失



需要先产出同一 capture、同一 `window_016`、同一 `280x504/N35` 的 image-only DA3 输出。没有这个输出时，不能用尺寸、AR/VIO 或 downstream cleanup 来替代这个实验。

## 下一次运行

```bash
python3.11 tools/python/da3_mac_window_export.py --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline_window016_2026_06_05 --model <path-to-DA3BASE_280x504_N35_image_only.mlpackage> --compute-unit all --resume
```
