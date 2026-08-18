# A/B use_ray_pose window_000 504 upper_bound_resize

A = use_ray_pose=False, existing baseline. B = use_ray_pose=True. All other script parameters are held constant.

## Key Metrics
- Processed RGB max abs diff: 0
- Depth max abs diff: 0; mean: 0
- Confidence max abs diff: 0; mean: 0
- Intrinsics max abs diff: 62.1294
- Extrinsics max abs diff: 0.101542
- Camera center B->A Sim3 residual RMSE: 0.0213609
- Camera normalized pairwise distance diff mean: 0.0447428
- Combined PLY B->A sampled Sim3 residual RMSE: 0.0142156
- Combined PLY dark centroid distance after Sim3: 0.00548964

## Artifacts
- Combined views side-by-side: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ab_ray_pose_window000_504_2026_06_06/compare_A_false_vs_B_true/combined35_views_A_false_B_true.png`
- Unique/save views side-by-side: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ab_ray_pose_window000_504_2026_06_06/compare_A_false_vs_B_true/unique_save_views_A_false_B_true.png`
- Camera centers plot: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ab_ray_pose_window000_504_2026_06_06/compare_A_false_vs_B_true/camera_centers_B_aligned_to_A.png`
- Histograms: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ab_ray_pose_window000_504_2026_06_06/compare_A_false_vs_B_true/numeric_diff_histograms.png`
- Per-frame table: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ab_ray_pose_window000_504_2026_06_06/compare_A_false_vs_B_true/per_frame_pose_conf_ab.csv`
