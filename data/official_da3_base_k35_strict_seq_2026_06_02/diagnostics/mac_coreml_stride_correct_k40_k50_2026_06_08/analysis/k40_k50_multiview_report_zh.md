# K40 vs K50 多视角 Stage 1 诊断（stride-correct）

## 结论预览

- 旧手机导出的 CoreML 输出不能作为官方 image-only 基线判断：CoreML 输出存在 padding strides，旧代码按紧密数组读取，depth/conf/pose 都会被错切。
- 本次 Mac 复跑使用同一批官方预处理 tensor，并按 MLMultiArray shape/strides 读取；K40/K50 的 pose 矩阵恢复为正常 3x4 W2C。
- K50 是否值得，不能看单帧；下面看轨迹、pose delta、内参和相邻点云一致性。

## 关键数值

| metric | K40 | K50 | 解释 |
|---|---:|---:|---|
| Mac CoreML prediction seconds | 13.9448 | 22.2155 | K50/K40 = 1.59x |
| pose path length | 1.281697 | 1.848506 | DA3 相对尺度下轨迹总长 |
| adjacent center step median | 0.026857 | 0.027605 | 相邻相机中心移动 |
| adjacent center step p90 | 0.057343 | 0.052314 | 越大越像跳变 |
| center second-diff p90 | 0.082768 | 0.105869 | 轨迹抖动指标，越小越平滑 |
| rotation delta p90 deg | 8.329503 | 11.326961 | 相邻姿态旋转变化 |
| cloud NN p50 median | 0.016335 | 0.016683 | 相邻点云粗一致性，越低越好 |
| cloud NN p90 median | 0.032215 | 0.036170 | 90分位粗一致性 |
| shared first40 Sim3 center error median | 0.007519 | | K50 对齐 K40 后轨迹形状差异 |
| shared first40 Sim3 center error p90 | 0.013680 | | 越小说明两者判断接近 |
| fx mean delta K50-K40 first40 | 20.075001 | | K50 预测焦距整体更大 |
| fy mean delta K50-K40 first40 | 23.968750 | | K50 预测焦距整体更大 |

## 产物

- `figures/pose_trajectory_top_xz.png`
- `figures/pose_delta_curves.png`
- `figures/intrinsics_curves.png`
- `figures/geometry_adjacent_nn_consistency.png`
- `figures/depth_conf_selected_contact_sheet.png`
- `tables/per_edge_geometry_nn.csv`
- `tables/per_frame_depth_conf.csv`
- `tables/pose_intrinsics_summary.json`