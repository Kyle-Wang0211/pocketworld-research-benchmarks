# DA3 continuity quarantine true-rerun attribution

日期：2026-06-05
source window：`window_006`

## 结论

- status: `true_rerun_continuity_quarantine_inconclusive_for_source`
- goal complete: `False`
- source is thick: `True`

window_006 remains inconclusive: the source window is thick or borderline, but the true rerun did not show a clear quarantine reduction.

This is still the current pose-conditioned DA3BASE_476x742_N35 CoreML product path. It tests a mobile continuity/windowing adaptation candidate, not official image-only parity.

Continue the same true-rerun attribution on the remaining prepared candidates, then decide whether continuity quarantine should be a hard product gate, a warning gate, or only a capture-quality signal.

## 大白话

- window_006 原始 official-save 17 帧：npz minor/k10=1.102, bbox/k10=1.045。
- prefix 未生成有效审计：通常是帧数太少或官方 Umeyama 对齐退化。
- segment 16 帧：npz minor/orig=0.917, bbox/orig=0.959。
- drop-high-risk 11 帧：npz minor/orig=0.892, bbox/orig=0.919。
- 这个样本继续支持 quarantine 方向，但还要和其它候选一起看。

## Variants

| variant | frames | pose scale | npz minor | npz minor/k10 | npz minor/orig | npz bbox/orig | glb minor/orig | pose diag/orig |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `official_save_source` | 17 | 0.877 | 0.915 | 1.102 | 1.000 | 1.000 | 1.000 | 1.000 |
| `prefix_before_first_break` | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `segment_from_first_break` | 16 | 1.059 | 0.839 | 1.030 | 0.917 | 0.959 | 1.018 | 0.740 |
| `drop_all_high_risk_targets` | 11 | 0.940 | 0.817 | 0.991 | 0.892 | 0.919 | 0.971 | 0.996 |

## Frame Sets

- `official_save_source`: `cap-458`, `cap-487`, `cap-492`, `cap-529`, `cap-536`, `cap-538`, `cap-567`, `cap-570`, `cap-583`, `cap-581`, `cap-591`, `cap-596`, `cap-601`, `cap-606`, `cap-608`, `cap-612`, `cap-619`
- `prefix_before_first_break`: 
- `segment_from_first_break`: `cap-487`, `cap-492`, `cap-529`, `cap-536`, `cap-538`, `cap-567`, `cap-570`, `cap-583`, `cap-581`, `cap-591`, `cap-596`, `cap-601`, `cap-606`, `cap-608`, `cap-612`, `cap-619`
- `drop_all_high_risk_targets`: `cap-458`, `cap-492`, `cap-538`, `cap-570`, `cap-581`, `cap-596`, `cap-601`, `cap-606`, `cap-608`, `cap-612`, `cap-619`
