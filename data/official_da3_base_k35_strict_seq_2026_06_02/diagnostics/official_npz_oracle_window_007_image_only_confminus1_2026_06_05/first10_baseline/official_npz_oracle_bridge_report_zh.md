# Official NPZ oracle bridge

- status: `materialized_official_python_oracle_inputs`
- official authority: `Depth-Anything-3/da3_streaming/npz_output_process.py`
- frame count: `10`
- npz folder: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/results_output`
- pose file: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/camera_poses.txt`
- output ply: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/official_npz_output_process.ply`

这个脚本只生成官方 Python 的输入，不重写点云过滤算法。

## Official command

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 /Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/da3_streaming/npz_output_process.py --npz_folder /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/results_output --pose_file /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/camera_poses.txt --output_file /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_window_007_image_only_confminus1_2026_06_05/first10_baseline/official_npz_output_process.ply --conf_threshold_coef 0.5 --sample_ratio 0.015
```
