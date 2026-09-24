# Full 414 Mobile Streaming Status

日期: 2026-06-03

## 结论摘要

这次已经证明: 在官方正确照片顺序下, DA3-BASE CoreML K35@476x742 可以按移动端 streaming 方式顺序跑完整 414 张, 共 24 个 windows。PyTorch all-at-once K35 的 15.36 GiB / 89.01 GiB buffer 失败不等价于手机路线失败, 因为移动端路线不是一次性把 K35 PyTorch 全量张量放进同一个 buffer, 而是按 CoreML sealed model 逐 window 执行。

当前还没有证明: K35 地板厚层是由缺少 loop 造成的。loop 主要约束跨 window 的全局漂移和尺度漂移, 但 `first_35_rgb.ply` 已经是单个 K35 window 内部点云。如果厚层在单 window 内部随帧数从 K5/K10 增加到 K35 出现, 根因更可能在 window 内 depth/pose/scale/fusion 表面没有完全压到同一平面。

## 固定输入顺序

完整 414 张原始序列位置:

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229`

严格时间顺序 capture:

`data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict`

已核对:

- frameCount: 414
- timestampMonotonic: true
- firstFrameID: `cap-1`
- lastFrameID: `cap-2219`
- windowCount: 24
- chunkSize: 35
- overlap: 18
- step: 17

注意: 原始 `photo_bundle.json` 不是严格 timestamp sorted, 后续所有正式实验都必须使用这里的 strict timestamp capture。

## 当前移动端模型参数

- model: DA3-BASE
- license: Apache-2.0
- CoreML resourceName: `DA3BASE_476x742_N35_pose`
- input: 742x476
- windowSize: 35
- commercialSafe: true
- route: sealed CoreML K35 sequential windows + official DA3 postprocess

## CoreML Full 414 执行结果

输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict`

结果:

- status: completed
- window_count: 24
- frame_count: 414
- completed_count: 414
- elapsed_s: 1024.252
- last logged RSS after predict: 4300.266 MB
- last window predict_ms: 46705.184

这说明 K35@476x742 在本机 CPU CoreML research executor 下可以完整顺序跑完。它不是 PyTorch all-at-once 的内存模式。

## 官方后处理结果

输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict_official_postprocess`

结果:

- status: completed
- window_count: 24
- frame_count: 414
- completed_count: 414
- poseScale count: 24
- poseScale min: 0.479680
- poseScale max: 0.877487
- poseScale mean: 0.701945

后处理已补齐官方 PyTorch 路线中的 Umeyama align / pose_scale / depth scale / intrinsics-extrinsics 回填。

## Adjacent Sim3 诊断

输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_full_414`

路线:

`DA3-BASE K35@476x742 CoreML full 414 official postprocess -> official dense Sim3 adjacent overlap diagnostics only`

结果:

- adjacent edge_count: 23
- estimated_count: 23
- rmse_mean: 0.112883
- p90_mean: 0.186386
- scale_mean: 1.015046
- scale_std: 0.049808

最坏相邻边:

- `window_014 -> window_015`: rmse 0.200622, p90 0.364880, median 0.053841, sim3_scale 0.977494
- `window_015 -> window_016`: rmse 0.198800, p90 0.352374, median 0.048382, sim3_scale 1.091248
- `window_006 -> window_007`: rmse 0.174356, p90 0.346300, median 0.052496, sim3_scale 1.017057
- `window_016 -> window_017`: rmse 0.179565, p90 0.313003, median 0.035222, sim3_scale 1.001698

最好相邻边:

- `window_022 -> window_023`: rmse 0.031048, p90 0.047232, median 0.016955, sim3_scale 0.997311
- `window_009 -> window_010`: rmse 0.040023, p90 0.058407, median 0.023995, sim3_scale 1.007721

解释: adjacent Sim3 能估计所有相邻窗口, 但有些桥接残差明显偏大。这个证据支持“多帧/多 window 表面未完全压到同一层”这个方向, 但不能单独证明 loop 一定能修复 K35 厚层。

