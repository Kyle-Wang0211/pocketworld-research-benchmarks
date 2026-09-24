# DA3 continuity quarantine capture manifest

日期：2026-06-05

## 说明

这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。

## High-Risk Frames

`cap-1897`, `cap-1921`, `cap-1940`, `cap-1949`, `cap-1959`

## Variants

| window | frames | removed |
|---|---:|---|
| `window_021_prefix_before_first_break` | 4 | `cap-1897`, `cap-1921`, `cap-1923`, `cap-1925`, `cap-1930`, `cap-1927`, `cap-1932`, `cap-1940`, `cap-1938`, `cap-1942`, `cap-1944`, `cap-1949`, `cap-1959` |
| `window_021_segment_from_first_break` | 13 | `cap-1877`, `cap-1881`, `cap-1883`, `cap-1885` |
| `window_021_drop_all_high_risk_targets` | 12 | `cap-1897`, `cap-1921`, `cap-1940`, `cap-1949`, `cap-1959` |
