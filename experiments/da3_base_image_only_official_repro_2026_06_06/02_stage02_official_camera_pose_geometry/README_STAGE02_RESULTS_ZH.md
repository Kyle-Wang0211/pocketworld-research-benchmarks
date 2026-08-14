# Stage 02 Results

Stage 02 visualizes DA3 image-only predicted camera geometry before pointcloud, Sim3, loop graph, or fusion.

## Key Numbers

- frame count: `35`
- suspect frames: `cap-74, cap-78, cap-80`
- fx range: `15.227173`
- fy range: `13.523193`
- adjacent center distance median / p90 / max: `0.029498` / `0.078685` / `0.557664`
- adjacent rotation median / p90 / max: `2.787402` / `8.020315` / `27.767794` degrees

## Outputs

- tables: `tables/`
- figures: `figures/`
- per-frame camera cards: `per_frame_camera_cards/`
- matrix heatmaps: `matrix_heatmaps/`
- contact sheets: `contact_sheets/`
- JSON report: `stage02_camera_pose_geometry_report.json`

## How To Read

- Trajectory figures show where DA3 thinks each camera is.
- Frustum figure shows each camera's viewing pyramid in DA3 world space.
- Intrinsics curves show whether focal length and principal point jump between frames.
- Pose delta curves show adjacent-frame camera jumps.
- Pairwise baseline heatmap shows distance between every pair of predicted camera centers.
- Matrix heatmaps show the raw K and w2c extrinsic matrices for all 35 frames.