## PLY 点云诊断

输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_alignment_clouds_full_414`

关键文件:

- `window_000_single_rgb.ply`
- `window_000_001_shared_aligned_rgb.ply`
- `window_000_001_shared_aligned_source_color.ply`
- `first_01_windows_rgb.ply`
- `first_02_windows_rgb.ply`
- `first_04_windows_rgb.ply`
- `first_08_windows_rgb.ply`
- `first_24_windows_rgb.ply`

当前诊断指标:

- window_000 single point_count: 26272
- window_000 single bbox diag: 2.9705
- window_000+001 shared residual rmse: 0.110518
- window_000+001 shared residual median: 0.050632
- window_000+001 shared residual p90: 0.187145
- window_000+001 shared residual p95: 0.265854
- first_24_windows point_count: 532369
- first_24_windows bbox diag: 3.3531

建议肉眼检查顺序:

1. `window_000_single_rgb.ply`
2. `first_01_windows_rgb.ply`
3. `first_02_windows_rgb.ply`
4. `first_04_windows_rgb.ply`
5. `first_08_windows_rgb.ply`
6. `first_24_windows_rgb.ply`

目的不是调算法, 而是确认厚层第一次从哪个累计规模出现。

## Loop / VPR 诊断

输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/loop_vpr_full_414/selavprpp`

使用:

- backend: SelaVPR++
- license: MIT for SelaVPR++ repo
- commercial_safe: true
- descriptor_shape: 414 x 2048
- default similarity_threshold: 0.85

结果:

- raw_loop_pair_count: 0
- loop_result_count: 0
- loop_window_count: 0

threshold sweep:

- 0.70: raw 170, nms 71
- 0.75: raw 83, nms 45
- 0.80: raw 12, nms 12
- 0.85: raw 0, nms 0
- 0.90: raw 0, nms 0

解释:

SelaVPR++ 在当前默认阈值 0.85 下没有找到 loop, 所以官方 loop/Sim3 优化没有额外 loop 约束可用。低阈值 0.80 有 12 个候选, 但这只能作为 diagnostic-only 候选检查, 不能直接当作生产 loop, 因为假 loop 会扭坏全局几何。

## SALAD 说明

官方 Depth-Anything-3 streaming 默认提到 SALAD VPR, 但 SALAD 不是当前商用安全路线。生产管线不使用 SALAD, 当前商用安全 VPR 路线使用 SelaVPR++。

## 当前判断

1. 不建议把“找一个一定有 loop 的 VPR”作为目标。目标应该是“找到真实 loop, 并且 Sim3 residual 低, 能让同一表面更薄更准”。
2. K35 厚层还不能归因给缺 loop。更需要先看 K5/K10/K35 在同一 window 内的地板厚度变化, 以及相邻 window overlap residual 是否对应肉眼厚层区域。
3. 如果 0.80 候选里有真实回环, 可以做 diagnostic-only Sim3 检查; 如果没有, 就应该接受这段 414 轨迹在默认阈值下没有可靠 loop。
4. 后续如果要生成 mesh/glb, 贴图不会自动修平几何厚层。必须先确认 geometry 表面是否压薄, 再进入贴图。

## 下一步建议

优先级最高:

1. 用 Preview 或点云 viewer 检查 `first_24_windows_rgb.ply`, 观察厚层是否是 window 内累计造成, 还是相邻 window 累计造成。
2. 导出最坏相邻边 `window_014/015/016/017` 的 shared source-color PLY, 对应 Sim3 p90 最大的区域做肉眼检查。
3. 对 SelaVPR++ threshold 0.80 的 12 个候选只做人工和几何残差验证, 不作为生产配置。

保留原则:

- 不引入 SALAD 到生产。
- 不自研 graph patch。
- 不自研新融合。
- 不为了出现 loop 而降低阈值。
- 只在官方一致性范围内做移动端可承载适配。

## 2026-06-03 追加诊断

### 最坏 adjacent Sim3 边 PLY

