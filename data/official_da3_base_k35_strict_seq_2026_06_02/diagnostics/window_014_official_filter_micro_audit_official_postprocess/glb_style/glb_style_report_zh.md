# glb_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_014_official_filter_micro_audit_official_postprocess/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 211922 | 2.8828 | 1.4456 | - | 0.8821 | - | 1.1069 |
| slots_00_01 | 0.600 | 423846 | 2.7754 | 1.4754 | 1.021x | 0.8545 | 0.969x | 0.9338 |
| slots_00_02 | 0.600 | 635754 | 2.5176 | 1.7355 | 1.176x | 0.8648 | 1.012x | 0.8137 |
| first_05 | 0.600 | 1000000 | 2.2012 | 1.8497 | 1.066x | 0.9659 | 1.117x | 0.8991 |
| first_10 | 0.600 | 1000000 | 2.1895 | 1.9081 | 1.032x | 1.0261 | 1.062x | 0.9861 |
| first_35 | 0.600 | 1000000 | 1.6738 | 2.1542 | 1.129x | 1.2064 | 1.176x | 0.8414 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
