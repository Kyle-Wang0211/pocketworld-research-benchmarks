# npz_streaming_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.711 | 3765 | 3.1447 | 1.3315 | - | 0.4904 | - | 0.4627 |
| slots_00_01 | 0.709 | 7513 | 3.1756 | 1.3395 | 1.006x | 0.4986 | 1.017x | 0.4671 |
| slots_00_02 | 0.709 | 11272 | 3.2189 | 1.3465 | 1.005x | 0.4922 | 0.987x | 0.4597 |
| first_05 | 0.704 | 18652 | 3.1851 | 1.3699 | 1.017x | 0.5060 | 1.028x | 0.4633 |
| first_10 | 0.714 | 37821 | 3.1464 | 1.3751 | 1.004x | 0.5121 | 1.012x | 0.4798 |
| first_35 | 0.694 | 128667 | 2.7739 | 1.4052 | 1.022x | 0.5589 | 1.091x | 0.5193 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