新增输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_adjacent_sim3_worst_edges_shared_ply`

导出了 p90 最大的 4 条相邻边 shared source-color PLY:

- `window_014 -> window_015`: adjacent p90 0.364880, root-aligned p90 0.386085
- `window_015 -> window_016`: adjacent p90 0.352374, root-aligned p90 0.364461
- `window_006 -> window_007`: adjacent p90 0.346300, root-aligned p90 0.401811
- `window_016 -> window_017`: adjacent p90 0.313003, root-aligned p90 0.353280

蓝色代表 parent window, 橙色代表 current window。这个结果说明最坏桥接边在 root frame 下仍然有 0.35-0.40m 量级的 p90 分层, 不是单纯 2D 预览错觉。

### SelaVPR++ threshold=0.80 只读 loop 诊断

新增输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/loop_vpr_full_414_threshold080_diagnostic/selavprpp`

注意: 这是 diagnostic-only, 不是生产阈值修改。默认 0.85 仍然保持为 0 loop candidates。

结果:

- raw loop pairs: 12
- official `process_loop_list` 后 loop windows: 5
- CoreML K35 loop chunk forward: completed, 5 windows, 122 completed frames, elapsed_s 221.044, last RSS 3517.203 MB
- official postprocess: completed
- dense Sim3 loop constraints: 5
- Sim3LoopOptimizer: completed
- pre scale mean/std: 1.015046 / 0.049808
- post scale mean/std: 1.011119 / 0.050996

Loop window 几何残差:

- `loop_window_000` chunks `17 -> 6`, gap 11, a_p90 0.170085, b_p90 0.108454, scale 0.881570
- `loop_window_001` chunks `19 -> 4`, gap 15, a_p90 0.158118, b_p90 0.098355, scale 0.963947
- `loop_window_002` chunks `2 -> 1`, gap 1, a_p90 0.098608, b_p90 0.113136, scale 0.988251; 这是近邻重复, 不是全局回环
- `loop_window_003` chunks `20 -> 6`, gap 14, a_p90 0.063198, b_p90 0.155304, scale 0.935300
- `loop_window_004` chunks `16 -> 6`, gap 10, a_p90 0.231772, b_p90 0.367188, scale 0.862199; 残差偏高, 作为约束有风险

初步解释:

0.80 能产生候选, 但当前证据仍不支持把 K35 厚层归因于缺 loop。原因是:

- 至少一个 loop window 是近邻重复, 不能算全局 loop。
- 一个长距离候选 b_p90 达到 0.367188, 几何约束风险较高。
- optimizer 虽然完成, 但 scale std 从 0.049808 增到 0.050996, 没有显示出更稳定的尺度压缩。
- K35 厚层已经能在单个 K35 window 或 adjacent shared frame 中观察到, loop 更像全局漂移约束, 不是当前最直接根因。

因此 0.80 只能继续作为人工/几何诊断候选, 不能进入生产默认配置。

### Adjacent-only vs loop080 optimized aggregate PLY

新增输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_loop080_vs_adjacent_aggregate_clouds`

对照规则:

- 使用同一批 full 414 / 24 windows 官方后处理输出
- 使用相同 sample ratio: 0.002
- 使用相同 confidence threshold coef: 0.75
- 对同一 frame slot 使用稳定随机种子, 保证 adjacent-only 和 loop080 optimized 是 matched sampling
- 只导出 PLY/PNG 和 residual report, 不做 graph patch, 不做新融合, 不做 Poisson/mesh

输出:

- `adjacent_only_matched_first24_rgb.ply`
- `loop080_optimized_matched_first24_rgb.ply`
- `loop080_vs_adjacent_source_color_overlay.ply`

数值:

- sampled points: 354765
- adjacent-only shared edge p90 mean: 0.208001
- loop080 optimized shared edge p90 mean: 0.202639
- delta p90 mean: -0.005362
- p90 improved / worsened edge count: 16 / 7
- loop vs adjacent point displacement median / p90: 0.101634 / 0.190502
- adjacent-only bbox diag: 3.350654
- loop080 optimized bbox diag: 3.120153

最坏 loop 后相邻边:

- `window_006 -> window_007`: adjacent p90 0.401811 -> loop080 p90 0.407063, 变差
- `window_015 -> window_016`: adjacent p90 0.364461 -> loop080 p90 0.361891, 轻微改善
- `window_014 -> window_015`: adjacent p90 0.386085 -> loop080 p90 0.347699, 明显改善但仍偏厚

解释:

loop080 optimizer 对全局尺度和 bbox 有压缩效果, 也让一部分相邻边 residual 下降, 但幅度很小, 而且仍有 7 条 adjacent shared edges 变差。blue/orange overlay 显示 loop080 是整体全局变形/位移, 不是把厚层稳定压成单层。因此它仍不能作为 K35 厚层的生产修复。

当前更稳妥的判断:

- threshold=0.80 可以保留为 diagnostic-only 候选。
- production 默认仍不应从 0.85 降到 0.80。
- K35 厚层继续优先查 window 内部 depth/pose/scale 和 official fusion/export 一致性, 而不是直接归因给缺 loop。

### Bad Windows Official Micro Audit

新增输出目录:

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_bad_windows_micro_audit_summary`

