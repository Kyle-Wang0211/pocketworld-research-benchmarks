# SelaVPR++ 0.80 Loop Diagnostic

这是 diagnostic-only, 不是生产阈值修改。官方默认式 0.85 仍然是 0 loop candidates。

## 结果

- raw loop pairs: 12
- official loop windows after process_loop_list: 5
- dense Sim3 loop constraints: 5
- optimizer status: completed
- pre scale mean/std: 1.015046 / 0.049808
- post scale mean/std: 1.011119 / 0.050996

## Loop Window 几何检查

| loop | chunks | gap | a_p90 | b_p90 | scale | 判断 |
|---|---:|---:|---:|---:|---:|---|
| loop_window_000 | 17->6 | 11 | 0.170085 | 0.108454 | 0.881570 | geometry plausible diagnostic |
| loop_window_001 | 19->4 | 15 | 0.158118 | 0.098355 | 0.963947 | geometry plausible diagnostic |
| loop_window_002 | 2->1 | 1 | 0.098608 | 0.113136 | 0.988251 | near-neighbor duplicate |
| loop_window_003 | 20->6 | 14 | 0.063198 | 0.155304 | 0.935300 | geometry plausible diagnostic |
| loop_window_004 | 16->6 | 10 | 0.231772 | 0.367188 | 0.862199 | risky high residual |

## 初步解释

- 0.80 可以产生候选, 但不等于应该进入生产。
- `loop_window_002` 是 chunk gap=1 的近邻, 更像重复邻接约束, 不是全局回环。
- `loop_window_004` 的 b_p90=0.367188, 残差偏高, 作为约束有风险。
- optimizer 能跑完, 但 post scale std 从 0.049808 到 0.050996, 并没有给出“loop 明显压薄 K35 厚层”的证据。
- 因此当前更合理的结论是: loop 可以继续诊断, 但 K35 厚层不能归因于缺 loop。

## 输出

- raw pair contact sheet: `threshold080_raw_pair_contact_sheet.png`
- loop window contact sheet: `threshold080_loop_window_contact_sheet.png`
