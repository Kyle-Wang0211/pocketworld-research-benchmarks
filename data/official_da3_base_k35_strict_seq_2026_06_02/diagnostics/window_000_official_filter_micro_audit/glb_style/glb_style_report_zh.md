# glb_style Report

- contact sheet: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_000_official_filter_micro_audit/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 211925 | 3.8789 | 1.1672 | - | 0.4441 | - | 0.4689 |
| slots_00_01 | 0.600 | 424063 | 3.8379 | 1.2141 | 1.040x | 0.4519 | 1.017x | 0.4614 |
| slots_00_02 | 0.600 | 636104 | 3.9277 | 1.2227 | 1.007x | 0.4496 | 0.995x | 0.4544 |
| first_05 | 0.600 | 1000000 | 3.8574 | 1.2581 | 1.029x | 0.4533 | 1.008x | 0.4360 |
| first_10 | 0.600 | 1000000 | 3.9289 | 1.2394 | 0.985x | 0.4540 | 1.002x | 0.4468 |
| first_35 | 0.600 | 1000000 | 3.1934 | 1.3455 | 1.086x | 0.5334 | 1.175x | 0.5112 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
