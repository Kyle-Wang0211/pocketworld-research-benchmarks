# TartanGround DA3 Multi-Window GT Benchmark

- route: TartanGround -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- dataset route: House/Data_omni/P0000
- camera names: lcam_front, lcam_left, lcam_right, lcam_back
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | bridge RMSE | bridge P90 | dense Sim3 RMSE | dense Sim3 P90 | dense+loop RMSE | dense+loop P90 | loop constraints | depth AbsRel | depth P90 m | verified pairs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| House_omni_P0000_lcam_front-lcam_left-lcam_right-lcam_back | slots385 | 11 | 325 | 375 | 0.142915 | 0.657376 | 1.053305 | 0.372989 | 0.584590 | 2.759786 | 4.026711 | 0 | nan | nan | 2823 |
| House_omni_P0000_lcam_front-lcam_left-lcam_right-lcam_back | slots700 | 20 | 586 | 114 | 0.188180 | 1.296227 | 2.018567 | 0.467368 | 0.709916 | 2.881369 | 4.453762 | 12 | nan | nan | 2823 |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
