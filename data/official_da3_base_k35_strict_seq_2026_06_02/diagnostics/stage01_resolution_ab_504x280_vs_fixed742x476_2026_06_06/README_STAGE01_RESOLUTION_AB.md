# Stage 01 Resolution A/B: 504x280 vs fixed 742x476

No PLY/fusion is generated in this diagnostic.

- A: official `process_res=504`, `upper_bound_resize`, highres source -> actual `504x280`.
- B: manual center-crop highres to `742:476` aspect, resize to `742x476`, then DA3 image-only inference with `process_res=742` so the official input processor leaves the fixed shape unchanged.

## Outputs

- A/B Stage 01 contact: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_resolution_ab_504x280_vs_fixed742x476_2026_06_06/contact_sheets/AB_504x280_vs_fixed742x476_stage01_contact.jpg`
- B depth contact: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_resolution_ab_504x280_vs_fixed742x476_2026_06_06/contact_sheets/B_fixed742x476_depth_contact.jpg`
- B confidence signal contact: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_resolution_ab_504x280_vs_fixed742x476_2026_06_06/contact_sheets/B_fixed742x476_conf_minus1_log_contact.jpg`
- Metrics CSV: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_resolution_ab_504x280_vs_fixed742x476_2026_06_06/tables/resolution_ab_metrics.csv`

## Runtime

- Device: `mps`
- Run ms: `88345.4`
