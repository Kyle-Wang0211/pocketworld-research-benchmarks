# DA3 continuity quarantine counterfactual audit

日期：2026-06-05

## 结论

- status: `counterfactual_quarantine_effect_weak_or_inconclusive`
- goal complete: `False`

Removing high-risk continuity targets from fixed outputs did not clearly reduce thickness. A true re-run may still be needed because DA3 predictions depend on full K-window context.

This audit removes frames only at point-generation time from fixed DA3 outputs. It proves a downstream inclusion effect, not the final result of re-running DA3 with a different K35 context.

If the counterfactual reduces thickness, run a true Dart-window simulation that splits or quarantines the high-risk capture segment, then re-run the current DA3BASE_476x742_N35 CoreML path on that altered window plan.

## 大白话

- 当前 official-save downstream 中 high-risk targets 是：cap-1396, cap-1413, cap-1429, cap-1437, cap-1441。
- 这个审计没有重跑 DA3，只是在现有预测结果上重新选择哪些帧参与官方风格点云生成。
- 只去掉第一个断点帧后，npz minor 相对 official-all 的比例是 1.052。
- 去掉所有 high-risk targets 后，npz minor 相对 official-all 的比例是 0.868。
- Removing high-risk continuity targets from fixed outputs did not clearly reduce thickness. A true re-run may still be needed because DA3 predictions depend on full K-window context.
- 如果这个信号强，下一步才值得做真正的 Dart window 分段/补帧重跑，而不是改官方复刻分支。

## High-Risk Steps

| from | to | dt | trans | az | el | kWeight | violations |
|---|---|---:|---:|---:|---:|---:|---|
| `cap-1369` | `cap-1396` | 4.467 | 0.410 | 0.283 | 0.387 | 0.687 | timestampDeltaSeconds, translationStepM, elevationDeltaRad |
| `cap-1396` | `cap-1413` | 2.834 | 0.171 | 0.034 | 0.195 | 0.846 | timestampDeltaSeconds |
| `cap-1417` | `cap-1429` | 2.100 | 0.093 | 0.004 | 0.109 | 0.616 | timestampDeltaSeconds |
| `cap-1429` | `cap-1437` | 1.633 | 0.295 | 0.358 | 0.156 | 0.531 | translationStepM, azimuthDeltaRad |
| `cap-1437` | `cap-1441` | 0.300 | 0.031 | 0.086 | 0.048 | 0.439 | toKWindowWeight |

## Variants

| variant | frames | removed | pose diag | npz minor | npz minor/all | npz bbox/all | glb minor/all |
|---|---:|---|---:|---:|---:|---:|---:|
| `official_save_all_17` | 17 | none | 1.166 | 0.954 | 1.000 | 1.000 | 1.000 |
| `drop_first_break_target` | 16 | `cap-1396` | 1.166 | 1.003 | 1.052 | 0.994 | 0.997 |
| `prefix_before_first_break` | 10 | `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448` | 0.297 | 0.678 | 0.711 | 0.709 | 0.861 |
| `segment_from_first_break` | 7 | `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369` | 0.547 | 0.961 | 1.008 | 1.174 | 1.033 |
| `drop_all_high_risk_targets` | 12 | `cap-1396`, `cap-1413`, `cap-1429`, `cap-1437`, `cap-1441` | 1.114 | 0.828 | 0.868 | 0.844 | 1.182 |
