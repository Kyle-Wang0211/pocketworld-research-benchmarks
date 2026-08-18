# K35/K40/K50 多视角 Stage 1 诊断（stride-correct）

## 结论预览

- 旧手机导出的 CoreML 输出不能作为官方 image-only 基线判断：CoreML 输出存在 padding strides，旧代码按紧密数组读取，depth/conf/pose 都会被错切。
- 本次 Mac 复跑使用同一批官方预处理 tensor，并按 MLMultiArray shape/strides 读取；K35/K40/K50 的 pose 矩阵恢复为正常 3x4 W2C。
- K40 相比 K35 有一点点窗口长度收益，但不是质变；K50 前 40 和 K40 基本贴近，额外 40→42 附近出现明显 pose/内参/几何 spike。
- 基于这组真实素材，不建议继续做 K60/K70；更长窗口没有显示稳定收益，反而在尾部引入高风险边。

## 关键数值

| metric | K35 | K40 | K50 | 解释 |
|---|---:|---:|---:|---|
| Mac CoreML prediction seconds | 10.843499 | 13.944828 | 22.215495 | lower 通常更稳/更一致，prediction seconds 除外 |
| adjacent center step median | 0.020830 | 0.026857 | 0.027605 | lower 通常更稳/更一致，prediction seconds 除外 |
| adjacent center step p90 | 0.037864 | 0.057343 | 0.052314 | lower 通常更稳/更一致，prediction seconds 除外 |
| center second-diff p90 | 0.047748 | 0.082768 | 0.105869 | lower 通常更稳/更一致，prediction seconds 除外 |
| rotation delta p90 deg | 5.267766 | 8.329503 | 11.326961 | lower 通常更稳/更一致，prediction seconds 除外 |
| cloud NN p50 median | 0.015734 | 0.016335 | 0.016683 | lower 通常更稳/更一致，prediction seconds 除外 |
| cloud NN p90 median | 0.033780 | 0.032215 | 0.036170 | lower 通常更稳/更一致，prediction seconds 除外 |

## 共享段轨迹形状差异

- K40 vs K35 first35 Sim3 center error median/p90: `0.040520` / `0.065529`
- K50 vs K35 first35 Sim3 center error median/p90: `0.040283` / `0.066026`
- K50 vs K40 first40 Sim3 center error median/p90: `0.007519` / `0.013680`

## 产物

- `figures/pose_trajectory_top_xz.png`
- `figures/pose_delta_curves.png`
- `figures/intrinsics_curves.png`
- `figures/geometry_adjacent_nn_consistency.png`
- `figures/depth_conf_selected_contact_sheet.png`
- `tables/per_edge_geometry_nn.csv`
- `tables/per_frame_depth_conf.csv`
- `tables/pose_intrinsics_summary.json`