# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_015_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.551 | 2920 | 2.9849 | 1.4822 | - | 0.8615 | - | 0.9183 |
| slots_00_01 | 0.530 | 5615 | 2.9660 | 1.5521 | 1.047x | 0.8754 | 1.016x | 1.1016 |
| slots_00_02 | 0.522 | 8293 | 2.8100 | 1.6203 | 1.044x | 0.8495 | 0.970x | 1.0266 |
| first_05 | 0.521 | 13812 | 2.7094 | 1.6659 | 1.028x | 0.8448 | 0.995x | 0.9629 |
| first_10 | 0.505 | 26735 | 2.5221 | 1.7279 | 1.037x | 0.8547 | 1.012x | 0.6790 |
| first_35 | 0.526 | 97599 | 2.5492 | 1.7185 | 0.995x | 0.9187 | 1.075x | 0.8291 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