对 `window_006/014/015/016` 追加了 official GLB export / DA3-Streaming NPZ pointcloud 规则的 micro audit, 并与 `window_000` baseline 一起汇总。每个窗口只读导出 slot 0、0+1、0+1+2、first5、first10、first35, 不改生产算法。

compact summary:

- `bad_windows_micro_audit_summary.json`
- `bad_windows_micro_audit_summary_zh.md`
- `bad_windows_first10_first35_contact_sheet.png`

关键数值:

- `window_006`: GLB first10 bbox 1.605227 -> first35 bbox 1.940905; NPZ first10 bbox 1.587128 -> first35 bbox 1.795190
- `window_014`: GLB first10 bbox 1.908092 -> first35 bbox 2.154181; NPZ first10 bbox 1.430443 -> first35 bbox 1.602098
- `window_015`: GLB first10 bbox 2.488748 -> first35 bbox 2.395815; NPZ first10 bbox 1.727919 -> first35 bbox 1.718531
- `window_016`: GLB first10 bbox 1.710428 -> first35 bbox 2.198072; NPZ first10 bbox 1.270586 -> first35 bbox 1.598674, NPZ first35 出现 PCA minor jump

解释:

- 这些坏窗口没有出现 0+1 或 0+1+2 级别的瞬间崩坏。
- 厚层/范围扩大更像随视角跨度和 slots 累计逐渐增长, 尤其 first35 相比 first10。
- `window_016` 说明 streaming NPZ 官方保存规则下也能出现 first35 厚化。
- `window_015` 说明不是简单“帧越多一定越坏”, 因为 GLB first10 达到高点后 first35 略回落。
- 这个证据进一步支持: K35 厚层不是目前能直接靠 loop 解释的问题, 更应继续查 window 内 pose-depth-scale / confidence / official export-fusion 一致性。

### VPR / Loop Replacement 判断

SelaVPR++ 是当前商用安全路线, 默认阈值 0.85 没有 loop。这个结果不能被理解成“需要换一个更容易给 loop 的 VPR”。更稳妥的目标是:

- 找真实 loop, 而不是找一定会输出 loop 的模型。
- loop candidate 必须同时通过视觉相似、时间间隔、official process_loop_list、dense Sim3 residual 检查。
- 如果一个新 VPR 只是多报候选, 但几何 residual 高, 它会把全局 pose graph 拉歪, 不能修 K35 厚层。
- 当前 loop080 diagnostic 已显示: bbox 有整体压缩, adjacent p90 mean 只小幅下降 0.005362, 仍有 7 条相邻边变差; 这不是稳定修复厚层的证据。

因此下一步不应优先“寻找有 loop 的同类算法”。除非我们能证明 414 张序列里确实存在可靠回环, 且 SelaVPR++ 默认阈值漏检了它。否则, 对 K35 厚层的官方一致性排查应继续放在 window 内 pose/depth/scale/confidence/export-fusion 上。
