# DA3 continuity quarantine capture manifest

日期：2026-06-05

## 说明

这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。

## High-Risk Frames

`cap-1396`, `cap-1413`, `cap-1429`, `cap-1437`, `cap-1441`

## Variants

| window | frames | removed |
|---|---:|---|
| `window_016_prefix_before_first_break` | 10 | `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448` |
| `window_016_segment_from_first_break` | 7 | `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369` |
| `window_016_drop_all_high_risk_targets` | 12 | `cap-1396`, `cap-1413`, `cap-1429`, `cap-1437`, `cap-1441` |
