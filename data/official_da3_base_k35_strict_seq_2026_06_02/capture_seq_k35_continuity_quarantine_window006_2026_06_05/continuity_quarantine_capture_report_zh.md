# DA3 continuity quarantine capture manifest

日期：2026-06-05

## 说明

这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。

## High-Risk Frames

`cap-487`, `cap-529`, `cap-536`, `cap-567`, `cap-583`, `cap-591`

## Variants

| window | frames | removed |
|---|---:|---|
| `window_006_prefix_before_first_break` | 1 | `cap-487`, `cap-492`, `cap-529`, `cap-536`, `cap-538`, `cap-567`, `cap-570`, `cap-583`, `cap-581`, `cap-591`, `cap-596`, `cap-601`, `cap-606`, `cap-608`, `cap-612`, `cap-619` |
| `window_006_segment_from_first_break` | 16 | `cap-458` |
| `window_006_drop_all_high_risk_targets` | 11 | `cap-487`, `cap-529`, `cap-536`, `cap-567`, `cap-583`, `cap-591` |
