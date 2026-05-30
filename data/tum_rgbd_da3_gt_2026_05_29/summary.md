# TUM RGB-D DA3 Multi-Window GT Benchmark

- route: TUM RGB-D -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- sequences: freiburg1_desk
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | stitched RMSE | stitched P90 | depth AbsRel | depth P90 m |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freiburg1_desk | slots385 | 11 | 325 | 95 | 0.010640 | 0.121603 | 0.169327 | 0.083468 | 0.224231 |
| freiburg1_desk | slots700 | 20 | 420 | 0 | 0.009002 | 0.110921 | 0.152905 | 0.107908 | 0.229307 |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
