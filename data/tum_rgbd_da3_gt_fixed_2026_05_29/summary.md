# TUM RGB-D DA3 Multi-Window GT Benchmark

- route: TUM RGB-D -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- sequences: freiburg1_desk
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | bridge RMSE | bridge P90 | dense Sim3 RMSE | dense Sim3 P90 | dense+loop RMSE | dense+loop P90 | loop constraints | depth AbsRel | depth P90 m |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| freiburg1_desk | slots385 | 11 | 325 | 95 | 0.008618 | 0.297806 | 0.323929 | 0.065679 | 0.110341 | 0.108068 | 0.132991 | 0 | nan | nan |
| freiburg1_desk | slots700 | 20 | 420 | 0 | 0.006958 | 0.235417 | 0.414611 | 0.098635 | 0.146224 | 0.064253 | 0.093591 | 27 | nan | nan |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
