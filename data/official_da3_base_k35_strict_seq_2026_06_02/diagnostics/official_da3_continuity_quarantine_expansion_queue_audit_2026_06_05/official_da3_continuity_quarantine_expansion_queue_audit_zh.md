# DA3 continuity quarantine expansion queue audit

日期：2026-06-05

## 结论

- status: `expansion_queue_and_manifest_batch_ready_true_reruns_needed`
- goal complete: `False`
- product ready: `False`

The Dart quarantine plan has enough information to rank risky source windows for the next true CoreML rerun batch. The queue keeps official DA3 replication separate from the mobile continuity adaptation candidate.

This ranking is not a geometry pass/fail result. It only chooses the next windows to rerun because full thickness attribution still requires actual CoreML outputs and downstream audits.

Run the same current DA3BASE_476x742_N35_pose CoreML path on the prepared research capture manifests, then compare official-save thickness against the prefix/segment/drop-high-risk variants.

## 大白话

- 这不是新算法结论，只是下一批真重跑的排队表：先挑官方 downstream 内 continuity 风险最大、且变体仍有足够真帧的 window。
- window_016 已经有 true rerun 证据，所以它在队列里保留为 baseline，不再作为第一优先级重复跑。
- 1. window_019: high-risk=9, max_dt=15.43s, max_trans=0.394m, drop_real=8, recommendation=lower_priority_short_segment
- 2. window_006: high-risk=6, max_dt=6.17s, max_trans=0.394m, drop_real=11, recommendation=next_true_rerun_candidate
- 3. window_021: high-risk=5, max_dt=4.03s, max_trans=0.714m, drop_real=12, recommendation=next_true_rerun_candidate
- 4. window_004: high-risk=6, max_dt=3.50s, max_trans=0.303m, drop_real=11, recommendation=next_true_rerun_candidate
- 5. window_007: high-risk=4, max_dt=12.30s, max_trans=0.458m, drop_real=13, recommendation=next_true_rerun_candidate
- 建议下一批先跑：`window_006`, `window_021`, `window_004`, `window_007`。这些 window 的风险足够高，同时 drop-high-risk 变体仍保留至少 10 个真帧。
- 下一步应生成这些 candidate 的研究 capture manifest，再跑同一条 DA3BASE_476x742_N35_pose CoreML + official postprocess 厚度审计。

## Top Candidates

| rank | source window | score | recommendation | high-risk frames | max dt/s | max trans/m | min quality | drop real | drop residual risk |
|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `window_019` | 125.998 | `lower_priority_short_segment` | 9 | 15.434 | 0.394 | 0.405 | 8 | 3 |
| 2 | `window_006` | 76.657 | `next_true_rerun_candidate` | 6 | 6.167 | 0.394 | 0.469 | 11 | 5 |
| 3 | `window_021` | 75.599 | `next_true_rerun_candidate` | 5 | 4.034 | 0.714 | 0.880 | 12 | 2 |
| 4 | `window_004` | 69.116 | `next_true_rerun_candidate` | 6 | 3.500 | 0.303 | 0.456 | 11 | 2 |
| 5 | `window_007` | 68.645 | `next_true_rerun_candidate` | 4 | 12.301 | 0.458 | 0.583 | 13 | 3 |
| 6 | `window_017` | 64.229 | `queue_candidate` | 5 | 5.000 | 0.371 | 0.459 | 12 | 3 |
| 7 | `window_023` | 61.068 | `queue_candidate` | 5 | 5.400 | 0.310 | 0.560 | 18 | 4 |
| 8 | `window_005` | 57.530 | `lower_priority_short_segment` | 5 | 1.667 | 0.240 | 0.374 | 12 | 2 |

## Recommended True-Rerun Batch

