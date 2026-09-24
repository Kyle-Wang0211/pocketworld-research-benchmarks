# DA3 continuity quarantine capture manifest

日期：2026-06-05

## 说明

这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。

## High-Risk Frames

`cap-630`, `cap-712`, `cap-725`, `cap-758`

## Variants

| window | frames | removed |
|---|---:|---|
| `window_007_prefix_before_first_break` | 1 | `cap-630`, `cap-635`, `cap-639`, `cap-712`, `cap-714`, `cap-720`, `cap-718`, `cap-725`, `cap-731`, `cap-733`, `cap-735`, `cap-737`, `cap-739`, `cap-741`, `cap-743`, `cap-758` |
| `window_007_segment_from_first_break` | 16 | `cap-621` |
| `window_007_drop_all_high_risk_targets` | 13 | `cap-630`, `cap-712`, `cap-725`, `cap-758` |
