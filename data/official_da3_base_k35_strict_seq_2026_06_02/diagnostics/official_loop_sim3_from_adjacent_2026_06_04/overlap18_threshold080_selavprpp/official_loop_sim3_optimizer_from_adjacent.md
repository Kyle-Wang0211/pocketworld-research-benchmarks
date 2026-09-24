# Official Loop Sim3 Optimizer From Adjacent

## 做了什么

- 使用已验证的 adjacent dense Sim3 JSON 作为 sequential transforms。
- 使用 SelaVPR++ loop capture 的官方 loop chunk 规则估计 loop constraints。
- 调用官方 Sim3LoopOptimizer。
- 不导出点云、不做清理、不做 mesh。

## Retrieval

- backend: selavprpp
- raw_loop_pair_count: 12
- loop_result_count: 5
- parameters: `{'top_k': 5, 'similarity_threshold': 0.8, 'min_frame_gap': 10, 'nms_threshold': 25, 'loop_half_window': 8, 'window_size': 35}`

## Adjacent

- edge_count: 23
- scale_range: 0.91453575 .. 1.0989432
- rmse_mean: 0.073725063
- p90_mean: 0.11742987
- rotation_angle_deg_max: 4.7057586

## Loop

- edge_count: 5
- estimated_count: 5
- scale_range: 0.89413557 .. 1.0074252
- a_rmse_mean: 0.05601469
- b_rmse_mean: 0.072485043
- rotation_angle_deg_max: 3.0151795

## Optimizer

- status: completed
- loop_constraint_count: 5
- pre_scale_mean/std: 1.0114188521056686 / 0.05041606022871378
- post_scale_mean/std: 1.0075315522110981 / 0.05110408594356637
