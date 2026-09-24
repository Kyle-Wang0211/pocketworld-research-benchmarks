# TartanGround DA3 Multi-Window GT Benchmark

- route: TartanGround -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- dataset route: House/Data_omni/P0000
- camera names: lcam_front, lcam_left, lcam_right, lcam_back
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | stitched RMSE | stitched P90 | depth AbsRel | depth P90 m | verified pairs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| House_omni_P0000_lcam_front-lcam_left-lcam_right-lcam_back | slots385 | 11 | 325 | 375 | 0.188203 | 1.411286 | 2.152457 | 0.234899 | 0.733915 | 0 |
| House_omni_P0000_lcam_front-lcam_left-lcam_right-lcam_back | slots700 | 20 | 586 | 114 | 0.240168 | 1.491215 | 2.388411 | 0.214685 | 0.787003 | 0 |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
