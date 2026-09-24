# DA3 continuity quarantine true-rerun attribution

日期：2026-06-05
source window：`window_021`

## 结论

- status: `source_window_not_thick_continuity_quarantine_negative_control`
- goal complete: `False`
- source is thick: `False`

window_021 is a negative/control sample: it has continuity risk, but the source official-save window is not thick by the current npz/glb growth metrics. Continuity risk alone is not enough to prove single-window thickening.

This is still the current pose-conditioned DA3BASE_476x742_N35 CoreML product path. It tests a mobile continuity/windowing adaptation candidate, not official image-only parity.

Continue the same true-rerun attribution on the remaining prepared candidates, then decide whether continuity quarantine should be a hard product gate, a warning gate, or only a capture-quality signal.

## 大白话

- window_021 原始 official-save 17 帧：npz minor/k10=0.984, bbox/k10=1.021。
- prefix 4 帧：npz minor/orig=0.693, bbox/orig=0.669。
- segment 13 帧：npz minor/orig=1.045, bbox/orig=0.988。
- drop-high-risk 12 帧：npz minor/orig=1.091, bbox/orig=1.026。
- 这不是 window_016 那种阳性减薄样本；它更像 negative/control，提醒我们 continuity gate 需要结合实际几何厚度，不能只看时间/位移/质量阈值。

## Variants

| variant | frames | pose scale | npz minor | npz minor/k10 | npz minor/orig | npz bbox/orig | glb minor/orig | pose diag/orig |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `official_save_source` | 17 | 0.647 | 1.192 | 0.984 | 1.000 | 1.000 | 1.000 | 1.000 |
| `prefix_before_first_break` | 4 | 1.091 | 0.826 | 1.000 | 0.693 | 0.669 | 0.633 | 0.045 |
| `segment_from_first_break` | 13 | 0.683 | 1.246 | 0.979 | 1.045 | 0.988 | 0.922 | 0.820 |
| `drop_all_high_risk_targets` | 12 | 0.641 | 1.301 | 0.978 | 1.091 | 1.026 | 0.990 | 0.954 |

## Frame Sets

- `official_save_source`: `cap-1877`, `cap-1881`, `cap-1883`, `cap-1885`, `cap-1897`, `cap-1921`, `cap-1923`, `cap-1925`, `cap-1930`, `cap-1927`, `cap-1932`, `cap-1940`, `cap-1938`, `cap-1942`, `cap-1944`, `cap-1949`, `cap-1959`
- `prefix_before_first_break`: `cap-1877`, `cap-1881`, `cap-1883`, `cap-1885`
- `segment_from_first_break`: `cap-1897`, `cap-1921`, `cap-1923`, `cap-1925`, `cap-1930`, `cap-1927`, `cap-1932`, `cap-1940`, `cap-1938`, `cap-1942`, `cap-1944`, `cap-1949`, `cap-1959`
- `drop_all_high_risk_targets`: `cap-1877`, `cap-1881`, `cap-1883`, `cap-1885`, `cap-1923`, `cap-1925`, `cap-1930`, `cap-1927`, `cap-1932`, `cap-1938`, `cap-1942`, `cap-1944`
