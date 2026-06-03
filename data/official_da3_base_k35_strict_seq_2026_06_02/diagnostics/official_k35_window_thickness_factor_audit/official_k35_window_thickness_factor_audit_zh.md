# Official K35 Window Thickness Factor Audit

这是 read-only diagnostic。只解析已有 official-filter micro audit JSON，不重新生成点云，不改 CoreML 输出，不改阈值，不做 graph patch/loop/mesh。

## 核心表格

| window | style | poseScale | bbox growth | minor growth | pose span growth | conf thr ratio | valid frac delta | depth p95 ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| window_000 | glb_style | 0.47968 | 1.08969 | 1.16898 | 3.81796 | 0.812786 | 0.000145773 | 0.978885 |
| window_000 | npz_streaming_style | 0.47968 | 1.03421 | 1.09017 | 3.81796 | 0.881593 | -0.0199909 | 0.978885 |
| window_006 | glb_style | 0.877487 | 1.20912 | 0.974241 | 1.64006 | 0.625369 | 4.55843e-05 | 1.2611 |
| window_006 | npz_streaming_style | 0.877487 | 1.13109 | 0.935291 | 1.64006 | 0.690233 | -0.0288446 | 1.2611 |
| window_014 | glb_style | 0.734565 | 1.12897 | 1.17571 | 3.20429 | 0.764496 | 7.09853e-05 | 1.0827 |
| window_014 | npz_streaming_style | 0.734565 | 1.12 | 1.19323 | 3.20429 | 0.810644 | -0.0366162 | 1.0827 |
| window_015 | glb_style | 0.69555 | 0.962659 | 1.01929 | 2.14673 | 1.00724 | -2.46325e-05 | 0.985019 |
| window_015 | npz_streaming_style | 0.69555 | 0.994567 | 1.0749 | 2.14673 | 1.01073 | 0.0217015 | 0.985019 |
| window_016 | glb_style | 0.723084 | 1.2851 | 1.10567 | 4.5954 | 1.09551 | -8.08949e-06 | 1.07358 |
| window_016 | npz_streaming_style | 0.723084 | 1.25822 | 1.46548 | 4.5954 | 0.794107 | -0.00821803 | 1.07358 |

## 最大增长

- largest bbox growth: `{"window_id": "window_016", "style": "glb_style", "pose_scale": 0.7230839040376699, "bbox_growth": 1.2851006596234356, "minor_growth": 1.105667583402953, "pose_span_growth": 4.595401355328742, "conf_threshold_ratio": 1.095505617977528, "valid_fraction_delta": -8.089489164864183e-06, "depth_p95_ratio": 1.0735751406236393}`
- largest PCA minor growth: `{"window_id": "window_016", "style": "npz_streaming_style", "pose_scale": 0.7230839040376699, "bbox_growth": 1.2582178072922119, "minor_growth": 1.4654765399923089, "pose_span_growth": 4.595401355328742, "conf_threshold_ratio": 0.7941074149059311, "valid_fraction_delta": -0.00821803114776909, "depth_p95_ratio": 1.0735751406236393}`

## 关键反证

- thickened despite tighter threshold: 1 rows
- thickened without valid fraction increase: 7 rows
- first35 not strictly worse than first10: 4 rows

## Correlation Clues

- `note`: Tiny sample diagnostic only; correlations are clues, not proof.
- `minor_growth_vs_pose_span_growth`: 0.753116
- `minor_growth_vs_conf_threshold_ratio`: 0.0296614
- `minor_growth_vs_valid_fraction_delta`: -0.0240654
- `minor_growth_vs_depth_p95_ratio`: -0.345558
- `bbox_growth_vs_pose_span_growth`: 0.451958

## 初步解释

- No production algorithm change is implied; this only ranks existing official micro-audit evidence.
- Loop is not a proven fix here because first35 thickness appears inside a single K35 window before cross-window loop constraints can act.
- Confidence looseness is not a sufficient explanation: some rows thicken even when first35 uses a tighter confidence threshold than first10.
- Valid fraction is not a sufficient explanation: some rows thicken without retaining a larger fraction of pixels.
- Pose span expansion is the strongest current suspect: first35 expands camera-center span substantially relative to first10 in every audited K35 row.
- Correlation values are small-sample clues only; use them to choose the next official consistency check, not as final proof.
- The next official-consistency check should compare per-slot or sub-span surfaces within the same window, especially pose/depth/scale consistency across later slots.