| source window | rank | score | high-risk frames | drop real | reason |
|---|---:|---:|---:|---:|---|
| `window_006` | 2 | 76.657 | 6 | 11 | manifest ready: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_continuity_quarantine_window006_2026_06_05` |
| `window_021` | 3 | 75.599 | 5 | 12 | manifest ready: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_continuity_quarantine_window021_2026_06_05` |
| `window_004` | 4 | 69.116 | 6 | 11 | manifest ready: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_continuity_quarantine_window004_2026_06_05` |
| `window_007` | 5 | 68.645 | 4 | 13 | manifest ready: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_continuity_quarantine_window007_2026_06_05` |

## Variant Summary

| source window | prefix real/risk | segment real/risk | drop real/risk | first break | high-risk IDs |
|---|---:|---:|---:|---|---|
| `window_019` | 1/0 | 16/8 | 8/3 | `cap-1659` | `cap-1659`, `cap-1673`, `cap-1671`, `cap-1677`, `cap-1681`, `cap-1679`, `cap-1774`, `cap-1780`, `cap-1801` |
| `window_006` | 1/0 | 16/5 | 11/5 | `cap-487` | `cap-487`, `cap-529`, `cap-536`, `cap-567`, `cap-583`, `cap-591` |
| `window_021` | 4/0 | 13/4 | 12/2 | `cap-1897` | `cap-1897`, `cap-1921`, `cap-1940`, `cap-1949`, `cap-1959` |
| `window_004` | 2/0 | 15/5 | 11/2 | `cap-333` | `cap-333`, `cap-339`, `cap-358`, `cap-382`, `cap-393`, `cap-395` |
| `window_007` | 1/0 | 16/3 | 13/3 | `cap-630` | `cap-630`, `cap-712`, `cap-725`, `cap-758` |
| `window_017` | 4/0 | 13/4 | 12/3 | `cap-1488` | `cap-1488`, `cap-1494`, `cap-1514`, `cap-1523`, `cap-1549` |
| `window_023` | 6/0 | 17/4 | 18/4 | `cap-2099` | `cap-2099`, `cap-2135`, `cap-2159`, `cap-2177`, `cap-2190` |
| `window_005` | 2/0 | 15/4 | 12/2 | `cap-411` | `cap-411`, `cap-413`, `cap-428`, `cap-434`, `cap-436` |
| `window_016` | 10/0 | 7/4 | 12/2 | `cap-1396` | `cap-1396`, `cap-1413`, `cap-1429`, `cap-1437`, `cap-1441` |
| `window_002` | 6/0 | 11/2 | 14/1 | `cap-148` | `cap-148`, `cap-167`, `cap-190` |
| `window_012` | 8/0 | 9/2 | 14/2 | `cap-1101` | `cap-1101`, `cap-1121`, `cap-1139` |
| `window_018` | 3/0 | 14/2 | 14/2 | `cap-1567` | `cap-1567`, `cap-1597`, `cap-1620` |
| `window_008` | 12/0 | 5/1 | 15/1 | `cap-815` | `cap-815`, `cap-829` |
| `window_014` | 1/0 | 16/1 | 15/0 | `cap-1232` | `cap-1232`, `cap-1245` |
| `window_001` | 2/0 | 15/1 | 15/2 | `cap-74` | `cap-74`, `cap-96` |
| `window_003` | 8/0 | 9/0 | 16/1 | `cap-257` | `cap-257` |
| `window_015` | 2/0 | 15/0 | 16/1 | `cap-1302` | `cap-1302` |
| `window_013` | 10/0 | 7/0 | 16/1 | `cap-1207` | `cap-1207` |
| `window_020` | 3/0 | 14/0 | 16/1 | `cap-1837` | `cap-1837` |
| `window_000` | 4/0 | 13/0 | 16/1 | `cap-21` | `cap-21` |
| `window_011` | 8/0 | 9/0 | 16/1 | `cap-1016` | `cap-1016` |

## Inputs

- `dataset_dir`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02`
- `official_window_plan`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_k_windows.json`
- `dart_quarantine_window_plan`: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/da3_k_windows_continuity_quarantine.json`
