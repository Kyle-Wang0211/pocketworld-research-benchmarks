# Official NPZ oracle bridge

- status: `failed_to_materialize_official_python_oracle_inputs`
- official authority: `Depth-Anything-3/da3_streaming/npz_output_process.py`
- frame count: `n/a`
- npz folder: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_bridge_window016_2026_06_05/results_output`
- pose file: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_bridge_window016_2026_06_05/camera_poses.txt`
- output ply: `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_npz_oracle_bridge_window016_2026_06_05/official_npz_output_process.ply`

这个脚本只生成官方 Python 的输入，不重写点云过滤算法。

## Error

- type: `ValueError`
- message: image/depth shape mismatch for cap-1346: image=504x280, depth=742x476
