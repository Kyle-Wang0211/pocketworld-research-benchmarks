# DA3 continuity quarantine true-rerun attribution

日期：2026-06-05
source window：`window_004`

## 结论

- status: `source_window_not_thick_continuity_quarantine_negative_control`
- goal complete: `False`
- source is thick: `False`

window_004 is a negative/control sample: it has continuity risk, but the source official-save window is not thick by the current npz/glb growth metrics. Continuity risk alone is not enough to prove single-window thickening.

This is still the current pose-conditioned DA3BASE_476x742_N35 CoreML product path. It tests a mobile continuity/windowing adaptation candidate, not official image-only parity.

Continue the same true-rerun attribution on the remaining prepared candidates, then decide whether continuity quarantine should be a hard product gate, a warning gate, or only a capture-quality signal.

## 大白话

- window_004 原始 official-save 17 帧：npz minor/k10=0.999, bbox/k10=0.977。
- prefix 未生成有效审计：通常是帧数太少或官方 Umeyama 对齐退化。
- segment 15 帧：npz minor/orig=1.180, bbox/orig=0.997。
- drop-high-risk 11 帧：npz minor/orig=1.174, bbox/orig=1.068。
- 这不是 window_016 那种阳性减薄样本；它更像 negative/control，提醒我们 continuity gate 需要结合实际几何厚度，不能只看时间/位移/质量阈值。

## Variants

| variant | frames | pose scale | npz minor | npz minor/k10 | npz minor/orig | npz bbox/orig | glb minor/orig | pose diag/orig |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `official_save_source` | 17 | 0.699 | 0.735 | 0.999 | 1.000 | 1.000 | 1.000 | 1.000 |
| `prefix_before_first_break` | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `segment_from_first_break` | 15 | 0.677 | 0.867 | 0.968 | 1.180 | 0.997 | 1.074 | 0.660 |
| `drop_all_high_risk_targets` | 11 | 0.703 | 0.862 | 0.996 | 1.174 | 1.068 | 1.117 | 1.000 |

## Frame Sets

- `official_save_source`: `cap-310`, `cap-312`, `cap-333`, `cap-335`, `cap-337`, `cap-339`, `cap-347`, `cap-358`, `cap-360`, `cap-371`, `cap-373`, `cap-380`, `cap-382`, `cap-387`, `cap-389`, `cap-393`, `cap-395`
- `prefix_before_first_break`: 
- `segment_from_first_break`: `cap-333`, `cap-335`, `cap-337`, `cap-339`, `cap-347`, `cap-358`, `cap-360`, `cap-371`, `cap-373`, `cap-380`, `cap-382`, `cap-387`, `cap-389`, `cap-393`, `cap-395`
- `drop_all_high_risk_targets`: `cap-310`, `cap-312`, `cap-335`, `cap-337`, `cap-347`, `cap-360`, `cap-371`, `cap-373`, `cap-380`, `cap-387`, `cap-389`
