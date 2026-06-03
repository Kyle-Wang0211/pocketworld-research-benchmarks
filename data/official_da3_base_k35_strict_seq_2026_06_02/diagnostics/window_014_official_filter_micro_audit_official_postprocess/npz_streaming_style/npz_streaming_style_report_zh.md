# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_014_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.584 | 3095 | 3.0443 | 1.4256 | - | 0.8593 | - | 1.1471 |
| slots_00_01 | 0.577 | 6115 | 3.0820 | 1.4092 | 0.988x | 0.7718 | 0.898x | 0.8695 |
| slots_00_02 | 0.565 | 8975 | 3.0430 | 1.4313 | 1.016x | 0.8382 | 1.086x | 0.8952 |
| first_05 | 0.553 | 14661 | 2.9281 | 1.4550 | 1.017x | 0.8490 | 1.013x | 0.9343 |
| first_10 | 0.553 | 29295 | 2.8745 | 1.4304 | 0.983x | 0.7882 | 0.928x | 0.9316 |
| first_35 | 0.516 | 95742 | 2.3302 | 1.6021 | 1.120x | 0.9405 | 1.193x | 1.0579 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
