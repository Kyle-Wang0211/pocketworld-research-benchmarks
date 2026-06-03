# glb_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_006_official_filter_micro_audit_official_postprocess/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 212014 | 2.6855 | 1.8756 | - | 0.8830 | - | 0.6131 |
| slots_00_01 | 0.600 | 423831 | 3.5352 | 1.3864 | 0.739x | 0.7956 | 0.901x | 1.0432 |
| slots_00_02 | 0.600 | 635779 | 4.0078 | 1.3438 | 0.969x | 0.7105 | 0.893x | 0.9284 |
| first_05 | 0.600 | 1000000 | 3.9141 | 1.4802 | 1.101x | 0.7418 | 1.044x | 0.8832 |
| first_10 | 0.600 | 1000000 | 3.3105 | 1.6052 | 1.084x | 0.8542 | 1.152x | 0.9271 |
| first_35 | 0.600 | 1000000 | 2.0703 | 1.9409 | 1.209x | 0.8322 | 0.974x | 0.6078 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
