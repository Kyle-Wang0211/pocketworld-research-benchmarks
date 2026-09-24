# DA3 continuity quarantine true-rerun attribution

日期：2026-06-05
source window：`window_007`

## 结论

- status: `source_window_not_thick_continuity_quarantine_negative_control`
- goal complete: `False`
- source is thick: `False`

window_007 is a negative/control sample: it has continuity risk, but the source official-save window is not thick by the current npz/glb growth metrics. Continuity risk alone is not enough to prove single-window thickening.

This is still the current pose-conditioned DA3BASE_476x742_N35 CoreML product path. It tests a mobile continuity/windowing adaptation candidate, not official image-only parity.

Continue the same true-rerun attribution on the remaining prepared candidates, then decide whether continuity quarantine should be a hard product gate, a warning gate, or only a capture-quality signal.

## 大白话

- window_007 原始 official-save 17 帧：npz minor/k10=0.969, bbox/k10=0.987。
- prefix 未生成有效审计：通常是帧数太少或官方 Umeyama 对齐退化。
- segment 16 帧：npz minor/orig=0.912, bbox/orig=0.949。
- drop-high-risk 13 帧：npz minor/orig=0.950, bbox/orig=1.062。
- 这不是 window_016 那种阳性减薄样本；它更像 negative/control，提醒我们 continuity gate 需要结合实际几何厚度，不能只看时间/位移/质量阈值。

## Variants

| variant | frames | pose scale | npz minor | npz minor/k10 | npz minor/orig | npz bbox/orig | glb minor/orig | pose diag/orig |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `official_save_source` | 17 | 0.731 | 1.018 | 0.969 | 1.000 | 1.000 | 1.000 | 1.000 |
| `prefix_before_first_break` | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `segment_from_first_break` | 16 | 0.730 | 0.929 | 1.006 | 0.912 | 0.949 | 1.260 | 1.000 |
| `drop_all_high_risk_targets` | 13 | 0.683 | 0.967 | 1.021 | 0.950 | 1.062 | 1.005 | 0.925 |

## Frame Sets

- `official_save_source`: `cap-621`, `cap-630`, `cap-635`, `cap-639`, `cap-712`, `cap-714`, `cap-720`, `cap-718`, `cap-725`, `cap-731`, `cap-733`, `cap-735`, `cap-737`, `cap-739`, `cap-741`, `cap-743`, `cap-758`
- `prefix_before_first_break`: 
- `segment_from_first_break`: `cap-630`, `cap-635`, `cap-639`, `cap-712`, `cap-714`, `cap-720`, `cap-718`, `cap-725`, `cap-731`, `cap-733`, `cap-735`, `cap-737`, `cap-739`, `cap-741`, `cap-743`, `cap-758`
- `drop_all_high_risk_targets`: `cap-621`, `cap-635`, `cap-639`, `cap-714`, `cap-720`, `cap-718`, `cap-731`, `cap-733`, `cap-735`, `cap-737`, `cap-739`, `cap-741`, `cap-743`
