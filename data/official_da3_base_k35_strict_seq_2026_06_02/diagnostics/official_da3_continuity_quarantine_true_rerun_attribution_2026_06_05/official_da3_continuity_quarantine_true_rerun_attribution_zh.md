# DA3 continuity quarantine true-rerun attribution

日期：2026-06-05

## 结论

- status: `true_rerun_continuity_quarantine_reduces_window016_thickness`
- goal complete: `False`

A true CoreML N35 rerun on continuity-quarantined variants reduces window_016 thickness substantially. The strongest signal is not deleting cap-1396 points downstream; it is preventing a discontinuous capture segment from sharing one DA3 K35 inference context.

This is still the current pose-conditioned product CoreML path, not full image-only DA3 parity. The official-replication branch remains unchanged; quarantine is a mobile capture/windowing adaptation candidate.

Implement a Dart-side research window split/quarantine simulator that recomputes continuity after removals, then re-run on more windows/captures before turning it into a product gate.

## 大白话

- 原始 window_016 official-save 17 帧仍厚：npz minor=0.969, bbox=1.997, 内部 minor/k10=1.429。
- 断点前 prefix 10 帧真重跑更薄：npz minor=0.753，约为原始的 0.778。
- 断点后 segment 7 帧单独跑：npz minor=0.850，bbox=2.269；它说明后半段不是简单无害，但不应和前半段共享同一个 K35 context。
- 去掉所有当前 high-risk targets 的 12 帧真重跑：npz minor=0.682，约为原始的 0.704；内部 minor/k10 只有 1.051。
- 这支持 continuity quarantine/window split，而不是 downstream 点云去重；官方复刻分支仍然保留，移动端适配分支再加这个 gate。

## Variants

| variant | frames | npz minor | npz minor/orig | npz bbox | npz bbox/orig | glb minor/orig | within npz minor/k10 | pose diag/orig |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `official_save_window016` | 17 | 0.969 | 1.000 | 1.997 | 1.000 | 1.000 | 1.429 | 1.000 |
| `prefix_before_first_break` | 10 | 0.753 | 0.778 | 1.489 | 0.745 | 0.778 | 1.000 | 0.255 |
| `segment_from_first_break` | 7 | 0.850 | 0.877 | 2.269 | 1.136 | 1.005 | 1.000 | 0.469 |
| `drop_all_high_risk_targets` | 12 | 0.682 | 0.704 | 1.512 | 0.757 | 0.874 | 1.051 | 0.955 |

## Frame Sets

- `official_save_window016`: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`, `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448`
- `prefix_before_first_break`: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`
- `segment_from_first_break`: `cap-1396`, `cap-1413`, `cap-1417`, `cap-1429`, `cap-1437`, `cap-1441`, `cap-1448`
- `drop_all_high_risk_targets`: `cap-1346`, `cap-1354`, `cap-1356`, `cap-1358`, `cap-1360`, `cap-1361`, `cap-1363`, `cap-1365`, `cap-1367`, `cap-1369`, `cap-1417`, `cap-1448`
