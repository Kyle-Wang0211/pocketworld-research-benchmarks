# DA3 Dart continuity quarantine plan audit

日期：2026-06-05

## 结论

- status: `dart_continuity_quarantine_plan_matches_window016_true_rerun_variants`
- goal complete: `False`
- product ready: `False`

Dart can now generate a separate continuity-quarantine K35 plan whose window_016 variants match the true CoreML rerun frame sets. This makes the window split/quarantine candidate portable enough for the APP policy layer, while leaving the official default plan intact.

This is not official DA3 image-only parity and it is not enabled as the product gate yet. It is a research/product adaptation candidate that still needs more windows and captures.

Run the quarantine plan on additional risky windows/captures, compare thickness deltas, then decide the smallest Dart-side acceptance gate that avoids single-window discontinuity.

## 大白话

- 官方默认 window 文件没有被替换；quarantine 是单独输出的研究/产品候选计划。
- Dart 侧已经能把 window_016 拆成断点前、断点后、去掉所有 high-risk targets 三组候选，并保持 CoreML N35 固定输入形状。
- prefix 变体保留 10 帧，true rerun 后 npz minor/orig=0.778。
- segment 变体保留 7 帧，true rerun 后 npz minor/orig=0.877。
- drop-high-risk 变体保留 12 帧，true rerun 后 npz minor/orig=0.704。
- 这说明当前最实际的产品方向是 Dart 侧 continuity gate/window split，而不是追 89GiB image-only 导出或 downstream 点云去重。

## Metrics

| metric | value |
|---|---:|
| `official_window_count` | `24` |
| `quarantine_window_count` | `63` |
| `risky_source_window_count` | `21` |
| `window_size` | `35` |
| `source_window016_official_save_frame_count` | `17` |

## Checks

| check | status | evidence |
|---|---:|---|
| `window_016_prefix_before_first_break_matches_true_rerun_frames` | `pass` | window_016_prefix_before_first_break downstream frame set matches true rerun prefix_before_first_break. |
| `window_016_prefix_before_first_break_preserves_fixed_n35_runtime_shape` | `pass` | window_016_prefix_before_first_break keeps CoreML N35 shape through runtime padding only. |
| `window_016_prefix_before_first_break_removed_frames_are_source_difference` | `pass` | window_016_prefix_before_first_break removedFrameIDs equals source official downstream minus retained downstream. |
| `window_016_segment_from_first_break_matches_true_rerun_frames` | `pass` | window_016_segment_from_first_break downstream frame set matches true rerun segment_from_first_break. |
| `window_016_segment_from_first_break_preserves_fixed_n35_runtime_shape` | `pass` | window_016_segment_from_first_break keeps CoreML N35 shape through runtime padding only. |
| `window_016_segment_from_first_break_removed_frames_are_source_difference` | `pass` | window_016_segment_from_first_break removedFrameIDs equals source official downstream minus retained downstream. |
| `window_016_drop_all_high_risk_targets_matches_true_rerun_frames` | `pass` | window_016_drop_all_high_risk_targets downstream frame set matches true rerun drop_all_high_risk_targets. |
| `window_016_drop_all_high_risk_targets_preserves_fixed_n35_runtime_shape` | `pass` | window_016_drop_all_high_risk_targets keeps CoreML N35 shape through runtime padding only. |
| `window_016_drop_all_high_risk_targets_removed_frames_are_source_difference` | `pass` | window_016_drop_all_high_risk_targets removedFrameIDs equals source official downstream minus retained downstream. |
| `official_default_plan_unchanged` | `pass` | da3_k_windows.json remains the official timestamp sliding-window plan. |
| `quarantine_plan_is_separate_research_file` | `pass` | Continuity quarantine is emitted as a separate research/product-candidate plan. |
| `quarantine_plan_scope` | `pass` | Dart generated 63 variants from 24 official windows, with 21 risky source windows. |
| `window016_source_downstream_still_official_save` | `pass` | Source window_016 downstream remains the official save-frame set. |

## Window 016 Variants

| variant | real frames | padding | continuity | high-risk steps | npz minor/orig | npz bbox/orig |
|---|---:|---:|---:|---:|---:|---:|
| `window_016_prefix_before_first_break` | 10 | 25 | `pass` | 0 | 0.778 | 0.745 |
| `window_016_segment_from_first_break` | 7 | 28 | `warning` | 4 | 0.877 | 1.136 |
| `window_016_drop_all_high_risk_targets` | 12 | 23 | `warning` | 2 | 0.704 | 0.757 |

## Frame Sets

- `window_016_prefix_before_first_break` downstream: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`
- `window_016_prefix_before_first_break` removed: `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448`
- `window_016_segment_from_first_break` downstream: `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448`
- `window_016_segment_from_first_break` removed: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`
- `window_016_drop_all_high_risk_targets` downstream: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`, `cap-1417`, `cap-1448`
- `window_016_drop_all_high_risk_targets` removed: `cap-1396`, `cap-1413`, `cap-1429`, `cap-1437`, `cap-1441`

## Inputs

- `dataset_dir`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02`
- `official_window_plan`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_k_windows.json`
- `dart_quarantine_window_plan`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_k_windows_continuity_quarantine.json`
- `true_rerun_attribution`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_continuity_quarantine_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_true_rerun_attribution.json`
