# glb_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_015_official_filter_micro_audit_official_postprocess/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 211975 | 2.5781 | 1.8304 | - | 0.8733 | - | 0.7271 |
| slots_00_01 | 0.600 | 423964 | 2.4336 | 1.8808 | 1.028x | 0.8944 | 1.024x | 0.6714 |
| slots_00_02 | 0.600 | 635788 | 2.2480 | 1.9843 | 1.055x | 0.9610 | 1.074x | 0.7023 |
| first_05 | 0.600 | 1000000 | 2.1055 | 2.0504 | 1.033x | 0.9686 | 1.008x | 0.6915 |
| first_10 | 0.600 | 1000000 | 1.7539 | 2.4887 | 1.214x | 0.9749 | 1.007x | 0.4752 |
| first_35 | 0.600 | 1000000 | 1.7666 | 2.3958 | 0.963x | 0.9937 | 1.019x | 0.4888 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
