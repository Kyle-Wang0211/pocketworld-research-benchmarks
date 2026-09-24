# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_016_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.505 | 2673 | 4.3355 | 1.3160 | - | 0.6582 | - | 0.7667 |
| slots_00_01 | 0.534 | 5663 | 4.5838 | 1.2737 | 0.968x | 0.5887 | 0.894x | 0.6816 |
| slots_00_02 | 0.543 | 8634 | 4.6593 | 1.2514 | 0.982x | 0.5667 | 0.963x | 0.6574 |
| first_05 | 0.530 | 14041 | 4.5736 | 1.2703 | 1.015x | 0.5895 | 1.040x | 0.6748 |
| first_10 | 0.523 | 27718 | 4.5930 | 1.2706 | 1.000x | 0.6193 | 1.051x | 0.7035 |
| first_35 | 0.515 | 95492 | 3.6474 | 1.5987 | 1.258x | 0.9076 | 1.465x | 0.9835 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `first_35`
