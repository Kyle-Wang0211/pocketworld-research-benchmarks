# DA3-BASE Image-Only K35 Export

- Runtime excludes DA3-Streaming, VGGT-Long, SALAD, external AR/VIO, and manifest camera pose inputs.
- DA3 image-only predicts intrinsics/extrinsics from RGB, then the copied official GLB-style exporter fuses points.
- Window: `window_000`; frames: 35; process_res: 504.
- Combined PLY: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/commercial_safe_da3base_image_only_k35_glb_export_2026_06_06/window_000/window_000_combined35_glb_style_rgb.ply`
- Unique/save PLY: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/commercial_safe_da3base_image_only_k35_glb_export_2026_06_06/window_000/window_000_official_save_unique_glb_style_rgb.ply`
- Results NPZ dir: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/commercial_safe_da3base_image_only_k35_glb_export_2026_06_06/window_000/results_output`

## Point Counts

- Combined exported points: 864091
- Unique/save exported points: 239907

## Runtime

- Load ms: 1494.8
- Run ms: 17866.2
- RSS delta MB: 184.6
