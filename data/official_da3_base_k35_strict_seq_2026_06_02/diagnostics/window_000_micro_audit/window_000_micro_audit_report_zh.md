# Window 000 Micro Audit

## 输出

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_micro_audit/window_000_micro_audit_contact_sheet.png`
- report JSON: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_micro_audit/window_000_micro_audit_report.json`

## 累积组指标

| group | slots | frames | points | bbox diag | bbox growth | PCA minor | minor growth | minor/major | camera diag |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0 | cap-1 | 3012 | 1.3398 | - | 0.4901 | - | 0.4590 | 0.0000 |
| slots_00_01 | 0,1 | cap-1,cap-3 | 6011 | 1.3505 | 1.008x | 0.5017 | 1.024x | 0.4694 | 0.0090 |
| slots_00_02 | 0,1,2 | cap-1,cap-3,cap-5 | 9031 | 1.3564 | 1.004x | 0.5008 | 0.998x | 0.4634 | 0.0258 |
| first_05 | 0,1,2,3,4 | cap-1,cap-3,cap-5,cap-7,cap-21 | 14960 | 1.3723 | 1.012x | 0.5068 | 1.012x | 0.4639 | 0.1076 |
| first_10 | 0,1,2,3,4,5,6,7,8,9 | cap-1,cap-3,cap-5,cap-7,cap-21,cap-23,cap-29,cap-31,cap-33,cap-35 | 30273 | 1.3754 | 1.002x | 0.5110 | 1.008x | 0.4755 | 0.1699 |
| first_35 | 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34 | cap-1,cap-3,cap-5,cap-7,cap-21,cap-23,cap-29,cap-31,cap-33,cap-35,cap-37,cap-39,cap-42,cap-44,cap-48,cap-50,cap-52,cap-54,cap-56,cap-74,cap-78,cap-80,cap-96,cap-103,cap-105,cap-107,cap-109,cap-114,cap-116,cap-118,cap-122,cap-124,cap-126,cap-128,cap-131 | 105145 | 1.4006 | 1.018x | 0.5588 | 1.094x | 0.5247 | 0.6625 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`

注：阈值只是 triage heuristic，最终判断需要结合 PNG 肉眼检查和 per-slot 指标。
