# TUM RGB-D DA3 Multi-Window GT Benchmark

- route: TUM RGB-D -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT
- sequences: freiburg1_desk
- bridge overlap: 6

| sequence | route | windows | selected | dropped | local RMSE | stitched RMSE | stitched P90 | depth AbsRel | depth P90 m |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freiburg1_desk | slots385 | 11 | 80 | 0 | nan | nan | nan | nan | nan |

Charts:

- `charts/pose_rmse_p90.png`
- `charts/depth_absrel_p90.png`
- `charts/trajectory_topdown.png`
