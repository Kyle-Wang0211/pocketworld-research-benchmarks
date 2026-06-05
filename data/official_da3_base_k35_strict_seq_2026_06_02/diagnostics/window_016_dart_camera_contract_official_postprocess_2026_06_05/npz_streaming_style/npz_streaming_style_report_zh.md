# npz_streaming_style Report

- contact sheet: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/window_016_dart_camera_contract_official_postprocess_2026_06_05/npz_streaming_style/npz_streaming_style_contact_sheet.png`
- source: `Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py`

| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_00 | 0.558 | 2955 | 2.8904 | 1.5267 | - | 0.7759 | - | 0.6364 |
| slots_00_01 | 0.572 | 6063 | 3.0558 | 1.4851 | 0.973x | 0.7209 | 0.929x | 0.7257 |
| slots_00_02 | 0.577 | 9172 | 3.1062 | 1.4437 | 0.972x | 0.6735 | 0.934x | 0.7589 |
| first_05 | 0.562 | 14874 | 3.0490 | 1.4302 | 0.991x | 0.6575 | 0.976x | 0.7447 |
| first_10 | 0.554 | 29355 | 3.0620 | 1.4356 | 1.004x | 0.6812 | 1.036x | 0.7753 |
| first_35 | 0.587 | 108775 | 2.4316 | 2.1370 | 1.489x | 1.1715 | 1.720x | 0.7915 |

## 自动标记

- first bbox diag jump >= 1.35x: `first_35`
- first PCA minor jump >= 1.35x: `first_35`
