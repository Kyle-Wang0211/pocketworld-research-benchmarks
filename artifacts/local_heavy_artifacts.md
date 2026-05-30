# Local Heavy Artifacts

These files are intentionally kept out of git. They are reproducibility inputs or large intermediate tensors for the reports archived in this repo.

## Latest 414-Frame Capture

- Capture bundle: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229`
- Baseline DA3 tensor export: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_cpu_probe`
- DA3-only vs DA3+MoGe benchmark output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229`
- MoGe auxiliary tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/moge_aux`
- Patch features CSV: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/patch_features.csv`

## Current Overlap Sweep

- Overlap-12 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap12`
- Overlap-9 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap09`
- Overlap-12 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap12_cpu`
- Overlap-9 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap09_cpu`

## Official-Style DA3-BASE K35 Streaming

- Lightweight archived reports: `data/official_da3_base_k35_streaming_2026_05_30/reports/`
- Local full run directory with DA3 tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30`
- Local vendored SelaVPR++ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/SelaVPRplusplus`
- Local vendored BoQ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/Bag-of-Queries`
- Local official DA3 streaming reference copy: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming`

Only manifests, summaries, reports, and scripts are committed. Large depth/confidence tensors, descriptor arrays, copied photos, local databases, and vendor checkouts are intentionally excluded.
