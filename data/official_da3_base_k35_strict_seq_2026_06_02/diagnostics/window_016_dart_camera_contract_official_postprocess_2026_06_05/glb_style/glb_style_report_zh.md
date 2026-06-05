# glb_style Report

- contact sheet: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_016_dart_camera_contract_official_postprocess_2026_06_05/glb_style/glb_style_contact_sheet.png`
- source: `Depth-Anything-3/src/depth_anything_3/utils/export/glb.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.600 | 211921 | 2.1660 | 1.6965 | - | 0.8720 | - | 0.6936 |
| slots_00_01 | 0.600 | 423845 | 2.5176 | 1.6685 | 0.983x | 0.8626 | 0.989x | 0.6717 |
| slots_00_02 | 0.600 | 635779 | 2.6055 | 1.4949 | 0.896x | 0.7064 | 0.819x | 0.6814 |
| first_05 | 0.600 | 1000000 | 2.1895 | 1.6750 | 1.120x | 0.8837 | 1.251x | 0.6908 |
| first_10 | 0.600 | 1000000 | 2.0859 | 1.7104 | 1.021x | 0.8508 | 0.963x | 0.6682 |
| first_35 | 0.600 | 1000000 | 2.2852 | 2.1981 | 1.285x | 0.9407 | 1.106x | 0.5964 |

## 自动标记

- first bbox diag jump >= 1.35x: `None`
- first PCA minor jump >= 1.35x: `None`
