# glb_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit_official_postprocess/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 211925 | 3.8789 | 2.5190 | - | 0.9357 | - | 0.4437 |
| slots_00_01 | 0.600 | 424063 | 3.8379 | 2.6186 | 1.040x | 0.9526 | 1.018x | 0.4382 |
| slots_00_02 | 0.600 | 636104 | 3.9277 | 2.6362 | 1.007x | 0.9478 | 0.995x | 0.4321 |
| first_05 | 0.600 | 1000000 | 3.8574 | 2.7146 | 1.030x | 0.9551 | 1.008x | 0.4131 |
| first_10 | 0.600 | 1000000 | 3.9289 | 2.6715 | 0.984x | 0.9540 | 0.999x | 0.4206 |
| first_35 | 0.600 | 1000000 | 3.1934 | 2.9111 | 1.090x | 1.1151 | 1.169x | 0.4823 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
