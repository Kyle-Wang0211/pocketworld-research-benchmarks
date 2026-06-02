# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.711 | 3765 | 3.1447 | 2.8033 | - | 1.0435 | - | 0.4421 |
| slots_00_01 | 0.709 | 7513 | 3.1756 | 2.8117 | 1.003x | 1.0616 | 1.017x | 0.4460 |
| slots_00_02 | 0.709 | 11272 | 3.2189 | 2.8441 | 1.012x | 1.0423 | 0.982x | 0.4362 |
| first_05 | 0.704 | 18652 | 3.1851 | 2.9044 | 1.021x | 1.0703 | 1.027x | 0.4398 |
| first_10 | 0.714 | 37821 | 3.1464 | 2.8615 | 0.985x | 1.0827 | 1.012x | 0.4544 |
| first_35 | 0.694 | 128667 | 2.7739 | 2.9594 | 1.034x | 1.1803 | 1.090x | 0.4957 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
