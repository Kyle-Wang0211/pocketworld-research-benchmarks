# Official Downstream Core-Frame vs Full-Chunk Audit

- date: `2026-06-05`
- status: `core_frame_downstream_does_not_close_window016_thickness`

## 结论

- 官方有两条容易混淆的 downstream：pcd/combined_pcd.ply 是把每个 chunk 的点云文件合并；results_output/frame_*.npz + npz_output_process.py 是用保存下来的 core-frame NPZ 再融合。
- core-frame 的作用主要是跨 chunk 去掉 overlap 帧，不是同一 window 内的表面融合/去重算法。
- 同一官方 PyTorch image-only 输出里，core-like K17 的 NPZ minor/k10 已经是 1.50207，full K35 是 1.55428，K35/K17 只有 1.03476。
- GLB-style 在 K17 的 minor/k10 是 1.20386，明显比 NPZ-style 温和；所以 confidence/filter/export style 会影响厚层外观，但 core-frame 不是根治。
- 首次 NPZ minor >=1.35 出现在 k=12 (1.41502)；跳变发生在核心区间内，不能只归因给 withheld overlap/full-chunk 尾部。

## 官方代码证据

| evidence | file:line | text |
|---|---|---|
| `confidence_convention` | `da3_streaming.py:276` | `predictions.conf -= 1.0` |
| `core_frame_save_indices_first_chunk` | `da3_streaming.py:215` | `save_indices = list(range(0, chunk_end - chunk_start - self.overlap_e))` |
| `core_frame_save_indices_middle_chunk` | `da3_streaming.py:219` | `save_indices = list(range(self.overlap_s, chunk_end - chunk_start - self.overlap_e))` |
| `full_chunk_pcd_first_chunk_save` | `da3_streaming.py:664` | `ply_path_first = os.path.join(self.pcd_dir, "0_pcd.ply")` |
| `full_chunk_pcd_aligned_chunk_save` | `da3_streaming.py:681` | `ply_path = os.path.join(self.pcd_dir, f"{chunk_idx+1}_pcd.ply")` |
| `combined_pcd_readme` | `README.md:91` | `- `${OUTPUT_DIR}/pcd/combined_pcd.ply`: The combined point cloud file. It contains the 3D points from all frames.` |
| `results_output_readme` | `README.md:97` | `- `${OUTPUT_DIR}/results_output`: The folder that contains the rgb, depth, confidence and intrinsic results for each frame. Note that the minimum value of confidence is 0.` |
| `npz_verify_command_readme` | `README.md:102` | `python npz_output_process.py --npz_folder ${OUTPUT_DIR}/results_output --pose_file ${OUTPUT_DIR}/camera_poses.txt --output_file ${OUTPUT_DIR}/output.ply` |
| `npz_default_conf_threshold_coef` | `npz_output_process.py:105` | `"--conf_threshold_coef", type=float, default=0.5, help="Confidence threshold coefficient"` |
| `npz_default_sample_ratio` | `npz_output_process.py:108` | `"--sample_ratio", type=float, default=0.015, help="Sample ratio for downsampling"` |
| `streaming_default_pointcloud_coef` | `base_config.yaml:36` | `conf_threshold_coef: 0.75 # conf_threshold = np.mean(confs) * conf_threshold_coef` |
| `streaming_default_sample_ratio` | `base_config.yaml:35` | `sample_ratio: 0.015` |

## Official PyTorch Image-Only Window 016

| selection | pose/k10 | depth p95/k10 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |
|---|---:|---:|---:|---:|---:|---:|
| k10 baseline | 1 | 1 | 1 | 1 | 1 | 1 |
| core-like k17 | 4.03323 | 0.986015 | 1.22952 | 1.20386 | 1.44493 | 1.50207 |
| full-chunk k35 | 4.95607 | 1.015 | 1.23737 | 1.23297 | 1.43681 | 1.55428 |

## K35 vs Core K17

- npz minor K35/K17: `1.03476`
- npz bbox K35/K17: `0.994378`
- glb minor K35/K17: `1.02418`
- pose span K35/K17: `1.22881`

## Current CoreML Pose Official-Save Context

- frame_source: `depth_index`
- frame_count: `17`
- CoreML official-save npz minor/k10: `1.42888`
- CoreML official-save npz bbox/k10: `1.39652`
- CoreML official-save glb minor/k10: `1.15254`
