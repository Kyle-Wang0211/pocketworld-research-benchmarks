# Official DA3 image-only overlap regression gate

日期：2026-06-04

## 结论

- status: `blocked_missing_image_only_target_output`
- can judge original thick layer: `False`
- highest priority gap: `da3_output_dir_missing`

这个 gate 只回答原始问题：固定 `DA3BASE_476x742_N35` 后，官方 image-only 路径是否消除单个 K35 window 内多帧看到同一表面造成的厚层。

## 固定前提

- resource: `DA3BASE_476x742_N35_image_only`
- window size: `35`
- input: `476x742`
- camera policy: `official_image_only_no_arkit_vio_inputs`
- preprocess baseline: `photos_depth_same_input`
- old `_pose` role: `old_pose_conditioned_is_reference_only`
- dimension sweep: `disabled`

## 输入预处理基线

- baseline: `photos_depth_same_input`
- ready for this gate: `True`
- expected tensor source: `photos_depth fixed 742x476 images`
- official API preprocess equivalent: `False`
- CoreML same-input parity: `True`
- shape matches fixed target: `True`
- resize mode: `direct_stretch`
- scale x/y: `0.175663` / `0.200337`
- aspect preserving: `False`
- blocking reasons: ``

`photos_depth_same_input` 是当前 CoreML/PyTorch 同输入 parity gate；它不是官方 highres API 动态预处理的等价物。厚层回归比较不能把这两条输入路径混用。

## 官方 downstream 参数

- path: `results_output/frame_*.npz + npz_output_process.py`
- conf threshold coef: `0.5`
- sample ratio: `0.015`
- cleanup: `none`

## 输出检查

| dataset | ready | contract | resource | shape ok | window frames | reasons |
|---|---:|---|---|---:|---:|---|
| pose_conditioned_reference | True | - | DA3BASE_476x742_N35_pose | True | 35 |  |
| image_only_candidate | False | - | - | False | 0 | da3_output_dir_missing, depth_index_missing, mac_da3_window_reports_missing, window_missing |

## 当前为什么不能判断厚层是否消失

还缺同一 capture/window 的 `DA3BASE_476x742_N35_image_only` CoreML 输出，所以现在不能判断 image-only 是否消除了原始厚层问题。

需要先产出同一 capture、同一 `window_016`、同一 `476x742/N35` 的 image-only DA3 输出。没有这个输出时，不能用尺寸、AR/VIO 或 downstream cleanup 来替代这个实验。

## 下一次运行

```bash
python3.11 tools/python/da3_mac_window_export.py --capture-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict --out-dir /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline --model <path-to-DA3BASE_476x742_N35_image_only.mlpackage> --compute-unit all --resume
```
