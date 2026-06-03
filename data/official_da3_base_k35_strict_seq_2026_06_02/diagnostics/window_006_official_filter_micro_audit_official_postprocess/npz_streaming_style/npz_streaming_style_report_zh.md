# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_006_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.513 | 2718 | 3.4826 | 1.5829 | - | 0.7716 | - | 1.0079 |
| slots_00_01 | 0.574 | 6085 | 3.8628 | 1.4505 | 0.916x | 0.7447 | 0.965x | 0.9850 |
| slots_00_02 | 0.601 | 9556 | 3.9888 | 1.4368 | 0.991x | 0.7260 | 0.975x | 0.9503 |
| first_05 | 0.602 | 15949 | 3.8920 | 1.4850 | 1.034x | 0.7467 | 1.028x | 0.8855 |
| first_10 | 0.580 | 30746 | 3.4886 | 1.5871 | 1.069x | 0.8497 | 1.138x | 0.9694 |
| first_35 | 0.552 | 102264 | 2.4079 | 1.7952 | 1.131x | 0.7947 | 0.935x | 0.6420 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
