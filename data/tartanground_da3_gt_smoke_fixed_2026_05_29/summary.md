# TartanGround DA3 Multi-Window GT Benchmark

- route: TartanGround -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- dataset route: House/Data_omni/P0000
- camera names: lcam_front, lcam_left, lcam_right, lcam_back
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | stitched RMSE | stitched P90 | depth AbsRel | depth P90 m | verified pairs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| House_omni_P0000_lcam_front-lcam_left-lcam_right-lcam_back | slots385 | 11 | 120 | 0 | nan | nan | nan | nan | nan | 0 |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
