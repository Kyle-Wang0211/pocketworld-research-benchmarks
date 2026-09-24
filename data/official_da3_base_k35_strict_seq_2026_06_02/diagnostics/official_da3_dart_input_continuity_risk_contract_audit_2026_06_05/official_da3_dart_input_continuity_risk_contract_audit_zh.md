# Official DA3 Dart input continuity-risk contract audit

- 日期：2026-06-05
- 状态：`dart_official_window_plan_flags_image_only_input_continuity_risk_without_changing_official_frames`
- 结论：Dart now labels window_016 as a DA3 image-only input continuity-risk window, with cap-1396 as the first saved high-risk target, while preserving the official timestamp streaming frame set.
- 边界：This is not a downstream point-cloud cleanup and it is not a replacement for official DA3 parity. It is metadata that makes the upstream input-risk visible before a product/research split policy is applied.

## 大白话

- window_016 的官方 downstream 帧集没有被改；Dart 只是新增了输入连续性风险字段。
- 第一个 official-save high-risk target 是 cap-1396；它在官方保存帧里，不是 withheld overlap 尾巴里才出现的帧。
- 第一处断点是 cap-1369 -> cap-1396：dt=4.467s，translation=0.410m，elevation=0.387rad。
- official-save high-risk step count=5，full chunk high-risk step count=11。
- 结论：厚层的第一嫌疑不是点云导出，而是官方 image-only 输入窗口里混入几何连续性断点后，上游 pose/depth 一致性开始漂。

## 核心指标

- `official_window_count`: `24`
- `quarantine_window_count`: `63`
- `risky_source_window_count`: `21`
- `audited_window_id`: `window_016`
- `official_save_frame_count`: `17`
- `official_save_high_risk_step_count`: `5`
- `chunk_high_risk_step_count`: `11`
- `first_official_save_high_risk_frame_id`: `cap-1396`

## Checks

| check | status | evidence |
| --- | --- | --- |
| `official_plan_schema_unchanged` | `pass` | da3_k_windows.json is still the strict official timestamp sliding-window plan. |
| `risk_schema_present` | `pass` | Official windows expose a DA3 image-only input continuity-risk contract. |
| `risk_warns_on_window016` | `pass` | window_016 carries warning status for saved-frame continuity risk. |
| `official_frame_set_preserved` | `pass` | The risk metadata does not alter officialSaveFrameIDs/downstreamFrameIDs. |
| `first_saved_risk_is_expected_frame` | `pass` | The first saved high-risk target is cap-1396. |
| `expected_frame_is_official_saved_core_frame` | `pass` | cap-1396 is an official saved frame at local index 10, not only a withheld tail frame. |
| `continuity_audit_exposes_break_metrics` | `pass` | The first high-risk step exceeds timestamp, translation, and elevation thresholds. |
| `quarantine_plan_remains_separate` | `pass` | Continuity quarantine remains a separate research/product-candidate file. |
