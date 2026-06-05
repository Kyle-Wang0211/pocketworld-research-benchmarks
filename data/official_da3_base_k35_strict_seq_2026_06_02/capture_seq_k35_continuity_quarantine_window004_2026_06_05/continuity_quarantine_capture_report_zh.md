# DA3 continuity quarantine capture manifest

日期：2026-06-05

## 说明

这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。

## High-Risk Frames

`cap-333`, `cap-339`, `cap-358`, `cap-382`, `cap-393`, `cap-395`

## Variants

| window | frames | removed |
|---|---:|---|
| `window_004_prefix_before_first_break` | 2 | `cap-333`, `cap-335`, `cap-337`, `cap-339`, `cap-347`, `cap-358`, `cap-360`, `cap-371`, `cap-373`, `cap-380`, `cap-382`, `cap-387`, `cap-389`, `cap-393`, `cap-395` |
| `window_004_segment_from_first_break` | 15 | `cap-310`, `cap-312` |
| `window_004_drop_all_high_risk_targets` | 11 | `cap-333`, `cap-339`, `cap-358`, `cap-382`, `cap-393`, `cap-395` |
